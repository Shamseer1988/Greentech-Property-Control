"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Banknote, ArrowLeft, CalendarClock, CheckCircle2 } from "lucide-react";
import { api } from "@/lib/api";
import { Can } from "@/components/can";
import { inputClass } from "@/components/ui/dialog";
import { ReceiptDialog } from "@/components/receipt-dialog";
import { money } from "@/lib/contract-types";

type Charge = {
  id: number;
  contract_id: number;
  contract_number: string;
  period_month: string;
  amount: number;
  outstanding: number;
  status: string;
  client: { id: number; code: string; name: string };
};

type PropertyGroup = {
  property_id: number;
  property_code: string;
  property_name: string;
  charges: Charge[];
  total_due: number;
};

type CashDue = {
  period: string;
  window_open: boolean;
  window: { start_day: number; end_day: number };
  properties: PropertyGroup[];
  total_due: number;
  count: number;
};

function thisMonth(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export default function CashDueBookingPage() {
  const [month, setMonth] = useState(thisMonth());
  const [data, setData] = useState<CashDue | null>(null);
  const [loading, setLoading] = useState(true);
  const [receiptFor, setReceiptFor] = useState<Charge | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      const resp = await api.get("/rent/cash-due", { params: { month: `${month}-01` } });
      setData(resp.data?.data ?? null);
    } catch {
      setData(null);
    } finally { setLoading(false); }
  };

  useEffect(() => { load(); }, [month]);  // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-end justify-between flex-wrap gap-2">
        <div>
          <Link href="/collections" className="text-xs text-muted-foreground hover:text-foreground inline-flex items-center gap-1 mb-1">
            <ArrowLeft className="h-3.5 w-3.5" /> Collections
          </Link>
          <h1 className="text-2xl lg:text-3xl font-semibold tracking-tight">Cash due booking</h1>
          <p className="text-sm text-muted-foreground">
            Cash-mode tenancies still owing this month — the run collectors work between the 5th and 15th.
          </p>
        </div>
        <input type="month" className={inputClass + " w-auto"} value={month}
          onChange={(e) => setMonth(e.target.value)} />
      </div>

      {data && (
        <div className={
          "rounded-xl p-4 flex items-center gap-3 border " +
          (data.window_open
            ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-700 dark:text-emerald-400"
            : "bg-muted/40 border-border text-muted-foreground")
        }>
          {data.window_open ? <CheckCircle2 className="h-5 w-5 shrink-0" /> : <CalendarClock className="h-5 w-5 shrink-0" />}
          <div className="text-sm">
            {data.window_open
              ? `The ${data.window.start_day}th–${data.window.end_day}th collection window is open.`
              : `Outside the ${data.window.start_day}th–${data.window.end_day}th collection window — still bookable, just early or late.`}
            {" "}
            <span className="font-medium">{money(data.total_due)}</span> outstanding across{" "}
            <span className="font-medium">{data.count}</span> charge{data.count === 1 ? "" : "s"}.
          </div>
        </div>
      )}

      {loading ? (
        <div className="glass rounded-xl p-10 text-center text-muted-foreground">Loading…</div>
      ) : !data || data.properties.length === 0 ? (
        <div className="glass rounded-xl p-10 text-center text-muted-foreground">
          Nothing outstanding for cash-mode tenancies this month.
        </div>
      ) : (
        <div className="space-y-4">
          {data.properties.map((p) => (
            <div key={p.property_id} className="glass rounded-xl overflow-hidden">
              <div className="px-4 py-3 border-b border-border/60 flex items-center justify-between">
                <div>
                  <div className="font-medium">{p.property_name}</div>
                  <div className="text-xs text-muted-foreground font-mono">{p.property_code}</div>
                </div>
                <div className="text-sm font-semibold">{money(p.total_due)}</div>
              </div>
              <table className="w-full text-sm">
                <tbody>
                  {p.charges.map((c) => (
                    <tr key={c.id} className="border-b border-border/40 last:border-0 hover:bg-accent/30">
                      <td className="py-2 px-4">
                        <div className="font-medium">{c.client.name}</div>
                        <div className="text-xs text-muted-foreground font-mono">
                          {c.client.code} · {c.contract_number}
                        </div>
                      </td>
                      <td className="py-2 px-4 text-right font-semibold">{money(c.outstanding)}</td>
                      <td className="py-2 px-4 text-right w-24">
                        <Can perm="receipt.create">
                          <button onClick={() => setReceiptFor(c)} title="Mark received"
                            className="inline-flex items-center gap-1.5 h-8 rounded-md border border-border px-2.5 text-xs hover:bg-accent">
                            <Banknote className="h-3.5 w-3.5" /> Receive
                          </button>
                        </Can>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
        </div>
      )}

      <ReceiptDialog
        open={Boolean(receiptFor)}
        clientId={receiptFor?.client.id ?? null}
        clientName={receiptFor?.client.name ?? null}
        onClose={() => setReceiptFor(null)}
        onPosted={async () => { setReceiptFor(null); await load(); }}
      />
    </div>
  );
}
