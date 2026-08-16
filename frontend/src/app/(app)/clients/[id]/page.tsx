"use client";

import { useMemo, useState, use } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouteParams } from "@/lib/use-route-params";
import { keys } from "@/lib/query-keys";
import {
  ArrowLeft, FileText, Banknote, AlertTriangle, Paperclip, Mail,
  Receipt as ReceiptIcon, LayoutDashboard, BarChart3, ChevronLeft, ChevronRight, Search,
  CalendarDays, Pencil, X, Check,
} from "lucide-react";
import { inputClass, selectClass } from "@/components/ui/dialog";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
} from "recharts";
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

type TabKey = "overview" | "documents" | "monthly_rent" | "reports" | "dashboard";

const TABS: { key: TabKey; label: string; icon: typeof FileText }[] = [
  { key: "overview", label: "Overview", icon: FileText },
  { key: "documents", label: "Documents", icon: Paperclip },
  { key: "monthly_rent", label: "Monthly Rent", icon: CalendarDays },
  { key: "reports", label: "Reports", icon: BarChart3 },
  { key: "dashboard", label: "Dashboard", icon: LayoutDashboard },
];

export default function ClientDashboard(props: { params: Promise<{ id: string }> }) {
  const params = use(props.params);
  const { id } = useRouteParams(params);
  const qc = useQueryClient();
  const [tab, setTab] = useState<TabKey>("overview");
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

      {tab === "documents" && <AttachmentsTab entityType="client" entityId={c.id} />}
      {tab === "overview" && <ClientOverviewTab data={data} clientId={c.id} />}
      {tab === "monthly_rent" && <ClientMonthlyRentTab clientId={c.id} />}
      {tab === "reports" && <ClientReportsTab data={data} clientId={c.id} />}
      {tab === "dashboard" && <ClientDashboardTab data={data} clientId={c.id} />}
    </div>
  );
}

