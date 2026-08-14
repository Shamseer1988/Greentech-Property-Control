"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import {
  Building2, DoorOpen, Key, Wrench, Clock, FileText, CheckSquare,
  Banknote, TrendingUp, TrendingDown, AlertTriangle, Users, ArrowRight,
  Landmark,
} from "lucide-react";
import { Skeleton } from "@/components/ui/states";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend,
} from "recharts";
import { api } from "@/lib/api";
import { keys } from "@/lib/query-keys";
import { useEvents } from "@/lib/use-events";
import { money } from "@/lib/contract-types";
import { inputClass } from "@/components/ui/dialog";

type Summary = {
  month: string;
  properties: { total: number; active: number; inactive: number; maintenance: number; vacated: number };
  units: { total: number; empty: number; occupied: number; maintenance: number; blocked: number; occupancy_percent: number };
  landlords: { total: number };
  clients: { total: number };
  contracts: { active: number };
  collections: {
    month: string; charged: number; collected: number; outstanding: number;
    received_in_month: number; collection_percent: number;
  };
  ageing: {
    total_outstanding: number; clients_in_arrears: number;
    worst: { client_id: number; client_name: string; total: number }[];
  };
  pnl: {
    rent_charged: number; rent_collected: number; rent_paid: number;
    expense_total: number; profit: number;
    company_overhead: number; unallocated_direct: number; net_profit: number;
  };
  contract_expiry: {
    buckets: { expired: number; d30: number; d60: number; d90: number; total: number };
    soonest: {
      contract_id: number; contract_number: string; client_name: string;
      expiry_date: string; days_left: number; monthly_rent: number; bucket: string;
    }[];
  };
  agreement_expiry: Record<string, number>;
  cheques: {
    due_this_week: { count: number; amount: number };
    bounced: { count: number; amount: number };
  };
  open_maintenance: number;
  approvals: { total: number } & Record<string, number>;
};

type OccupancyByProperty = {
  property_id: number; code: string; name: string;
  total_units: number; occupied: number; empty: number;
  occupancy_percent: number;
};

type CashflowForecast = {
  as_of: string;
  buckets: Record<"30" | "60" | "90", { expected_in: number; expected_out: number; net: number }>;
};

type RenewalsAtRisk = {
  within_days: number;
  client_contracts: { id: number; contract_number: string; client_name: string | null; expiry_date: string; days_left: number }[];
  landlord_contracts: { id: number; property_name: string | null; landlord_name: string | null; expiry_date: string; days_left: number }[];
  generated_agreements: { id: number; agreement_number: string; party_role: string; end_date: string; days_left: number }[];
  total: number;
};

type ChequeAgeing = {
  buckets: Record<"0-30" | "31-60" | "61-90" | "90+", number>;
  total: number;
  rows: { id: number; cheque_number: string; amount: number; status: string; cheque_date: string; days_overdue: number }[];
};

const UNIT_STATUS_COLORS: Record<string, string> = {
  occupied: "#10b981",
  empty: "#94a3b8",
  maintenance: "#f59e0b",
  blocked: "#f43f5e",
};

function currentMonth() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

/**
 * The month in one screen. Money first — what was charged, what came in,
 * what the month made — because that is the question the workbook was
 * opened to answer. Estate and housekeeping follow underneath.
 */
