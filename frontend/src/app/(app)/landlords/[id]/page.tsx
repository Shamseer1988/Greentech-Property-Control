"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouteParams } from "@/lib/use-route-params";
import { keys } from "@/lib/query-keys";
import {
  ArrowLeft, Building2, Banknote, FileText, Paperclip, Wallet, Mail,
} from "lucide-react";
import { api } from "@/lib/api";
import { Can } from "@/components/can";
import { ComposeDialog } from "@/components/compose-dialog";
import { AttachmentsTab } from "@/components/attachments-tab";
import { AgreementWizard } from "@/components/agreement-wizard";
import { PartyAgreementsList } from "@/components/party-agreements-list";
import { Stat, Section, EmptyRow, Money, DaysPill } from "@/components/dashboard-bits";
import { inputClass } from "@/components/ui/dialog";
import { money, MODE_LABEL } from "@/lib/contract-types";

type Agreement = {
  agreement_id: number; property_id: number; property_name: string;
  agreement_number: string | null; start_date: string; expiry_date: string;
  days_left: number; monthly_rent: number | null;
  security_deposit: number | null; renewal_status: string;
};

type Data = {
  landlord: { id: number; code: string; name: string; name_ar: string | null;
              phone: string | null; email: string | null; status: string;
              qid_cr_number: string | null; qid_cr_expiry_date: string | null };
  properties: { id: number; code: string; name: string; property_type: string }[];
  agreements: Agreement[];
  monthly_commitment: number;
  total_paid_to_date: number;
  recent_payments: { id: number; voucher_number: string; period_month: string;
                     amount: number; mode: string; reference: string | null }[];
  per_property: { property_id: number; property_name: string;
                  rent_charged: number; rent_paid: number;
                  expense_total: number; profit: number }[];
  month: string;
};