function ClientOverviewTab({ data, clientId }: { data: Data; clientId: number }) {
  const c = data.client;
  const ageMonths = data.ageing?.months ?? {};
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      {/* LEFT COLUMN */}
      <div className="space-y-4">
        <PartyAgreementsList entityType="client" entityId={clientId} />

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
                    <th className="py-2 pr-3 text-right">Rent</th>
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
                        <Link href={`/properties/${r.property_id}`} className="hover:text-primary text-xs">
                          {r.property_name}
                        </Link>
                      </td>
                      <td className="py-2 pr-3 font-mono text-xs">
                        {r.units.length ? r.units.join(", ") : "—"}
                      </td>
                      <td className="py-2 pr-3 text-xs">{MODE_LABEL[r.payment_mode] ?? r.payment_mode}</td>
                      <td className="py-2 pr-3 text-right text-xs">{money(r.monthly_rent)}</td>
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
                      <td className="py-2 pr-3 text-right text-xs">{money(q.amount)}</td>
                      <td className="py-2 pr-3 text-xs">{q.is_security ? "Security" : "Rent"}</td>
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

      {/* RIGHT COLUMN */}
      <div className="space-y-4">
        <Section title="Ageing"
          action={<Link href={`/collections/${clientId}`}
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

        <div className="glass rounded-xl p-4 space-y-3">
          <div className="text-sm font-semibold">Client profile</div>
          <div className="grid grid-cols-2 gap-2 text-xs">
            <div>
              <div className="text-muted-foreground">Type</div>
              <div className="font-medium capitalize">{c.client_type ?? "—"}</div>
            </div>
            <div>
              <div className="text-muted-foreground">QID / CR</div>
              <div className="font-mono">{c.qid_cr_number ?? "—"}</div>
            </div>
            {c.qid_cr_expiry_date && (
              <div className="col-span-2">
                <div className="text-muted-foreground">QID / CR expiry</div>
                <div className="font-mono">{c.qid_cr_expiry_date}</div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function ClientDashboardTab({ data, clientId }: { data: Data; clientId: number }) {
  const ageMonths = data.ageing?.months ?? {};

  const ageChartData = useMemo(() => {
    const entries: { month: string; Amount: number }[] = [];
    if (data.ageing?.older && data.ageing.older > 0) {
      entries.push({ month: "Older", Amount: data.ageing.older });
    }
    Object.entries(ageMonths)
      .sort(([a], [b]) => a.localeCompare(b))
      .forEach(([m, v]) => entries.push({ month: m.slice(0, 7), Amount: v }));
    return entries;
  }, [ageMonths, data.ageing]);

  const contractChartData = useMemo(() =>
    data.contracts.map((r) => ({
      name: r.contract_number,
      Rent: r.monthly_rent,
      status: r.status,
    })),
  [data.contracts]);

  const totalRent = data.contracts
    .filter((r) => r.status === "active")
    .reduce((s, r) => s + r.monthly_rent, 0);

  const occupancyPct = data.contracts.length
    ? Math.round((data.active_contracts / data.contracts.length) * 100) : 0;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <div className="glass rounded-xl p-4 flex flex-col items-center justify-center text-center">
          <div className="text-xs text-muted-foreground mb-1">Contract activity</div>
          <div className="text-4xl font-bold text-primary">{occupancyPct}%</div>
          <div className="text-xs text-muted-foreground mt-1">{data.active_contracts} of {data.contracts.length} active</div>
        </div>
        <div className="glass rounded-xl p-4 flex flex-col items-center justify-center text-center">
          <div className="text-xs text-muted-foreground mb-1">Monthly rent (active)</div>
          <div className="text-3xl font-bold text-emerald-600">{money(totalRent)}</div>
        </div>
        <div className="glass rounded-xl p-4 flex flex-col items-center justify-center text-center">
          <div className="text-xs text-muted-foreground mb-1">Outstanding balance</div>
          <div className={"text-3xl font-bold " + (data.outstanding > 0 ? "text-rose-600" : "text-emerald-600")}>
            {money(data.outstanding)}
          </div>
          <Link href={`/collections/${clientId}`} className="text-xs text-primary hover:underline mt-1">
            View statement →
          </Link>
        </div>
      </div>

      {ageChartData.length > 0 && (
        <div className="glass rounded-xl p-4">
          <div className="text-sm font-semibold mb-4">Outstanding ageing by month</div>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={ageChartData} margin={{ top: 0, right: 0, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" className="stroke-border/30" />
              <XAxis dataKey="month" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => v.toLocaleString()} />
              <Tooltip formatter={(v: number) => money(v)} />
              <Bar dataKey="Amount" fill="#ef4444" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {contractChartData.length > 0 && (
        <div className="glass rounded-xl p-4">
          <div className="text-sm font-semibold mb-4">Monthly rent by contract</div>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={contractChartData} margin={{ top: 0, right: 0, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" className="stroke-border/30" />
              <XAxis dataKey="name" tick={{ fontSize: 10 }} />
              <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => v.toLocaleString()} />
              <Tooltip formatter={(v: number) => money(v)} />
              <Bar dataKey="Rent" fill="#6366f1" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {data.cheques.length > 0 && (
        <div className="glass rounded-xl p-4">
          <div className="text-sm font-semibold mb-3">Cheque pipeline</div>
          <div className="flex flex-wrap gap-2">
            {(["pending", "deposited", "cleared", "returned", "cancelled"] as const).map((s) => {
              const cnt = data.cheques.filter((q) => q.status === s).length;
              if (cnt === 0) return null;
              return (
                <div key={s} className={"glass rounded-lg px-3 py-2 text-center " + (CHEQUE_TONE[s] ?? "")}>
                  <div className="text-lg font-semibold">{cnt}</div>
                  <div className="text-xs capitalize">{s}</div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

const RECEIPTS_PAGE_SIZE = 15;

function ClientReportsTab({ data, clientId }: { data: Data; clientId: number }) {
  const [q, setQ] = useState("");
  const [page, setPage] = useState(0);
  const ageMonths = data.ageing?.months ?? {};

  const filteredReceipts = useMemo(() => {
    const lq = q.toLowerCase();
    return lq
      ? data.recent_receipts.filter((r) =>
          r.receipt_number.toLowerCase().includes(lq) ||
          r.receipt_date.includes(lq) ||
          (MODE_LABEL[r.mode] ?? r.mode).toLowerCase().includes(lq))
      : data.recent_receipts;
  }, [data.recent_receipts, q]);

  const paged = filteredReceipts.slice(page * RECEIPTS_PAGE_SIZE, (page + 1) * RECEIPTS_PAGE_SIZE);
  const pageCount = Math.max(1, Math.ceil(filteredReceipts.length / RECEIPTS_PAGE_SIZE));

  const totalAging = data.ageing?.total ?? 0;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Section title="Statement summary"
          action={<Link href={`/collections/${clientId}`} className="text-xs text-muted-foreground hover:text-primary">Full SOA →</Link>}>
          {totalAging === 0 && data.recent_receipts.length === 0 ? (
            <EmptyRow>No financial history yet.</EmptyRow>
          ) : (
            <div className="space-y-2">
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Outstanding balance</span>
                <span className={"font-semibold " + (totalAging > 0 ? "text-rose-600" : "text-emerald-600")}>
                  {money(totalAging)}
                </span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Recent receipts collected</span>
                <span className="font-semibold">{money(data.recent_receipts.reduce((s, r) => s + r.amount, 0))}</span>
              </div>
              {Object.keys(ageMonths).length > 0 && (
                <div className="mt-2 pt-2 border-t border-border space-y-1">
                  <div className="text-xs text-muted-foreground font-medium">Ageing detail</div>
                  {data.ageing?.older && data.ageing.older > 0 && (
                    <Line label="Older" value={data.ageing.older} />
                  )}
                  {Object.entries(ageMonths)
                    .sort(([a], [b]) => a.localeCompare(b))
                    .map(([m, v]) => <Line key={m} label={m.slice(0, 7)} value={v} />)}
                </div>
              )}
            </div>
          )}
        </Section>

        <Section title="Contracts summary">
          {data.contracts.length === 0 ? (
            <EmptyRow>No contracts.</EmptyRow>
          ) : (
            <div className="space-y-2">
              {data.contracts.map((r) => (
                <div key={r.contract_id} className="flex items-center justify-between gap-2 py-1 border-b border-border/40 last:border-0">
                  <div>
                    <Link href={`/contracts/${r.contract_id}`} className="text-xs font-mono hover:text-primary">
                      {r.contract_number}
                    </Link>
                    <div className="text-[10px] text-muted-foreground">{r.property_name} · {r.expiry_date}</div>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <span className="text-xs font-medium">{money(r.monthly_rent)}</span>
                    <span className={"rounded-full px-2 py-0.5 text-xs " + (STATUS_TONE[r.status] ?? "bg-muted text-muted-foreground")}>
                      {r.status}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Section>
      </div>

      <Section title="Receipt history">
        <div className="flex items-center gap-2 mb-3">
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground pointer-events-none" />
            <input value={q} onChange={(e) => { setQ(e.target.value); setPage(0); }}
              placeholder="Search receipts…"
              className="h-8 pl-8 pr-3 w-48 rounded-md border border-input bg-card/60 text-sm" />
          </div>
        </div>
        {data.recent_receipts.length === 0 ? (
          <EmptyRow>No receipts recorded.</EmptyRow>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-left text-xs text-muted-foreground border-b border-border">
                  <tr>
                    <th className="py-2 pr-3">Receipt #</th>
                    <th className="py-2 pr-3">Date</th>
                    <th className="py-2 pr-3">Mode</th>
                    <th className="py-2 pr-3 text-right">Amount</th>
                    <th className="py-2 pr-3">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {paged.length === 0 ? (
                    <tr><td colSpan={5} className="py-6 text-center text-muted-foreground">No results.</td></tr>
                  ) : paged.map((r) => (
                    <tr key={r.id} className="border-b border-border/60 hover:bg-accent/30">
                      <td className="py-1.5 pr-3 font-mono text-xs">{r.receipt_number}</td>
                      <td className="py-1.5 pr-3 text-xs">{r.receipt_date}</td>
                      <td className="py-1.5 pr-3 text-xs">{MODE_LABEL[r.mode] ?? r.mode}</td>
                      <td className="py-1.5 pr-3 text-right text-xs font-medium">{money(r.amount)}</td>
                      <td className="py-1.5 pr-3">
                        <span className={"rounded-full px-2 py-0.5 text-xs " +
                          (r.status === "posted" ? "bg-emerald-500/10 text-emerald-600" : "bg-muted text-muted-foreground")}>
                          {r.status}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {filteredReceipts.length > RECEIPTS_PAGE_SIZE && (
              <div className="flex items-center justify-between text-xs text-muted-foreground pt-2">
                <span>{filteredReceipts.length} receipts · page {page + 1} of {pageCount}</span>
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

function Line({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex justify-between text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span>{money(value)}</span>
    </div>
  );
}

// ─── Monthly Rent Tab ────────────────────────────────────────────────────────

type RentCharge = {
  id: number; period_month: string; amount: number; allocated: number;
  outstanding: number; status: string; is_free_month: boolean;
  remarks: string | null; contract_id: number;
  contract?: { contract_number?: string };
};

type AmendForm = {
  chargeId: number; newAmount: string; isFreeMonth: boolean; remarks: string; saving: boolean; error: string | null;
};

function monthLabel(yyyyMmDd: string) {
  const d = new Date(yyyyMmDd + (yyyyMmDd.length === 7 ? "-01" : ""));
  return d.toLocaleDateString("en-GB", { month: "short", year: "2-digit" });
}

const STATUS_CLS: Record<string, string> = {
  open: "bg-rose-500/10 text-rose-600",
  part_paid: "bg-amber-500/10 text-amber-600",
  paid: "bg-emerald-500/10 text-emerald-600",
  cancelled: "bg-muted text-muted-foreground",
};

function ClientMonthlyRentTab({ clientId }: { clientId: number }) {
  const [charges, setCharges] = useState<RentCharge[]>([]);
  const [loading, setLoading] = useState(true);
  const [filterStatus, setFilterStatus] = useState("");
  const [amend, setAmend] = useState<AmendForm | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      const res = await api.get("/rent/charges", { params: { client_id: clientId } });
      setCharges(Array.isArray(res.data?.data) ? res.data.data : []);
    } finally { setLoading(false); }
  };

  useMemo(() => { load(); }, [clientId]); // eslint-disable-line react-hooks/exhaustive-deps

  const filtered = useMemo(() => {
    if (!filterStatus) return charges;
    return charges.filter((c) => c.status === filterStatus);
  }, [charges, filterStatus]);

  const openAmend = (c: RentCharge) => {
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
      await api.patch(`/rent/charges/${amend.chargeId}`, {
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
            <h2 className="font-semibold">Monthly Rent Schedule</h2>
            <p className="text-xs text-muted-foreground">Amend a single month's amount — e.g. a discount or free month.</p>
          </div>
          <div className="flex items-center gap-2">
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
          No rent charges found. Generate the rent schedule first.
        </div>
      ) : (
        <div className="glass rounded-xl overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-xs text-muted-foreground border-b border-border bg-muted/30">
                <tr>
                  <th className="px-4 py-2.5">Month</th>
                  <th className="px-4 py-2.5">Contract</th>
                  <th className="px-4 py-2.5 text-right">Amount</th>
                  <th className="px-4 py-2.5 text-right">Allocated</th>
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
                        {monthLabel(c.period_month)}
                        {c.is_free_month && (
                          <span className="ml-1.5 text-xs bg-emerald-500/10 text-emerald-600 rounded px-1">Free</span>
                        )}
                      </td>
                      <td className="px-4 py-2.5 text-muted-foreground font-mono text-xs">
                        {c.contract?.contract_number ?? `#${c.contract_id}`}
                      </td>
                      <td className="px-4 py-2.5 text-right font-semibold">{money(c.amount)}</td>
                      <td className="px-4 py-2.5 text-right text-emerald-600">{money(c.allocated)}</td>
                      <td className={"px-4 py-2.5 text-right font-semibold " + (c.outstanding > 0 ? "text-rose-600" : "")}>
                        {money(c.outstanding)}
                      </td>
                      <td className="px-4 py-2.5">
                        <span className={"rounded-full px-2 py-0.5 text-xs " + (STATUS_CLS[c.status] ?? "bg-muted text-muted-foreground")}>
                          {c.status.replace("_", " ")}
                        </span>
                      </td>
                      <td className="px-4 py-2.5 text-xs text-muted-foreground max-w-[160px] truncate">
                        {c.remarks ?? "—"}
                      </td>
                      <td className="px-4 py-2.5">
                        <Can perm="rent.generate">
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
                      <tr key={`amend-${c.id}`} className="bg-amber-500/5 border-t-0">
                        <td colSpan={8} className="px-4 py-3">
                          <div className="flex items-start gap-3 flex-wrap">
                            <div className="text-xs font-medium text-muted-foreground pt-2 min-w-[80px]">
                              Amend {monthLabel(c.period_month)}
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
                              <input type="text" placeholder="Reason for amendment…"
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