export default function DashboardPage() {
  const qc = useQueryClient();
  const [month, setMonth] = useState(currentMonth());

  useEvents("occupancy", () => {
    qc.invalidateQueries({ queryKey: ["dashboard"] });
    qc.invalidateQueries({ queryKey: ["properties"] });
  });

  // One useQuery per panel so a failure on one chart doesn't blank the
  // others. Query keys live in lib/query-keys.ts so mutations elsewhere
  // can invalidate them precisely.
  const summaryQuery = useQuery({
    queryKey: [...keys.dashboard.summary(), month],
    queryFn: async () =>
      (await api.get("/dashboard/summary", { params: { month: `${month}-01` } }))
        .data.data as Summary,
  });
  const byPropertyQuery = useQuery({
    queryKey: keys.dashboard.byProperty(),
    queryFn: async () =>
      (await api.get("/dashboard/charts/occupancy-by-property")).data.data as OccupancyByProperty[],
  });
  const cashflowQuery = useQuery({
    queryKey: keys.dashboard.cashflowForecast(),
    queryFn: async () => (await api.get("/dashboard/cashflow-forecast")).data.data as CashflowForecast,
  });
  const renewalsQuery = useQuery({
    queryKey: keys.dashboard.renewalsAtRisk(),
    queryFn: async () => (await api.get("/dashboard/renewals-at-risk")).data.data as RenewalsAtRisk,
  });
  const chequeAgeingQuery = useQuery({
    queryKey: keys.dashboard.chequeAgeing(),
    queryFn: async () => (await api.get("/dashboard/cheque-ageing")).data.data as ChequeAgeing,
  });

  const summary = summaryQuery.data ?? null;
  const byProperty = byPropertyQuery.data ?? [];
  const cashflow = cashflowQuery.data ?? null;
  const renewals = renewalsQuery.data ?? null;
  const chequeAgeing = chequeAgeingQuery.data ?? null;

  if (summaryQuery.isLoading) {
    return (
      <div className="space-y-6 animate-fade-in">
        <div className="space-y-2">
          <Skeleton className="h-7 w-48" />
          <Skeleton className="h-3 w-72" />
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="glass rounded-xl p-4 space-y-2">
              <Skeleton className="h-3 w-1/2" />
              <Skeleton className="h-7 w-1/3" />
              <Skeleton className="h-3 w-2/3" />
            </div>
          ))}
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div className="glass rounded-xl p-4 lg:col-span-2 h-72"><Skeleton className="h-full w-full" /></div>
          <div className="glass rounded-xl p-4 h-72"><Skeleton className="h-full w-full" /></div>
        </div>
      </div>
    );
  }

  if (!summary) {
    return (
      <div className="glass rounded-xl p-10 text-center border border-destructive/30 bg-destructive/5 space-y-2">
        <div className="font-medium text-destructive">Dashboard data couldn&apos;t be loaded.</div>
        <div className="text-xs text-muted-foreground">The summary API didn&apos;t respond. Check the browser DevTools network tab for details, then refresh.</div>
        <button onClick={() => window.location.reload()} className="mt-2 inline-flex items-center gap-1 rounded-md border border-border bg-card/60 px-3 py-1.5 text-xs hover:bg-accent">
          Refresh
        </button>
      </div>
    );
  }

  const expiryTotal = Object.entries(summary.agreement_expiry)
    .filter(([k]) => k !== "safe")
    .reduce((acc, [, v]) => acc + (v ?? 0), 0);

  const unitPie = [
    { name: "Occupied", value: summary.units.occupied, key: "occupied" },
    { name: "Empty", value: summary.units.empty, key: "empty" },
    { name: "Maintenance", value: summary.units.maintenance, key: "maintenance" },
    { name: "Blocked", value: summary.units.blocked, key: "blocked" },
  ].filter((s) => s.value > 0);

  const propertyBars = byProperty.slice(0, 10).map((p) => ({
    name: p.name.length > 14 ? p.name.slice(0, 14) + "…" : p.name,
    occupied: p.occupied,
    empty: p.empty,
  }));

  const c = summary.collections;
  const expiry = summary.contract_expiry.buckets;

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-end justify-between flex-wrap gap-2">
        <div>
          <h1 className="text-2xl lg:text-3xl font-semibold tracking-tight">Dashboard</h1>
          <p className="text-sm text-muted-foreground">
            Rent, margin and what needs attention this month.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <input type="month" className={inputClass + " w-auto"} value={month}
            onChange={(e) => setMonth(e.target.value)} />
          <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
            <Clock className="h-3.5 w-3.5" /> {new Date().toLocaleTimeString()}
          </span>
        </div>
      </div>

      {/* ---- Money ---- */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Card label="Rent charged" value={money(c.charged)}
          sub={`${summary.contracts.active} active contracts`}
          icon={FileText} accent="from-blue-500 to-indigo-500" href="/collections" />
        <Card label="Collected" value={money(c.collected)}
          sub={`${c.collection_percent}% of what was charged`}
          icon={Banknote} accent="from-emerald-500 to-teal-500"
          tone={c.collection_percent >= 90 ? "emerald" : c.collection_percent >= 60 ? "amber" : "rose"}
          href="/collections" />
        <Card label="Outstanding" value={money(summary.ageing.total_outstanding)}
          sub={`${summary.ageing.clients_in_arrears} client(s) in arrears`}
          icon={AlertTriangle} accent="from-amber-500 to-orange-500"
          tone={summary.ageing.total_outstanding > 0 ? "amber" : "emerald"}
          href="/collections/ageing" />
        <Card label="Net profit" value={money(summary.pnl.net_profit ?? 0)}
          sub="after landlord rent and costs"
          icon={(summary.pnl.net_profit ?? 0) >= 0 ? TrendingUp : TrendingDown}
          accent="from-violet-500 to-purple-600"
          tone={(summary.pnl.net_profit ?? 0) >= 0 ? "emerald" : "rose"}
          href="/pnl" />
      </div>

      {/* ---- Estate ---- */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Card label="Properties" value={summary.properties.total}
          sub={`${summary.properties.active} active`} icon={Building2}
          accent="from-blue-500 to-indigo-500" href="/properties" />
        <Card label="Units" value={summary.units.total}
          sub={`${summary.units.occupancy_percent}% occupancy`} icon={DoorOpen}
          accent="from-emerald-500 to-teal-500" />
        <Card label="Empty units" value={summary.units.empty}
          sub={`${summary.units.occupied} occupied`} icon={DoorOpen}
          accent="from-slate-400 to-slate-600"
          tone={summary.units.empty > 0 ? "amber" : "emerald"}
          href="/reports/empty-units" />
        <Card label="Clients" value={summary.clients.total}
          sub={`${summary.landlords.total} landlords`} icon={Users}
          accent="from-violet-500 to-purple-600" href="/clients" />
      </div>

      {/* ---- Needs attention ---- */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
        <Card label="Contracts expiring" value={expiry.total}
          sub={`${expiry.expired} expired · ${expiry.d30} in 30 days`}
          icon={FileText} accent="from-rose-500 to-pink-600"
          tone={expiry.expired > 0 ? "rose" : expiry.total > 0 ? "amber" : undefined}
          href="/reports/contract-expiry" />
        <Card label="Agreements expiring" value={expiryTotal}
          sub="landlord side, within 90 days" icon={Key}
          accent="from-rose-500 to-pink-600"
          tone={expiryTotal > 0 ? "rose" : undefined} href="/alerts" />
        <Card label="PDCs due this week" value={summary.cheques.due_this_week.count}
          sub={money(summary.cheques.due_this_week.amount)} icon={Banknote}
          accent="from-sky-500 to-cyan-600"
          tone={summary.cheques.due_this_week.count > 0 ? "sky" : undefined}
          href="/reports/pdc-register" />
        <Card label="Bounced cheques" value={summary.cheques.bounced.count}
          sub={money(summary.cheques.bounced.amount)} icon={AlertTriangle}
          accent="from-rose-500 to-pink-600"
          tone={summary.cheques.bounced.count > 0 ? "rose" : undefined}
          href="/reports/pdc-register" />
        <Card label="Pending approvals" value={summary.approvals.total}
          sub="awaiting decision" icon={CheckSquare}
          accent="from-amber-500 to-orange-500"
          tone={summary.approvals.total > 0 ? "amber" : undefined}
          href="/approvals" />
      </div>

      {/* ---- Lists that need a name, not a number ---- */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Panel title="Expiring soonest" href="/reports/contract-expiry">
          {summary.contract_expiry.soonest.length === 0 ? (
            <Empty>Nothing expires in the next 90 days.</Empty>
          ) : (
            <ul className="divide-y divide-border/60">
              {summary.contract_expiry.soonest.map((row) => (
                <li key={row.contract_id} className="py-2 flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <Link href={`/contracts/${row.contract_id}`}
                      className="text-sm hover:text-primary truncate block">
                      {row.client_name}
                    </Link>
                    <div className="text-[11px] text-muted-foreground font-mono">
                      {row.contract_number} · {row.expiry_date}
                    </div>
                  </div>
                  <span className={
                    "shrink-0 rounded-full px-2 py-0.5 text-xs " +
                    (row.days_left < 0 ? "bg-rose-500/10 text-rose-600"
                      : row.days_left <= 30 ? "bg-amber-500/10 text-amber-600"
                        : "bg-muted text-muted-foreground")
                  }>
                    {row.days_left < 0 ? `${-row.days_left}d overdue` : `${row.days_left}d`}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        <Panel title="Largest arrears" href="/collections/ageing">
          {summary.ageing.worst.length === 0 ? (
            <Empty>Everyone is paid up.</Empty>
          ) : (
            <ul className="divide-y divide-border/60">
              {summary.ageing.worst.map((row) => (
                <li key={row.client_id} className="py-2 flex items-center justify-between gap-3">
                  <Link href={`/collections/${row.client_id}`}
                    className="text-sm hover:text-primary truncate">
                    {row.client_name}
                  </Link>
                  <span className="shrink-0 text-sm font-semibold text-rose-600">
                    {money(row.total)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="glass rounded-xl p-4 lg:col-span-2 min-h-[280px]">
          <h2 className="text-sm font-semibold mb-2">Occupancy by property</h2>
          {propertyBars.length === 0 ? (
            <div className="h-56 grid place-items-center text-sm text-muted-foreground">No data yet.</div>
          ) : (
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={propertyBars} margin={{ top: 10, right: 8, left: -16, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                <XAxis dataKey="name" tick={{ fontSize: 11 }} stroke="hsl(var(--muted-foreground))" />
                <YAxis tick={{ fontSize: 11 }} stroke="hsl(var(--muted-foreground))" />
                <Tooltip contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 8, fontSize: 12 }} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Bar dataKey="occupied" stackId="a" fill={UNIT_STATUS_COLORS.occupied} />
                <Bar dataKey="empty" stackId="a" fill={UNIT_STATUS_COLORS.empty} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>

        <div className="glass rounded-xl p-4 min-h-[280px]">
          <h2 className="text-sm font-semibold mb-2">Unit status</h2>
          {unitPie.length === 0 ? (
            <div className="h-56 grid place-items-center text-sm text-muted-foreground">No units yet.</div>
          ) : (
            <ResponsiveContainer width="100%" height={260}>
              <PieChart>
                <Pie data={unitPie} dataKey="value" innerRadius={50} outerRadius={84} paddingAngle={2}>
                  {unitPie.map((s) => <Cell key={s.key} fill={UNIT_STATUS_COLORS[s.key]} />)}
                </Pie>
                <Tooltip contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 8, fontSize: 12 }} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
              </PieChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      {/* ---- Cash-flow, renewals, cheque ageing ---- */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="glass rounded-xl p-4 min-h-[260px]">
          <h2 className="text-sm font-semibold mb-2 flex items-center gap-1.5">
            <Landmark className="h-4 w-4 text-muted-foreground" /> Cash-flow forecast
          </h2>
          {!cashflow ? (
            <div className="h-56 grid place-items-center text-sm text-muted-foreground">Loading…</div>
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart
                data={(["30", "60", "90"] as const).map((d) => ({
                  name: `${d}d`,
                  in: cashflow.buckets[d].expected_in,
                  out: cashflow.buckets[d].expected_out,
                }))}
                margin={{ top: 10, right: 8, left: -16, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                <XAxis dataKey="name" tick={{ fontSize: 11 }} stroke="hsl(var(--muted-foreground))" />
                <YAxis tick={{ fontSize: 11 }} stroke="hsl(var(--muted-foreground))" />
                <Tooltip
                  formatter={(v: number) => money(v)}
                  contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 8, fontSize: 12 }} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Bar dataKey="in" name="Expected in" fill="#10b981" />
                <Bar dataKey="out" name="Expected out" fill="#f43f5e" />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>

        <Panel title="Renewals at risk" href="/agreements">
          {!renewals ? (
            <div className="text-sm text-muted-foreground">Loading…</div>
          ) : renewals.total === 0 ? (
            <Empty>Nothing expiring within {renewals.within_days} days.</Empty>
          ) : (
            <ul className="divide-y divide-border/60">
              {renewals.client_contracts.slice(0, 4).map((r) => (
                <li key={`cc-${r.id}`} className="py-2 flex items-center justify-between gap-3">
                  <Link href={`/contracts/${r.id}`} className="text-sm hover:text-primary truncate min-w-0">
                    {r.client_name ?? r.contract_number}
                  </Link>
                  <span className="shrink-0 text-xs text-muted-foreground">{r.days_left}d</span>
                </li>
              ))}
              {renewals.generated_agreements.slice(0, 4).map((r) => (
                <li key={`ga-${r.id}`} className="py-2 flex items-center justify-between gap-3">
                  <Link href="/agreements" className="text-sm hover:text-primary truncate min-w-0 font-mono">
                    {r.agreement_number}
                  </Link>
                  <span className="shrink-0 text-xs text-muted-foreground">{r.days_left}d</span>
                </li>
              ))}
              {renewals.landlord_contracts.slice(0, 4).map((r) => (
                <li key={`lc-${r.id}`} className="py-2 flex items-center justify-between gap-3">
                  <span className="text-sm truncate min-w-0">{r.property_name ?? r.landlord_name}</span>
                  <span className="shrink-0 text-xs text-muted-foreground">{r.days_left}d</span>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        <Panel title="Overdue cheques" href="/reports/pdc-register">
          {!chequeAgeing ? (
            <div className="text-sm text-muted-foreground">Loading…</div>
          ) : chequeAgeing.total === 0 ? (
            <Empty>No overdue or bounced cheques.</Empty>
          ) : (
            <div className="space-y-1.5">
              {(["0-30", "31-60", "61-90", "90+"] as const).map((bucket) => (
                <div key={bucket} className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">{bucket} days</span>
                  <span className={chequeAgeing.buckets[bucket] > 0 ? "font-medium text-rose-600" : "text-muted-foreground"}>
                    {money(chequeAgeing.buckets[bucket])}
                  </span>
                </div>
              ))}
              <div className="flex items-center justify-between text-sm pt-1.5 border-t border-border font-semibold">
                <span>Total</span>
                <span className="text-rose-600">{money(chequeAgeing.total)}</span>
              </div>
            </div>
          )}
        </Panel>
      </div>

      {summary.open_maintenance > 0 && (
        <div className="glass rounded-xl p-4 text-sm inline-flex items-center gap-2">
          <Wrench className="h-4 w-4 text-amber-600" />
          {summary.open_maintenance} maintenance job(s) in progress.
        </div>
      )}
    </div>
  );
}

function Panel({ title, href, children }: {
  title: string; href?: string; children: React.ReactNode;
}) {
  return (
    <div className="glass rounded-xl p-4">
      <div className="flex items-center justify-between mb-1">
        <h2 className="text-sm font-semibold">{title}</h2>
        {href && (
          <Link href={href}
            className="text-xs text-muted-foreground hover:text-primary inline-flex items-center gap-1">
            All <ArrowRight className="h-3 w-3" />
          </Link>
        )}
      </div>
      {children}
    </div>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return <div className="py-6 text-center text-sm text-muted-foreground">{children}</div>;
}

function Card({
  label, value, sub, icon: Icon, accent, tone, href,
}: {
  label: string; value: number | string; sub?: string;
  icon: typeof Building2; accent: string;
  tone?: "emerald" | "amber" | "rose" | "sky";
  href?: string;
}) {
  const toneCls =
    tone === "emerald" ? "text-emerald-600" :
    tone === "amber" ? "text-amber-600" :
    tone === "rose" ? "text-rose-600" :
    tone === "sky" ? "text-sky-600" : "";
  const className = "glass rounded-xl p-4 relative overflow-hidden block transition-colors " + (href ? "hover:bg-accent/30 hover:-translate-y-0.5 cursor-pointer" : "");
  const inner = (
    <>
      <div className={`absolute -top-10 -right-10 h-32 w-32 rounded-full bg-gradient-to-br ${accent} opacity-20 blur-2xl pointer-events-none`} />
      <div className="flex items-center justify-between">
        <span className="text-sm text-muted-foreground">{label}</span>
        <Icon className="h-4 w-4 text-muted-foreground" />
      </div>
      <div className={"mt-2 text-2xl font-semibold " + toneCls}>{value}</div>
      {sub && <div className="mt-1 text-xs text-muted-foreground">{sub}</div>}
    </>
  );
  if (href) return <Link href={href} className={className}>{inner}</Link>;
  return <div className={className}>{inner}</div>;
}
