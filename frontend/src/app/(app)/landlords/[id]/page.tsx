"use client";

import { useMemo, useState, use } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouteParams } from "@/lib/use-route-params";
import { keys } from "@/lib/query-keys";
import {
  ArrowLeft, Building2, Banknote, FileText, Paperclip, Wallet, Mail,
  LayoutDashboard, BarChart3, ChevronLeft, ChevronRight, Search,
  CalendarDays, Pencil, X, Check, AlertTriangle,
} from "lucide-react";
import { selectClass } from "@/components/ui/dialog";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
  AreaChart, Area, Legend,
} from "recharts";
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

type TabKey = "overview" | "properties" | "documents" | "monthly_rent" | "reports" | "dashboard";

const TABS: { key: TabKey; label: string; icon: typeof FileText }[] = [
  { key: "overview", label: "Overview", icon: FileText },
  { key: "properties", label: "Properties", icon: Building2 },
  { key: "documents", label: "Documents", icon: Paperclip },
  { key: "monthly_rent", label: "Monthly Rent", icon: CalendarDays },
  { key: "reports", label: "Reports", icon: BarChart3 },
  { key: "dashboard", label: "Dashboard", icon: LayoutDashboard },
];

function currentMonth() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export default function LandlordDashboard(props: { params: Promise<{ id: string }> }) {
  const params = use(props.params);
  const { id } = useRouteParams(params);
  const qc = useQueryClient();
  const [month, setMonth] = useState(currentMonth());
  const [tab, setTab] = useState<TabKey>("overview");
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
          <div className="flex items-center gap-2 flex-wrap">
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
            <span className={"rounded-full px-2.5 py-1 text-xs " +
              (l.status === "active" ? "bg-emerald-500/10 text-emerald-600" : "bg-muted text-muted-foreground")}>
              {l.status}
            </span>
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

      <div className="flex border-b border-border overflow-x-auto">
        {TABS.map(({ key, label, icon: Icon }) => (
          <button key={key} onClick={() => setTab(key)}
            className={
              "px-4 py-2 text-sm font-medium border-b-2 transition-colors inline-flex items-center gap-2 whitespace-nowrap " +
              (tab === key ? "border-primary text-primary"
                : "border-transparent text-muted-foreground hover:text-foreground")
            }>
            <Icon className="h-4 w-4" /> {label}
          </button>
        ))}
      </div>

      {tab === "documents" && <AttachmentsTab entityType="landlord" entityId={l.id} />}
      {tab === "properties" && <LandlordPropertiesTab data={data} />}
      {tab === "overview" && <LandlordOverviewTab data={data} />}
      {tab === "monthly_rent" && <LandlordMonthlyRentTab landlordId={l.id} properties={data.properties} />}
      {tab === "reports" && <LandlordReportsTab data={data} />}
      {tab === "dashboard" && <LandlordDashboardTab data={data} landlordId={l.id} />}
    </div>
  );
}

