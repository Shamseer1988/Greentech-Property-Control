"use client";

import { useEffect, useState } from "react";
import {
  Plus, Banknote, ArrowDownToLine, CheckCircle2, XCircle, RotateCcw, Undo2, Wallet,
} from "lucide-react";
import { api } from "@/lib/api";
import { Can } from "@/components/can";
import { Modal, Field, inputClass } from "@/components/ui/dialog";
import { toast, errorMessage } from "@/components/ui/toast";
import { ReceiptDialog } from "@/components/receipt-dialog";
import type { Contract, Cheque } from "@/lib/contract-types";
import { CHEQUE_TONE, money } from "@/lib/contract-types";

type PreviewRow = { sequence: number; cheque_date: string; for_month: string; amount: number };

/** The PDC book: 12 rent cheques + a security cheque, and their lifecycle. */
export function ChequeGrid({ contract, onChanged }: { contract: Contract; onChanged: () => void }) {
  const [rows, setRows] = useState<Cheque[]>([]);
  const [loading, setLoading] = useState(true);
  const [showEntry, setShowEntry] = useState(false);
  const [acting, setActing] = useState<{ cheque: Cheque; kind: string } | null>(null);
  const [payCashFor, setPayCashFor] = useState<Cheque | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      const resp = await api.get(`/contracts/${contract.id}/cheques`);
      setRows(Array.isArray(resp.data?.data) ? resp.data.data : []);
    } finally { setLoading(false); }
  };

  useEffect(() => { load(); }, [contract.id]);  // eslint-disable-line react-hooks/exhaustive-deps

  const act = async (cheque: Cheque, kind: string, body: Record<string, unknown> = {}) => {
    try {
      await api.post(`/contracts/cheques/${cheque.id}/${kind}`, body);
      toast.success(`Cheque ${cheque.cheque_number} — ${kind}`);
      await load();
      onChanged();
    } catch (err: unknown) {
      toast.error("Could not update the cheque", errorMessage(err));
    }
  };

  // Hand a cheque back and immediately record the cash that replaces
  // it — the amount and month carry over so nothing is retyped.
  const returnAndPayCash = async (c: Cheque) => {
    try {
      await api.post(`/contracts/cheques/${c.id}/return`, {
        remarks: "Client returned the cheque, paying cash instead",
      });
      toast.success(`Cheque ${c.cheque_number} returned`);
      await load();
      onChanged();
      setPayCashFor(c);
    } catch (err: unknown) {
      toast.error("Could not return the cheque", errorMessage(err));
    }
  };

  const cleared = rows.filter((c) => c.status === "cleared").length;
  const bounced = rows.filter((c) => c.status === "bounced").length;
  const held = rows.filter((c) => c.status === "received" && !c.is_security).length;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex gap-2 text-xs">
          <Stat label="On hand" value={held} />
          <Stat label="Cleared" value={cleared} tone="emerald" />
          {bounced > 0 && <Stat label="Bounced" value={bounced} tone="rose" />}
        </div>
        <Can perm="cheque.manage">
          <button onClick={() => setShowEntry(true)}
            className="inline-flex h-9 items-center gap-2 rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground hover:bg-primary/90">
            <Plus className="h-4 w-4" /> Enter cheque book
          </button>
        </Can>
      </div>

      <div className="glass rounded-xl overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-left text-xs text-muted-foreground border-b border-border">
            <tr>
              <th className="py-2 px-3">Cheque no.</th>
              <th className="py-2 px-3">Bank</th>
              <th className="py-2 px-3">Date</th>
              <th className="py-2 px-3">For month</th>
              <th className="py-2 px-3 text-right">Amount</th>
              <th className="py-2 px-3">Status</th>
              <th className="py-2 px-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={7} className="py-10 text-center text-muted-foreground">Loading…</td></tr>
            ) : rows.length === 0 ? (
              <tr><td colSpan={7} className="py-10 text-center text-muted-foreground">
                No cheques registered. Use “Enter cheque book” to record the 12 rent
                cheques and the security cheque in one go.
              </td></tr>
            ) : rows.map((c) => (
              <tr key={c.id} className="border-b border-border/60">
                <td className="py-2 px-3 font-mono text-xs">
                  {c.cheque_number}
                  {c.is_security && (
                    <span className="ml-1 rounded bg-violet-500/10 text-violet-600 px-1 text-[10px]">
                      security
                    </span>
                  )}
                  {c.replaces_cheque_id && (
                    <div className="text-[10px] text-muted-foreground">replacement</div>
                  )}
                </td>
                <td className="py-2 px-3 text-xs">{c.bank_name ?? "—"}</td>
                <td className="py-2 px-3 font-mono text-xs">{c.cheque_date}</td>
                <td className="py-2 px-3 font-mono text-xs">{c.for_month ?? "—"}</td>
                <td className="py-2 px-3 text-right font-medium">{money(c.amount)}</td>
                <td className="py-2 px-3">
                  <span className={"rounded-full px-2 py-0.5 text-xs capitalize " + (CHEQUE_TONE[c.status] ?? "")}>
                    {c.status}
                  </span>
                </td>
                <td className="py-2 px-3 text-right whitespace-nowrap">
                  <Can perm="cheque.manage">
                    {c.status === "received" && !c.is_security && (
                      <>
                        <IconBtn label="Deposit" onClick={() => act(c, "deposit")}><ArrowDownToLine className="h-3.5 w-3.5" /></IconBtn>
                        <IconBtn label="Return (client pays cash)" onClick={() => returnAndPayCash(c)}>
                          <Wallet className="h-3.5 w-3.5" />
                        </IconBtn>
                      </>
                    )}
                    {c.status === "received" && c.is_security && (
                      <IconBtn label="Return" onClick={() => act(c, "return")}><Undo2 className="h-3.5 w-3.5" /></IconBtn>
                    )}
                    {c.status === "deposited" && (
                      <>
                        <IconBtn label="Cleared" tone="emerald" onClick={() => act(c, "clear")}>
                          <CheckCircle2 className="h-3.5 w-3.5" />
                        </IconBtn>
                        <IconBtn label="Bounced" tone="rose" onClick={() => setActing({ cheque: c, kind: "bounce" })}>
                          <XCircle className="h-3.5 w-3.5" />
                        </IconBtn>
                        {!c.is_security && (
                          <IconBtn label="Return (client pays cash)" onClick={() => returnAndPayCash(c)}>
                            <Wallet className="h-3.5 w-3.5" />
                          </IconBtn>
                        )}
                      </>
                    )}
                    {c.status === "bounced" && (
                      <>
                        <IconBtn label="Re-present (redeposit)" onClick={() => act(c, "deposit")}>
                          <ArrowDownToLine className="h-3.5 w-3.5" />
                        </IconBtn>
                        <IconBtn label="Replace" onClick={() => setActing({ cheque: c, kind: "replace" })}>
                          <RotateCcw className="h-3.5 w-3.5" />
                        </IconBtn>
                      </>
                    )}
                  </Can>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <ChequeBookDialog
        open={showEntry}
        contract={contract}
        onClose={() => setShowEntry(false)}
        onSaved={async () => { setShowEntry(false); await load(); onChanged(); }}
      />

      <ChequeActionDialog
        acting={acting}
        onClose={() => setActing(null)}
        onDone={async () => { setActing(null); await load(); onChanged(); }}
      />

      <ReceiptDialog
        open={Boolean(payCashFor)}
        clientId={contract.client_id}
        clientName={contract.client?.name ?? null}
        initialMode="cash"
        initialAmount={payCashFor?.amount}
        initialMonth={payCashFor?.for_month ?? null}
        onClose={() => setPayCashFor(null)}
        onPosted={async () => { setPayCashFor(null); await load(); onChanged(); }}
      />
    </div>
  );
}

