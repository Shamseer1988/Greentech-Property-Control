"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  Banknote, RefreshCw, Receipt as ReceiptIcon, FileText, AlertTriangle, Wallet, Search,
} from "lucide-react";
import type { ColumnDef } from "@tanstack/react-table";
import { api } from "@/lib/api";
import { Can } from "@/components/can";
import { inputClass, selectClass } from "@/components/ui/dialog";
import { DataTable } from "@/components/ui/data-table";
import { ReceiptDialog } from "@/components/receipt-dialog";
import { money } from "@/lib/contract-types";
import { useDebouncedValue } from "@/lib/use-debounce";

type Owing = {
  client_id: number;
  client_code: string | null;
  client_name: string | null;
  outstanding: number;
  open_months: number;
  oldest_month: string | null;
  days_overdue: number;
};

type Summary = {
  month: string;
  charged: number;
  collected: number;
  outstanding: number;
  received_in_month: number;
  collection_percent: number;
};

function thisMonth(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-01`;
}

export default function CollectionsPage() {
  const [rows, setRows] = useState<Owing[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [month, setMonth] = useState(thisMonth().slice(0, 7));
  const [q, setQ] = useState("");
  const debouncedQ = useDebouncedValue(q);
  const [minOverdueDays, setMinOverdueDays] = useState(0);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [receiptFor, setReceiptFor] = useState<Owing | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      const [o, s] = await Promise.all([
        api.get("/rent/outstanding", { params: { upto: `${month}-01` } }),
        api.get("/rent/summary", { params: { month: `${month}-01` } }),
      ]);
      setRows(Array.isArray(o.data?.data) ? o.data.data : []);
      setSummary(s.data?.data ?? null);
    } catch {
      setRows([]);
      setSummary(null);
    } finally { setLoading(false); }
  };

  useEffect(() => { load(); }, [month]);  // eslint-disable-line react-hooks/exhaustive-deps

  const filteredRows = useMemo(() => {
    const needle = debouncedQ.trim().toLowerCase();
    return rows.filter((r) => {
      if (needle &&
        !r.client_name?.toLowerCase().includes(needle) &&
        !r.client_code?.toLowerCase().includes(needle)) return false;
      if (minOverdueDays > 0 && r.days_overdue < minOverdueDays) return false;
      return true;
    });
  }, [rows, debouncedQ, minOverdueDays]);

  const generate = async () => {
    setGenerating(true);
    try {
      await api.post("/rent/generate", { upto: `${month}-01` });
      await load();
    } finally { setGenerating(false); }
  };

  const total = rows.reduce((sum, r) => sum + r.outstanding, 0);
  const filteredTotal = filteredRows.reduce((sum, r) => sum + r.outstanding, 0);

  const columns = useMemo<ColumnDef<Owing, unknown>[]>(() => [
    {
      id: "client", header: "Client", accessorFn: (r) => r.client_name ?? "",
      cell: (c) => {
        const r = c.row.original;
        return (
          <div>
            <Link href={`/collections/${r.client_id}`} className="font-medium hover:text-primary">
              {r.client_name}
            </Link>
            <div className="text-xs text-muted-foreground font-mono">{r.client_code}</div>
          </div>
        );
      },
    },
    {
      accessorKey: "outstanding", header: "Outstanding",
      cell: (c) => (
        <span className="font-semibold text-rose-600">{money(c.getValue<number>())}</span>
      ),
    },
    { accessorKey: "open_months", header: "Open months" },
    {
      accessorKey: "oldest_month", header: "Oldest due",
      cell: (c) => {
        const r = c.row.original;
        return (
          <div className="inline-flex items-center gap-2 flex-wrap">
            <span className="font-mono text-xs">{r.oldest_month?.slice(0, 7)}</span>
            {r.days_overdue > 30 && (
              <span className="text-xs text-amber-600 inline-flex items-center gap-1">
                <AlertTriangle className="h-3 w-3" /> {r.days_overdue}d overdue
              </span>
            )}
          </div>
        );
      },
    },
    {
      id: "actions", header: "Actions", enableSorting: false,
      cell: (c) => {
        const r = c.row.original;
        return (
          <div className="flex items-center justify-end gap-0.5">
            <Link href={`/collections/${r.client_id}`} title="Statement of account"
              className="h-8 w-8 inline-flex items-center justify-center rounded-md hover:bg-accent">
              <FileText className="h-3.5 w-3.5" />
            </Link>
            <Can perm="receipt.create">
              <button onClick={() => setReceiptFor(r)} title="Receive payment"
                className="h-8 w-8 inline-flex items-center justify-center rounded-md hover:bg-accent">
                <Banknote className="h-3.5 w-3.5" />
              </button>
            </Can>
          </div>
        );
      },
    },
  ], []);

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-end justify-between flex-wrap gap-2">
        <div>
          <h1 className="text-2xl lg:text-3xl font-semibold tracking-tight">Collections</h1>
          <p className="text-sm text-muted-foreground">
            What each client owes, and the money coming in against it.
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <input type="month" className={inputClass + " w-auto"} value={month}
            onChange={(e) => setMonth(e.target.value)} />
          <Can perm="rent.generate">
            <button onClick={generate} disabled={generating}
              className="inline-flex h-9 items-center gap-2 rounded-md border border-border bg-card/60 px-3 text-sm hover:bg-accent disabled:opacity-60">
              <RefreshCw className={"h-4 w-4 " + (generating ? "animate-spin" : "")} />
              {generating ? "Generating…" : "Generate rent"}
            </button>
          </Can>
        </div>
      </div>

      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <KpiCard label="Charged this month" value={money(summary.charged)} />
          <KpiCard label="Collected" value={money(summary.collected)} tone="emerald"
            sub={`${summary.collection_percent}% of the month`} />
          <KpiCard label="Still due this month" value={money(summary.outstanding)}
            tone={summary.outstanding > 0 ? "amber" : undefined} />
          <KpiCard label="Total outstanding" value={money(total)}
            tone={total > 0 ? "rose" : undefined}
            sub={`${rows.length} client${rows.length === 1 ? "" : "s"}`} />
        </div>
      )}

      <div className="glass rounded-xl p-4">
        <div className="flex items-center gap-2 flex-wrap">
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground pointer-events-none" />
            <input value={q} onChange={(e) => setQ(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && load()}
              placeholder="Search client code or name…"
              className="h-9 pl-8 pr-3 w-60 rounded-md border border-input bg-card/60 text-sm" />
          </div>
          <select value={String(minOverdueDays)}
            onChange={(e) => setMinOverdueDays(Number(e.target.value))}
            className={selectClass + " !w-auto"}>
            <option value="0">All overdue status</option>
            <option value="1">Any overdue</option>
            <option value="30">30+ days overdue</option>
            <option value="60">60+ days overdue</option>
            <option value="90">90+ days overdue</option>
            <option value="180">6+ months overdue</option>
          </select>
          <button onClick={load} disabled={loading}
            className="h-9 rounded-md border border-border bg-card/60 px-3 text-sm hover:bg-accent disabled:opacity-60">
            Search
          </button>
          {filteredRows.length !== rows.length && (
            <span className="text-xs text-muted-foreground">
              {filteredRows.length} of {rows.length} clients · {money(filteredTotal)}
            </span>
          )}
        </div>
      </div>

      <DataTable
        columns={columns}
        data={filteredRows}
        loading={loading}
        maxBodyHeight="60vh"
        emptyMessage="Nothing outstanding. Generate the rent schedule if this month's charges haven't been raised yet."
        getRowId={(r) => String(r.client_id)}
        footer={
          filteredRows.length > 0 ? (
            <tr>
              <td colSpan={2} className="px-3 py-2 text-sm font-semibold text-right">
                Total shown
              </td>
              <td colSpan={3} className="px-3 py-2 text-sm font-semibold text-rose-600">
                {money(filteredTotal)}
              </td>
            </tr>
          ) : undefined
        }
      />

      <div className="flex gap-3 text-sm">
        <Link href="/collections/ageing" className="text-primary hover:underline inline-flex items-center gap-1">
          <ReceiptIcon className="h-4 w-4" /> Ageing report →
        </Link>
        <Link href="/collections/cash-due" className="text-primary hover:underline inline-flex items-center gap-1">
          <Wallet className="h-4 w-4" /> Cash due booking →
        </Link>
      </div>

      <ReceiptDialog
        open={Boolean(receiptFor)}
        clientId={receiptFor?.client_id ?? null}
        clientName={receiptFor?.client_name ?? null}
        onClose={() => setReceiptFor(null)}
        onPosted={async () => { setReceiptFor(null); await load(); }}
      />
    </div>
  );
}

function KpiCard({ label, value, sub, tone }: {
  label: string; value: string; sub?: string;
  tone?: "emerald" | "amber" | "rose";
}) {
  const cls = tone === "emerald" ? "text-emerald-600"
    : tone === "amber" ? "text-amber-600"
    : tone === "rose" ? "text-rose-600" : "";
  return (
    <div className="glass rounded-xl p-4">
      <div className="text-sm text-muted-foreground">{label}</div>
      <div className={"mt-1 text-2xl font-semibold " + cls}>{value}</div>
      {sub && <div className="mt-1 text-xs text-muted-foreground">{sub}</div>}
    </div>
  );
}

