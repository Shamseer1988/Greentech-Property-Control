"use client";

import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { ArrowLeft, Printer, Banknote, XCircle } from "lucide-react";
import { api } from "@/lib/api";
import { useRouteParams } from "@/lib/use-route-params";
import { keys } from "@/lib/query-keys";
import { Can } from "@/components/can";
import { Modal, Field, inputClass } from "@/components/ui/dialog";
import { toast, errorMessage } from "@/components/ui/toast";
import { ReceiptDialog } from "@/components/receipt-dialog";
import { money } from "@/lib/contract-types";

type Line = {
  date: string;
  type: string;
  reference: string | null;
  particulars: string;
  debit: number;
  credit: number;
  balance: number;
  note: string | null;
};

type Statement = {
  client: { id: number; code: string; name: string; name_ar: string | null };
  lines: Line[];
  totals: { debit: number; credit: number; balance: number };
  to_date: string;
};

type Receipt = {
  id: number;
  receipt_number: string;
  receipt_date: string;
  amount: number;
  mode: string;
  reference: string | null;
  status: string;
  void_reason: string | null;
  unallocated: number;
};

/** The Soa sheet, reborn: charges and receipts with a running balance. */
export default function StatementPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = useRouteParams(params);
  const qc = useQueryClient();
  const [showReceipt, setShowReceipt] = useState(false);
  const [voiding, setVoiding] = useState<Receipt | null>(null);

  const soaQuery = useQuery({
    queryKey: keys.collections.statement(id),
    queryFn: async () => (await api.get(`/rent/statement/${id}`)).data?.data as Statement,
  });
  const receiptsQuery = useQuery({
    queryKey: keys.collections.receipts({ client_id: id }),
    queryFn: async () => {
      const r = await api.get("/rent/receipts", { params: { client_id: id } });
      return (Array.isArray(r.data?.data) ? r.data.data : []) as Receipt[];
    },
  });
  const soa = soaQuery.data ?? null;
  const receipts = receiptsQuery.data ?? [];
  const loading = soaQuery.isLoading || receiptsQuery.isLoading;
  const load = () => Promise.all([
    qc.invalidateQueries({ queryKey: keys.collections.statement(id) }),
    qc.invalidateQueries({ queryKey: keys.collections.receipts({ client_id: id }) }),
  ]);

  if (loading || !soa) {
    return <div className="text-sm text-muted-foreground animate-pulse">Loading statement…</div>;
  }

  return (
    <div className="space-y-6 animate-fade-in soa-print-root">
      <div className="print:hidden">
        <Link href="/collections" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft className="h-3.5 w-3.5" /> Back to collections
        </Link>
      </div>

      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl lg:text-3xl font-semibold tracking-tight">
            Statement of account
          </h1>
          <p className="text-sm text-muted-foreground">
            {soa.client.name}
            {soa.client.name_ar && <span dir="rtl"> · {soa.client.name_ar}</span>}
            {" · "}<span className="font-mono">{soa.client.code}</span>
            {" · as at "}{soa.to_date}
          </p>
        </div>
        <div className="flex items-center gap-2 print:hidden">
          <button onClick={() => window.print()}
            className="h-9 inline-flex items-center gap-2 rounded-md border border-border bg-card/60 px-3 text-sm hover:bg-accent">
            <Printer className="h-4 w-4" /> Print
          </button>
          <Can perm="receipt.create">
            <button onClick={() => setShowReceipt(true)}
              className="h-9 inline-flex items-center gap-2 rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground hover:bg-primary/90">
              <Banknote className="h-4 w-4" /> Receive payment
            </button>
          </Can>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3">
        <Card label="Total charged" value={money(soa.totals.debit)} />
        <Card label="Total received" value={money(soa.totals.credit)} tone="emerald" />
        <Card label="Balance due" value={money(soa.totals.balance)}
          tone={soa.totals.balance > 0 ? "rose" : "emerald"} />
      </div>

      <div className="glass rounded-xl overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-left text-xs text-muted-foreground border-b border-border">
            <tr>
              <th className="py-2 px-3">Date</th>
              <th className="py-2 px-3">Particulars</th>
              <th className="py-2 px-3">Reference</th>
              <th className="py-2 px-3 text-right">Debit</th>
              <th className="py-2 px-3 text-right">Credit</th>
              <th className="py-2 px-3 text-right">Balance</th>
            </tr>
          </thead>
          <tbody>
            {soa.lines.length === 0 ? (
              <tr><td colSpan={6} className="py-10 text-center text-muted-foreground">
                Nothing on this account yet.
              </td></tr>
            ) : soa.lines.map((l, i) => (
              <tr key={i} className="border-b border-border/60">
                <td className="py-2 px-3 font-mono text-xs">{l.date}</td>
                <td className="py-2 px-3">
                  {l.particulars}
                  {l.note && <div className="text-[11px] text-muted-foreground">{l.note}</div>}
                </td>
                <td className="py-2 px-3 font-mono text-xs">{l.reference ?? "—"}</td>
                <td className="py-2 px-3 text-right">{l.debit ? money(l.debit) : ""}</td>
                <td className="py-2 px-3 text-right text-emerald-600">
                  {l.credit ? money(l.credit) : ""}
                </td>
                <td className="py-2 px-3 text-right font-medium">{money(l.balance)}</td>
              </tr>
            ))}
          </tbody>
          <tfoot className="border-t-2 border-border font-semibold">
            <tr>
              <td className="py-2 px-3" colSpan={3}>Totals</td>
              <td className="py-2 px-3 text-right">{money(soa.totals.debit)}</td>
              <td className="py-2 px-3 text-right">{money(soa.totals.credit)}</td>
              <td className="py-2 px-3 text-right">{money(soa.totals.balance)}</td>
            </tr>
          </tfoot>
        </table>
      </div>

      <div className="glass rounded-xl overflow-x-auto print:hidden">
        <div className="px-4 pt-3 text-sm font-semibold">Receipts</div>
        <table className="w-full text-sm mt-2">
          <thead className="text-left text-xs text-muted-foreground border-b border-border">
            <tr>
              <th className="py-2 px-3">Receipt</th>
              <th className="py-2 px-3">Date</th>
              <th className="py-2 px-3">Mode</th>
              <th className="py-2 px-3 text-right">Amount</th>
              <th className="py-2 px-3">Status</th>
              <th className="py-2 px-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {receipts.length === 0 ? (
              <tr><td colSpan={6} className="py-8 text-center text-muted-foreground">
                No receipts yet.
              </td></tr>
            ) : receipts.map((r) => (
              <tr key={r.id} className="border-b border-border/60">
                <td className="py-2 px-3 font-mono text-xs">{r.receipt_number}</td>
                <td className="py-2 px-3 font-mono text-xs">{r.receipt_date}</td>
                <td className="py-2 px-3 capitalize">{r.mode}</td>
                <td className="py-2 px-3 text-right">
                  {money(r.amount)}
                  {r.unallocated > 0 && (
                    <div className="text-[11px] text-amber-600">
                      {money(r.unallocated)} on account
                    </div>
                  )}
                </td>
                <td className="py-2 px-3">
                  <span className={
                    "rounded-full px-2 py-0.5 text-xs capitalize " +
                    (r.status === "voided" ? "bg-rose-500/10 text-rose-600"
                      : "bg-emerald-500/10 text-emerald-600")
                  }>
                    {r.status}
                  </span>
                  {r.void_reason && (
                    <div className="text-[11px] text-muted-foreground">{r.void_reason}</div>
                  )}
                </td>
                <td className="py-2 px-3 text-right">
                  {r.status === "posted" && (
                    <Can perm="receipt.void">
                      <button onClick={() => setVoiding(r)} title="Void receipt"
                        className="h-8 w-8 grid place-items-center rounded-md hover:bg-destructive/10 text-destructive inline-block">
                        <XCircle className="h-3.5 w-3.5" />
                      </button>
                    </Can>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <ReceiptDialog
        open={showReceipt}
        clientId={soa.client.id}
        clientName={soa.client.name}
        onClose={() => setShowReceipt(false)}
        onPosted={async () => { setShowReceipt(false); await load(); }}
      />

      <VoidDialog
        receipt={voiding}
        onClose={() => setVoiding(null)}
        onVoided={async () => { setVoiding(null); await load(); }}
      />
    </div>
  );
}

function Card({ label, value, tone }: { label: string; value: string; tone?: "emerald" | "rose" }) {
  const cls = tone === "emerald" ? "text-emerald-600" : tone === "rose" ? "text-rose-600" : "";
  return (
    <div className="glass rounded-xl p-4">
      <div className="text-sm text-muted-foreground">{label}</div>
      <div className={"mt-1 text-2xl font-semibold " + cls}>{value}</div>
    </div>
  );
}

function VoidDialog({ receipt, onClose, onVoided }: {
  receipt: Receipt | null; onClose: () => void; onVoided: () => void;
}) {
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => { setReason(""); }, [receipt]);
  if (!receipt) return <Modal open={false} onClose={onClose} title="">{null}</Modal>;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      const resp = await api.post(`/rent/receipts/${receipt.id}/void`, { reason });
      if (resp.status === 202) {
        toast.success("Sent for approval", resp.data?.message ?? "");
      } else {
        toast.success(`Receipt ${receipt.receipt_number} voided`,
          "The months it settled are open again");
      }
      onVoided();
    } catch (err: unknown) {
      toast.error("Could not void the receipt", errorMessage(err));
    } finally { setBusy(false); }
  };

  return (
    <Modal open onClose={onClose} title={`Void receipt ${receipt.receipt_number}`}>
      <form onSubmit={submit} className="space-y-3">
        <div className="rounded-lg border border-amber-500/40 bg-amber-500/5 p-3 text-xs">
          The receipt is kept on the ledger with its number — voiding reverses its
          allocations so the months it paid become due again.
        </div>
        <Field label="Reason">
          <input required className={inputClass} value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="e.g. posted against the wrong client" />
        </Field>
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={onClose}
            className="h-9 rounded-md border border-border bg-card/60 px-3 text-sm">Cancel</button>
          <button type="submit" disabled={busy || !reason.trim()}
            className="h-9 rounded-md bg-destructive px-4 text-sm font-medium text-destructive-foreground hover:bg-destructive/90 disabled:opacity-60">
            {busy ? "Voiding…" : "Void receipt"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
