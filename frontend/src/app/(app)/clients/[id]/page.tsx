"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouteParams } from "@/lib/use-route-params";
import { keys } from "@/lib/query-keys";
import {
  ArrowLeft, FileText, Banknote, AlertTriangle, Paperclip, Mail,
  Receipt as ReceiptIcon,
} from "lucide-react";
import { api } from "@/lib/api";
import { Can } from "@/components/can";
import { ComposeDialog } from "@/components/compose-dialog";
import { AttachmentsTab } from "@/components/attachments-tab";
import { AgreementWizard } from "@/components/agreement-wizard";
import { PartyAgreementsList } from "@/components/party-agreements-list";
import { Stat, Section, EmptyRow, Money, DaysPill } from "@/components/dashboard-bits";
import { money, STATUS_TONE, MODE_LABEL, CHEQUE_TONE } from "@/lib/contract-types";

type ContractRow = {
  contract_id: number; contract_number: string;
  property_id: number; property_name: string;
  status: string; payment_mode: string; monthly_rent: number;
  start_date: string; expiry_date: string; days_left: number;
  units: string[];
};

type Data = {
  client: { id: number; code: string; name: string; name_ar: string | null;
            client_type: string | null; status: string;
            phone: string | null; email: string | null;
            qid_cr_number: string | null; qid_cr_expiry_date: string | null };
  contracts: ContractRow[];
  active_contracts: number;
  outstanding: number;
  ageing: { months: Record<string, number>; older: number; total: number } | null;
  recent_receipts: { id: number; receipt_number: string; receipt_date: string;
                     amount: number; mode: string; status: string }[];
  cheques: { id: number; cheque_number: string; cheque_date: string;
             amount: number; status: string; is_security: boolean }[];
  month: string;
};

