"use client";

import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useRouteParams } from "@/lib/use-route-params";
import Link from "next/link";
import {
  ArrowLeft, Download, FileDown, Printer, Eye, EyeOff, ArrowUp, ArrowDown,
} from "lucide-react";
import {
  useReactTable, getCoreRowModel, getSortedRowModel, getPaginationRowModel, flexRender,
  type ColumnDef, type SortingState, type VisibilityState,
} from "@tanstack/react-table";
import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight } from "lucide-react";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from "recharts";
import { api } from "@/lib/api";
import { Can } from "@/components/can";
import { ErrorBoundary } from "@/components/error-boundary";
import { inputClass, selectClass } from "@/components/ui/dialog";
import { toast, errorMessage } from "@/components/ui/toast";
import { keys } from "@/lib/query-keys";

function renderCellValue(v: unknown): React.ReactNode {
  if (v === null || v === undefined || v === "") {
    return <span className="text-muted-foreground">—</span>;
  }
  if (typeof v === "boolean") return v ? "yes" : "no";
  if (typeof v === "number") return Number.isInteger(v) ? v.toString() : v.toLocaleString();
  if (typeof v === "string") return v;
  // Defensive: stringify objects / arrays so a stray nested object never
  // crashes the whole report viewer.
  try {
    return JSON.stringify(v);
  } catch {
    return String(v);
  }
}

type Column = { key: string; label: string; width?: number };
type Row = Record<string, unknown>;
type ReportPayload = { columns: Column[]; rows: Row[]; meta?: Record<string, unknown> };
type ReportInfo = { slug: string; title: string; category: string; description: string };

type FilterField = {
  key: string;
  label: string;
  type: "text" | "number" | "select" | "date" | "month" | "property";
  options?: { value: string; label: string }[];
  placeholder?: string;
};

/** Month-keyed reports default to the current month server-side. Seed
 * the control with it too, otherwise the field reads blank while the
 * table shows figures — which looks like a bug even though it isn't. */
function thisMonth() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-01`;
}

function monthsAgo(n: number) {
  const d = new Date();
  d.setDate(1);
  d.setMonth(d.getMonth() - n);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-01`;
}

const FILTERS: Record<string, FilterField[]> = {
  "property-occupancy": [
    { key: "status", label: "Status", type: "select", options: [
      { value: "", label: "All" },
      { value: "active", label: "Active" },
      { value: "inactive", label: "Inactive" },
      { value: "maintenance", label: "Maintenance" },
      { value: "vacated", label: "Vacated" },
    ]},
    { key: "city", label: "City", type: "text", placeholder: "Doha" },
  ],
  "empty-units": [
    { key: "property_id", label: "Property", type: "property" },
  ],
  "empty-units-trend": [
    { key: "start", label: "From month", type: "month" },
    { key: "end", label: "To month", type: "month" },
    { key: "property_id", label: "Property (blank = every camp)", type: "property" },
  ],
  "agreement-expiry": [
    { key: "property_id", label: "Property", type: "property" },
    { key: "bucket", label: "Bucket", type: "select", options: [
      { value: "", label: "All" },
      { value: "expired", label: "Expired" },
      { value: "7", label: "Within 7 days" },
      { value: "30", label: "Within 30 days" },
      { value: "60", label: "Within 60 days" },
      { value: "90", label: "Within 90 days" },
    ]},
  ],
  "rent-collection": [
    { key: "month", label: "Month", type: "month" },
    { key: "property_id", label: "Property", type: "property" },
    { key: "status", label: "Status", type: "select", options: [
      { value: "", label: "All" },
      { value: "open", label: "Unpaid" },
      { value: "part_paid", label: "Part paid" },
      { value: "paid", label: "Paid" },
    ]},
  ],
  "ageing": [
    { key: "upto", label: "As at month", type: "month" },
    { key: "months", label: "Columns", type: "number", placeholder: "12" },
    { key: "property_id", label: "Property", type: "property" },
  ],
  "contract-expiry": [
    { key: "within_days", label: "Within days", type: "number", placeholder: "90" },
    { key: "property_id", label: "Property", type: "property" },
    { key: "all", label: "Scope", type: "select", options: [
      { value: "", label: "Expiring only" },
      { value: "1", label: "All active contracts" },
    ]},
  ],
  "pdc-register": [
    { key: "status", label: "Status", type: "select", options: [
      { value: "", label: "All" },
      { value: "received", label: "On hand" },
      { value: "deposited", label: "With the bank" },
      { value: "cleared", label: "Cleared" },
      { value: "bounced", label: "Bounced" },
      { value: "replaced", label: "Replaced" },
      { value: "returned", label: "Returned" },
    ]},
    { key: "property_id", label: "Property", type: "property" },
    { key: "from", label: "Cheque date from", type: "date" },
    { key: "to", label: "Cheque date to", type: "date" },
  ],
  "property-pnl": [
    { key: "month", label: "Month", type: "month" },
    { key: "property_id", label: "Property", type: "property" },
  ],
  "company-pnl": [
    { key: "month", label: "Month", type: "month" },
  ],
  "audit-trail": [
    { key: "module", label: "Module", type: "text", placeholder: "contract" },
    { key: "action", label: "Action", type: "text", placeholder: "amend" },
    { key: "date_from", label: "From", type: "date" },
    { key: "date_to", label: "To", type: "date" },
  ],
};