function LandlordPropertiesTab({ data }: { data: Data }) {
  return (
    <Section title={`Properties owned (${data.properties.length})`}>
      {data.properties.length === 0 ? (
        <EmptyRow>No properties on file for this landlord.</EmptyRow>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
          {data.properties.map((p) => (
            <Link key={p.id} href={`/properties/${p.id}`}
              className="glass rounded-xl p-4 hover:bg-accent/30 transition-colors block">
              <div className="flex items-center gap-2">
                <div className="h-9 w-9 rounded-lg bg-primary/10 flex items-center justify-center">
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
  );
}

function LandlordOverviewTab({ data }: { data: Data }) {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      {/* LEFT COLUMN */}
      <div className="space-y-4">
        <PartyAgreementsList entityType="landlord" entityId={data.landlord.id} />

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
                    <th className="py-2 pr-3 text-right">Monthly rent</th>
                    <th className="py-2 pr-3 text-right">Deposit</th>
                    <th className="py-2 pr-3">Expiry</th>
                  </tr>
                </thead>
                <tbody>
                  {data.agreements.map((a) => (
                    <tr key={a.agreement_id} className="border-b border-border/60 hover:bg-accent/30">
                      <td className="py-2 pr-3">
                        <Link href={`/properties/${a.property_id}`} className="hover:text-primary text-xs">
                          {a.property_name}
                        </Link>
                      </td>
                      <td className="py-2 pr-3 font-mono text-xs">{a.agreement_number ?? "—"}</td>
                      <td className="py-2 pr-3 text-right text-xs">
                        {a.monthly_rent != null ? money(a.monthly_rent) : "—"}
                      </td>
                      <td className="py-2 pr-3 text-right text-xs">
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

        <Section title={`P&L — ${data.month.slice(0, 7)}`}
          action={<Link href="/pnl" className="text-xs text-muted-foreground hover:text-primary">Full P&L →</Link>}>
          {data.per_property.length === 0 ? (
            <EmptyRow>No properties on the books.</EmptyRow>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-left text-xs text-muted-foreground border-b border-border">
                  <tr>
                    <th className="py-2 pr-3">Property</th>
                    <th className="py-2 pr-3 text-right">Charged</th>
                    <th className="py-2 pr-3 text-right">Paid</th>
                    <th className="py-2 pr-3 text-right">Costs</th>
                    <th className="py-2 pr-3 text-right">Margin</th>
                  </tr>
                </thead>
                <tbody>
                  {data.per_property.map((r) => (
                    <tr key={r.property_id} className="border-b border-border/60">
                      <td className="py-1.5 pr-3 text-xs">
                        <Link href={`/properties/${r.property_id}`} className="hover:text-primary">
                          {r.property_name}
                        </Link>
                      </td>
                      <td className="py-1.5 pr-3 text-right text-xs">{money(r.rent_charged)}</td>
                      <td className="py-1.5 pr-3 text-right text-xs">{money(r.rent_paid)}</td>
                      <td className="py-1.5 pr-3 text-right text-xs">{money(r.expense_total)}</td>
                      <td className="py-1.5 pr-3 text-right text-xs font-semibold">
                        <Money value={r.profit} signed />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Section>
      </div>

      {/* RIGHT COLUMN */}
      <div className="space-y-4">
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

        <div className="glass rounded-xl p-4 space-y-3">
          <div className="text-sm font-semibold">Landlord profile</div>
          <div className="grid grid-cols-2 gap-2 text-xs">
            <div>
              <div className="text-muted-foreground">QID / CR</div>
              <div className="font-mono">{data.landlord.qid_cr_number ?? "—"}</div>
            </div>
            <div>
              <div className="text-muted-foreground">Status</div>
              <div className="capitalize font-medium">{data.landlord.status}</div>
            </div>
            {data.landlord.qid_cr_expiry_date && (
              <div className="col-span-2">
                <div className="text-muted-foreground">QID / CR expiry</div>
                <div className="font-mono">{data.landlord.qid_cr_expiry_date}</div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function LandlordDashboardTab({ data, landlordId }: { data: Data; landlordId: number }) {
  const totalProfit = data.per_property.reduce((s, r) => s + r.profit, 0);
  const totalCharged = data.per_property.reduce((s, r) => s + r.rent_charged, 0);

  const pnlChartData = useMemo(() =>
    data.per_property.map((r) => ({
      name: r.property_name.length > 14 ? r.property_name.slice(0, 14) + "…" : r.property_name,
      "Charged": r.rent_charged,
      "Paid to landlord": r.rent_paid,
      "Costs": r.expense_total,
      "Margin": r.profit,
    })),
  [data.per_property]);

  const paymentChartData = useMemo(() =>
    [...data.recent_payments]
      .reverse()
      .slice(-12)
      .map((p) => ({ month: String(p.period_month).slice(0, 7), Amount: p.amount })),
  [data.recent_payments]);

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <div className="glass rounded-xl p-4 flex flex-col items-center justify-center text-center">
          <div className="text-xs text-muted-foreground mb-1">Properties</div>
          <div className="text-4xl font-bold text-primary">{data.properties.length}</div>
          <div className="text-xs text-muted-foreground mt-1">{data.agreements.length} live agreement(s)</div>
        </div>
        <div className="glass rounded-xl p-4 flex flex-col items-center justify-center text-center">
          <div className="text-xs text-muted-foreground mb-1">Monthly commitment</div>
          <div className="text-3xl font-bold text-rose-500">{money(data.monthly_commitment)}</div>
          <div className="text-xs text-muted-foreground mt-1">rent owed to landlord</div>
        </div>
        <div className="glass rounded-xl p-4 flex flex-col items-center justify-center text-center">
          <div className="text-xs text-muted-foreground mb-1">Margin this month</div>
          <div className={"text-3xl font-bold " + (totalProfit >= 0 ? "text-emerald-600" : "text-rose-600")}>
            {money(totalProfit)}
          </div>
          {totalCharged > 0 && (
            <div className="text-xs text-muted-foreground mt-1">
              {Math.round((totalProfit / totalCharged) * 100)}% of rent charged
            </div>
          )}
        </div>
      </div>

      {pnlChartData.length > 0 && (
        <div className="glass rounded-xl p-4">
          <div className="text-sm font-semibold mb-4">P&L by property — {data.month.slice(0, 7)}</div>
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={pnlChartData} margin={{ top: 0, right: 0, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" className="stroke-border/30" />
              <XAxis dataKey="name" tick={{ fontSize: 10 }} />
              <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => v.toLocaleString()} />
              <Tooltip formatter={(v: number) => money(v)} />
              <Legend />
              <Bar dataKey="Charged" fill="#6366f1" radius={[2, 2, 0, 0]} />
              <Bar dataKey="Paid to landlord" fill="#ef4444" radius={[2, 2, 0, 0]} />
              <Bar dataKey="Margin" fill="#10b981" radius={[2, 2, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {paymentChartData.length > 1 && (
        <div className="glass rounded-xl p-4">
          <div className="text-sm font-semibold mb-4">Payment history (last 12 vouchers)</div>
          <ResponsiveContainer width="100%" height={180}>
            <AreaChart data={paymentChartData} margin={{ top: 0, right: 0, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" className="stroke-border/30" />
              <XAxis dataKey="month" tick={{ fontSize: 10 }} />
              <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => v.toLocaleString()} />
              <Tooltip formatter={(v: number) => money(v)} />
              <Area type="monotone" dataKey="Amount" fill="#6366f1" stroke="#6366f1" fillOpacity={0.15} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}

      {data.agreements.length > 0 && (
        <div className="glass rounded-xl p-4">
          <div className="text-sm font-semibold mb-3">Agreement pipeline</div>
          <div className="flex flex-wrap gap-2">
            {(["expiring_soon", "active", "expired"] as const).map((status) => {
              const items = data.agreements.filter((a) =>
                status === "expiring_soon" ? a.days_left <= 90 && a.days_left > 0
                : status === "active" ? a.days_left > 90
                : a.days_left <= 0
              );
              if (items.length === 0) return null;
              return (
                <div key={status} className={"glass rounded-lg px-3 py-2 text-center " + (
                  status === "expiring_soon" ? "bg-amber-500/10 text-amber-600"
                  : status === "expired" ? "bg-rose-500/10 text-rose-600"
                  : "bg-emerald-500/10 text-emerald-600")}>
                  <div className="text-lg font-semibold">{items.length}</div>
                  <div className="text-xs capitalize">{status.replaceAll("_", " ")}</div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

const PAYMENTS_PAGE_SIZE = 15;

function LandlordReportsTab({ data }: { data: Data }) {
  const [q, setQ] = useState("");
  const [page, setPage] = useState(0);

  const filteredPayments = useMemo(() => {
    const lq = q.toLowerCase();
    return lq
      ? data.recent_payments.filter((p) =>
          p.voucher_number.toLowerCase().includes(lq) ||
          String(p.period_month).includes(lq) ||
          (MODE_LABEL[p.mode] ?? p.mode).toLowerCase().includes(lq) ||
          (p.reference ?? "").toLowerCase().includes(lq))
      : data.recent_payments;
  }, [data.recent_payments, q]);

  const sorted = useMemo(() => [...filteredPayments].reverse(), [filteredPayments]);
  const paged = sorted.slice(page * PAYMENTS_PAGE_SIZE, (page + 1) * PAYMENTS_PAGE_SIZE);
  const pageCount = Math.max(1, Math.ceil(sorted.length / PAYMENTS_PAGE_SIZE));

  const totalPaid = data.recent_payments.reduce((s, p) => s + p.amount, 0);
  const totalCharged = data.per_property.reduce((s, r) => s + r.rent_charged, 0);
  const totalProfit = data.per_property.reduce((s, r) => s + r.profit, 0);

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Section title="Financial summary">
          <div className="space-y-2">
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">Total paid to landlord</span>
              <span className="font-semibold text-rose-600">{money(totalPaid)}</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">Rent charged to tenants</span>
              <span className="font-semibold">{money(totalCharged)}</span>
            </div>
            <div className="flex justify-between text-sm border-t border-border pt-2">
              <span className="text-muted-foreground">Margin (this month)</span>
              <span className={"font-semibold " + (totalProfit >= 0 ? "text-emerald-600" : "text-rose-600")}>
                {money(totalProfit)}
              </span>
            </div>
          </div>
        </Section>

        <Section title={`P&L breakdown — ${data.month.slice(0, 7)}`}
          action={<Link href="/pnl" className="text-xs text-muted-foreground hover:text-primary">Full P&L →</Link>}>
          {data.per_property.length === 0 ? (
            <EmptyRow>No properties this month.</EmptyRow>
          ) : (
            <div className="space-y-2">
              {data.per_property.map((r) => (
                <div key={r.property_id} className="flex items-center justify-between gap-2 py-1 border-b border-border/40 last:border-0">
                  <Link href={`/properties/${r.property_id}`} className="text-xs hover:text-primary truncate">
                    {r.property_name}
                  </Link>
                  <div className="flex items-center gap-3 shrink-0 text-xs">
                    <span className="text-muted-foreground">charged {money(r.rent_charged)}</span>
                    <span className={"font-semibold " + (r.profit >= 0 ? "text-emerald-600" : "text-rose-600")}>
                      {money(r.profit)}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Section>
      </div>

      <Section title="Payment voucher history">
        <div className="flex items-center gap-2 mb-3">
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground pointer-events-none" />
            <input value={q} onChange={(e) => { setQ(e.target.value); setPage(0); }}
              placeholder="Search vouchers…"
              className="h-8 pl-8 pr-3 w-48 rounded-md border border-input bg-card/60 text-sm" />
          </div>
        </div>
        {data.recent_payments.length === 0 ? (
          <EmptyRow>No payment vouchers on record.</EmptyRow>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-left text-xs text-muted-foreground border-b border-border">
                  <tr>
                    <th className="py-2 pr-3">Voucher #</th>
                    <th className="py-2 pr-3">Period</th>
                    <th className="py-2 pr-3">Mode</th>
                    <th className="py-2 pr-3">Reference</th>
                    <th className="py-2 pr-3 text-right">Amount</th>
                  </tr>
                </thead>
                <tbody>
                  {paged.length === 0 ? (
                    <tr><td colSpan={5} className="py-6 text-center text-muted-foreground">No results.</td></tr>
                  ) : paged.map((p) => (
                    <tr key={p.id} className="border-b border-border/60 hover:bg-accent/30">
                      <td className="py-1.5 pr-3 font-mono text-xs">{p.voucher_number}</td>
                      <td className="py-1.5 pr-3 text-xs">{String(p.period_month).slice(0, 7)}</td>
                      <td className="py-1.5 pr-3 text-xs">{MODE_LABEL[p.mode] ?? p.mode}</td>
                      <td className="py-1.5 pr-3 text-xs text-muted-foreground">{p.reference ?? "—"}</td>
                      <td className="py-1.5 pr-3 text-right text-xs font-medium">{money(p.amount)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {sorted.length > PAYMENTS_PAGE_SIZE && (
              <div className="flex items-center justify-between text-xs text-muted-foreground pt-2">
                <span>{sorted.length} vouchers · page {page + 1} of {pageCount}</span>
                <div className="flex items-center gap-1">
                  <button onClick={() => setPage((p) => Math.max(0, p - 1))} disabled={page === 0}
                    className="h-7 w-7 inline-flex items-center justify-center rounded-md border border-border hover:bg-accent disabled:opacity-40">
                    <ChevronLeft className="h-3.5 w-3.5" />
                  </button>
                  <button onClick={() => setPage((p) => Math.min(pageCount - 1, p + 1))} disabled={page >= pageCount - 1}
                    className="h-7 w-7 inline-flex items-center justify-center rounded-md border border-border hover:bg-accent disabled:opacity-40">
                    <ChevronRight className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </Section>
    </div>
  );
}

// ─── Landlord Monthly Rent Tab ────────────────────────────────────────────────

type LandlordCharge = {
  id: number; period_month: string; amount: number; allocated: number;
  outstanding: number; status: string; is_free_month: boolean;
  remarks: string | null; property_id: number;
  property?: { name?: string; code?: string };
  contract_number?: string;
};

type LAmendForm = {
  chargeId: number; newAmount: string; isFreeMonth: boolean; remarks: string; saving: boolean; error: string | null;
};

function lMonthLabel(yyyyMmDd: string) {
  const d = new Date(yyyyMmDd + (yyyyMmDd.length === 7 ? "-01" : ""));
  return d.toLocaleDateString("en-GB", { month: "short", year: "2-digit" });
}

const L_STATUS_CLS: Record<string, string> = {
  open: "bg-rose-500/10 text-rose-600",
  part_paid: "bg-amber-500/10 text-amber-600",
  paid: "bg-emerald-500/10 text-emerald-600",
  cancelled: "bg-muted text-muted-foreground",
};

function LandlordMonthlyRentTab({
  landlordId,
  properties,
}: {
  landlordId: number;
  properties: { id: number; code: string; name: string }[];
}) {
  const [charges, setCharges] = useState<LandlordCharge[]>([]);
  const [loading, setLoading] = useState(true);
  const [filterProp, setFilterProp] = useState("");
  const [filterStatus, setFilterStatus] = useState("");
  const [amend, setAmend] = useState<LAmendForm | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      const params: Record<string, string | number> = { landlord_id: landlordId };
      if (filterProp) params.property_id = filterProp;
      const res = await api.get("/rent/landlord-charges", { params });
      setCharges(Array.isArray(res.data?.data) ? res.data.data : []);
    } finally { setLoading(false); }
  };

  useMemo(() => { load(); }, [landlordId]); // eslint-disable-line react-hooks/exhaustive-deps

  const filtered = useMemo(() => {
    let rows = charges;
    if (filterProp) rows = rows.filter((c) => String(c.property_id) === filterProp);
    if (filterStatus) rows = rows.filter((c) => c.status === filterStatus);
    return rows;
  }, [charges, filterProp, filterStatus]);

  const openAmend = (c: LandlordCharge) => {
    setAmend({
      chargeId: c.id,
      newAmount: String(c.amount),
      isFreeMonth: c.is_free_month,
      remarks: c.remarks ?? "",
      saving: false,
      error: null,
    });
  };

  const saveAmend = async () => {
    if (!amend) return;
    setAmend({ ...amend, saving: true, error: null });
    try {
      await api.patch(`/rent/landlord-charges/${amend.chargeId}`, {
        new_amount: amend.isFreeMonth ? 0 : parseFloat(amend.newAmount || "0"),
        is_free_month: amend.isFreeMonth,
        remarks: amend.remarks,
      });
      setAmend(null);
      await load();
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { message?: string } } })?.response?.data?.message ?? "Save failed";
      setAmend({ ...amend, saving: false, error: msg });
    }
  };

  return (
    <div className="space-y-4">
      <div className="glass rounded-xl p-4">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div>
            <h2 className="font-semibold">Monthly Landlord Charges</h2>
            <p className="text-xs text-muted-foreground">Grant free months or discounts — amend a single month's charge per property.</p>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <select value={filterProp} onChange={(e) => setFilterProp(e.target.value)}
              className={selectClass + " !w-auto"}>
              <option value="">All properties</option>
              {properties.map((p) => (
                <option key={p.id} value={String(p.id)}>{p.name}</option>
              ))}
            </select>
            <select value={filterStatus} onChange={(e) => setFilterStatus(e.target.value)}
              className={selectClass + " !w-auto"}>
              <option value="">All status</option>
              <option value="open">Open</option>
              <option value="part_paid">Part paid</option>
              <option value="paid">Paid</option>
              <option value="cancelled">Cancelled</option>
            </select>
            <button onClick={load} disabled={loading}
              className="h-9 px-3 rounded-md border border-border bg-card/60 text-sm hover:bg-accent disabled:opacity-60">
              Refresh
            </button>
          </div>
        </div>
      </div>

      {loading ? (
        <div className="text-sm text-muted-foreground animate-pulse py-8 text-center">Loading charges…</div>
      ) : filtered.length === 0 ? (
        <div className="glass rounded-xl p-8 text-center text-sm text-muted-foreground">
          No landlord charges found. Generate the dues schedule first.
        </div>
      ) : (
        <div className="glass rounded-xl overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-xs text-muted-foreground border-b border-border bg-muted/30">
                <tr>
                  <th className="px-4 py-2.5">Month</th>
                  <th className="px-4 py-2.5">Property</th>
                  <th className="px-4 py-2.5">Contract</th>
                  <th className="px-4 py-2.5 text-right">Amount</th>
                  <th className="px-4 py-2.5 text-right">Paid</th>
                  <th className="px-4 py-2.5 text-right">Outstanding</th>
                  <th className="px-4 py-2.5">Status</th>
                  <th className="px-4 py-2.5">Note</th>
                  <th className="px-4 py-2.5">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {filtered.map((c) => (
                  <>
                    <tr key={c.id}
                      className={"hover:bg-accent/30 transition-colors " + (c.is_free_month ? "bg-emerald-500/5" : "")}>
                      <td className="px-4 py-2.5 font-mono font-medium">
                        {lMonthLabel(c.period_month)}
                        {c.is_free_month && (
                          <span className="ml-1.5 text-xs bg-emerald-500/10 text-emerald-600 rounded px-1">Free</span>
                        )}
                      </td>
                      <td className="px-4 py-2.5 text-sm">
                        <div className="font-medium leading-tight">{c.property?.name ?? `#${c.property_id}`}</div>
                        <div className="text-xs text-muted-foreground font-mono">{c.property?.code}</div>
                      </td>
                      <td className="px-4 py-2.5 text-muted-foreground font-mono text-xs">
                        {c.contract_number ?? "—"}
                      </td>
                      <td className="px-4 py-2.5 text-right font-semibold">{money(c.amount)}</td>
                      <td className="px-4 py-2.5 text-right text-emerald-600">{money(c.allocated)}</td>
                      <td className={"px-4 py-2.5 text-right font-semibold " + (c.outstanding > 0 ? "text-rose-600" : "")}>
                        {money(c.outstanding)}
                      </td>
                      <td className="px-4 py-2.5">
                        <span className={"rounded-full px-2 py-0.5 text-xs " + (L_STATUS_CLS[c.status] ?? "bg-muted text-muted-foreground")}>
                          {c.status.replace("_", " ")}
                        </span>
                      </td>
                      <td className="px-4 py-2.5 text-xs text-muted-foreground max-w-[140px] truncate">
                        {c.remarks ?? "—"}
                      </td>
                      <td className="px-4 py-2.5">
                        <Can perm="property.amend">
                          {c.status !== "paid" && (
                            <button onClick={() => openAmend(c)}
                              className="h-7 px-2 inline-flex items-center gap-1 rounded-md border border-border bg-card/60 text-xs hover:bg-accent">
                              <Pencil className="h-3 w-3" /> Amend
                            </button>
                          )}
                        </Can>
                      </td>
                    </tr>
                    {amend?.chargeId === c.id && (
                      <tr key={`amend-${c.id}`} className="bg-amber-500/5">
                        <td colSpan={9} className="px-4 py-3">
                          <div className="flex items-start gap-3 flex-wrap">
                            <div className="text-xs font-medium text-muted-foreground pt-2 min-w-[100px]">
                              Amend {lMonthLabel(c.period_month)}
                              <div className="text-[10px]">{c.property?.name}</div>
                            </div>

                            <label className="flex items-center gap-2 text-sm pt-1.5 cursor-pointer">
                              <input type="checkbox" checked={amend.isFreeMonth}
                                onChange={(e) => setAmend({ ...amend, isFreeMonth: e.target.checked, newAmount: e.target.checked ? "0" : String(c.amount) })}
                                className="rounded" />
                              Free month (set to 0)
                            </label>

                            <div className="flex items-center gap-1">
                              <label className="text-xs text-muted-foreground">New amount</label>
                              <input type="number" min="0" step="0.01"
                                value={amend.newAmount}
                                disabled={amend.isFreeMonth}
                                onChange={(e) => setAmend({ ...amend, newAmount: e.target.value })}
                                className={inputClass + " w-32 disabled:opacity-50"} />
                            </div>

                            <div className="flex items-center gap-1 flex-1 min-w-[200px]">
                              <label className="text-xs text-muted-foreground whitespace-nowrap">Reason</label>
                              <input type="text" placeholder="Reason (e.g. discount agreed with landlord)…"
                                value={amend.remarks}
                                onChange={(e) => setAmend({ ...amend, remarks: e.target.value })}
                                className={inputClass + " flex-1"} />
                            </div>

                            <div className="flex items-center gap-1 pt-0.5">
                              <button onClick={saveAmend} disabled={amend.saving}
                                className="h-8 px-3 inline-flex items-center gap-1.5 rounded-md bg-primary text-primary-foreground text-xs hover:bg-primary/90 disabled:opacity-60">
                                <Check className="h-3 w-3" /> {amend.saving ? "Saving…" : "Save"}
                              </button>
                              <button onClick={() => setAmend(null)}
                                className="h-8 px-2 inline-flex items-center rounded-md border border-border bg-card/60 text-xs hover:bg-accent">
                                <X className="h-3 w-3" />
                              </button>
                            </div>

                            {amend.error && (
                              <div className="w-full text-xs text-rose-600 flex items-center gap-1">
                                <AlertTriangle className="h-3 w-3" /> {amend.error}
                              </div>
                            )}
                          </div>
                        </td>
                      </tr>
                    )}
                  </>
                ))}
              </tbody>
            </table>
          </div>
          <div className="px-4 py-2 border-t border-border bg-muted/20 flex items-center justify-between text-xs text-muted-foreground">
            <span>{filtered.length} charge{filtered.length === 1 ? "" : "s"}</span>
            <span className="font-semibold text-rose-600">
              Outstanding: {money(filtered.reduce((s, c) => s + c.outstanding, 0))}
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
