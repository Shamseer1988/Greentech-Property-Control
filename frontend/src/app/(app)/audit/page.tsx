"use client";

import { Fragment, useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  ChevronDown, ChevronRight, ChevronLeft, ChevronsLeft, ChevronsRight, RotateCcw,
} from "lucide-react";
import { api } from "@/lib/api";
import { AuditDiff, type AuditDiffEntry } from "@/components/audit-diff";
import { inputClass, selectClass } from "@/components/ui/dialog";
import { keys } from "@/lib/query-keys";

const PAGE_SIZE_OPTIONS = [50, 100, 200, 500];

type Row = {
  id: number;
  user_id: number | null;
  username: string | null;
  action: string;
  module: string;
  entity_type: string | null;
  entity_id: string | null;
  ip_address: string | null;
  remarks: string | null;
  created_at: string;
  old_value: Record<string, unknown> | null;
  new_value: Record<string, unknown> | null;
  diff: AuditDiffEntry[] | null;
};

type Facets = {
  modules: string[];
  actions: string[];
  users: { user_id: number | null; username: string; count: number }[];
};

const EMPTY_FACETS: Facets = { modules: [], actions: [], users: [] };

/** A row is worth expanding when there's something underneath it. */
function hasDetail(r: Row): boolean {
  return Boolean((r.diff && r.diff.length) || r.old_value || r.new_value);
}

