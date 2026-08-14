"use client";

import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { FileText, Download, RotateCcw, Ban, RefreshCw } from "lucide-react";
import type { ColumnDef } from "@tanstack/react-table";
import { api } from "@/lib/api";
import { Can } from "@/components/can";
import { selectClass } from "@/components/ui/dialog";
import { DataTable } from "@/components/ui/data-table";
import { toast, errorMessage } from "@/components/ui/toast";
import { AgreementWizard } from "@/components/agreement-wizard";
import { useDebouncedValue } from "@/lib/use-debounce";
import { money } from "@/lib/contract-types";
import { keys } from "@/lib/query-keys";

type AgreementRow = {
  id: number;
  agreement_number: string;
  template_slug: string;
  party_role: "landlord" | "client";
  landlord?: { id: number; code: string; name: string } | null;
  client?: { id: number; code: string; name: string } | null;
  start_date: string;
  end_date: string;
  rent_amount: number | null;
  currency: string;
  status: string;
  attachment_id: number | null;
  superseded_by_id: number | null;
};

const STATUS_TONE: Record<string, string> = {
  generated: "bg-emerald-500/10 text-emerald-600",
  voided: "bg-muted text-muted-foreground line-through",
};

export default function AgreementsPage() {
  const qc = useQueryClient();
  const [status, setStatus] = useState("");
  const [q, setQ] = useState("");
  const debouncedQ = useDebouncedValue(q);
  const [showWizard, setShowWizard] = useState(false);
  const [voidTarget, setVoidTarget] = useState<AgreementRow | null>(null);
  const [voidReason, setVoidReason] = useState("");
  const [showBulkRenewConfirm, setShowBulkRenewConfirm] = useState(false);
  const [bulkRenewing, setBulkRenewing] = useState(false);
  const BULK_RENEW_WITHIN_DAYS = 60;

  // The list route paginates server-side, but this page still filters by
  // `q` client-side (no full-text search param on /agreements yet), so it
  // fetches one full status-filtered page rather than opting into
  // DataTable's manual-pagination mode.
  const listQuery = useQuery({
    queryKey: keys.agreements.list({ status }),
    queryFn: async () => {
      const params: Record<string, string | number> = { per_page: 200 };
      if (status) params.status = status;
      const resp = await api.get("/agreements", { params });
      return Array.isArray(resp.data?.data) ? (resp.data.data as AgreementRow[]) : [];
    },
  });
  const rows = listQuery.data ?? [];
  const loading = listQuery.isLoading;
  const invalidate = () => qc.invalidateQueries({ queryKey: keys.agreements.all() });

  const expiringSoonCount = useMemo(() => {
    const cutoff = new Date();
    cutoff.setDate(cutoff.getDate() + BULK_RENEW_WITHIN_DAYS);
    return rows.filter((r) =>
      r.status === "generated" && !r.superseded_by_id && new Date(r.end_date) <= cutoff).length;
  }, [rows]);

  const bulkRenew = async () => {
    setBulkRenewing(true);
    try {
      const resp = await api.post("/agreements/bulk-renew", { within_days: BULK_RENEW_WITHIN_DAYS });
      const { renewed_count, failed_count } = resp.data.data;
      toast.success(`${renewed_count} agreement(s) renewed` + (failed_count ? `, ${failed_count} failed` : ""));
      setShowBulkRenewConfirm(false);
      invalidate();
    } catch (err: unknown) {
      toast.error("Bulk renewal failed", errorMessage(err));
    } finally {
      setBulkRenewing(false);
    }
  };

  const filtered = useMemo(() => {
    if (!debouncedQ) return rows;
    const needle = debouncedQ.toLowerCase();
    return rows.filter((r) =>
      r.agreement_number.toLowerCase().includes(needle) ||
      r.landlord?.name.toLowerCase().includes(needle) ||
      r.client?.name.toLowerCase().includes(needle));
  }, [rows, debouncedQ]);

  const voidAgreement = async () => {
    if (!voidTarget) return;
    try {
      await api.post(`/agreements/${voidTarget.id}/void`, { reason: voidReason });
      toast.success(`Agreement ${voidTarget.agreement_number} voided`);
      setVoidTarget(null); setVoidReason("");
      invalidate();
    } catch (err: unknown) {
      toast.error("Could not void the agreement", errorMessage(err));
    }
  };

  const columns = useMemo<ColumnDef<AgreementRow, unknown>[]>(() => [
    { accessorKey: "agreement_number", header: "Agreement",
      cell: (c) => <span className="font-mono text-xs">{c.getValue<string>()}</span> },
    { id: "party", header: "Party",
      cell: (c) => {
        const r = c.row.original;
        const party = r.party_role === "landlord" ? r.landlord : r.client;
        return (
          <div>
            <span className="font-medium">{party?.name ?? "—"}</span>
            <span className="ml-1.5 text-xs text-muted-foreground capitalize">({r.party_role})</span>
          </div>
        );
      },
    },
    { accessorKey: "start_date", header: "Term",
      cell: (c) => <span className="font-mono text-xs">{c.row.original.start_date} → {c.row.original.end_date}</span> },
    { accessorKey: "rent_amount", header: "Rent",
      cell: (c) => c.row.original.rent_amount != null
        ? `${money(c.row.original.rent_amount)} ${c.row.original.currency}` : "—" },
    { accessorKey: "status", header: "Status",
      cell: (c) => <span className={"rounded-full px-2 py-0.5 text-xs capitalize " + (STATUS_TONE[c.getValue<string>()] ?? "")}>{c.getValue<string>()}</span> },
    { id: "actions", header: "", cell: (c) => {
        const r = c.row.original;
        return (
          <div className="flex items-center gap-1.5 justify-end">
            {r.attachment_id && (
              <a href={`/api/v1/attachments/${r.attachment_id}/download`} target="_blank" rel="noreferrer"
                title="Download .docx"
                className="h-7 w-7 grid place-items-center rounded-md hover:bg-accent">
                <Download className="h-3.5 w-3.5" />
              </a>
            )}
            <Can perm="agreement.create">
              <button type="button" title="Regenerate"
                onClick={async () => {
                  try {
                    await api.post(`/agreements/${r.id}/regenerate`, {});
                    toast.success("New agreement generated");
                    invalidate();
                  } catch (err: unknown) {
                    toast.error("Could not regenerate", errorMessage(err));
                  }
                }}
                className="h-7 w-7 grid place-items-center rounded-md hover:bg-accent">
                <RotateCcw className="h-3.5 w-3.5" />
              </button>
            </Can>
            {r.status === "generated" && (
              <Can perm="agreement.void">
                <button type="button" title="Void" onClick={() => setVoidTarget(r)}
                  className="h-7 w-7 grid place-items-center rounded-md hover:bg-accent text-destructive">
                  <Ban className="h-3.5 w-3.5" />
                </button>
              </Can>
            )}
          </div>
        );
      },
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
  ], []);

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-end justify-between flex-wrap gap-2">
        <div>
          <h1 className="text-2xl lg:text-3xl font-semibold tracking-tight">Agreements</h1>
          <p className="text-sm text-muted-foreground">
            Generated bilingual rental agreements, landlord and client side.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Can perm="agreement.create">
            <button onClick={() => setShowBulkRenewConfirm(true)} disabled={expiringSoonCount === 0}
              title={expiringSoonCount === 0 ? "Nothing expiring within 60 days" : undefined}
              className="inline-flex items-center gap-1.5 h-9 rounded-md border border-border bg-card/60 px-3 text-sm hover:bg-accent disabled:opacity-50 disabled:hover:bg-card/60">
              <RefreshCw className="h-3.5 w-3.5" /> Renew expiring{expiringSoonCount > 0 ? ` (${expiringSoonCount})` : ""}
            </button>
          </Can>
          <Can perm="agreement.create">
            <button onClick={() => setShowWizard(true)}
              className="inline-flex items-center gap-1.5 h-9 rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground hover:bg-primary/90">
              <FileText className="h-3.5 w-3.5" /> New agreement
            </button>
          </Can>
        </div>
      </div>

      <div className="glass rounded-xl p-4">
        <div className="flex items-center gap-2 flex-wrap">
          <input value={q} onChange={(e) => setQ(e.target.value)}
            placeholder="Search agreement no., party…"
            className="h-9 w-64 shrink-0 rounded-md border border-input bg-card/60 px-3 text-sm" />
          <select className={selectClass + " !w-auto shrink-0"} value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">All statuses</option>
            <option value="generated">Generated</option>
            <option value="voided">Voided</option>
          </select>
        </div>
      </div>

      <DataTable columns={columns} data={filtered} loading={loading} maxBodyHeight="65vh"
        emptyMessage="No agreements generated yet" />

      {rows.length === 0 && !loading && (
        <div className="glass rounded-xl p-8 text-center space-y-2">
          <FileText className="h-8 w-8 mx-auto text-muted-foreground" />
          <div className="text-sm text-muted-foreground">
            Generate a bilingual rental agreement from a landlord or client&apos;s page, or
            start one here.
          </div>
        </div>
      )}

      <AgreementWizard open={showWizard} onClose={() => setShowWizard(false)}
        onGenerated={invalidate} />

      {showBulkRenewConfirm && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-black/50 backdrop-blur-sm p-4"
          onClick={() => !bulkRenewing && setShowBulkRenewConfirm(false)}>
          <div className="glass-strong w-full max-w-md rounded-2xl p-6" onClick={(e) => e.stopPropagation()}>
            <div className="font-semibold mb-2">Renew {expiringSoonCount} expiring agreement{expiringSoonCount === 1 ? "" : "s"}?</div>
            <div className="text-sm text-muted-foreground">
              Every generated agreement ending within {BULK_RENEW_WITHIN_DAYS} days will be regenerated with the
              same terms for the next equivalent period. The original stays on file, marked as superseded.
            </div>
            <div className="flex justify-end gap-2 mt-4">
              <button onClick={() => setShowBulkRenewConfirm(false)} disabled={bulkRenewing}
                className="h-9 rounded-md border border-border bg-card/60 px-3 text-sm disabled:opacity-50">Cancel</button>
              <button onClick={bulkRenew} disabled={bulkRenewing}
                className="h-9 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-60">
                {bulkRenewing ? "Renewing…" : `Renew ${expiringSoonCount}`}
              </button>
            </div>
          </div>
        </div>
      )}

      {voidTarget && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-black/50 backdrop-blur-sm p-4"
          onClick={() => setVoidTarget(null)}>
          <div className="glass-strong w-full max-w-md rounded-2xl p-6" onClick={(e) => e.stopPropagation()}>
            <div className="font-semibold mb-2">Void {voidTarget.agreement_number}?</div>
            <textarea className="w-full min-h-[80px] rounded-md border border-input bg-background p-3 text-sm"
              placeholder="Reason (required)" value={voidReason} onChange={(e) => setVoidReason(e.target.value)} />
            <div className="flex justify-end gap-2 mt-3">
              <button onClick={() => setVoidTarget(null)} className="h-9 rounded-md border border-border bg-card/60 px-3 text-sm">Cancel</button>
              <button onClick={voidAgreement} disabled={!voidReason.trim()}
                className="h-9 rounded-md bg-destructive px-4 text-sm font-medium text-destructive-foreground disabled:opacity-50">
                Void
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
