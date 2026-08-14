"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  Plus, Building2, MapPin, AlertTriangle,
  ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight,
} from "lucide-react";
import { api } from "@/lib/api";
import { Can } from "@/components/can";
import { selectClass } from "@/components/ui/dialog";
import { Skeleton, EmptyState } from "@/components/ui/states";
import { useDebouncedValue } from "@/lib/use-debounce";
import { usePropertyTypes } from "@/lib/use-property-types";
import { keys } from "@/lib/query-keys";

const PAGE_SIZE_OPTIONS = [12, 24, 48, 96];

type Property = {
  id: number;
  code: string;
  name: string;
  property_type: string;
  city: string | null;
  area: string | null;
  status: string;
  ownership_type: string;
  floors_count: number;
  units_count: number;
  landlord: {
    id: number;
    code: string;
    name: string;
  } | null;
  active_agreement: {
    id: number;
    expiry_date: string;
    landlord: { id: number; name: string };
  } | null;
};

const STATUSES = ["active", "inactive", "maintenance", "on_hold"];

function statusBadgeClass(s: string): string {
  if (s === "active") return "bg-emerald-500/10 text-emerald-600";
  if (s === "on_hold") return "bg-amber-500/10 text-amber-600";
  if (s === "maintenance") return "bg-sky-500/10 text-sky-600";
  return "bg-muted text-muted-foreground";
}