function Stat({ label, value, tone }: { label: string; value: number; tone?: "emerald" | "rose" }) {
  const cls = tone === "emerald" ? "text-emerald-600" : tone === "rose" ? "text-rose-600" : "";
  return (
    <div className="rounded-md border border-border bg-card/60 px-2.5 py-1">
      <span className={"font-semibold " + cls}>{value}</span>{" "}
      <span className="text-muted-foreground">{label}</span>
    </div>
  );
}

function IconBtn({ label, onClick, tone, children }: {
  label: string; onClick: () => void; tone?: "emerald" | "rose"; children: React.ReactNode;
}) {
  const cls = tone === "emerald" ? "hover:bg-emerald-500/10 text-emerald-600"
    : tone === "rose" ? "hover:bg-rose-500/10 text-rose-600" : "hover:bg-accent";
  return (
    <button onClick={onClick} title={label} aria-label={label}
      className={"h-8 w-8 grid place-items-center rounded-md inline-block " + cls}>
      {children}
    </button>
  );
}

/** Enter the whole book at once: dates and amounts are pre-filled from
 *  the contract, so the operator only types cheque numbers. */
function ChequeBookDialog({ open, contract, onClose, onSaved }: {
  open: boolean; contract: Contract; onClose: () => void; onSaved: () => void;
}) {
  const [preview, setPreview] = useState<PreviewRow[]>([]);
  const [numbers, setNumbers] = useState<string[]>([]);
  const [bank, setBank] = useState("");
  const [securityNumber, setSecurityNumber] = useState("");
  const [securityAmount, setSecurityAmount] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    setBank("");
    setSecurityNumber("");
    setSecurityAmount(String(contract.monthly_rent));
    api.get(`/contracts/${contract.id}/cheques/preview`, { params: { count: 12 } })
      .then((r) => {
        const rows: PreviewRow[] = r.data.data ?? [];
        setPreview(rows);
        setNumbers(Array(rows.length).fill(""));
      })
      .catch(() => { setPreview([]); setNumbers([]); });
  }, [open, contract.id, contract.monthly_rent]);

  const filled = numbers.filter((n) => n.trim()).length;

  // Fill rows 2..N from row 1's number, incrementing the trailing digit
  // run and preserving its zero-padding width — "105" → 106, 107 …;
  // "CHQ-0105" → CHQ-0106, CHQ-0107 … so a bank's real numbering
  // convention survives the auto-fill.
  const autoFill = () => {
    const first = (numbers[0] ?? "").trim();
    const m = first.match(/^(.*?)(\d+)(\D*)$/);
    if (!m) {
      toast.error("Can't auto-fill", "Enter the first cheque number, then auto-fill the rest.");
      return;
    }
    const [, prefix, digits, suffix] = m;
    const width = digits.length;
    const start = parseInt(digits, 10);
    setNumbers((prev) => prev.map((v, i) => {
      if (i === 0) return v;
      return `${prefix}${String(start + i).padStart(width, "0")}${suffix}`;
    }));
  };

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      const cheques = preview
        .map((row, i) => ({ row, number: numbers[i]?.trim() }))
        .filter((x) => x.number)
        .map((x) => ({
          cheque_number: x.number,
          bank_name: bank || null,
          cheque_date: x.row.cheque_date,
          for_month: x.row.for_month,
          amount: x.row.amount,
        }));
      const security = securityNumber.trim()
        ? {
            cheque_number: securityNumber.trim(),
            bank_name: bank || null,
            cheque_date: contract.start_date,
            amount: securityAmount ? Number(securityAmount) : contract.monthly_rent,
          }
        : null;
      const resp = await api.post(`/contracts/${contract.id}/cheques`, { cheques, security });
      toast.success(`${resp.data?.data?.length ?? 0} cheque(s) registered`);
      onSaved();
    } catch (err: unknown) {
      toast.error("Could not save the cheque book", errorMessage(err));
    } finally { setBusy(false); }
  };

  return (
    <Modal open={open} onClose={onClose} title="Enter cheque book" size="lg">
      <form onSubmit={save} className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <Field label="Bank (applies to all)">
            <input className={inputClass} value={bank} onChange={(e) => setBank(e.target.value)}
              placeholder="e.g. QNB" />
          </Field>
          <Field label="Cheques filled">
            <div className="flex gap-2">
              <input className={inputClass} value={`${filled} of ${preview.length}`} disabled />
              <button type="button" onClick={autoFill} disabled={!numbers[0]?.trim()}
                title="Fill the remaining rows by incrementing the first cheque number"
                className="h-9 shrink-0 rounded-md border border-border bg-card/60 px-3 text-xs font-medium hover:bg-accent disabled:opacity-50 whitespace-nowrap">
                Auto-fill
              </button>
            </div>
          </Field>
        </div>

        <div className="rounded-lg border border-border overflow-hidden">
          <table className="w-full text-xs">
            <thead className="bg-card/60 text-muted-foreground">
              <tr>
                <th className="py-1.5 px-2 text-left">#</th>
                <th className="py-1.5 px-2 text-left">Cheque date</th>
                <th className="py-1.5 px-2 text-left">For month</th>
                <th className="py-1.5 px-2 text-right">Amount</th>
                <th className="py-1.5 px-2 text-left">Cheque number</th>
              </tr>
            </thead>
            <tbody className="max-h-64">
              {preview.map((row, i) => (
                <tr key={row.sequence} className="border-t border-border/60">
                  <td className="py-1 px-2">{row.sequence}</td>
                  <td className="py-1 px-2 font-mono">{row.cheque_date}</td>
                  <td className="py-1 px-2 font-mono">{row.for_month?.slice(0, 7)}</td>
                  <td className="py-1 px-2 text-right">{money(row.amount)}</td>
                  <td className="py-1 px-2">
                    <input
                      className="h-7 w-full rounded border border-input bg-card/60 px-2 font-mono text-xs"
                      value={numbers[i] ?? ""}
                      onChange={(e) => setNumbers((prev) => {
                        const next = [...prev];
                        next[i] = e.target.value;
                        return next;
                      })}
                      placeholder="—"
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="rounded-lg border border-violet-500/30 bg-violet-500/5 p-3 grid grid-cols-2 gap-3">
          <div className="col-span-2 text-xs font-medium inline-flex items-center gap-1.5">
            <Banknote className="h-3.5 w-3.5" /> Security cheque
          </div>
          <Field label="Cheque number">
            <input className={inputClass} value={securityNumber}
              onChange={(e) => setSecurityNumber(e.target.value)} placeholder="Optional" />
          </Field>
          <Field label="Amount">
            <input type="number" step="0.01" className={inputClass} value={securityAmount}
              onChange={(e) => setSecurityAmount(e.target.value)} />
          </Field>
        </div>

        <div className="text-xs text-muted-foreground">
          Blank rows are skipped. If any cheque number is rejected the whole book is
          discarded, so you never end up with a half-entered set.
        </div>

        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={onClose}
            className="h-9 rounded-md border border-border bg-card/60 px-3 text-sm">Cancel</button>
          <button type="submit" disabled={busy || (filled === 0 && !securityNumber.trim())}
            className="h-9 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-60">
            {busy ? "Saving…" : `Register ${filled + (securityNumber.trim() ? 1 : 0)} cheque(s)`}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function ChequeActionDialog({ acting, onClose, onDone }: {
  acting: { cheque: Cheque; kind: string } | null;
  onClose: () => void;
  onDone: () => void;
}) {
  const [form, setForm] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  useEffect(() => { setForm({}); }, [acting]);

  if (!acting) return <Modal open={false} onClose={onClose} title="">{null}</Modal>;
  const { cheque, kind } = acting;
  const set = (k: string, v: string) => setForm((f) => ({ ...f, [k]: v }));

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      if (kind === "bounce") {
        await api.post(`/contracts/cheques/${cheque.id}/bounce`, {
          reason: form.reason, when: form.when || null,
        });
        toast.success(`Cheque ${cheque.cheque_number} marked bounced`);
      } else {
        await api.post(`/contracts/cheques/${cheque.id}/replace`, {
          cheque_number: form.cheque_number, cheque_date: form.cheque_date,
          amount: form.amount ? Number(form.amount) : null,
        });
        toast.success("Replacement cheque registered");
      }
      onDone();
    } catch (err: unknown) {
      toast.error("Could not update the cheque", errorMessage(err));
    } finally { setBusy(false); }
  };

  return (
    <Modal open onClose={onClose}
      title={kind === "bounce" ? `Cheque ${cheque.cheque_number} bounced` : `Replace cheque ${cheque.cheque_number}`}>
      <form onSubmit={submit} className="space-y-3">
        {kind === "bounce" ? (
          <>
            <Field label="Reason">
              <input required className={inputClass} value={form.reason ?? ""}
                onChange={(e) => set("reason", e.target.value)}
                placeholder="e.g. insufficient funds" />
            </Field>
            <Field label="Date">
              <input type="date" className={inputClass} value={form.when ?? ""}
                onChange={(e) => set("when", e.target.value)} />
            </Field>
          </>
        ) : (
          <div className="grid grid-cols-2 gap-3">
            <Field label="New cheque number">
              <input required className={inputClass} value={form.cheque_number ?? ""}
                onChange={(e) => set("cheque_number", e.target.value)} />
            </Field>
            <Field label="New cheque date">
              <input required type="date" className={inputClass} value={form.cheque_date ?? ""}
                onChange={(e) => set("cheque_date", e.target.value)} />
            </Field>
            <Field label="Amount" span={2}>
              <input type="number" step="0.01" className={inputClass} value={form.amount ?? ""}
                onChange={(e) => set("amount", e.target.value)}
                placeholder={`Same as original (${money(cheque.amount)})`} />
            </Field>
            <div className="col-span-2 text-xs text-muted-foreground">
              The bounced cheque stays on record and links to this replacement.
            </div>
          </div>
        )}
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={onClose}
            className="h-9 rounded-md border border-border bg-card/60 px-3 text-sm">Cancel</button>
          <button type="submit" disabled={busy}
            className="h-9 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-60">
            {busy ? "Saving…" : kind === "bounce" ? "Mark bounced" : "Register replacement"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
