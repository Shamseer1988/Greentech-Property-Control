"use client";

import { useEffect, useMemo, useState, use } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { ArrowLeft, Printer, Layers, DoorClosed, ChevronDown, ChevronsDownUp, ChevronsUpDown } from "lucide-react";
import { api } from "@/lib/api";
import { useRouteParams } from "@/lib/use-route-params";
import { useEvents } from "@/lib/use-events";
import { useUnitTypes } from "@/lib/use-unit-types";
import { Skeleton, ErrorState, EmptyState } from "@/components/ui/states";

type Occupant = {
  client_id: number;
  client_name: string | null;
  contract_id: number;
  contract_number: string;
  monthly_rent: number | null;
  start_date: string | null;
  expiry_date: string | null;
};

type Unit = {
  id: number;
  unit_number: string;
  unit_name: string | null;
  unit_type: string;
  size: string | null;
  is_shared_facility: boolean;
  occupancy_status: string;
  monthly_rent: number | null;
  occupant: Occupant | null;
};

type Floor = {
  id: number;
  floor_number: string;
  units: Unit[];
};

type Property = { id: number; code: string; name: string };

const TONES: Record<string, { label: string; dot: string; tile: string }> = {
  empty:       { label: "Empty",       dot: "bg-slate-400",   tile: "border-slate-400/40 bg-slate-500/5 hover:bg-slate-500/10" },
  occupied:    { label: "Occupied",    dot: "bg-emerald-500", tile: "border-emerald-500/40 bg-emerald-500/5 hover:bg-emerald-500/10" },
  maintenance: { label: "Maintenance", dot: "bg-amber-500",   tile: "border-amber-500/40 bg-amber-500/5 hover:bg-amber-500/10" },
  blocked:     { label: "Blocked",     dot: "bg-rose-500",    tile: "border-rose-500/40 bg-rose-500/5 hover:bg-rose-500/10" },
};

function money(n: number | null): string {
  return n == null ? "—" : n.toLocaleString(undefined, { maximumFractionDigits: 0 });
}

function UnitTile({ unit, facilityCodes }: { unit: Unit; facilityCodes: Set<string> }) {
  const tone = TONES[unit.occupancy_status] ?? TONES.empty;
  const facility = facilityCodes.has(unit.unit_type);
  return (
    <div
      className={
        "group relative rounded-lg border p-2 text-center transition-colors print:break-inside-avoid " + tone.tile +
        (facility ? " border-dashed" : "")
      }
    >
      <div className="flex items-center justify-center gap-1">
        <span className={"h-1.5 w-1.5 rounded-full shrink-0 " + tone.dot} />
        <span className="text-xs font-mono font-semibold truncate">{unit.unit_number}</span>
      </div>
      <div className="text-[9px] text-muted-foreground capitalize truncate mt-0.5">
        {unit.unit_type.replaceAll("_", " ")}
        {facility && (unit.is_shared_facility ? " · shared" : " · dedicated")}
      </div>

      {/* Hover popup — occupant details for an occupied unit, or just
          the unit's own facts when it isn't. Pure CSS hover (no mouse
          tracking) since a floor plan can have hundreds of tiles. */}
      <div
        className="pointer-events-none absolute bottom-full left-1/2 z-20 mb-2 w-52 -translate-x-1/2 rounded-lg border border-border bg-card text-foreground p-3 text-left text-xs opacity-0 shadow-xl transition-opacity duration-100 group-hover:opacity-100 print:hidden"
      >
        <div className="font-semibold font-mono">{unit.unit_number}{unit.unit_name ? ` · ${unit.unit_name}` : ""}</div>
        <div className="text-muted-foreground capitalize mt-0.5">
          {unit.unit_type.replaceAll("_", " ")}{unit.size ? ` · ${unit.size}` : ""}
        </div>
        <div className={"mt-1.5 inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[10px] font-medium " + tone.tile}>
          <span className={"h-1.5 w-1.5 rounded-full " + tone.dot} /> {tone.label}
        </div>
        {unit.occupant ? (
          <div className="mt-2 space-y-1 border-t border-border pt-2">
            <div className="font-medium">{unit.occupant.client_name ?? "—"}</div>
            <div className="text-muted-foreground font-mono">{unit.occupant.contract_number}</div>
            <div className="flex justify-between"><span className="text-muted-foreground">Rent</span><span>{money(unit.occupant.monthly_rent)}</span></div>
            <div className="flex justify-between"><span className="text-muted-foreground">From</span><span className="font-mono">{unit.occupant.start_date ?? "—"}</span></div>
            <div className="flex justify-between"><span className="text-muted-foreground">Until</span><span className="font-mono">{unit.occupant.expiry_date ?? "—"}</span></div>
          </div>
        ) : unit.monthly_rent != null ? (
          <div className="mt-2 border-t border-border pt-2 flex justify-between">
            <span className="text-muted-foreground">Base rent</span><span>{money(unit.monthly_rent)}</span>
          </div>
        ) : null}
        <div className="absolute left-1/2 top-full h-2 w-2 -translate-x-1/2 -translate-y-1/2 rotate-45 border-b border-r border-border bg-card" />
      </div>
    </div>
  );
}

