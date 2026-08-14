"use client";

import { useEffect, useMemo, useState } from "react";
import { TrendingUp, TrendingDown, Wallet, Banknote, FileDown, Printer } from "lucide-react";
import {
  ComposedChart, Bar, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from "recharts";
import { api } from "@/lib/api";
import { inputClass } from "@/components/ui/dialog";
import { Stat } from "@/components/dashboard-bits";
import { money } from "@/lib/contract-types";
import { Can } from "@/components/can";
import { toast, errorMessage } from "@/components/ui/toast";

type Row = { line: string; section: string; total: number; [monthKey: string]: string | number };
type ReportData = { columns: { key: string; label: string }[]; rows: Row[];
                    meta: { months: string[]; start: string; end: string } };

const SUBTOTAL_LINES = new Set([
  "Total Revenues", "Cost of Sales", "Gross Profit / (Loss)",
  "Total Indirect Expenses", "Net Profit / (Loss)",
]);
const RESULT_LINES = new Set(["Gross Profit / (Loss)", "Net Profit / (Loss)"]);

function monthsAgo(n: number) {
  const d = new Date();
  d.setMonth(d.getMonth() - n);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}
const thisMonth = () => monthsAgo(0);

export default function PnlDashboardPage() {
  const [fromMonth, setFromMonth] = useState(monthsAgo(7));
  const [toMonth, setToMonth] = useState(thisMonth());
  const [data, setData] = useState<ReportData | null>(null);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState<"xlsx" | "pdf" | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      const resp = await api.get("/reports/monthly-pnl", {
        params: { from_month: `${fromMonth}-01`, to_month: `${toMonth}-01` },
      });
      setData(resp.data?.data ?? null);
    } catch {
      setData(null);
    } finally {
      setLoading(false);
    }
  };

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, []);

  const byLine = useMemo(() => {
    const map = new Map<string, Row>();
    for (const r of data?.rows ?? []) map.set(r.line, r);
    return map;
  }, [data]);

  const monthKeys = data?.meta.months ?? [];
  const monthLabel = (key: string) =>
    data?.columns.find((c) => c.key === key)?.label ?? key;

  const chartData = useMemo(() => {
    const revenue = byLine.get("Total Revenues");
    const cost = byLine.get("Cost of Sales");
    const net = byLine.get("Net Profit / (Loss)");
    return monthKeys.map((k) => ({
      month: monthLabel(k),
      revenue: Number(revenue?.[k] ?? 0),
      cost: Number(cost?.[k] ?? 0),
      net: Number(net?.[k] ?? 0),
    }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [byLine, monthKeys]);

  const latestNet = data ? byLine.get("Net Profit / (Loss)") : undefined;
  const latestRevenue = data ? byLine.get("Total Revenues") : undefined;
  const latestCost = data ? byLine.get("Cost of Sales") : undefined;
  const lastKey = monthKeys[monthKeys.length - 1];

  const download = async (format: "xlsx" | "pdf") => {
    setExporting(format);
    try {
      const params = { from_month: `${fromMonth}-01`, to_month: `${toMonth}-01`, format };
      const r = await api.get("/reports/monthly-pnl/export", { params, responseType: "blob" });
      const url = window.URL.createObjectURL(new Blob([r.data]));
      const a = document.createElement("a");
      a.href = url;
      a.download = `monthly-pnl-${new Date().toISOString().slice(0, 10)}.${format}`;
      a.click();
      window.URL.revokeObjectURL(url);
    } catch (err: unknown) {
      toast.error(`Could not export the ${format.toUpperCase()}`, errorMessage(err));
    } finally {
      setExporting(null);
    }
  };

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-end justify-between flex-wrap gap-2">
        <div>
          <h1 className="text-2xl lg:text-3xl font-semibold tracking-tight">P&amp;L Dashboard</h1>
          <p className="text-sm text-muted-foreground">
            Company profit &amp; loss across months, side by side — accrual basis, matching the
            accounting software&apos;s own layout.
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <input type="month" value={fromMonth} onChange={(e) => setFromMonth(e.target.value)}
                className={inputClass + " !w-auto"} />
          <span className="text-sm text-muted-foreground">to</span>
          <input type="month" value={toMonth} onChange={(e) => setToMonth(e.target.value)}
                className={inputClass + " !w-auto"} />
          <button onClick={load} className="h-9 rounded-md border border-border bg-card/60 px-3 text-sm hover:bg-accent">
            Apply
          </button>
          <Can perm="report.export">
            <button onClick={() => download("pdf")} disabled={exporting !== null}
                    className="h-9 rounded-md border border-border bg-card/60 px-3 text-sm hover:bg-accent disabled:opacity-50 inline-flex items-center gap-1.5">
              <Printer className="h-3.5 w-3.5" /> {exporting === "pdf" ? "Building…" : "PDF"}
            </button>
            <button onClick={() => download("xlsx")} disabled={exporting !== null}
                    className="h-9 rounded-md border border-border bg-card/60 px-3 text-sm hover:bg-accent disabled:opacity-50 inline-flex items-center gap-1.5">
              <FileDown className="h-3.5 w-3.5" /> {exporting === "xlsx" ? "Building…" : "Excel"}
            </button>
          </Can>
        </div>
      </div>

      {loading ? (
        <div className="text-sm text-muted-foreground animate-pulse">Loading…</div>
      ) : !data || data.rows.length === 0 ? (
        <div className="glass rounded-xl p-8 text-center text-sm text-muted-foreground">
          Nothing recorded for this range yet.
        </div>
      ) : (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <Stat label="Total revenues" value={money(Number(latestRevenue?.[lastKey] ?? 0))}
                 sub={monthLabel(lastKey)} icon={Banknote} />
            <Stat label="Cost of sales" value={money(Number(latestCost?.[lastKey] ?? 0))}
                 sub="direct costs + rent paid" icon={Wallet} />
            <Stat label="Net profit" value={money(Number(latestNet?.[lastKey] ?? 0))}
                 sub={monthLabel(lastKey)}
                 icon={Number(latestNet?.[lastKey] ?? 0) >= 0 ? TrendingUp : TrendingDown}
                 tone={Number(latestNet?.[lastKey] ?? 0) >= 0 ? "emerald" : "rose"} />
            <Stat label="Net profit (range total)" value={money(Number(latestNet?.total ?? 0))}
                 sub={`${monthLabel(monthKeys[0])} – ${monthLabel(lastKey)}`}
                 icon={Number(latestNet?.total ?? 0) >= 0 ? TrendingUp : TrendingDown}
                 tone={Number(latestNet?.total ?? 0) >= 0 ? "emerald" : "rose"} />
          </div>

          <div className="glass rounded-xl p-4">
            <div className="text-sm font-medium mb-3">Revenue, cost of sales and net profit</div>
            <ResponsiveContainer width="100%" height={280}>
              <ComposedChart data={chartData} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                <XAxis dataKey="month" tick={{ fontSize: 11 }} stroke="hsl(var(--muted-foreground))" />
                <YAxis tick={{ fontSize: 11 }} stroke="hsl(var(--muted-foreground))" />
                <Tooltip formatter={(v: number) => money(v)}
                        contentStyle={{ background: "hsl(var(--card))",
                          border: "1px solid hsl(var(--border))", borderRadius: 8, fontSize: 12 }} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Bar dataKey="revenue" name="Total Revenues" fill="#3b82f6" radius={[4, 4, 0, 0]} />
                <Bar dataKey="cost" name="Cost of Sales" fill="#f59e0b" radius={[4, 4, 0, 0]} />
                <Line type="monotone" dataKey="net" name="Net Profit" stroke="#10b981" strokeWidth={2.5} dot={{ r: 3 }} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>

          <div className="glass rounded-xl overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border bg-card/40">
                    <th className="text-left font-medium px-4 py-2.5 sticky left-0 bg-card/40 z-10 min-w-[220px]">
                      Line
                    </th>
                    {monthKeys.map((k) => (
                      <th key={k} className="text-right font-medium px-3 py-2.5 whitespace-nowrap min-w-[100px]">
                        {monthLabel(k)}
                      </th>
                    ))}
                    <th className="text-right font-medium px-4 py-2.5 whitespace-nowrap min-w-[110px]">Total</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/60">
                  {data.rows.map((r, i) => {
                    const isSubtotal = SUBTOTAL_LINES.has(r.line);
                    const isResult = RESULT_LINES.has(r.line);
                    return (
                      <tr key={i} className={isSubtotal ? "bg-accent/30" : ""}>
                        <td className={`px-4 py-2 sticky left-0 z-10 ${isSubtotal ? "bg-accent/30 font-semibold" : "bg-card"}`}>
                          {r.line}
                        </td>
                        {monthKeys.map((k) => {
                          const v = Number(r[k] ?? 0);
                          return (
                            <td key={k} className={`text-right px-3 py-2 font-mono text-xs ${
                              isResult ? (v >= 0 ? "text-emerald-600" : "text-rose-600") : ""
                            } ${isSubtotal ? "font-semibold" : ""}`}>
                              {money(v)}
                            </td>
                          );
                        })}
                        <td className={`text-right px-4 py-2 font-mono text-xs font-semibold ${
                          isResult ? (r.total >= 0 ? "text-emerald-600" : "text-rose-600") : ""
                        }`}>
                          {money(r.total)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
