"use client";

import { useMemo, useState } from "react";
import {
  Banknote, Building2, CheckCircle2, Layers, Loader2, XCircle, Search,
} from "lucide-react";
import { api } from "@/lib/api";
import { toast, errorMessage } from "@/components/ui/toast";
import { money } from "@/lib/contract-types";

/* ─── types ─── */
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
  posted: { client_id?: number; landlord_id?: number; property_id?: number;
             receipt_number?: string; voucher_number?: string; amount: number }[];
  failed: { client_id?: number; landlord_id?: number; property_id?: number; error: string }[];
};

/* ─── helpers ─── */
function monthsInRange(from: string, to: string): string[] {
  const months: string[] = [];
  let [fy, fm] = from.split("-").map(Number);
  const [ty, tm] = to.split("-").map(Number);
  while (fy < ty || (fy === ty && fm <= tm)) {
    months.push(`${fy}-${String(fm).padStart(2, "0")}`);
    fm++; if (fm > 12) { fm = 1; fy++; }
  }
  return months;
}

function monthLabel(yyyyMM: string): string {
  const [y, m] = yyyyMM.split("-");
  return new Date(Number(y), Number(m) - 1, 1)
    .toLocaleDateString("en-US", { month: "short", year: "2-digit" });
}

const todayIso = () => new Date().toISOString().slice(0, 10);
const thisMonth = () => new Date().toISOString().slice(0, 7);

const PAYMENT_MODES = [
  { value: "cash", label: "Cash" },
  { value: "cheque", label: "Cheque" },
  { value: "transfer", label: "Transfer" },
  { value: "online", label: "Online" },
];