/** Filters a report should start with when nothing is saved. */
const FILTER_DEFAULTS: Record<string, Record<string, string>> = {
  "rent-collection": { month: thisMonth() },
  "ageing": { upto: thisMonth() },
  "property-pnl": { month: thisMonth() },
  "company-pnl": { month: thisMonth() },
  "empty-units-trend": { start: monthsAgo(5), end: thisMonth() },
};

const SAVED_FILTERS_KEY = "greentech.report-filters";

function loadSavedFilters(slug: string): Record<string, string> {
  if (typeof window === "undefined") return {};
  try {
    const raw = window.localStorage.getItem(`${SAVED_FILTERS_KEY}.${slug}`);
    return raw ? JSON.parse(raw) : {};
  } catch { return {}; }
}

function saveFilters(slug: string, filters: Record<string, string>) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(`${SAVED_FILTERS_KEY}.${slug}`, JSON.stringify(filters));
}

export default function ReportPage(props: { params: Promise<{ slug: string }> }) {
  return (
    <ErrorBoundary fallbackTitle="The report viewer crashed.">
      <ReportPageInner params={props.params} />
    </ErrorBoundary>
  );
}

function ReportPageInner({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = useRouteParams(params);

  // `filters` is the live form state; `submittedFilters` is what the last
  // "Run report" click (or the initial load) actually asked for — the
  // query key is keyed on the latter so editing a filter field doesn't
  // refetch until the user submits, matching this page's original
  // click-to-run UX rather than the auto-refetch-on-change pattern used
  // elsewhere.
  const [filters, setFilters] = useState<Record<string, string>>({});
  const [submittedFilters, setSubmittedFilters] = useState<Record<string, string> | null>(null);
  const [sorting, setSorting] = useState<SortingState>([]);
  const [visibility, setVisibility] = useState<VisibilityState>({});
  const [pagination, setPagination] = useState({ pageIndex: 0, pageSize: 25 });
  const [showColumns, setShowColumns] = useState(false);
  const [exporting, setExporting] = useState<"xlsx" | "pdf" | null>(null);

  const filterFields = FILTERS[slug] ?? [];
  const needsProperties = filterFields.some((f) => f.type === "property");

  // Seed both the draft and submitted filters on mount / slug change —
  // no manual "run" call needed, useQuery below reacts to
  // `submittedFilters` changing.
  useEffect(() => {
    const saved = loadSavedFilters(slug);
    const initial = Object.keys(saved).length
      ? saved
      : { ...(FILTER_DEFAULTS[slug] ?? {}) };
    setFilters(initial);
    setSubmittedFilters(initial);
  }, [slug]);

  const reportsQuery = useQuery({
    queryKey: keys.reports.catalog(),
    queryFn: async () => (await api.get("/reports")).data.data as ReportInfo[],
  });
  const info = reportsQuery.data?.find((x) => x.slug === slug) ?? null;

  const propertiesQuery = useQuery({
    queryKey: keys.properties.list({}),
    queryFn: async () => {
      const r = await api.get("/properties");
      return Array.isArray(r.data?.data) ? (r.data.data as { id: number; code: string; name: string }[]) : [];
    },
    enabled: needsProperties,
  });
  const properties = propertiesQuery.data ?? [];

  const payloadQuery = useQuery({
    queryKey: keys.reports.run(slug, submittedFilters ?? {}),
    queryFn: async () => {
      const params: Record<string, string> = {};
      for (const [k, v] of Object.entries(submittedFilters ?? {})) if (v) params[k] = v;
      const r = await api.get(`/reports/${slug}`, { params });
      return r.data.data as ReportPayload;
    },
    enabled: submittedFilters !== null,
  });
  const payload = payloadQuery.data ?? null;
  const loading = payloadQuery.isLoading;

  const run = () => {
    setSubmittedFilters(filters);
    saveFilters(slug, filters);
  };

  const download = async (format: "xlsx" | "pdf") => {
    const params: Record<string, string> = { format };
    for (const [k, v] of Object.entries(filters)) if (v) params[k] = v;
    setExporting(format);
    try {
      const r = await api.get(`/reports/${slug}/export`, { params, responseType: "blob" });
      const url = URL.createObjectURL(r.data);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${slug}-${new Date().toISOString().slice(0, 10)}.${format}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err: unknown) {
      toast.error(`Could not export the ${format.toUpperCase()}`, errorMessage(err));
    } finally {
      setExporting(null);
    }
  };

  // Reset sorting / visibility on slug change so we never carry state into
  // a report with a totally different column set.
  useEffect(() => {
    setSorting([]);
    setVisibility({});
    setPagination({ pageIndex: 0, pageSize: 25 });
  }, [slug]);

  const columns = useMemo<ColumnDef<Row>[]>(() => {
    if (!payload || !Array.isArray(payload.columns)) return [];
    return payload.columns.map((c) => ({
      id: c.key,
      accessorFn: (row: Row) => (row && typeof row === "object" ? row[c.key] : undefined),
      header: () => c.label,
      cell: (ctx) => renderCellValue(ctx.getValue()),
    }));
  }, [payload]);

  const data = useMemo<Row[]>(() => {
    if (!payload || !Array.isArray(payload.rows)) return [];
    return payload.rows.filter((r): r is Row => r !== null && typeof r === "object");
  }, [payload]);

  const table = useReactTable({
    data,
    columns,
    state: { sorting, columnVisibility: visibility, pagination },
    onSortingChange: setSorting,
    onColumnVisibilityChange: setVisibility,
    onPaginationChange: setPagination,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
  });

  const setF = (k: string, v: string) => setFilters((f) => ({ ...f, [k]: v }));

  // Empty-units-trend chart data: one bar per month, occupied/empty
  // stacked. Whatever the property filter narrowed payload.rows to
  // (one camp, or all of them) is what gets summed per month, so the
  // same control drives both "camp-wise" and "total" views.
  const trendChart = useMemo(() => {
    if (slug !== "empty-units-trend" || !payload) return [];
    const byMonth = new Map<string, { month: string; occupied: number; empty: number }>();
    for (const row of payload.rows) {
      const month = String(row.month ?? "").slice(0, 7);
      if (!month) continue;
      const entry = byMonth.get(month) ?? { month, occupied: 0, empty: 0 };
      entry.occupied += Number(row.occupied_units ?? 0);
      entry.empty += Number(row.empty_units ?? 0);
      byMonth.set(month, entry);
    }
    return [...byMonth.values()].sort((a, b) => a.month.localeCompare(b.month));
  }, [slug, payload]);

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="print-hidden">
        <Link href="/reports" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft className="h-3.5 w-3.5" /> Back to reports
        </Link>
        <div className="mt-2 flex items-end justify-between flex-wrap gap-2">
          <div>
            <h1 className="text-2xl lg:text-3xl font-semibold tracking-tight">{info?.title ?? slug}</h1>
            {info?.description && <p className="text-sm text-muted-foreground">{info.description}</p>}
          </div>
          <div className="flex items-center gap-2">
            <button onClick={() => setShowColumns((v) => !v)}
              className="inline-flex h-9 items-center gap-2 rounded-md border border-border bg-card/60 px-3 text-sm hover:bg-accent">
              {showColumns ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />} Columns
            </button>
            <button onClick={() => window.print()}
              className="inline-flex h-9 items-center gap-2 rounded-md border border-border bg-card/60 px-3 text-sm hover:bg-accent">
              <Printer className="h-4 w-4" /> Print
            </button>
            <Can perm="report.export">
              <button onClick={() => download("pdf")} disabled={exporting !== null}
                className="inline-flex h-9 items-center gap-2 rounded-md border border-border bg-card/60 px-3 text-sm hover:bg-accent disabled:opacity-60">
                <FileDown className="h-4 w-4" />
                {exporting === "pdf" ? "Building…" : "PDF"}
              </button>
              <button onClick={() => download("xlsx")} disabled={exporting !== null}
                className="inline-flex h-9 items-center gap-2 rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-60">
                <Download className="h-4 w-4" />
                {exporting === "xlsx" ? "Building…" : "Excel"}
              </button>
            </Can>
          </div>
        </div>
      </div>

      {filterFields.length > 0 && (
        <div className="glass rounded-xl p-4 print-hidden">
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
            {filterFields.map((f) => (
              <div key={f.key} className="space-y-1">
                <label className="text-xs text-muted-foreground">{f.label}</label>
                {f.type === "select" ? (
                  <select className={selectClass} value={filters[f.key] ?? ""} onChange={(e) => setF(f.key, e.target.value)}>
                    {(f.options ?? []).map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                  </select>
                ) : f.type === "property" ? (
                  <select className={selectClass} value={filters[f.key] ?? ""} onChange={(e) => setF(f.key, e.target.value)}>
                    <option value="">All properties</option>
                    {properties.map((p) => <option key={p.id} value={p.id}>{p.name} ({p.code})</option>)}
                  </select>
                ) : f.type === "month" ? (
                  // Stored as YYYY-MM-01 because the API takes a date;
                  // the control only speaks YYYY-MM.
                  <input
                    className={inputClass}
                    type="month"
                    value={(filters[f.key] ?? "").slice(0, 7)}
                    onChange={(e) => setF(f.key, e.target.value ? `${e.target.value}-01` : "")}
                  />
                ) : (
                  <input
                    className={inputClass}
                    type={f.type === "number" ? "number" : f.type === "date" ? "date" : "text"}
                    placeholder={f.placeholder}
                    value={filters[f.key] ?? ""}
                    onChange={(e) => setF(f.key, e.target.value)}
                  />
                )}
              </div>
            ))}
          </div>
          <div className="flex items-center gap-2 mt-3">
            <button onClick={() => run()}
              className="h-9 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:bg-primary/90">
              Run report
            </button>
            <button onClick={() => {
              const reset = { ...(FILTER_DEFAULTS[slug] ?? {}) };
              setFilters(reset);
              setSubmittedFilters(reset);
              saveFilters(slug, reset);
            }}
              className="h-9 rounded-md border border-border bg-card/60 px-3 text-sm hover:bg-accent">
              Reset filters
            </button>
            <div className="ml-auto text-xs text-muted-foreground">Filters persist in your browser.</div>
          </div>
        </div>
      )}

      {showColumns && payload && (
        <div className="glass rounded-xl p-4 print-hidden">
          <div className="text-xs uppercase tracking-wide text-muted-foreground mb-2">Visible columns</div>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2">
            {table.getAllLeafColumns().map((c) => {
              const meta = payload?.columns.find((col) => col.key === c.id);
              return (
                <label key={c.id} className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={c.getIsVisible()} onChange={c.getToggleVisibilityHandler()} />
                  {meta?.label ?? c.id}
                </label>
              );
            })}
          </div>
        </div>
      )}

      {slug === "empty-units-trend" && trendChart.length > 0 && (
        <div className="glass rounded-xl p-4 print-hidden">
          <h2 className="text-sm font-semibold mb-2">Occupied vs. empty, by month</h2>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={trendChart} margin={{ top: 10, right: 8, left: -16, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
              <XAxis dataKey="month" tick={{ fontSize: 11 }} stroke="hsl(var(--muted-foreground))" />
              <YAxis tick={{ fontSize: 11 }} stroke="hsl(var(--muted-foreground))" />
              <Tooltip contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 8, fontSize: 12 }} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar dataKey="occupied" stackId="a" name="Occupied" fill="#10b981" />
              <Bar dataKey="empty" stackId="a" name="Empty" fill="#f43f5e" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      <div className="glass rounded-xl overflow-hidden print-clean">
        {loading ? (
          <div className="p-10 text-center text-sm text-muted-foreground">Loading…</div>
        ) : !payload || payload.rows.length === 0 ? (
          <div className="p-10 text-center text-sm text-muted-foreground">
            {payload?.meta?.note ? String(payload.meta.note) : "No rows match the current filters."}
          </div>
        ) : (
          <div className="overflow-x-auto max-h-[65vh] overflow-y-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-xs text-muted-foreground border-b border-border sticky top-0 bg-card/80 backdrop-blur z-10">
                {table.getHeaderGroups().map((hg) => (
                  <tr key={hg.id}>
                    {hg.headers.map((header) => {
                      const sort = header.column.getIsSorted();
                      return (
                        <th key={header.id}
                            onClick={header.column.getToggleSortingHandler()}
                            className="py-2 px-3 select-none cursor-pointer hover:text-foreground whitespace-nowrap">
                          <span className="inline-flex items-center gap-1">
                            {flexRender(header.column.columnDef.header, header.getContext())}
                            {sort === "asc" && <ArrowUp className="h-3 w-3" />}
                            {sort === "desc" && <ArrowDown className="h-3 w-3" />}
                          </span>
                        </th>
                      );
                    })}
                  </tr>
                ))}
              </thead>
              <tbody>
                {table.getRowModel().rows.map((row) => (
                  <tr key={row.id} className="border-b border-border/60 hover:bg-accent/30">
                    {row.getVisibleCells().map((cell) => (
                      <td key={cell.id} className="py-2 px-3 whitespace-nowrap">
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {payload && payload.rows.length > 0 && (
          <div className="flex items-center justify-between gap-3 flex-wrap px-4 py-2 text-xs text-muted-foreground border-t border-border print-hidden">
            <div className="flex items-center gap-2">
              <span>{payload.rows.length} row(s)</span>
              <span>· Page {table.getState().pagination.pageIndex + 1} of {Math.max(1, table.getPageCount())}</span>
            </div>
            <div className="flex items-center gap-2">
              <label className="flex items-center gap-1.5">
                Rows per page
                <select
                  className={selectClass + " h-7 w-auto text-xs py-0"}
                  value={table.getState().pagination.pageSize}
                  onChange={(e) => table.setPageSize(Number(e.target.value))}
                >
                  {[10, 25, 50, 100].map((n) => <option key={n} value={n}>{n}</option>)}
                </select>
              </label>
              <div className="flex items-center gap-0.5">
                <button type="button" onClick={() => table.setPageIndex(0)} disabled={!table.getCanPreviousPage()}
                  className="h-7 w-7 grid place-items-center rounded-md hover:bg-accent disabled:opacity-40 disabled:hover:bg-transparent">
                  <ChevronsLeft className="h-3.5 w-3.5" />
                </button>
                <button type="button" onClick={() => table.previousPage()} disabled={!table.getCanPreviousPage()}
                  className="h-7 w-7 grid place-items-center rounded-md hover:bg-accent disabled:opacity-40 disabled:hover:bg-transparent">
                  <ChevronLeft className="h-3.5 w-3.5" />
                </button>
                <button type="button" onClick={() => table.nextPage()} disabled={!table.getCanNextPage()}
                  className="h-7 w-7 grid place-items-center rounded-md hover:bg-accent disabled:opacity-40 disabled:hover:bg-transparent">
                  <ChevronRight className="h-3.5 w-3.5" />
                </button>
                <button type="button" onClick={() => table.setPageIndex(table.getPageCount() - 1)} disabled={!table.getCanNextPage()}
                  className="h-7 w-7 grid place-items-center rounded-md hover:bg-accent disabled:opacity-40 disabled:hover:bg-transparent">
                  <ChevronsRight className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>
          </div>
        )}
      </div>

      <style jsx global>{`
        @media print {
          .print-hidden { display: none !important; }
          .glass { background: white !important; backdrop-filter: none !important; border: 1px solid #ddd; }
          body { background: white !important; }
          aside, header { display: none !important; }
          main { padding: 0 !important; }
        }
      `}</style>
    </div>
  );
}
