"use client";

import { useQuery } from "@tanstack/react-query";
import { Download, FileText } from "lucide-react";
import { api } from "@/lib/api";
import { Section, EmptyRow } from "@/components/dashboard-bits";
import { money } from "@/lib/contract-types";
import { keys } from "@/lib/query-keys";

type AgreementRow = {
  id: number;
  agreement_number: string;
  template_slug: string;
  start_date: string;
  end_date: string;
  rent_amount: number | null;
  currency: string;
  status: string;
  attachment_id: number | null;
};

const STATUS_TONE: Record<string, string> = {
  generated: "bg-emerald-500/10 text-emerald-600",
  voided: "bg-muted text-muted-foreground line-through",
};

/** The generated-agreement list embedded on a landlord's or client's own
 *  page — the same records also show up in the company-wide /agreements
 *  list and in the plain Documents tab (the .docx is tagged
 *  category="agreement" there too).
 *
 *  Refetches itself via the shared `keys.agreements.all()` cache entry —
 *  any mutation that calls `queryClient.invalidateQueries({ queryKey:
 *  keys.agreements.all() })` (agreement-wizard.tsx's onGenerated, the
 *  void/regenerate/bulk-renew handlers on /agreements) updates every
 *  instance of this component on screen, so no bespoke refresh-counter
 *  prop is needed. */
export function PartyAgreementsList({ entityType, entityId }: {
  entityType: "landlord" | "client"; entityId: number;
}) {
  const listQuery = useQuery({
    queryKey: keys.agreements.list({ entity_type: entityType, entity_id: entityId }),
    queryFn: async () => {
      const r = await api.get("/agreements", { params: { entity_type: entityType, entity_id: entityId } });
      return (r.data?.data ?? []) as AgreementRow[];
    },
  });
  const rows = listQuery.data ?? [];
  const loading = listQuery.isLoading;

  if (loading) return <div className="text-sm text-muted-foreground animate-pulse">Loading agreements…</div>;

  return (
    <Section title={`Generated agreements (${rows.length})`}>
      {rows.length === 0 ? (
        <EmptyRow>No agreements generated yet.</EmptyRow>
      ) : (
        <ul className="divide-y divide-border/60">
          {rows.map((a) => (
            <li key={a.id} className="py-2 flex items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <FileText className="h-4 w-4 text-muted-foreground shrink-0" />
                <div>
                  <div className="font-mono text-xs">{a.agreement_number}</div>
                  <div className="text-[11px] text-muted-foreground">
                    {a.start_date} → {a.end_date}
                    {a.rent_amount != null && ` · ${money(a.rent_amount)} ${a.currency}`}
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <span className={"rounded-full px-2 py-0.5 text-[11px] capitalize " + (STATUS_TONE[a.status] ?? "")}>
                  {a.status}
                </span>
                {a.attachment_id && (
                  <a href={`/api/v1/attachments/${a.attachment_id}/download`} target="_blank" rel="noreferrer"
                    title="Download .docx" className="h-7 w-7 grid place-items-center rounded-md hover:bg-accent">
                    <Download className="h-3.5 w-3.5" />
                  </a>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </Section>
  );
}