export default function PropertiesPage() {
  const router = useRouter();
  const { types: propertyTypes } = usePropertyTypes();
  const [q, setQ] = useState("");
  const debouncedQ = useDebouncedValue(q);
  const [status, setStatus] = useState("");
  const [showDeactivated, setShowDeactivated] = useState(false);
  const [type, setType] = useState("");
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(24);

  const filters = { q: debouncedQ, status, type, showDeactivated };
  const listQuery = useQuery({
    queryKey: keys.properties.list(filters),
    queryFn: async () => {
      const params: Record<string, string> = {};
      if (debouncedQ) params.q = debouncedQ;
      if (type) params.type = type;
      // An explicit status pick always wins. Otherwise, hide "inactive"
      // (deactivated) by default while still showing maintenance/on_hold —
      // those are operational states, not a deactivation.
      if (status) params.status = status;
      else if (!showDeactivated) params.exclude_status = "inactive";
      const resp = await api.get("/properties", { params });
      return Array.isArray(resp?.data?.data) ? (resp.data.data as Property[]) : [];
    },
  });
  const rows = listQuery.data ?? [];
  const loading = listQuery.isLoading;
  const load = () => listQuery.refetch();

  useEffect(() => { setPage(0); }, [debouncedQ, status, type, showDeactivated]);

  const pageCount = Math.max(1, Math.ceil(rows.length / pageSize));
  const paged = useMemo(
    () => rows.slice(page * pageSize, page * pageSize + pageSize),
    [rows, page, pageSize],
  );

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-end justify-between flex-wrap gap-2">
        <div>
          <h1 className="text-2xl lg:text-3xl font-semibold tracking-tight">Properties</h1>
          <p className="text-sm text-muted-foreground">Buildings, camps, villas and stores taken from landlords.</p>
        </div>
        <Can perm="property.create">
          <Link href="/properties/new"
            className="inline-flex h-9 items-center gap-2 rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground hover:bg-primary/90">
            <Plus className="h-4 w-4" /> New property
          </Link>
        </Can>
      </div>

      <div className="glass rounded-xl p-4">
        <div className="flex items-center gap-2 flex-wrap">
          <input
            value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && load()}
            placeholder="Search code, name, city, area…"
            className="h-9 w-64 shrink-0 rounded-md border border-input bg-card/60 px-3 text-sm"
          />
          <select className={selectClass + " !w-auto shrink-0"} value={type} onChange={(e) => setType(e.target.value)}>
            <option value="">All types</option>
            {propertyTypes.map((t) => <option key={t.code} value={t.code}>{t.name}</option>)}
          </select>
          <select className={selectClass + " !w-auto shrink-0"} value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">All statuses</option>
            {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <label className="inline-flex items-center gap-1.5 text-xs text-muted-foreground shrink-0 whitespace-nowrap">
            <input type="checkbox" checked={showDeactivated} onChange={(e) => setShowDeactivated(e.target.checked)} />
            Show deactivated
          </label>
          <button onClick={load} className="h-9 shrink-0 rounded-md border border-border bg-card/60 px-3 text-sm hover:bg-accent">Filter</button>
        </div>
      </div>

      <div className="glass rounded-xl p-4">
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
          {loading && Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="glass rounded-xl p-4 space-y-3">
              <div className="flex items-center gap-2">
                <Skeleton className="h-9 w-9 rounded-lg" />
                <div className="flex-1 space-y-1.5">
                  <Skeleton className="h-3 w-2/3" />
                  <Skeleton className="h-3 w-1/3" />
                </div>
              </div>
              <Skeleton className="h-3 w-1/2" />
              <div className="grid grid-cols-3 gap-2">
                <Skeleton className="h-10" /><Skeleton className="h-10" /><Skeleton className="h-10" />
              </div>
            </div>
          ))}
          {!loading && rows.length === 0 && (
            <div className="col-span-full">
              <EmptyState
                icon={Building2}
                title="No properties yet"
                hint="Create your first property to start tracking floors and units."
              />
            </div>
          )}
          {paged.map((p) => {
            const expiry = p.active_agreement?.expiry_date ?? null;
            const days = expiry ? Math.ceil((new Date(expiry).getTime() - Date.now()) / 86400000) : null;
            const expiringSoon = days !== null && days <= 90;
            const expired = days !== null && days < 0;
            const landlord = p.landlord ?? p.active_agreement?.landlord ?? null;
            return (
              <Link key={p.id} href={`/properties/${p.id}`}
                className="glass rounded-xl p-4 hover:bg-accent/30 transition-colors block">
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <div className="h-9 w-9 rounded-lg bg-primary/10 grid place-items-center">
                      <Building2 className="h-4 w-4 text-primary" />
                    </div>
                    <div>
                      <div className="font-medium leading-tight">{p.name}</div>
                      <div className="text-xs text-muted-foreground font-mono">{p.code}</div>
                    </div>
                  </div>
                  <span className={"rounded-full px-2 py-0.5 text-xs capitalize " + statusBadgeClass(p.status)}>
                    {p.status.replace("_", " ")}
                  </span>
                </div>
                <div className="mt-3 text-xs text-muted-foreground capitalize">
                  {(p.property_type ?? "—").replaceAll("_", " ")} · {(p.ownership_type ?? "—").replaceAll("_", " ")}
                </div>
                <div className="mt-1 text-xs text-muted-foreground flex items-center gap-1">
                  <MapPin className="h-3 w-3" /> {[p.area, p.city].filter(Boolean).join(", ") || "—"}
                </div>
                <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
                  <Stat label="Floors" value={p.floors_count} />
                  <Stat label="Units" value={p.units_count} />
                </div>
                {landlord && (
                  <div className={"mt-3 text-xs flex items-center gap-1 " + (expired ? "text-destructive" : expiringSoon ? "text-amber-600" : "text-muted-foreground")}>
                    {expiringSoon && <AlertTriangle className="h-3 w-3" />}
                    <span
                      role="link"
                      onClick={(e) => { e.preventDefault(); e.stopPropagation(); router.push(`/landlords/${landlord.id}`); }}
                      className="hover:text-primary hover:underline"
                    >
                      {landlord.name}
                    </span>
                    {expiry ? ` · ${expired ? "expired" : `expires ${expiry}${days !== null ? ` (${days}d)` : ""}`}` : ""}
                  </div>
                )}
              </Link>
            );
          })}
        </div>

        <div className="flex items-center justify-between gap-3 flex-wrap pt-4 mt-4 border-t border-border text-xs text-muted-foreground">
          <div className="flex items-center gap-2">
            <span>{rows.length} propert{rows.length === 1 ? "y" : "ies"}</span>
            <span>· Page {page + 1} of {pageCount}</span>
          </div>
          <div className="flex items-center gap-2">
            <label className="flex items-center gap-1.5">
              Per page
              <select
                className={selectClass + " h-7 w-auto text-xs py-0"}
                value={pageSize}
                onChange={(e) => { setPageSize(Number(e.target.value)); setPage(0); }}
              >
                {PAGE_SIZE_OPTIONS.map((n) => <option key={n} value={n}>{n}</option>)}
              </select>
            </label>
            <div className="flex items-center gap-0.5">
              <button type="button" onClick={() => setPage(0)} disabled={page === 0}
                className="h-7 w-7 grid place-items-center rounded-md hover:bg-accent disabled:opacity-40 disabled:hover:bg-transparent">
                <ChevronsLeft className="h-3.5 w-3.5" />
              </button>
              <button type="button" onClick={() => setPage((p) => Math.max(0, p - 1))} disabled={page === 0}
                className="h-7 w-7 grid place-items-center rounded-md hover:bg-accent disabled:opacity-40 disabled:hover:bg-transparent">
                <ChevronLeft className="h-3.5 w-3.5" />
              </button>
              <button type="button" onClick={() => setPage((p) => Math.min(pageCount - 1, p + 1))} disabled={page >= pageCount - 1}
                className="h-7 w-7 grid place-items-center rounded-md hover:bg-accent disabled:opacity-40 disabled:hover:bg-transparent">
                <ChevronRight className="h-3.5 w-3.5" />
              </button>
              <button type="button" onClick={() => setPage(pageCount - 1)} disabled={page >= pageCount - 1}
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

function Stat({ label, value }: { label: string; value: number | null }) {
  return (
    <div className="rounded-md bg-card/60 border border-border p-2 text-center">
      <div className="text-base font-semibold">{value ?? "—"}</div>
      <div className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</div>
    </div>
  );
}

