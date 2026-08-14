"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, Printer } from "lucide-react";
import { api } from "@/lib/api";
import { inputClass, selectClass } from "@/components/ui/dialog";
import { money } from "@/lib/contract-types";

type Row = {
  client_id: number;
  client_code: string | null;
  client_name: string | null;
  older: number;
  months: Record<string, number>;
  total: number;
};

type Ageing = {
  months: string[];
  rows: Row[];
  grand_total: number;
  upto: string;
};

/** The Ageing sheet, reborn: one row per client, one column per month. */
export default function AgeingPage() {
  const [data, setData] = useState<Ageing | null>(null);
  const [months, setMonths] = useState(6);
  const [upto, setUpto] = useState(new Date().toISOString().slice(0, 7));
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const resp = await api.get("/rent/ageing", {
        params: { months, upto: `${upto}-01` },
      });
      setData(resp.data?.data ?? null);
    } catch {
      setData(null);
    } finally { setLoading(false); }
  };

  useEffect(() => { load(); }, [months, upto]);  // eslint-disable-line react-hooks/exhaustive-deps

  const hasOlder = Boolean(data?.rows.some((r) => r.older > 0));

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="print:hidden">
        <Link href="/collections" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft className="h-3.5 w-3.5" /> Back to collections
        </Link>
      </div>

      <div className="flex items-end justify-between flex-wrap gap-2">
        <div>
          <h1 className="text-2xl lg:text-3xl font-semibold tracking-tight">Ageing</h1>
          <p className="text-sm text-muted-foreground">
            Outstanding rent by client and month — what the Ageing sheet used to hold.
          </p>
        </div>
        <div className="flex items-center gap-2 print:hidden">
          <input type="month" className={inputClass + " w-auto"} value={upto}
            onChange={(e) => setUpto(e.target.value)} />
          <select className={selectClass + " !w-auto"} value={months}
            onChange={(e) => setMonths(Number(e.target.value))}>
            <option value={6}>6 months</option>
            <option value={12}>12 months</option>
            <option value={24}>24 months</option>
          </select>
          <button onClick={() => window.print()}
            className="h-9 inline-flex items-center gap-2 rounded-md border border-border bg-card/60 px-3 text-sm hover:bg-accent">
            <Printer className="h-4 w-4" /> Print
          </button>
        </div>
      </div>

      <div className="glass rounded-xl overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-left text-xs text-muted-foreground border-b border-border">
            <tr>
              <th className="py-2 px-3 sticky left-0 bg-card/80">Client</th>
              {hasOlder && <th className="py-2 px-3 text-right">Older</th>}
              {(data?.months ?? []).map((m) => (
                <th key={m} className="py-2 px-3 text-right whitespace-nowrap">
                  {m.slice(0, 7)}
                </th>
              ))}
              <th className="py-2 px-3 text-right">Total</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={(data?.months.length ?? 6) + 3}
                className="py-10 text-center text-muted-foreground">Loading…</td></tr>
            ) : !data || data.rows.length === 0 ? (
              <tr><td colSpan={(data?.months.length ?? 6) + 3}
                className="py-10 text-center text-muted-foreground">
                Nothing outstanding in this window.
              </td></tr>
            ) : data.rows.map((r) => (
              <tr key={r.client_id} className="border-b border-border/60 hover:bg-accent/30">
                <td className="py-2 px-3 sticky left-0 bg-card/80">
                  <Link href={`/collections/${r.client_id}`} className="hover:text-primary">
                    {r.client_name}
                  </Link>
                  <div className="text-[11px] text-muted-foreground font-mono">{r.client_code}</div>
                </td>
                {hasOlder && (
                  <td className="py-2 px-3 text-right text-rose-600">
                    {r.older ? money(r.older) : ""}
                  </td>
                )}
                {data.months.map((m) => (
                  <td key={m} className="py-2 px-3 text-right">
                    {r.months[m] ? money(r.months[m]) : ""}
                  </td>
                ))}
                <td className="py-2 px-3 text-right font-semibold">{money(r.total)}</td>
              </tr>
            ))}
          </tbody>
          {data && data.rows.length > 0 && (
            <tfoot className="border-t-2 border-border font-semibold">
              <tr>
                <td className="py-2 px-3 sticky left-0 bg-card/80">Total</td>
                {hasOlder && (
                  <td className="py-2 px-3 text-right">
                    {money(data.rows.reduce((s, r) => s + r.older, 0))}
                  </td>
                )}
                {data.months.map((m) => (
                  <td key={m} className="py-2 px-3 text-right">
                    {money(data.rows.reduce((s, r) => s + (r.months[m] ?? 0), 0))}
                  </td>
                ))}
                <td className="py-2 px-3 text-right">{money(data.grand_total)}</td>
              </tr>
            </tfoot>
          )}
        </table>
      </div>
    </div>
  );
}