/* ─── component ─── */
export default function BulkEntryPage() {
  const [tab, setTab] = useState<"receipts" | "landlord">("receipts");
  const [fromMonth, setFromMonth] = useState(thisMonth());
  const [toMonth, setToMonth] = useState(thisMonth());
  const [loading, setLoading] = useState(false);
  const [groups, setGroups] = useState<Group[]>([]);

  /* per-charge state */
  const [selected, setSelected] = useState<Record<number, boolean>>({});
  const [amounts, setAmounts] = useState<Record<number, string>>({});

  /* per-row state */
  const [rowModes, setRowModes] = useState<Record<string, string>>({});
  const [rowDates, setRowDates] = useState<Record<string, string>>({});

  /* batch state */
  const [payDate, setPayDate] = useState(todayIso());
  const [payMode, setPayMode] = useState("cash");
  const [posting, setPosting] = useState(false);
  const [postingRow, setPostingRow] = useState<string | null>(null);
  const [result, setResult] = useState<PostResult | null>(null);

  /* filter state */
  const [filterQ, setFilterQ] = useState("");
  const [filterStatus, setFilterStatus] = useState<"all" | "unpaid" | "paid">("all");

  /* ─── derived ─── */
  const months = useMemo(() => monthsInRange(fromMonth, toMonth), [fromMonth, toMonth]);

  const filteredGroups = useMemo(() => {
    let list = groups;
    if (filterQ) {
      const q = filterQ.toLowerCase();
      list = list.filter((g) =>
        g.kind === "client"
          ? g.client.name.toLowerCase().includes(q) || (g.client.code ?? "").toLowerCase().includes(q)
          : g.landlord.name.toLowerCase().includes(q) || g.property.name.toLowerCase().includes(q),
      );
    }
    if (filterStatus === "unpaid") list = list.filter((g) => g.total_outstanding > 0);
    if (filterStatus === "paid") list = list.filter((g) => g.total_outstanding === 0);
    return list;
  }, [groups, filterQ, filterStatus]);

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

  const allFilteredSelected = useMemo(
    () => filteredGroups.length > 0 && filteredGroups.every((g) =>
      g.charges.filter((c) => c.outstanding > 0).every((c) => selected[c.id])
    ),
    [filteredGroups, selected],
  );

  /* ─── actions ─── */
  const load = async () => {
    setLoading(true);
    setResult(null);
    try {
      const params = {
        from_month: `${fromMonth}-01`,
        to_month: `${toMonth}-01`,
      };
      const url = tab === "receipts" ? "/rent/bulk-preview" : "/expenses/landlord-dues/bulk-preview";
      const resp = await api.get(url, { params });
      const rows: Group[] = (resp.data?.data ?? []).map((r: Record<string, unknown>) =>
        tab === "receipts"
          ? { kind: "client", key: `c${(r.client as { id: number }).id}`, ...r }
          : { kind: "landlord",
              key: `l${(r.landlord as { id: number }).id}-${(r.property as { id: number }).id}`,
              ...r },
      );
      setGroups(rows);
      const nextSelected: Record<number, boolean> = {};
      const nextAmounts: Record<number, string> = {};
      const nextModes: Record<string, string> = {};
      const nextDates: Record<string, string> = {};
      for (const g of rows) {
        nextModes[g.key] = "cash";
        nextDates[g.key] = todayIso();
        for (const c of g.charges) {
          nextSelected[c.id] = c.outstanding > 0;
          nextAmounts[c.id] = String(c.outstanding);
        }
      }
      setSelected(nextSelected);
      setAmounts(nextAmounts);
      setRowModes(nextModes);
      setRowDates(nextDates);
    } finally {
      setLoading(false);
    }
  };

  const toggleGroup = (g: Group, value: boolean) => {
    setSelected((prev) => {
      const next = { ...prev };
      for (const c of g.charges) if (c.outstanding > 0) next[c.id] = value;
      return next;
    });
  };

  const toggleAll = (value: boolean) => {
    setSelected((prev) => {
      const next = { ...prev };
      for (const g of filteredGroups) {
        for (const c of g.charges) if (c.outstanding > 0) next[c.id] = value;
      }
      return next;
    });
  };

  const applyModeToAll = (mode: string) => {
    setRowModes((prev) => {
      const next = { ...prev };
      for (const g of filteredGroups) next[g.key] = mode;
      return next;
    });
  };

  const postRow = async (g: Group) => {
    const rMode = rowModes[g.key] || "cash";
    const rDate = rowDates[g.key] || todayIso();
    const allocations = g.charges
      .filter((c) => c.outstanding > 0 && Number(amounts[c.id] ?? c.outstanding) > 0)
      .map((c) => ({ charge_id: c.id, amount: Number(amounts[c.id] ?? c.outstanding) }));
    if (!allocations.length) return;
    setPostingRow(g.key);
    try {
      const url = tab === "receipts" ? "/rent/bulk-post" : "/expenses/landlord-dues/bulk-post";
      const entry = g.kind === "client"
        ? { client_id: g.client.id, allocations }
        : { landlord_id: g.landlord.id, property_id: g.property.id,
            contract_id: g.contract_id, allocations };
      const body = tab === "receipts"
        ? { receipt_date: rDate, mode: rMode, entries: [entry] }
        : { payment_date: rDate, mode: rMode, entries: [entry] };
      const resp = await api.post(url, body);
      const posted = resp.data?.data?.posted ?? [];
      toast.success(
        "Posted",
        posted.map((p: { receipt_number?: string; voucher_number?: string; amount: number }) =>
          `${p.receipt_number || p.voucher_number} (${money(p.amount)})`).join(", ") || "Success",
      );
      await load();
    } catch (err: unknown) {
      toast.error("Post failed", errorMessage(err));
    } finally {
      setPostingRow(null);
    }
  };

  const postBatch = async () => {
    const entries = groups
      .map((g) => {
        const allocations = g.charges
          .filter((c) => selected[c.id] && Number(amounts[c.id] || 0) > 0)
          .map((c) => ({ charge_id: c.id, amount: Number(amounts[c.id]) }));
        if (!allocations.length) return null;
        return g.kind === "client"
          ? { client_id: g.client.id, allocations }
          : { landlord_id: g.landlord.id, property_id: g.property.id,
              contract_id: g.contract_id, allocations };
      })
      .filter((e): e is NonNullable<typeof e> => e !== null);
    if (!entries.length) return;
    setPosting(true);
    setResult(null);
    try {
      const url = tab === "receipts" ? "/rent/bulk-post" : "/expenses/landlord-dues/bulk-post";
      const body = tab === "receipts"
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

  /* ─── render ─── */
  return (
    <div className="space-y-5 animate-fade-in">
      {/* Header */}
      <div>
        <h1 className="text-2xl lg:text-3xl font-semibold tracking-tight">Bulk Entry</h1>
        <p className="text-sm text-muted-foreground">
          Post receipts or landlord payments across a month range — edit amounts per row before posting.
        </p>
      </div>

      {/* Controls bar */}
      <div className="glass rounded-xl p-4 space-y-3">
        {/* Tab + month range */}
        <div className="flex items-center gap-3 flex-wrap">
          <div className="inline-flex rounded-lg border border-border p-0.5 bg-card/60">
            {(["receipts", "landlord"] as const).map((t) => (
              <button key={t}
                onClick={() => { setTab(t); setGroups([]); setResult(null); }}
                className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                  tab === t ? "bg-primary/10 text-primary" : "text-muted-foreground hover:text-foreground"
                }`}>
                {t === "receipts" ? <Banknote className="h-3.5 w-3.5" /> : <Building2 className="h-3.5 w-3.5" />}
                {t === "receipts" ? "Client Receipts" : "Landlord Payments"}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-2 ml-auto flex-wrap">
            <span className="text-xs text-muted-foreground">From</span>
            <input type="month" value={fromMonth} onChange={(e) => setFromMonth(e.target.value)}
              className="h-8 rounded-md border border-input bg-card/60 px-2 text-sm w-auto" />
            <span className="text-xs text-muted-foreground">To</span>
            <input type="month" value={toMonth} onChange={(e) => setToMonth(e.target.value)}
              className="h-8 rounded-md border border-input bg-card/60 px-2 text-sm w-auto" />
            <button onClick={load} disabled={loading}
              className="h-8 rounded-md border border-border bg-card/60 px-3 text-sm hover:bg-accent disabled:opacity-50 inline-flex items-center gap-1.5">
              {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Layers className="h-3.5 w-3.5" />}
              Load outstanding
            </button>
          </div>
        </div>

        {/* Filters — only show once data is loaded */}
        {groups.length > 0 && (
          <div className="flex items-center gap-2 flex-wrap pt-1 border-t border-border/60">
            <div className="relative">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground pointer-events-none" />
              <input value={filterQ} onChange={(e) => setFilterQ(e.target.value)}
                placeholder={tab === "receipts" ? "Search client…" : "Search landlord or property…"}
                className="h-8 pl-8 pr-3 w-52 rounded-md border border-input bg-card/60 text-sm" />
            </div>
            <select value={filterStatus} onChange={(e) => setFilterStatus(e.target.value as typeof filterStatus)}
              className="h-8 rounded-md border border-input bg-card/60 px-2 text-sm">
              <option value="all">All ({groups.length})</option>
              <option value="unpaid">Has dues ({groups.filter(g => g.total_outstanding > 0).length})</option>
              <option value="paid">Fully paid ({groups.filter(g => g.total_outstanding === 0).length})</option>
            </select>
            <div className="flex items-center gap-1.5 ml-auto text-xs text-muted-foreground">
              <span>Set all mode:</span>
              {PAYMENT_MODES.map((m) => (
                <button key={m.value} onClick={() => applyModeToAll(m.value)}
                  className="h-6 px-2 rounded-md border border-border hover:bg-accent text-xs">
                  {m.label}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Post result banner */}
      {result && (
        <div className="glass rounded-xl p-4 space-y-2">
          <div className="text-sm font-medium flex items-center gap-2">
            {result.failed.length === 0
              ? <CheckCircle2 className="h-4 w-4 text-emerald-600" />
              : <XCircle className="h-4 w-4 text-rose-600" />}
            {result.posted.length} posted{result.failed.length > 0 ? `, ${result.failed.length} failed` : " successfully"}
          </div>
          {result.posted.length > 0 && (
            <div className="flex flex-wrap gap-x-4 gap-y-1">
              {result.posted.map((p, i) => (
                <span key={i} className="text-xs text-emerald-700 dark:text-emerald-400 inline-flex items-center gap-1">
                  <CheckCircle2 className="h-3 w-3" />
                  {p.receipt_number || p.voucher_number} — {money(p.amount)}
                </span>
              ))}
            </div>
          )}
          {result.failed.length > 0 && (
            <div className="flex flex-wrap gap-x-4 gap-y-1">
              {result.failed.map((f, i) => (
                <span key={i} className="text-xs text-rose-600 inline-flex items-center gap-1">
                  <XCircle className="h-3 w-3" /> {f.error}
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Empty state */}
      {groups.length === 0 && !loading && (
        <div className="glass rounded-xl p-10 text-center text-sm text-muted-foreground">
          Pick a month range and click <strong>Load outstanding</strong> to see dues in that window.
        </div>
      )}

      {/* ── Spreadsheet table ── */}
      {filteredGroups.length > 0 && (
        <div className="glass rounded-xl overflow-hidden">
          <div className="overflow-auto" style={{ maxHeight: "calc(100vh - 340px)" }}>
            <table className="min-w-full text-sm border-collapse">
              <thead>
                <tr className="sticky top-0 z-30 bg-muted/80 backdrop-blur-sm border-b border-border">
                  {/* Select-all checkbox */}
                  <th className="sticky left-0 z-20 bg-muted/80 backdrop-blur-sm w-10 px-3 py-2.5 text-left">
                    <input type="checkbox" checked={allFilteredSelected}
                      onChange={(e) => toggleAll(e.target.checked)} />
                  </th>
                  {/* Client / Landlord name */}
                  <th className="sticky left-10 z-20 bg-muted/80 backdrop-blur-sm min-w-[200px] px-3 py-2.5 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wide whitespace-nowrap">
                    {tab === "receipts" ? "Client" : "Landlord / Property"}
                  </th>
                  {/* Mode */}
                  <th className="min-w-[100px] px-3 py-2.5 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wide whitespace-nowrap">
                    Mode
                  </th>
                  {/* Month columns */}
                  {months.map((m) => (
                    <th key={m} className="min-w-[90px] px-2 py-2.5 text-center text-xs font-semibold text-muted-foreground uppercase tracking-wide whitespace-nowrap">
                      {monthLabel(m)}
                    </th>
                  ))}
                  {/* Outstanding */}
                  <th className="min-w-[110px] px-3 py-2.5 text-right text-xs font-semibold text-muted-foreground uppercase tracking-wide whitespace-nowrap">
                    Outstanding
                  </th>
                  {/* Date */}
                  <th className="min-w-[130px] px-3 py-2.5 text-center text-xs font-semibold text-muted-foreground uppercase tracking-wide whitespace-nowrap">
                    Date
                  </th>
                  {/* Action — sticky right */}
                  <th className="sticky right-0 z-20 bg-muted/80 backdrop-blur-sm min-w-[80px] px-3 py-2.5 text-center text-xs font-semibold text-muted-foreground uppercase tracking-wide whitespace-nowrap">
                    Action
                  </th>
                </tr>
              </thead>
              <tbody>
                {filteredGroups.map((g, idx) => {
                  const chargeMap: Record<string, Charge> = {};
                  for (const c of g.charges) chargeMap[c.period_month.slice(0, 7)] = c;

                  const label = g.kind === "client" ? g.client.name : g.landlord.name;
                  const sub = g.kind === "client" ? g.client.code : g.property.name;
                  const hasUnpaid = g.charges.some((c) => c.outstanding > 0);
                  const unpaidCharges = g.charges.filter((c) => c.outstanding > 0);
                  const allRowSelected = unpaidCharges.length > 0 && unpaidCharges.every((c) => selected[c.id]);
                  const rowBg = idx % 2 === 0 ? "bg-card" : "bg-muted/20";

                  return (
                    <tr key={g.key} className={`${rowBg} hover:bg-accent/10 transition-colors`}>
                      {/* Checkbox */}
                      <td className={`sticky left-0 z-10 ${rowBg} border-b border-border/40 px-3 py-2`}>
                        <input type="checkbox" checked={allRowSelected} disabled={!hasUnpaid}
                          onChange={(e) => toggleGroup(g, e.target.checked)} />
                      </td>
                      {/* Name */}
                      <td className={`sticky left-10 z-10 ${rowBg} border-b border-border/40 px-3 py-2 min-w-[200px]`}>
                        <div className="font-medium text-sm truncate max-w-[190px]" title={label}>{label}</div>
                        {sub && <div className="text-xs text-muted-foreground font-mono">{sub}</div>}
                      </td>
                      {/* Mode selector */}
                      <td className="border-b border-border/40 px-2 py-1.5">
                        <select
                          value={rowModes[g.key] || "cash"}
                          onChange={(e) => setRowModes((prev) => ({ ...prev, [g.key]: e.target.value }))}
                          className="h-7 w-24 rounded-md border border-input bg-card/80 px-1.5 text-xs">
                          {PAYMENT_MODES.map((m) => (
                            <option key={m.value} value={m.value}>{m.label}</option>
                          ))}
                        </select>
                      </td>
                      {/* Monthly amount cells */}
                      {months.map((m) => {
                        const charge = chargeMap[m];
                        if (!charge) {
                          return (
                            <td key={m} className="border-b border-border/40 px-2 py-2 text-center">
                              <span className="text-muted-foreground/30 text-xs">—</span>
                            </td>
                          );
                        }
                        const isPaid = charge.outstanding === 0;
                        const val = amounts[charge.id] ?? String(charge.outstanding);
                        return (
                          <td key={m} className="border-b border-border/40 px-1 py-1">
                            {isPaid ? (
                              <div className="mx-0.5 h-7 flex items-center justify-end rounded-md px-2 bg-emerald-50 dark:bg-emerald-950/30">
                                <span className="text-xs font-semibold text-emerald-700 dark:text-emerald-400 whitespace-nowrap">
                                  {charge.amount.toLocaleString()}
                                </span>
                              </div>
                            ) : (
                              <input
                                type="number"
                                step="0.01"
                                min={0}
                                value={val}
                                onChange={(e) => {
                                  setSelected((prev) => ({ ...prev, [charge.id]: true }));
                                  setAmounts((prev) => ({ ...prev, [charge.id]: e.target.value }));
                                }}
                                className="w-full h-7 text-right text-xs rounded-md px-2 bg-orange-50 dark:bg-orange-950/30 text-orange-700 dark:text-orange-300 font-semibold border border-orange-200 dark:border-orange-800 outline-none focus:ring-1 focus:ring-primary"
                              />
                            )}
                          </td>
                        );
                      })}
                      {/* Outstanding total */}
                      <td className="border-b border-border/40 px-3 py-2 text-right whitespace-nowrap">
                        <span className={`text-sm font-semibold ${g.total_outstanding > 0 ? "text-rose-600" : "text-emerald-600"}`}>
                          {money(g.total_outstanding)}
                        </span>
                      </td>
                      {/* Date */}
                      <td className="border-b border-border/40 px-2 py-1.5 text-center">
                        <input
                          type="date"
                          value={rowDates[g.key] || todayIso()}
                          onChange={(e) => setRowDates((prev) => ({ ...prev, [g.key]: e.target.value }))}
                          className="h-7 rounded-md border border-input bg-card/80 px-1.5 text-xs w-32"
                        />
                      </td>
                      {/* POST button — sticky right */}
                      <td className={`sticky right-0 z-10 ${rowBg} border-b border-border/40 px-2 py-1.5 text-center`}>
                        <button
                          onClick={() => postRow(g)}
                          disabled={postingRow === g.key || !hasUnpaid}
                          className="h-7 px-3 rounded-md bg-primary text-primary-foreground text-xs font-semibold hover:bg-primary/90 disabled:opacity-40 inline-flex items-center gap-1 whitespace-nowrap">
                          {postingRow === g.key && <Loader2 className="h-3 w-3 animate-spin" />}
                          POST
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Legend */}
          <div className="px-4 py-2 border-t border-border/60 flex items-center gap-4 text-xs text-muted-foreground">
            <span className="inline-flex items-center gap-1.5">
              <span className="h-3 w-3 rounded-sm bg-emerald-100 dark:bg-emerald-950/60 border border-emerald-300 dark:border-emerald-700" />
              Paid — readonly
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="h-3 w-3 rounded-sm bg-orange-100 dark:bg-orange-950/60 border border-orange-300 dark:border-orange-700" />
              Unpaid — editable
            </span>
            <span className="ml-auto">{filteredGroups.length} rows · {months.length} month{months.length !== 1 ? "s" : ""}</span>
          </div>
        </div>
      )}

      {/* ── Sticky batch footer ── */}
      {groups.length > 0 && (
        <div className="sticky bottom-4 z-40">
          <div className="glass-strong rounded-xl p-4 flex items-center gap-3 flex-wrap shadow-2xl border border-border/60">
            <div>
              <div className="text-sm font-semibold">
                {selectedCount} row{selectedCount !== 1 ? "s" : ""} selected
              </div>
              <div className="text-xs text-muted-foreground">{money(selectedTotal)} total</div>
            </div>
            <div className="h-8 w-px bg-border mx-1" />
            <div className="flex items-center gap-2 ml-auto flex-wrap">
              <input type="date" value={payDate} onChange={(e) => setPayDate(e.target.value)}
                className="h-9 rounded-md border border-input bg-card/60 px-2 text-sm w-auto" />
              <select value={payMode} onChange={(e) => setPayMode(e.target.value)}
                className="h-9 rounded-md border border-input bg-card/60 px-2 text-sm">
                {PAYMENT_MODES.map((m) => (
                  <option key={m.value} value={m.value}>{m.label}</option>
                ))}
              </select>
              <button
                onClick={postBatch}
                disabled={posting || selectedTotal <= 0}
                className="h-9 rounded-md bg-primary px-5 text-sm font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-50 inline-flex items-center gap-1.5">
                {posting && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                POST BATCH
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