export default function AuditPage() {
  const [module, setModule] = useState("");
  const [action, setAction] = useState("");
  const [userId, setUserId] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [open, setOpen] = useState<number | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(100);

  const filters = { module, action, userId, dateFrom, dateTo };
  useEffect(() => { setPage(1); }, [module, action, userId, dateFrom, dateTo]);

  const listQuery = useQuery({
    queryKey: keys.audit.list({ ...filters, page, pageSize }),
    queryFn: async () => {
      const params: Record<string, string | number> = { page, per_page: pageSize };
      if (module) params.module = module;
      if (action) params.action = action;
      if (userId) params.user_id = userId;
      if (dateFrom) params.date_from = dateFrom;
      if (dateTo) params.date_to = dateTo;
      const resp = await api.get("/audit", { params });
      return resp.data as { data: Row[]; meta: { total_count: number; total_pages: number } };
    },
    placeholderData: (prev) => prev,
  });
  const rows = listQuery.data?.data ?? [];
  const meta = listQuery.data?.meta;
  const loading = listQuery.isLoading;
  const totalPages = meta?.total_pages ?? 1;

  const facetsQuery = useQuery({
    queryKey: keys.audit.facets(),
    queryFn: async () => (await api.get("/audit/facets")).data?.data as Facets ?? EMPTY_FACETS,
  });
  const facets = facetsQuery.data ?? EMPTY_FACETS;

  const clear = () => {
    setModule(""); setAction(""); setUserId(""); setDateFrom(""); setDateTo("");
  };
  const filtered = module || action || userId || dateFrom || dateTo;

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h1 className="text-2xl lg:text-3xl font-semibold tracking-tight">Audit log</h1>
        <p className="text-sm text-muted-foreground">
          Who changed what, when, and from where. Open a row to see the values
          before and after.
        </p>
      </div>

      <div className="glass rounded-xl p-4">
        <div className="flex items-end gap-2 flex-wrap mb-3">
          <Filter label="Module">
            <select className={selectClass + " !w-auto"} value={module}
              onChange={(e) => setModule(e.target.value)}>
              <option value="">All</option>
              {facets.modules.map((m) => <option key={m} value={m}>{m}</option>)}
            </select>
          </Filter>
          <Filter label="Action">
            <select className={selectClass + " !w-auto"} value={action}
              onChange={(e) => setAction(e.target.value)}>
              <option value="">All</option>
              {facets.actions.map((a) => <option key={a} value={a}>{a}</option>)}
            </select>
          </Filter>
          <Filter label="User">
            <select className={selectClass + " !w-auto"} value={userId}
              onChange={(e) => setUserId(e.target.value)}>
              <option value="">Everyone</option>
              {facets.users.map((u) => (
                <option key={`${u.user_id}-${u.username}`} value={u.user_id ?? ""}>
                  {u.username} ({u.count})
                </option>
              ))}
            </select>
          </Filter>
          <Filter label="From">
            <input type="date" className={inputClass + " w-auto"} value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)} />
          </Filter>
          <Filter label="To">
            <input type="date" className={inputClass + " w-auto"} value={dateTo}
              onChange={(e) => setDateTo(e.target.value)} />
          </Filter>
          {filtered && (
            <button onClick={clear}
              className="h-9 inline-flex items-center gap-1.5 rounded-md border border-border bg-card/60 px-3 text-sm hover:bg-accent">
              <RotateCcw className="h-3.5 w-3.5" /> Clear
            </button>
          )}
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-muted-foreground border-b border-border">
              <tr>
                <th className="py-2 pr-2 w-6"></th>
                <th className="py-2 pr-4">Time (UTC)</th>
                <th className="py-2 pr-4">User</th>
                <th className="py-2 pr-4">Module</th>
                <th className="py-2 pr-4">Action</th>
                <th className="py-2 pr-4">Entity</th>
                <th className="py-2 pr-4">IP</th>
                <th className="py-2 pr-4">Remarks</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={8} className="py-10 text-center text-muted-foreground">
                  Loading…
                </td></tr>
              ) : rows.length === 0 ? (
                <tr><td colSpan={8} className="py-10 text-center text-muted-foreground">
                  {filtered ? "Nothing matches those filters." : "No log entries."}
                </td></tr>
              ) : (
                rows.map((r) => {
                  const expandable = hasDetail(r);
                  const isOpen = open === r.id;
                  return (
                    <Fragment key={r.id}>
                      <tr
                        onClick={() => expandable && setOpen(isOpen ? null : r.id)}
                        className={"border-b border-border/60 hover:bg-accent/30 "
                          + (expandable ? "cursor-pointer" : "")}>
                        <td className="py-2 pr-2 text-muted-foreground">
                          {expandable && (isOpen
                            ? <ChevronDown className="h-3.5 w-3.5" />
                            : <ChevronRight className="h-3.5 w-3.5" />)}
                        </td>
                        <td className="py-2 pr-4 font-mono text-xs whitespace-nowrap">
                          {r.created_at?.slice(0, 19).replace("T", " ")}
                        </td>
                        <td className="py-2 pr-4">{r.username ?? "—"}</td>
                        <td className="py-2 pr-4">{r.module}</td>
                        <td className="py-2 pr-4">
                          <span className="inline-flex rounded-full bg-primary/10 px-2 py-0.5 text-xs text-primary">
                            {r.action}
                          </span>
                        </td>
                        <td className="py-2 pr-4 font-mono text-xs">
                          {r.entity_type ? `${r.entity_type}#${r.entity_id ?? "?"}` : "—"}
                        </td>
                        <td className="py-2 pr-4 font-mono text-xs">{r.ip_address ?? "—"}</td>
                        <td className="py-2 pr-4 text-muted-foreground">{r.remarks ?? ""}</td>
                      </tr>
                      {isOpen && (
                        <tr className="border-b border-border/60 bg-card/30">
                          <td colSpan={8} className="p-3">
                            {r.diff && r.diff.length > 0 ? (
                              <AuditDiff diff={r.diff} />
                            ) : (
                              <Snapshot old={r.old_value} next={r.new_value} />
                            )}
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        <div className="flex items-center justify-between gap-3 flex-wrap px-1 pt-3 text-xs text-muted-foreground">
          <div className="flex items-center gap-2">
            <span>{meta?.total_count ?? 0} row{meta?.total_count === 1 ? "" : "s"}</span>
            <span>· Page {page} of {totalPages}</span>
          </div>
          <div className="flex items-center gap-2">
            <label className="flex items-center gap-1.5">
              Rows per page
              <select
                className={selectClass + " h-7 w-auto text-xs py-0"}
                value={pageSize}
                onChange={(e) => { setPageSize(Number(e.target.value)); setPage(1); }}
              >
                {PAGE_SIZE_OPTIONS.map((n) => <option key={n} value={n}>{n}</option>)}
              </select>
            </label>
            <div className="flex items-center gap-0.5">
              <button type="button" onClick={() => setPage(1)} disabled={page <= 1}
                className="h-7 w-7 grid place-items-center rounded-md hover:bg-accent disabled:opacity-40 disabled:hover:bg-transparent">
                <ChevronsLeft className="h-3.5 w-3.5" />
              </button>
              <button type="button" onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page <= 1}
                className="h-7 w-7 grid place-items-center rounded-md hover:bg-accent disabled:opacity-40 disabled:hover:bg-transparent">
                <ChevronLeft className="h-3.5 w-3.5" />
              </button>
              <button type="button" onClick={() => setPage((p) => Math.min(totalPages, p + 1))} disabled={page >= totalPages}
                className="h-7 w-7 grid place-items-center rounded-md hover:bg-accent disabled:opacity-40 disabled:hover:bg-transparent">
                <ChevronRight className="h-3.5 w-3.5" />
              </button>
              <button type="button" onClick={() => setPage(totalPages)} disabled={page >= totalPages}
                className="h-7 w-7 grid place-items-center rounded-md hover:bg-accent disabled:opacity-40 disabled:hover:bg-transparent">
                <ChevronsRight className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function Filter({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-[11px] text-muted-foreground">{label}</span>
      {children}
    </label>
  );
}

/** A create or delete carries only one side — show the record itself
 * rather than an empty diff. */
function Snapshot({ old, next }: {
  old: Record<string, unknown> | null; next: Record<string, unknown> | null;
}) {
  const value = next ?? old;
  if (!value) {
    return <div className="text-xs text-muted-foreground">No values recorded.</div>;
  }
  return (
    <div className="space-y-1">
      <div className="text-[11px] text-muted-foreground">
        {next ? "Recorded values" : "Values before removal"}
      </div>
      <pre className="rounded-md border border-border bg-card/40 p-3 text-xs overflow-x-auto">
        {JSON.stringify(value, null, 2)}
      </pre>
    </div>
  );
}