type Totals = {
  units: number;
  occupied: number;
  empty: number;
  maintenance: number;
  blocked: number;
  floors: number;
};

function StatCard({
  label, value, sub, tone,
}: { label: string; value: number | string; sub?: string; tone: "primary" | "emerald" | "sky" | "amber" | "rose" | "slate" }) {
  const toneCls = {
    primary: "from-primary/15 to-primary/0 text-primary",
    emerald: "from-emerald-500/15 to-emerald-500/0 text-emerald-600 dark:text-emerald-400",
    sky: "from-sky-500/15 to-sky-500/0 text-sky-600 dark:text-sky-400",
    amber: "from-amber-500/15 to-amber-500/0 text-amber-600 dark:text-amber-400",
    rose: "from-rose-500/15 to-rose-500/0 text-rose-600 dark:text-rose-400",
    slate: "from-slate-500/15 to-slate-500/0 text-slate-600 dark:text-slate-400",
  }[tone];
  return (
    <div className={"rounded-xl border border-border/60 bg-gradient-to-br p-3 " + toneCls}>
      <div className="text-[10px] uppercase tracking-wide opacity-80">{label}</div>
      <div className="text-xl font-semibold leading-tight mt-0.5">{value}</div>
      {sub && <div className="text-[10px] opacity-70 mt-0.5">{sub}</div>}
    </div>
  );
}

