"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Printer, TrendingUp, TrendingDown, AlertTriangle } from "lucide-react";
import type { ColumnDef } from "@tanstack/react-table";
import { api } from "@/lib/api";
import { inputClass } from "@/components/ui/dialog";
import { DataTable } from "@/components/ui/data-table";
import { money } from "@/lib/contract-types";

type Row = {
  property_id: number;
  property_code: string;
  property_name: string;
  rent_charged: number;
  rent_collected: number;
  rent_paid: number;
  expenses: Record<string, number>;
  expense_total: number;
  profit: number;
  cash_profit: number;
};

type Pnl = {
  month: string;
  rows: Row[];
  totals: {
    rent_charged: number; rent_collected: number; rent_paid: number;
    expense_total: number; profit: number;
    company_overhead: number; unallocated_direct: number; net_profit: number;
  };
};

function currentMonth() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

/**
 * The New-2026 block, reborn: per property, what was charged, what the
 * landlord took, what it cost to run, and the margin left over. This is
 * the number the accounting software cannot produce.
 */
export default function PnlPage() {
  const [data, setData] = useState<Pnl | null>(null);
  const [month, setMonth] = useState(currentMonth());
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const resp = await api.get("/expenses/pnl", { params: { month: `${month}-01` } });
      setData(resp.data?.data ?? null);
    } catch {
      setData(null);
    } finally { setLoading(false); }
  };

  useEffect(() => { load(); }, [month]);  // eslint-disable-line react-hooks/exhaustive-deps

  // Every expense category that appears anywhere becomes a column, so
  // the table mirrors the workbook's per-block expense rows.
  const expenseColumns = useMemo(() => {
    const names = new Set<string>();
    for (const row of data?.rows ?? []) {
      for (const name of Object.keys(row.expenses)) names.add(name);
    }
    return [...names].sort();
  }, [data]);

  const active = (data?.rows ?? []).filter(
    (r) => r.rent_charged || r.rent_paid || r.expense_total);

  const columns = useMemo<ColumnDef<Row, unknown>[]>(() => [
    {
      id: "property", header: "Property", accessorFn: (r) => r.property_name,
      cell: (c) => {
        const r = c.row.original;
        return (
          <div>
            <Link href={`/properties/${r.property_id}`} className="hover:text-primary">
              {r.property_name}
            </Link>
            <div className="text-[11px] text-muted-foreground font-mono">{r.property_code}</div>
          </div>
        );
      },
    },
    { accessorKey: "rent_charged", header: "Rent charged", cell: (c) => money(c.getValue<number>()) },
    {
      accessorKey: "rent_collected", header: "Collected",
      cell: (c) => <span className="text-emerald-600">{money(c.getValue<number>())}</span>,
    },
    { accessorKey: "rent_paid", header: "Rent paid", cell: (c) => money(c.getValue<number>()) },
    ...expenseColumns.map((name): ColumnDef<Row, unknown> => ({
      id: `exp:${name}`, header: name, enableSorting: false,
      accessorFn: (r) => r.expenses[name] ?? 0,
      cell: (c) => { const v = c.getValue<number>(); return v ? money(v) : ""; },
    })),
    {
      accessorKey: "profit", header: "Profit / loss",
      cell: (c) => {
        const v = c.getValue<number>();
        return <span className={"font-semibold " + (v >= 0 ? "text-emerald-600" : "text-rose-600")}>{money(v)}</span>;
      },
    },
  ], [expenseColumns]);

  const footer = data && active.length > 0 ? (
    <tr>
      <td className="py-2 px-3">Total</td>
      <td className="py-2 px-3">{money(data.totals.rent_charged)}</td>
      <td className="py-2 px-3">{money(data.totals.rent_collected)}</td>
      <td className="py-2 px-3">{money(data.totals.rent_paid)}</td>
      {expenseColumns.map((name) => (
        <td key={name} className="py-2 px-3">
          {money(active.reduce((s, r) => s + (r.expenses[name] ?? 0), 0))}
        </td>
      ))}
      <td className="py-2 px-3">{money(data.totals.profit)}</td>
    </tr>
  ) : null;

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-end justify-between flex-wrap gap-2">
        <div>
          <h1 className="text-2xl lg:text-3xl font-semibold tracking-tight">
            Property profit &amp; loss
          </h1>
          <p className="text-sm text-muted-foreground">
            Rent charged, less what the landlord took, less what the property cost to run.
          </p>
        </div>
        <div className="flex items-center gap-2 print:hidden">
          <input type="month" className={inputClass + " w-auto"} value={month}
            onChange={(e) => setMonth(e.target.value)} />
          <button onClick={() => window.print()}
            className="h-9 inline-flex items-center gap-2 rounded-md border border-border bg-card/60 px-3 text-sm hover:bg-accent">
            <Printer className="h-4 w-4" /> Print
          </button>
        </div>
      </div>

      {data && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <Stat label="Rent charged" value={money(data.totals.rent_charged)} />
          <Stat label="Paid to landlords" value={money(data.totals.rent_paid)} />
          <Stat label="Property costs" value={money(data.totals.expense_total)} />
          <Stat label="Property margin" value={money(data.totals.profit)}
            tone={data.totals.profit >= 0 ? "emerald" : "rose"} />
        </div>
      )}

      <DataTable columns={columns} data={active} loading={loading} footer={footer}
        emptyMessage="Nothing recorded for this month yet. Generate the rent schedule, record landlord payments, and import or enter the expenses."
        getRowId={(r) => String(r.property_id)} />

      {data && (
        <div className="glass rounded-xl p-4 space-y-2">
          <div className="text-sm font-semibold">From property margin to net profit</div>
          <Line label="Property margin" value={data.totals.profit} />
          {data.totals.unallocated_direct > 0 && (
            <Line label="Direct costs not yet allocated to a property"
              value={-data.totals.unallocated_direct} warn />
          )}
          <Line label="Company overhead (salary, fuel, telephone…)"
            value={-data.totals.company_overhead} />
          <div className="flex justify-between text-sm font-semibold pt-2 border-t border-border">
            <span>Net profit</span>
            <span className={data.totals.net_profit >= 0 ? "text-emerald-600" : "text-rose-600"}>
              {money(data.totals.net_profit)}
            </span>
          </div>
          {data.totals.unallocated_direct > 0 && (
            <div className="text-xs text-amber-600 inline-flex items-start gap-1.5 pt-1">
              <AlertTriangle className="h-3.5 w-3.5 mt-0.5 shrink-0" />
              Some property costs aren&apos;t on a property yet, so those properties look
              more profitable than they are. Allocate them on the Expenses page.
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function Stat({ label, value, tone }: {
  label: string; value: string; tone?: "emerald" | "rose";
}) {
  const Icon = tone === "rose" ? TrendingDown : TrendingUp;
  const cls = tone === "emerald" ? "text-emerald-600" : tone === "rose" ? "text-rose-600" : "";
  return (
    <div className="glass rounded-xl p-4">
      <div className="text-sm text-muted-foreground flex items-center justify-between">
        {label}
        {tone && <Icon className={"h-4 w-4 " + cls} />}
      </div>
      <div className={"mt-1 text-2xl font-semibold " + cls}>{value}</div>
    </div>
  );
}

function Line({ label, value, warn }: { label: string; value: number; warn?: boolean }) {
  return (
    <div className="flex justify-between text-sm">
      <span className={warn ? "text-amber-600" : "text-muted-foreground"}>{label}</span>
      <span>{money(value)}</span>
    </div>
  );
}
