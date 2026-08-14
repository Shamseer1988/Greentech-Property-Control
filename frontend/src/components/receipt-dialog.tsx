"use client";

import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { Modal, Field, inputClass, selectClass, textareaClass } from "@/components/ui/dialog";
import { toast, errorMessage } from "@/components/ui/toast";
import { money } from "@/lib/contract-types";

type Charge = {
  id: number;
  period_month: string;
  amount: number;
  allocated: number;
  outstanding: number;
  status: string;
  contract_number?: string;
  is_opening_balance: boolean;
};

type ChequeOnFile = {
  id: number;
  cheque_number: string;
  amount: number;
  cheque_date: string;
  for_month: string | null;
  contract_number: string | null;
  is_security: boolean;
};

/**
 * Receive money and show, before posting, exactly which months it will
 * settle. Default is oldest-first; ticking "choose months" lets the
 * operator direct it and that override is recorded on the allocation.
 *
 * `initialMode`/`initialAmount`/`initialMonth` prefill the form — used
 * when a cheque was just returned and the operator is recording the
 * cash that replaces it (`cheque-grid.tsx`), so the amount and month
 * carry over instead of being retyped.
 */
export function ReceiptDialog({ open, clientId, clientName, onClose, onPosted,
  initialMode, initialAmount, initialMonth }: {
  open: boolean;
  clientId: number | null;
  clientName: string | null;
  onClose: () => void;
  onPosted: () => void;
  initialMode?: string;
  initialAmount?: number;
  initialMonth?: string | null;
}) {
  const [charges, setCharges] = useState<Charge[]>([]);
  const [amount, setAmount] = useState("");
  const [receiptDate, setReceiptDate] = useState(new Date().toISOString().slice(0, 10));
  const [mode, setMode] = useState("cash");
  const [reference, setReference] = useState("");
  const [remarks, setRemarks] = useState("");
  const [manual, setManual] = useState(false);
  const [picked, setPicked] = useState<Set<number>>(new Set());
  const [busy, setBusy] = useState(false);
  const [cheques, setCheques] = useState<ChequeOnFile[]>([]);
  const [chequeId, setChequeId] = useState("");

  useEffect(() => {
    if (!open || !clientId) return;
    setAmount(initialAmount != null ? String(initialAmount) : "");
    setReceiptDate(new Date().toISOString().slice(0, 10));
    setMode(initialMode ?? "cash");
    setReference("");
    setRemarks("");
    setChequeId("");
    api.get("/rent/charges", { params: { client_id: clientId } })
      .then((r) => {
        const rows: Charge[] = (r.data?.data ?? []).filter((c: Charge) => c.outstanding > 0);
        rows.sort((a, b) => a.period_month.localeCompare(b.period_month));
        setCharges(rows);
        if (initialMonth) {
          const match = rows.find((c) => c.period_month.slice(0, 7) === initialMonth.slice(0, 7));
          if (match) {
            setManual(true);
            setPicked(new Set([match.id]));
            return;
          }
        }
        setManual(false);
        setPicked(new Set());
      })
      .catch(() => setCharges([]));
    api.get("/contracts/cheques", { params: { client_id: clientId, status: "received" } })
      .then((r) => setCheques((r.data?.data ?? []).filter((c: ChequeOnFile) => !c.is_security)))
      .catch(() => setCheques([]));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, clientId]);

  // Picking a cheque on file locks the amount to it — the receipt
  // posts through the deposit path so the cheque register and the
  // rent ledger move together (see docs/ACCOUNTING-RULES.md rule 9).
  const pickCheque = (id: string) => {
    setChequeId(id);
    const c = cheques.find((x) => String(x.id) === id);
    if (c) {
      setAmount(String(c.amount));
      setReference(`Cheque ${c.cheque_number}`);
    }
  };

  const totalDue = charges.reduce((s, c) => s + c.outstanding, 0);

  /** Which months this amount will settle, in the order it will happen. */
  const preview = useMemo(() => {
    const value = Number(amount) || 0;
    if (value <= 0) return { lines: [] as { charge: Charge; applied: number }[], leftover: 0 };
    const pool = manual
      ? charges.filter((c) => picked.has(c.id))
      : charges;
    let remaining = value;
    const lines: { charge: Charge; applied: number }[] = [];
    for (const charge of pool) {
      if (remaining <= 0) break;
      const applied = Math.min(charge.outstanding, remaining);
      lines.push({ charge, applied });
      remaining = Math.round((remaining - applied) * 100) / 100;
    }
    return { lines, leftover: Math.round(remaining * 100) / 100 };
  }, [amount, charges, manual, picked]);

  const toggle = (id: number) => setPicked((prev) => {
    const next = new Set(prev);
    if (next.has(id)) next.delete(id); else next.add(id);
    return next;
  });

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!clientId) return;
    setBusy(true);
    try {
      if (mode === "cheque" && chequeId) {
        // A cheque already on file: deposit it. That path posts the
        // receipt itself (deposit is the revenue-recognition point —
        // see ACCOUNTING-RULES rule 9), so the cheque register and the
        // rent ledger can't drift apart.
        const resp = await api.post(`/contracts/cheques/${chequeId}/deposit`, {
          when: receiptDate,
        });
        toast.success(`Cheque ${resp.data?.data?.cheque_number ?? ""} deposited`);
      } else {
        const body: Record<string, unknown> = {
          client_id: clientId,
          amount: Number(amount),
          receipt_date: receiptDate,
          mode,
          reference: reference || null,
          remarks: remarks || null,
        };
        if (manual && picked.size > 0) {
          body.allocations = preview.lines.map((l) => ({
            charge_id: l.charge.id, amount: l.applied,
          }));
        }
        const resp = await api.post("/rent/receipts", body);
        const r = resp.data?.data;
        toast.success(`Receipt ${r?.receipt_number ?? ""} posted`,
          r?.unallocated > 0 ? `${money(r.unallocated)} held on account` : undefined);
      }
      onPosted();
    } catch (err: unknown) {
      toast.error("Could not post the receipt", errorMessage(err));
    } finally { setBusy(false); }
  };

  return (
    <Modal open={open} onClose={onClose} title={`Receive payment — ${clientName ?? ""}`} size="lg">
      <form onSubmit={submit} className="space-y-3">
        <div className="rounded-lg border border-border bg-card/40 p-3 text-xs">
          <span className="text-muted-foreground">Total outstanding:</span>{" "}
          <span className="font-semibold">{money(totalDue)}</span>
          <span className="text-muted-foreground"> across {charges.length} month
            {charges.length === 1 ? "" : "s"}</span>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <Field label="Amount received">
            <input required type="number" step="0.01" min="0.01" className={inputClass}
              value={amount} disabled={Boolean(chequeId)}
              onChange={(e) => setAmount(e.target.value)} />
            {totalDue > 0 && amount === "" && !chequeId && (
              <button type="button" onClick={() => setAmount(String(totalDue))}
                className="text-[11px] text-primary mt-1 hover:underline">
                Settle everything: {money(totalDue)}
              </button>
            )}
          </Field>
          <Field label="Date">
            <input required type="date" className={inputClass} value={receiptDate}
              onChange={(e) => setReceiptDate(e.target.value)} />
          </Field>
          <Field label="Mode">
            <select className={selectClass} value={mode} onChange={(e) => {
              setMode(e.target.value);
              if (e.target.value !== "cheque") setChequeId("");
            }}>
              <option value="cash">Cash</option>
              <option value="online">Online transfer</option>
              <option value="cheque">Cheque</option>
              <option value="adjustment">Adjustment</option>
            </select>
          </Field>
          <Field label="Reference">
            <input className={inputClass} value={reference} disabled={Boolean(chequeId)}
              onChange={(e) => setReference(e.target.value)}
              placeholder="Transfer / cheque no." />
          </Field>
        </div>

        {mode === "cheque" && (
          <Field label="Cheque on file (optional)">
            <select className={selectClass} value={chequeId} onChange={(e) => pickCheque(e.target.value)}>
              <option value="">— A cheque not yet registered —</option>
              {cheques.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.cheque_number} · {money(c.amount)}
                  {c.for_month ? ` · ${c.for_month.slice(0, 7)}` : ""}
                  {c.contract_number ? ` · ${c.contract_number}` : ""}
                </option>
              ))}
            </select>
            <div className="text-[11px] text-muted-foreground mt-1">
              {chequeId
                ? "Posts by depositing this cheque — amount and reference are locked to it."
                : "Pick one to deposit it directly, or leave blank to record an untracked cheque."}
            </div>
          </Field>
        )}

        <label className="inline-flex items-center gap-2 text-sm cursor-pointer">
          <input type="checkbox" checked={manual} onChange={(e) => {
            setManual(e.target.checked);
            setPicked(new Set());
          }} />
          Choose which months this settles
          <span className="text-xs text-muted-foreground">
            (default: oldest first)
          </span>
        </label>

        {manual && (
          <div className="grid grid-cols-3 sm:grid-cols-4 gap-1.5 max-h-32 overflow-y-auto">
            {charges.map((c) => (
              <button key={c.id} type="button" onClick={() => toggle(c.id)}
                className={
                  "rounded-md border p-1.5 text-xs transition-colors " +
                  (picked.has(c.id)
                    ? "border-primary bg-primary/10 text-primary"
                    : "border-border bg-card/60 hover:bg-accent")
                }>
                <div className="font-mono">
                  {c.is_opening_balance ? "Opening" : c.period_month.slice(0, 7)}
                </div>
                <div className="text-[10px] text-muted-foreground">{money(c.outstanding)}</div>
              </button>
            ))}
          </div>
        )}

        {preview.lines.length > 0 && (
          <div className="rounded-lg border border-border bg-card/40 p-3 space-y-1">
            <div className="text-xs font-medium">This receipt will settle</div>
            {preview.lines.map((l) => (
              <div key={l.charge.id} className="flex justify-between text-xs">
                <span className="font-mono">
                  {l.charge.is_opening_balance ? "Opening balance" : l.charge.period_month.slice(0, 7)}
                </span>
                <span>
                  {money(l.applied)}
                  {l.applied < l.charge.outstanding && (
                    <span className="text-muted-foreground"> of {money(l.charge.outstanding)}</span>
                  )}
                </span>
              </div>
            ))}
            {preview.leftover > 0 && (
              <div className="flex justify-between text-xs text-amber-600 pt-1 border-t border-border">
                <span>Held on account</span>
                <span>{money(preview.leftover)}</span>
              </div>
            )}
          </div>
        )}

        <Field label="Remarks">
          <textarea className={textareaClass} value={remarks}
            onChange={(e) => setRemarks(e.target.value)} />
        </Field>

        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={onClose}
            className="h-9 rounded-md border border-border bg-card/60 px-3 text-sm">Cancel</button>
          <button type="submit" disabled={busy || !amount || Number(amount) <= 0}
            className="h-9 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-60">
            {busy ? "Posting…" : "Post receipt"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