function currentMonth() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export default function LandlordDashboard({ params }: { params: Promise<{ id: string }> }) {
  const { id } = useRouteParams(params);
  const qc = useQueryClient();
  const [month, setMonth] = useState(currentMonth());
  const [tab, setTab] = useState<"overview" | "properties" | "documents">("overview");
  const [composing, setComposing] = useState(false);
  const [showAgreementWizard, setShowAgreementWizard] = useState(false);

  const dataQuery = useQuery({
    queryKey: [...keys.dashboard.landlord(id), month],
    queryFn: async () =>
      (await api.get(`/dashboard/landlord/${id}`, { params: { month: `${month}-01` } })).data.data as Data,
  });
  const data = dataQuery.data ?? null;
  const loading = dataQuery.isLoading;
  const invalidateAgreements = () => qc.invalidateQueries({ queryKey: keys.agreements.all() });

  if (loading) {
    return <div className="text-sm text-muted-foreground animate-pulse">Loading landlord…</div>;
  }
  if (!data) {
    return (
      <div className="glass rounded-xl p-10 text-center space-y-2">
        <div className="font-medium">That landlord could not be loaded.</div>
        <Link href="/landlords" className="text-sm text-primary hover:underline">
          Back to landlords
        </Link>
      </div>
    );
  }

  const l = data.landlord;
  const totalProfit = data.per_property.reduce((s, r) => s + r.profit, 0);

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <Link href="/landlords"
          className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft className="h-3.5 w-3.5" /> Back to landlords
        </Link>
        <div className="mt-2 flex items-start justify-between flex-wrap gap-3">
          <div>
            <h1 className="text-2xl lg:text-3xl font-semibold tracking-tight">{l.name}</h1>
            <div className="text-sm text-muted-foreground flex items-center gap-2 flex-wrap">
              <span className="font-mono">{l.code}</span>
              {l.name_ar && <span dir="rtl">{l.name_ar}</span>}
              {l.phone && <span>· {l.phone}</span>}
              {l.email && <span>· {l.email}</span>}
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
            <input type="month" className={inputClass + " w-auto"} value={month}
              onChange={(e) => setMonth(e.target.value)} />
          </div>
        </div>

      <ComposeDialog open={composing} partyType="landlord" partyId={l.id}
        partyName={l.name} partyEmail={l.email}
        onClose={() => setComposing(false)} />
      <AgreementWizard open={showAgreementWizard} onClose={() => setShowAgreementWizard(false)}
        presetPartyRole="landlord" presetLandlordId={l.id}
        onGenerated={invalidateAgreements} />
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat label="Properties" value={data.properties.length}
          sub={`${data.agreements.length} live agreement(s)`} icon={Building2} />
        <Stat label="Monthly commitment" value={money(data.monthly_commitment)}
          sub="rent we owe each month" icon={Wallet} />
        <Stat label="Paid to date" value={money(data.total_paid_to_date)}
          sub="across all vouchers" icon={Banknote} />
        <Stat label="Margin this month" value={money(totalProfit)}
          sub="their buildings, after costs" icon={FileText}
          tone={totalProfit >= 0 ? "emerald" : "rose"} />
      </div>

      <div className="flex border-b border-border">
        {(["overview", "properties", "documents"] as const).map((key) => (
          <button key={key} onClick={() => setTab(key)}
            className={
              "px-4 py-2 text-sm font-medium border-b-2 transition-colors inline-flex items-center gap-2 " +
              (tab === key ? "border-primary text-primary"
                : "border-transparent text-muted-foreground hover:text-foreground")
            }>
            {key === "overview" ? <FileText className="h-4 w-4" />
              : key === "properties" ? <Building2 className="h-4 w-4" />
              : <Paperclip className="h-4 w-4" />}
            {key === "overview" ? "Overview" : key === "properties" ? "Properties" : "Documents"}
          </button>
        ))}
      </div>

      {tab === "documents" ? (
        <AttachmentsTab entityType="landlord" entityId={l.id} />
      ) : tab === "properties" ? (
        <Section title={`Properties owned (${data.properties.length})`}>
          {data.properties.length === 0 ? (
            <EmptyRow>No properties on file for this landlord.</EmptyRow>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
              {data.properties.map((p) => (
                <Link key={p.id} href={`/properties/${p.id}`}
                  className="glass rounded-xl p-4 hover:bg-accent/30 transition-colors block">
                  <div className="flex items-center gap-2">
                    <div className="h-9 w-9 rounded-lg bg-primary/10 grid place-items-center">
                      <Building2 className="h-4 w-4 text-primary" />
                    </div>
                    <div>
                      <div className="font-medium leading-tight">{p.name}</div>
                      <div className="text-xs text-muted-foreground font-mono">{p.code}</div>
                    </div>
                  </div>
                  <div className="mt-2 text-xs text-muted-foreground capitalize">
                    {(p.property_type ?? "—").replaceAll("_", " ")}
                  </div>
                </Link>
              ))}
            </div>
          )}
        </Section>
      ) : (
        <div className="space-y-4">
          <PartyAgreementsList entityType="landlord" entityId={l.id} />

          <Section title="Agreements">
            {data.agreements.length === 0 ? (
              <EmptyRow>No active agreements.</EmptyRow>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="text-left text-xs text-muted-foreground border-b border-border">
                    <tr>
                      <th className="py-2 pr-3">Property</th>
                      <th className="py-2 pr-3">Agreement</th>
                      <th className="py-2 pr-3">Period</th>
                      <th className="py-2 pr-3 text-right">Monthly rent</th>
                      <th className="py-2 pr-3 text-right">Deposit</th>
                      <th className="py-2 pr-3">Expiry</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.agreements.map((a) => (
                      <tr key={a.agreement_id} className="border-b border-border/60 hover:bg-accent/30">
                        <td className="py-2 pr-3">
                          <Link href={`/properties/${a.property_id}`} className="hover:text-primary">
                            {a.property_name}
                          </Link>
                        </td>
                        <td className="py-2 pr-3 font-mono text-xs">{a.agreement_number ?? "—"}</td>
                        <td className="py-2 pr-3 text-xs text-muted-foreground">
                          {a.start_date} → {a.expiry_date}
                        </td>
                        <td className="py-2 pr-3 text-right">
                          {a.monthly_rent != null ? money(a.monthly_rent) : "—"}
                        </td>
                        <td className="py-2 pr-3 text-right">
                          {a.security_deposit != null ? money(a.security_deposit) : "—"}
                        </td>
                        <td className="py-2 pr-3"><DaysPill days={a.days_left} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Section>

          <Section title={`How their buildings did — ${data.month.slice(0, 7)}`}
            action={<Link href="/pnl" className="text-xs text-muted-foreground hover:text-primary">
              Full P&amp;L →
            </Link>}>
            {data.per_property.length === 0 ? (
              <EmptyRow>No properties on the books.</EmptyRow>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="text-left text-xs text-muted-foreground border-b border-border">
                    <tr>
                      <th className="py-2 pr-3">Property</th>
                      <th className="py-2 pr-3 text-right">Rent charged</th>
                      <th className="py-2 pr-3 text-right">Paid to landlord</th>
                      <th className="py-2 pr-3 text-right">Running costs</th>
                      <th className="py-2 pr-3 text-right">Margin</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.per_property.map((r) => (
                      <tr key={r.property_id} className="border-b border-border/60">
                        <td className="py-2 pr-3">
                          <Link href={`/properties/${r.property_id}`} className="hover:text-primary">
                            {r.property_name}
                          </Link>
                        </td>
                        <td className="py-2 pr-3 text-right">{money(r.rent_charged)}</td>
                        <td className="py-2 pr-3 text-right">{money(r.rent_paid)}</td>
                        <td className="py-2 pr-3 text-right">{money(r.expense_total)}</td>
                        <td className="py-2 pr-3 text-right font-semibold">
                          <Money value={r.profit} signed />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Section>

          <Section title="Recent payments">
            {data.recent_payments.length === 0 ? (
              <EmptyRow>No payment vouchers yet.</EmptyRow>
            ) : (
              <ul className="divide-y divide-border/60">
                {data.recent_payments.slice().reverse().map((p) => (
                  <li key={p.id} className="py-2 flex items-center justify-between gap-3">
                    <div>
                      <div className="font-mono text-xs">{p.voucher_number}</div>
                      <div className="text-[11px] text-muted-foreground">
                        {String(p.period_month).slice(0, 7)} · {MODE_LABEL[p.mode] ?? p.mode}
                        {p.reference && ` · ${p.reference}`}
                      </div>
                    </div>
                    <Money value={p.amount} />
                  </li>
                ))}
              </ul>
            )}
          </Section>
        </div>
      )}
    </div>
  );
}
