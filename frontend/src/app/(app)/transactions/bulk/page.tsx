"use client";

import { useMemo, useState } from "react";
import { Banknote, Building2, CheckCircle2, Layers, Loader2, XCircle } from "lucide-react";
import { api } from "@/lib/api";
import { inputClass, selectClass } from "@/components/ui/dialog";
import { money } from "@/lib/contract-types";

type Charge = {
  id: number;
  period_month: string;
  amount: number;
  outstanding: number;
  contract_number?: string | null;
  is_free_month?: boolean;
};

type ClientGroup = {
  kind: "client";
  key: string;
  client: { id: number; code?: string; name: string };
  charges: Charge[];
  total_outstanding: number;
};

type LandlordGroup = {
  kind: "landlord";
  key: string;
  landlord: { id: number; code?: string; name: string };
  property: { id: number; code?: string; name: string };
  contract_id: number | null;
  charges: Charge[];
  total_outstanding: number;
};

type Group = ClientGroup | LandlordGroup;

type PostResult = {
  posted: Array<{ client_id?: number; landlord_id?: number; property_id?: number;
                  receipt_number?: string; voucher_number?: string; amount: number }>;
  failed: Array<{ client_id?: number; landlord_id?: number; property_id?: number; error: string }>;
};

function monthInput(value: string) {
  // <input type="month"> wants YYYY-MM; the API wants YYYY-MM-01.
  return value ? `${value}-01` : "";
}

const todayIso = () => new Date().toISOString().slice(0, 10);
const thisMonth = () => new Date().toISOString().slice(0, 7);