export default function FloorPlanPage(props: { params: Promise<{ id: string }> }) {
  const params = use(props.params);
  const { id } = useRouteParams(params);
  const qc = useQueryClient();
  const { types: unitTypes } = useUnitTypes();
  const facilityCodes = useMemo(
    () => new Set(unitTypes.filter((t) => t.is_facility).map((t) => t.code)), [unitTypes]);

  useEvents("occupancy", () => {
    qc.invalidateQueries({ queryKey: ["properties", "structure", id] });
  });

  const propQ = useQuery({
    queryKey: ["properties", "detail", id],
    queryFn: async () => (await api.get(`/properties/${id}`)).data.data as Property,
    enabled: Boolean(id),
  });

  const structureQ = useQuery({
    queryKey: ["properties", "structure", id],
    queryFn: async () => (await api.get(`/properties/${id}/structure`)).data.data as Floor[],
    enabled: Boolean(id),
  });

  const totals: Totals | null = useMemo(() => {
    if (!structureQ.data) return null;
    const t: Totals = { units: 0, occupied: 0, empty: 0, maintenance: 0, blocked: 0, floors: 0 };
    t.floors = structureQ.data.length;
    for (const f of structureQ.data) {
      for (const u of f.units) {
        t.units += 1;
        if (u.occupancy_status === "occupied") t.occupied += 1;
        else if (u.occupancy_status === "empty") t.empty += 1;
        else if (u.occupancy_status === "maintenance") t.maintenance += 1;
        else if (u.occupancy_status === "blocked") t.blocked += 1;
      }
    }
    return t;
  }, [structureQ.data]);

  // Per-floor collapse state, persisted so refreshing the page doesn't
  // re-expand a long list the operator just tidied up. Keyed by property
  // so two properties don't share state.
  const collapseKey = `greentech.floorplan.collapsed.${id}`;
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [collapseLoaded, setCollapseLoaded] = useState(false);

  useEffect(() => {
    if (!id) return;
    try {
      const raw = window.localStorage.getItem(collapseKey);
      if (raw) setCollapsed(new Set(JSON.parse(raw) as string[]));
    } catch { /* ignore */ }
    setCollapseLoaded(true);
  }, [collapseKey, id]);

  useEffect(() => {
    if (!collapseLoaded) return;
    try {
      window.localStorage.setItem(collapseKey, JSON.stringify([...collapsed]));
    } catch { /* ignore */ }
  }, [collapsed, collapseKey, collapseLoaded]);

  const toggleFloor = (floorId: number | string) => {
    setCollapsed((prev) => {
      const next = new Set(prev);
      const key = String(floorId);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const collapseAll = () => {
    if (!structureQ.data) return;
    setCollapsed(new Set(structureQ.data.map((f) => String(f.id))));
  };
  const expandAll = () => setCollapsed(new Set());

  const printedOn = new Date().toLocaleString();
  const occupancyPct = totals && totals.units > 0 ? Math.round((totals.occupied / totals.units) * 100) : 0;

  return (
    <div className="floorplan-print-root space-y-5 animate-fade-in print:space-y-3">
      <div className="print:hidden">
        <Link
          href={`/properties/${id}`}
          className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-3.5 w-3.5" /> Back to property
        </Link>
      </div>

      {/* Hero header card */}
      <div className="relative overflow-hidden rounded-2xl border border-border/60 bg-gradient-to-br from-primary/10 via-card/60 to-card/30 p-5 sm:p-6 backdrop-blur">
        <div className="absolute -top-16 -right-16 h-48 w-48 rounded-full bg-primary/10 blur-3xl pointer-events-none" />
        <div className="relative flex flex-wrap items-end justify-between gap-4">
          <div className="min-w-0">
            <h1 className="text-2xl lg:text-3xl font-semibold tracking-tight">
              Floor plan
              {propQ.data && <span className="text-muted-foreground"> · {propQ.data.name}</span>}
            </h1>
            <p className="text-sm text-muted-foreground print:hidden mt-1">
              Unit map of the whole property. From Phase 2 the tiles show which client holds each unit.
            </p>
            <p className="hidden print:block text-xs text-black/70 mt-1">Generated {printedOn}</p>
          </div>
          <div className="print:hidden inline-flex items-center gap-1.5">
            {structureQ.data && structureQ.data.length > 1 && (
              <button
                type="button"
                onClick={collapsed.size === structureQ.data.length ? expandAll : collapseAll}
                aria-label={collapsed.size === structureQ.data.length ? "Expand all floors" : "Collapse all floors"}
                title={collapsed.size === structureQ.data.length ? "Expand all floors" : "Collapse all floors"}
                className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-card/70 px-3 py-1.5 text-xs font-medium hover:bg-accent shadow-sm"
              >
                {collapsed.size === structureQ.data.length ? (
                  <><ChevronsUpDown className="h-3.5 w-3.5" /> Expand all</>
                ) : (
                  <><ChevronsDownUp className="h-3.5 w-3.5" /> Collapse all</>
                )}
              </button>
            )}
            <button
              type="button"
              onClick={() => window.print()}
              aria-label="Print floor plan"
              className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-card/70 px-3 py-1.5 text-xs font-medium hover:bg-accent shadow-sm"
            >
              <Printer className="h-3.5 w-3.5" /> Print
            </button>
          </div>
        </div>

        {/* Stat strip */}
        {totals && (
          <div className="relative grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2 mt-5">
            <StatCard label="Occupancy" value={`${occupancyPct}%`} sub={`${totals.occupied}/${totals.units} units`} tone="primary" />
            <StatCard label="Floors" value={totals.floors} sub={`${totals.units} units`} tone="slate" />
            <StatCard label="Occupied" value={totals.occupied} tone="emerald" />
            <StatCard label="Empty" value={totals.empty} tone="slate" />
            <StatCard label="Maintenance" value={totals.maintenance} tone="amber" />
            <StatCard label="Blocked" value={totals.blocked} tone="rose" />
          </div>
        )}

        {/* Legend */}
        <div className="relative flex flex-wrap items-center gap-1.5 mt-5 print:mt-3">
          {Object.entries(TONES).map(([k, t]) => (
            <div
              key={k}
              className="inline-flex items-center gap-1.5 rounded-full border border-border/60 bg-background/50 px-2.5 py-1 text-[10px] font-medium"
            >
              <span className={"h-2 w-2 rounded-full " + t.dot} />
              {t.label}
            </div>
          ))}
          <div className="inline-flex items-center gap-1.5 rounded-full border border-dashed border-border/60 bg-background/50 px-2.5 py-1 text-[10px] font-medium">
            Dashed = facility (kitchen / bathroom / play area)
          </div>
        </div>
      </div>

      {structureQ.isLoading && (
        <div className="space-y-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-32 w-full" />
          ))}
        </div>
      )}
      {structureQ.isError && (
        <ErrorState
          title="Couldn't load the floor plan"
          message="The structure request failed. Check your connection and try again."
          onRetry={() => structureQ.refetch()}
        />
      )}
      {structureQ.data && structureQ.data.length === 0 && (
        <EmptyState
          title="No floors defined yet"
          hint="Add floors and units to this property to see them here."
        />
      )}

      {structureQ.data && structureQ.data.map((f) => {
        const floorUnits = f.units.length;
        const floorOcc = f.units.filter((r) => r.occupancy_status === "occupied").length;
        const isCollapsed = collapsed.has(String(f.id));
        return (
          <section key={f.id} className="floorplan-page space-y-3 print:break-inside-avoid">
            <button
              type="button"
              onClick={() => toggleFloor(f.id)}
              aria-expanded={!isCollapsed}
              aria-controls={`floor-${f.id}-units`}
              className="group w-full flex items-center justify-between gap-3 rounded-lg px-2 py-1.5 -mx-2 hover:bg-accent/40 transition-colors print:hover:bg-transparent print:pointer-events-none"
            >
              <div className="inline-flex items-center gap-2.5 min-w-0">
                <ChevronDown
                  className={
                    "h-4 w-4 text-muted-foreground transition-transform shrink-0 print:hidden " +
                    (isCollapsed ? "-rotate-90" : "rotate-0")
                  }
                  aria-hidden="true"
                />
                <div className="grid place-items-center h-8 w-8 rounded-lg bg-primary/10 text-primary shrink-0">
                  <Layers className="h-4 w-4" />
                </div>
                <div className="min-w-0 text-left">
                  <h2 className="text-base font-semibold leading-tight truncate">Floor {f.floor_number}</h2>
                  <div className="text-[11px] text-muted-foreground inline-flex items-center gap-2 flex-wrap">
                    <span className="inline-flex items-center gap-1">
                      <DoorClosed className="h-3 w-3" /> {floorUnits} unit{floorUnits === 1 ? "" : "s"}
                    </span>
                    {floorUnits > 0 && (
                      <span className="text-emerald-600 dark:text-emerald-400 font-medium">
                        {Math.round((floorOcc / floorUnits) * 100)}% occ
                      </span>
                    )}
                  </div>
                </div>
              </div>
              {isCollapsed && (
                <span className="text-[10px] text-muted-foreground print:hidden shrink-0">
                  click to expand
                </span>
              )}
            </button>

            <div
              id={`floor-${f.id}-units`}
              className={isCollapsed ? "hidden print:block" : "block"}
            >
              {f.units.length === 0 ? (
                <div className="text-xs text-muted-foreground italic">No units on this floor.</div>
              ) : (
                <div className="grid grid-cols-3 sm:grid-cols-5 md:grid-cols-7 xl:grid-cols-9 gap-2 print:grid-cols-6">
                  {f.units.map((r) => (
                    <UnitTile key={r.id} unit={r} facilityCodes={facilityCodes} />
                  ))}
                </div>
              )}
            </div>
          </section>
        );
      })}
    </div>
  );
}

// Print styles for this page live in src/app/globals.css under
// `@media print`. They key off the `.floorplan-page` class added to each
// floor section and the `.floorplan-print-root` class on the outer
// wrapper, so nothing leaks into the rest of the app.