export default function ClientDashboard({ params }: { params: Promise<{ id: string }> }) {
  const { id } = useRouteParams(params);
  const qc = useQueryClient();
  const [tab, setTab] = useState<"overview" | "documents">("overview");
  const [composing, setComposing] = useState(false);
  const [showAgreementWizard, setShowAgreementWizard] = useState(false);

  const dataQuery = useQuery({
    queryKey: keys.dashboard.client(id),
    queryFn: async () => (await api.get(`/dashboard/client/${id}`)).data.data as Data,
  });
  const data = dataQuery.data ?? null;
  const loading = dataQuery.isLoading;
  const invalidateAgreements = () => qc.invalidateQueries({ queryKey: keys.agreements.all() });

  if (loading) {
    return <div className="text-sm text-muted-foreground animate-pulse">Loading client…</div>;
  }
  if (!data) {
    return (
      <div className="glass rounded-xl p-10 text-center space-y-2">
        <div className="font-medium">That client could not be loaded.</div>
        <Link href="/clients" className="text-sm text-primary hover:underline">
          Back to clients
        </Link>
      </div>
    );
  }

  const c = data.client;
  const ageMonths = data.ageing?.months ?? {};

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <Link href="/clients"
          className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft className="h-3.5 w-3.5" /> Back to clients
        </Link>
        <div className="mt-2 flex items-start justify-between flex-wrap gap-3">
          <div>
            <h1 className="text-2xl lg:text-3xl font-semibold tracking-tight">{c.name}</h1>
            <div className="text-sm text-muted-foreground flex items-center gap-2 flex-wrap">
              <span className="font-mono">{c.code}</span>
              {c.name_ar && <span dir="rtl">{c.name_ar}</span>}
              {c.phone && <span>· {c.phone}</span>}
              {c.email && <span>· {c.email}</span>}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Can perm="agreement.create">
              <button onClick={() => setShowAgreementWizard(true)}
                className="h-9 inline-flex items-center gap-2 rounded-md border border-border bg-card/60 px-3 text-sm hover:bg-accent">
                <FileText className="h-4 w-4" /> Generate Agreement
              </button>
            </Can>
            <Can perm="notification.send">
              <button onClick={() => setComposing(true)}
                className="h-9 inline-flex items-center gap-2 rounded-md border border-border bg-card/60 px-3 text-sm hover:bg-accent">
                <Mail className="h-4 w-4" /> Email
              </button>
            </Can>
            <span className={"rounded-full px-2.5 py-1 text-xs " +
              (STATUS_TONE[c.status] ?? "bg-muted text-muted-foreground")}>
              {c.status}
            </span>
          </div>
        </div>
      </div>

      <ComposeDialog open={composing} partyType="client" partyId={c.id}
        partyName={c.name} partyEmail={c.email}
        contractId={data.contracts.find((r) => r.status === "active")?.contract_id}
        onClose={() => setComposing(false)} />
      <AgreementWizard open={showAgreementWizard} onClose={() => setShowAgreementWizard(false)}
        presetPartyRole="client" presetClientId={c.id}
        onGenerated={invalidateAgreements} />

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat label="Active contracts" value={data.active_contracts}
          sub={`${data.contracts.length} in total`} icon={FileText} />
        <Stat label="Outstanding" value={money(data.outstanding)}
          sub={data.outstanding > 0 ? "unpaid rent" : "fully settled"}
          icon={AlertTriangle}
          tone={data.outstanding > 0 ? "rose" : "emerald"}
          href={`/collections/${c.id}`} />
        <Stat label="Monthly rent"
          value={money(data.contracts
            .filter((r) => r.status === "active")
            .reduce((s, r) => s + r.monthly_rent, 0))}
          sub="across active contracts" icon={Banknote} />
        <Stat label="Cheques on hand" value={data.cheques.length}
          sub={money(data.cheques.reduce((s, r) => s + r.amount, 0))}
          icon={ReceiptIcon} />
      </div>

      <div className="flex border-b border-border">
        {(["overview", "documents"] as const).map((key) => (
          <button key={key} onClick={() => setTab(key)}
            className={
              "px-4 py-2 text-sm font-medium border-b-2 transition-colors inline-flex items-center gap-2 " +
              (tab === key ? "border-primary text-primary"
                : "border-transparent text-muted-foreground hover:text-foreground")
            }>
            {key === "overview" ? <FileText className="h-4 w-4" /> : <Paperclip className="h-4 w-4" />}
            {key === "overview" ? "Overview" : "Documents"}
          </button>
        ))}
      </div>

      {tab === "documents" ? (
        <AttachmentsTab entityType="client" entityId={c.id} />
      ) : (
        <div className="space-y-4">
          <PartyAgreementsList entityType="client" entityId={c.id} />

          <Section title="Contracts">
            {data.contracts.length === 0 ? (
              <EmptyRow>No contracts yet.</EmptyRow>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="text-left text-xs text-muted-foreground border-b border-border">
                    <tr>
                      <th className="py-2 pr-3">Contract</th>
                      <th className="py-2 pr-3">Property</th>
                      <th className="py-2 pr-3">Units</th>
                      <th className="py-2 pr-3">Mode</th>
                      <th className="py-2 pr-3 text-right">Monthly rent</th>
                      <th className="py-2 pr-3">Expiry</th>
                      <th className="py-2 pr-3">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.contracts.map((r) => (
                      <tr key={r.contract_id} className="border-b border-border/60 hover:bg-accent/30">
                        <td className="py-2 pr-3">
                          <Link href={`/contracts/${r.contract_id}`}
                            className="font-mono text-xs hover:text-primary">
                            {r.contract_number}
                          </Link>
                        </td>
                        <td className="py-2 pr-3">
                          <Link href={`/properties/${r.property_id}`} className="hover:text-primary">
                            {r.property_name}
                          </Link>
                        </td>
                        <td className="py-2 pr-3 font-mono text-xs">
                          {r.units.length ? r.units.join(", ") : "—"}
                        </td>
                        <td className="py-2 pr-3">{MODE_LABEL[r.payment_mode] ?? r.payment_mode}</td>
                        <td className="py-2 pr-3 text-right">{money(r.monthly_rent)}</td>
                        <td className="py-2 pr-3">
                          <div className="text-xs">{r.expiry_date}</div>
                          {r.status === "active" && <DaysPill days={r.days_left} />}
                        </td>
                        <td className="py-2 pr-3">
                          <span className={"rounded-full px-2 py-0.5 text-xs " +
                            (STATUS_TONE[r.status] ?? "bg-muted text-muted-foreground")}>
                            {r.status}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Section>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <Section title="Ageing"
              action={<Link href={`/collections/${c.id}`}
                className="text-xs text-muted-foreground hover:text-primary">Statement →</Link>}>
              {!data.ageing || data.ageing.total === 0 ? (
                <EmptyRow>Nothing outstanding.</EmptyRow>
              ) : (
                <div className="space-y-1">
                  {data.ageing.older > 0 && (
                    <Line label="Older" value={data.ageing.older} />
                  )}
                  {Object.entries(ageMonths)
                    .sort(([a], [b]) => a.localeCompare(b))
                    .map(([m, v]) => <Line key={m} label={m.slice(0, 7)} value={v} />)}
                  <div className="flex justify-between pt-2 border-t border-border text-sm font-semibold">
                    <span>Total due</span>
                    <span className="text-rose-600">{money(data.ageing.total)}</span>
                  </div>
                </div>
              )}
            </Section>

            <Section title="Recent receipts">
              {data.recent_receipts.length === 0 ? (
                <EmptyRow>No receipts recorded.</EmptyRow>
              ) : (
                <ul className="divide-y divide-border/60">
                  {data.recent_receipts.map((r) => (
                    <li key={r.id} className="py-2 flex items-center justify-between gap-3">
                      <div>
                        <div className="font-mono text-xs">{r.receipt_number}</div>
                        <div className="text-[11px] text-muted-foreground">
                          {r.receipt_date} · {MODE_LABEL[r.mode] ?? r.mode}
                        </div>
                      </div>
                      <Money value={r.amount} />
                    </li>
                  ))}
                </ul>
              )}
            </Section>
          </div>

          {data.cheques.length > 0 && (
            <Section title="Cheques on hand">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="text-left text-xs text-muted-foreground border-b border-border">
                    <tr>
                      <th className="py-2 pr-3">Cheque</th>
                      <th className="py-2 pr-3">Date</th>
                      <th className="py-2 pr-3 text-right">Amount</th>
                      <th className="py-2 pr-3">Type</th>
                      <th className="py-2 pr-3">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.cheques.map((q) => (
                      <tr key={q.id} className="border-b border-border/60">
                        <td className="py-2 pr-3 font-mono text-xs">{q.cheque_number}</td>
                        <td className="py-2 pr-3 text-xs">{q.cheque_date}</td>
                        <td className="py-2 pr-3 text-right">{money(q.amount)}</td>
                        <td className="py-2 pr-3 text-xs">
                          {q.is_security ? "Security" : "Rent"}
                        </td>
                        <td className="py-2 pr-3">
                          <span className={"rounded-full px-2 py-0.5 text-xs " +
                            (CHEQUE_TONE[q.status] ?? "bg-muted text-muted-foreground")}>
                            {q.status}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Section>
          )}
        </div>
      )}
    </div>
  );
}

function Line({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex justify-between text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span>{money(value)}</span>
    </div>
  );
}