export default function BulkEntryPage() {
  const [mode, setMode] = useState<"receipts" | "landlord">("receipts");
  const [fromMonth, setFromMonth] = useState(thisMonth());
  const [toMonth, setToMonth] = useState(thisMonth());
  const [loading, setLoading] = useState(false);
  const [groups, setGroups] = useState<Group[]>([]);
  const [selected, setSelected] = useState<Record<number, boolean>>({});
  const [amounts, setAmounts] = useState<Record<number, string>>({});
  const [payDate, setPayDate] = useState(todayIso());
  const [payMode, setPayMode] = useState("cash");
  const [posting, setPosting] = useState(false);
  const [result, setResult] = useState<PostResult | null>(null);

  const load = async () => {
    setLoading(true);
    setResult(null);
    try {
      const params = { from_month: monthInput(fromMonth), to_month: monthInput(toMonth) };
      const url = mode === "receipts" ? "/rent/bulk-preview" : "/expenses/landlord-dues/bulk-preview";
      const resp = await api.get(url, { params });
      const rows: Group[] = (resp.data?.data ?? []).map((r: Record<string, unknown>) =>
        mode === "receipts"
          ? { kind: "client", key: `c${(r.client as { id: number }).id}`, ...r }
          : {
              kind: "landlord",
              key: `l${(r.landlord as { id: number }).id}-${(r.property as { id: number }).id}`,
              ...r,
            },
      );
      setGroups(rows);
      const nextSelected: Record<number, boolean> = {};
      const nextAmounts: Record<number, string> = {};
      for (const g of rows) {
        for (const c of g.charges) {
          nextSelected[c.id] = c.outstanding > 0;
          nextAmounts[c.id] = String(c.outstanding);
        }
      }
      setSelected(nextSelected);
      setAmounts(nextAmounts);
    } finally {
      setLoading(false);
    }
  };

  const toggleGroup = (g: Group, value: boolean) => {
    setSelected((prev) => {
      const next = { ...prev };
      for (const c of g.charges) next[c.id] = value;
      return next;
    });
  };

  const selectedTotal = useMemo(() => {
    let total = 0;
    for (const g of groups) {
      for (const c of g.charges) {
        if (selected[c.id]) total += Number(amounts[c.id] || 0);
      }
    }
    return Math.round(total * 100) / 100;
  }, [groups, selected, amounts]);

  const selectedCount = useMemo(
    () => groups.reduce((n, g) => n + g.charges.filter((c) => selected[c.id]).length, 0),
    [groups, selected],
  );

  const post = async () => {
    const entries = groups
      .map((g) => {
        const allocations = g.charges
          .filter((c) => selected[c.id] && Number(amounts[c.id] || 0) > 0)
          .map((c) => ({ charge_id: c.id, amount: Number(amounts[c.id]) }));
        if (allocations.length === 0) return null;
        return g.kind === "client"
          ? { client_id: g.client.id, allocations }
          : { landlord_id: g.landlord.id, property_id: g.property.id,
              contract_id: g.contract_id, allocations };
      })
      .filter((e): e is NonNullable<typeof e> => e !== null);

    if (entries.length === 0) return;
    setPosting(true);
    setResult(null);
    try {
      const url = mode === "receipts" ? "/rent/bulk-post" : "/expenses/landlord-dues/bulk-post";
      const body = mode === "receipts"
        ? { receipt_date: payDate, mode: payMode, entries }
        : { payment_date: payDate, mode: payMode, entries };
      const resp = await api.post(url, body);
      await load();
      setResult(resp.data?.data ?? null);
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { data?: PostResult } } };
      await load();
      if (axiosErr.response?.data?.data) setResult(axiosErr.response.data.data);
    } finally {
      setPosting(false);
    }
  };

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h1 className="text-2xl lg:text-3xl font-semibold tracking-tight">Bulk Entry</h1>
        <p className="text-sm text-muted-foreground">
          Post receipts from many clients, or payments to many landlords, across a month range in
          one batch — with room to edit amounts for partial payment before posting.
        </p>
      </div>

      <div className="glass rounded-xl p-4 space-y-4">
        <div className="flex items-center gap-2 flex-wrap">
          <div className="inline-flex rounded-lg border border-border p-0.5 bg-card/60">
            <button
              onClick={() => { setMode("receipts"); setGroups([]); setResult(null); }}
              className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                mode === "receipts" ? "bg-primary/10 text-primary" : "text-muted-foreground hover:text-foreground"
              }`}
            >
              <Banknote className="h-3.5 w-3.5" /> Client Receipts
            </button>
            <button
              onClick={() => { setMode("landlord"); setGroups([]); setResult(null); }}
              className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                mode === "landlord" ? "bg-primary/10 text-primary" : "text-muted-foreground hover:text-foreground"
              }`}
            >
              <Building2 className="h-3.5 w-3.5" /> Landlord Payments
            </button>
          </div>

          <div className="flex items-center gap-2 ml-auto flex-wrap">
            <label className="text-xs text-muted-foreground">From</label>
            <input type="month" value={fromMonth} onChange={(e) => setFromMonth(e.target.value)}
                  className={inputClass + " !w-auto"} />
            <label className="text-xs text-muted-foreground">To</label>
            <input type="month" value={toMonth} onChange={(e) => setToMonth(e.target.value)}
                  className={inputClass + " !w-auto"} />
            <button onClick={load} disabled={loading}
                    className="h-9 rounded-md border border-border bg-card/60 px-3 text-sm hover:bg-accent disabled:opacity-50 inline-flex items-center gap-1.5">
              {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Layers className="h-3.5 w-3.5" />}
              Load outstanding
            </button>
          </div>
        </div>
      </div>

      {result && (
        <div className="glass rounded-xl p-4 space-y-2">
          <div className="text-sm font-medium">
            {result.posted.length} posted{result.failed.length > 0 ? `, ${result.failed.length} failed` : ""}
          </div>
          {result.posted.length > 0 && (
            <ul className="text-xs text-muted-foreground space-y-0.5">
              {result.posted.map((p, i) => (
                <li key={i} className="inline-flex items-center gap-1.5 mr-4">
                  <CheckCircle2 className="h-3 w-3 text-emerald-600" />
                  {p.receipt_number || p.voucher_number} — {money(p.amount)}
                </li>
              ))}
            </ul>
          )}
          {result.failed.length > 0 && (
            <ul className="text-xs text-red-600 space-y-0.5">
              {result.failed.map((f, i) => (
                <li key={i} className="inline-flex items-center gap-1.5">
                  <XCircle className="h-3 w-3" /> {f.error}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {groups.length === 0 && !loading && (
        <div className="glass rounded-xl p-8 text-center text-sm text-muted-foreground">
          Pick a month range and click &ldquo;Load outstanding&rdquo; to see who has dues in that window.
        </div>
      )}

      <div className="space-y-3">
        {groups.map((g) => {
          const allChecked = g.charges.every((c) => selected[c.id]);
          const label = g.kind === "client" ? g.client.name : `${g.landlord.name} — ${g.property.name}`;
          const sub = g.kind === "client" ? g.client.code : g.property.code;
          return (
            <div key={g.key} className="glass rounded-xl overflow-hidden">
              <div className="flex items-center justify-between px-4 py-3 border-b border-border bg-card/40">
                <label className="flex items-center gap-2 text-sm font-medium cursor-pointer">
                  <input type="checkbox" checked={allChecked}
                         onChange={(e) => toggleGroup(g, e.target.checked)} />
                  {label}
                  {sub && <span className="text-xs text-muted-foreground font-mono">{sub}</span>}
                </label>
                <span className="text-sm font-medium">{money(g.total_outstanding)} outstanding</span>
              </div>
              <div className="divide-y divide-border">
                {g.charges.map((c) => (
                  <div key={c.id} className="flex items-center gap-3 px-4 py-2 text-sm">
                    <input type="checkbox" checked={!!selected[c.id]}
                           onChange={(e) => setSelected((prev) => ({ ...prev, [c.id]: e.target.checked }))} />
                    <span className="font-mono text-xs w-24 shrink-0">{c.period_month}</span>
                    {c.contract_number && (
                      <span className="text-xs text-muted-foreground font-mono w-32 shrink-0 truncate">
                        {c.contract_number}
                      </span>
                    )}
                    <span className="text-xs text-muted-foreground w-24 shrink-0">Due {money(c.amount)}</span>
                    <span className="text-xs text-muted-foreground w-28 shrink-0">
                      Outstanding {money(c.outstanding)}
                    </span>
                    <div className="ml-auto flex items-center gap-1.5">
                      <span className="text-xs text-muted-foreground">
                        {mode === "receipts" ? "Receive now" : "Pay now"}
                      </span>
                      <input
                        type="number" step="0.01" min={0} max={c.outstanding}
                        value={amounts[c.id] ?? ""}
                        onChange={(e) => setAmounts((prev) => ({ ...prev, [c.id]: e.target.value }))}
                        className={inputClass + " !w-28 !h-8 text-right"}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>

      {groups.length > 0 && (
        <div className="sticky bottom-4 glass-strong rounded-xl p-4 flex items-center gap-3 flex-wrap shadow-xl">
          <div className="text-sm">
            <span className="font-semibold">{selectedCount}</span> row(s) selected —{" "}
            <span className="font-semibold">{money(selectedTotal)}</span> total
          </div>
          <div className="flex items-center gap-2 ml-auto flex-wrap">
            <input type="date" value={payDate} onChange={(e) => setPayDate(e.target.value)}
                  className={inputClass + " !w-auto"} />
            <select value={payMode} onChange={(e) => setPayMode(e.target.value)}
                    className={selectClass + " !w-auto"}>
              <option value="cash">Cash</option>
              <option value="cheque">Cheque</option>
              <option value="online">Online</option>
            </select>
            <button
              onClick={post}
              disabled={posting || selectedTotal <= 0}
              className="h-9 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 inline-flex items-center gap-1.5"
            >
              {posting && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
              Post batch
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
