"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Plus, Building2, MapPin, AlertTriangle, Layers, Store, Trash2,
  ArrowRight, ArrowLeft, CheckCircle2, Home, Sparkles,
  ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight,
} from "lucide-react";
import { api } from "@/lib/api";
import { Can } from "@/components/can";
import { Modal, Field, inputClass, selectClass, textareaClass } from "@/components/ui/dialog";
import { toast, errorMessage } from "@/components/ui/toast";
import { Skeleton, EmptyState } from "@/components/ui/states";
import { useDebouncedValue } from "@/lib/use-debounce";
import { usePropertyTypes } from "@/lib/use-property-types";
import { useUnitTypes } from "@/lib/use-unit-types";
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

const OWNERSHIP = ["rented", "company_owned", "temporary"];
const STATUSES = ["active", "inactive", "maintenance", "on_hold"];

function statusBadgeClass(s: string): string {
  if (s === "active") return "bg-emerald-500/10 text-emerald-600";
  if (s === "on_hold") return "bg-amber-500/10 text-amber-600";
  if (s === "maintenance") return "bg-sky-500/10 text-sky-600";
  return "bg-muted text-muted-foreground";
}

export default function PropertiesPage() {
  const router = useRouter();
  const qc = useQueryClient();
  const { types: propertyTypes } = usePropertyTypes();
  const [q, setQ] = useState("");
  const debouncedQ = useDebouncedValue(q);
  const [status, setStatus] = useState("");
  const [showDeactivated, setShowDeactivated] = useState(false);
  const [type, setType] = useState("");
  const [showForm, setShowForm] = useState(false);
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
  const invalidate = () => qc.invalidateQueries({ queryKey: keys.properties.all() });

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
          <button onClick={() => setShowForm(true)}
            className="inline-flex h-9 items-center gap-2 rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground hover:bg-primary/90">
            <Plus className="h-4 w-4" /> New property
          </button>
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

      <PropertyDialog open={showForm} onClose={() => setShowForm(false)}
        onSaved={() => { setShowForm(false); invalidate(); }} />
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

type LandlordOption = { id: number; code: string; name: string };

const MAX_FLOORS = 50;
const MAX_UPF = 100;
const MAX_STORES = 50;
const MAX_BUILDINGS = 20;

type LayoutSpec = {
  floors: number;
  units_per_floor: number;
  floor_prefix: string;
  unit_prefix: string;
  ground_floor: boolean;
  default_unit_type: string;
};

const DEFAULT_LAYOUT: LayoutSpec = {
  floors: 1,
  units_per_floor: 4,
  floor_prefix: "",
  unit_prefix: "",
  ground_floor: false,
  default_unit_type: "room",
};

/** One building inside a compound — a wing, a block, a standalone
 * villa on a shared plot. Which fields apply depends on the selected
 * unit type's generation mode (see Unit Types under Settings → Property):
 * "floors" types (room, villa…) walk floors x rooms-per-floor; "count"
 * types (store, shop…) are a flat quantity on one dedicated floor, with
 * an optional mezzanine unit and/or one linked room per unit. A building
 * never mixes the two shapes — the chosen type alone decides which
 * fields render, so a store-type building never shows a stray Floors
 * field, and a room-type building never gets a bolted-on store count. */
type BuildingSpec = {
  key: string;           // stable React key, not sent to the API
  code: string;           // short label used in floor/unit numbers — "A" if left blank
  label: string;
  unit_type: string;
  // "floors" mode:
  floors: number;
  units_per_floor: number;
  ground_floor: boolean;
  // "count" mode:
  unit_count: number;
  with_mezzanine: boolean;
  room_with_store: boolean;
};

let buildingSeq = 0;
function newBuilding(index: number, defaultUnitType = "room"): BuildingSpec {
  buildingSeq += 1;
  return {
    key: `b${buildingSeq}`,
    code: "",
    label: `Building ${String.fromCharCode(65 + (index % 26))}`,
    unit_type: defaultUnitType,
    floors: 1,
    units_per_floor: 4,
    ground_floor: false,
    unit_count: 0,
    with_mezzanine: false,
    room_with_store: false,
  };
}

function clamp(n: number, lo: number, hi: number) {
  if (Number.isNaN(n)) return lo;
  return Math.max(lo, Math.min(hi, Math.floor(n)));
}

function letterFor(index: number): string {
  const letter = String.fromCharCode(65 + (index % 26));
  const cycle = Math.floor(index / 26) + 1;
  return cycle === 1 ? letter : `${letter}${cycle}`;
}

type Step = "details" | "structure";
type StructureMode = "single" | "compound";

function PropertyDialog({ open, onClose, onSaved }: { open: boolean; onClose: () => void; onSaved: () => void }) {
  const router = useRouter();
  const { types: propertyTypes } = usePropertyTypes();
  const { types: unitTypes } = useUnitTypes();
  const unitTypeByCode = useMemo(
    () => Object.fromEntries(unitTypes.map((t) => [t.code, t])), [unitTypes]);
  const bulkModeFor = (code: string) => unitTypeByCode[code]?.bulk_mode ?? "floors";
  const [step, setStep] = useState<Step>("details");
  const [form, setForm] = useState<Record<string, unknown>>({ property_type: "full_building", ownership_type: "rented" });
  const [landlords, setLandlords] = useState<LandlordOption[]>([]);
  const [busy, setBusy] = useState(false);
  const [genLayout, setGenLayout] = useState(true);
  const [mode, setMode] = useState<StructureMode>("single");
  const [layout, setLayout] = useState<LayoutSpec>(DEFAULT_LAYOUT);
  const [buildings, setBuildings] = useState<BuildingSpec[]>([newBuilding(0), newBuilding(1)]);

  useEffect(() => {
    if (open) {
      setStep("details");
      setForm({ property_type: "full_building", ownership_type: "rented" });
      setGenLayout(true);
      setMode("single");
      setLayout(DEFAULT_LAYOUT);
      setBuildings([newBuilding(0), newBuilding(1)]);
      api.get("/landlords").then((r) => setLandlords(r.data.data)).catch(() => setLandlords([]));
    }
  }, [open]);

  const set = (k: string, v: unknown) => setForm((f) => ({ ...f, [k]: v }));
  const setL = <K extends keyof LayoutSpec>(k: K, v: LayoutSpec[K]) => setLayout((l) => ({ ...l, [k]: v }));
  const setB = <K extends keyof BuildingSpec>(key: string, k: K, v: BuildingSpec[K]) =>
    setBuildings((rows) => rows.map((r) => (r.key === key ? { ...r, [k]: v } : r)));

  const name = String(form.name ?? "").trim();
  const canContinue = name.length > 0 && !!form.property_type;

  const safe = useMemo(() => ({
    floors: clamp(layout.floors, 1, MAX_FLOORS),
    units_per_floor: clamp(layout.units_per_floor, 1, MAX_UPF),
  }), [layout.floors, layout.units_per_floor]);

  const safeBuildings = useMemo(() => buildings.map((b, i) => ({
    ...b,
    floors: clamp(b.floors, 1, MAX_FLOORS),
    units_per_floor: clamp(b.units_per_floor, 1, MAX_UPF),
    unit_count: clamp(b.unit_count, 0, MAX_STORES),
    resolvedCode: b.code.trim().toUpperCase() || letterFor(i),
  })), [buildings]);

  const totals = useMemo(() => {
    if (mode === "compound") {
      return safeBuildings.reduce((acc, b) => {
        if (bulkModeFor(b.unit_type) === "floors") {
          const rooms = b.floors * b.units_per_floor;
          return {
            buildings: acc.buildings + 1, floors: acc.floors + b.floors,
            rooms: acc.rooms + rooms, stores: acc.stores, units: acc.units + rooms,
          };
        }
        const storeUnits = b.unit_count;
        const roomUnits = b.room_with_store ? b.unit_count : 0;
        const mezzUnits = b.with_mezzanine ? 1 : 0;
        const hasFloor = b.unit_count > 0 || b.with_mezzanine;
        return {
          buildings: acc.buildings + 1, floors: acc.floors + (hasFloor ? 1 : 0),
          rooms: acc.rooms + roomUnits, stores: acc.stores + storeUnits,
          units: acc.units + storeUnits + roomUnits + mezzUnits,
        };
      }, { buildings: 0, floors: 0, rooms: 0, stores: 0, units: 0 });
    }
    const rooms = safe.floors * safe.units_per_floor;
    return { buildings: 1, floors: safe.floors, rooms, stores: 0, units: rooms };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, safeBuildings, safe, unitTypeByCode]);

  const codesClash = useMemo(() => {
    const seen = new Set<string>();
    for (const b of safeBuildings) {
      if (seen.has(b.resolvedCode)) return true;
      seen.add(b.resolvedCode);
    }
    return false;
  }, [safeBuildings]);

  const sample = useMemo(() => {
    const floorSeq = layout.ground_floor ? "G" : "1";
    const pad = Math.max(2, String(safe.units_per_floor).length);
    return `${layout.unit_prefix}${floorSeq}${String(1).padStart(pad, "0")}`;
  }, [layout.ground_floor, layout.unit_prefix, safe.units_per_floor]);

  const addBuilding = () => setBuildings((rows) =>
    rows.length >= MAX_BUILDINGS ? rows : [...rows, newBuilding(rows.length)]);
  const removeBuilding = (key: string) => setBuildings((rows) =>
    rows.length <= 1 ? rows : rows.filter((r) => r.key !== key));

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      const payload: Record<string, unknown> = { ...form };
      if (genLayout) {
        payload.layout = mode === "compound"
          ? {
              buildings: safeBuildings.map((b) => {
                const base = {
                  code: b.code.trim() || undefined,
                  label: b.label.trim() || undefined,
                  unit_type: b.unit_type,
                };
                return bulkModeFor(b.unit_type) === "floors"
                  ? { ...base, floors: b.floors, units_per_floor: b.units_per_floor, ground_floor: b.ground_floor }
                  : { ...base, unit_count: b.unit_count, with_mezzanine: b.with_mezzanine, room_with_store: b.room_with_store };
              }),
            }
          : {
              floors: safe.floors,
              units_per_floor: safe.units_per_floor,
              floor_prefix: layout.floor_prefix,
              unit_prefix: layout.unit_prefix,
              ground_floor: layout.ground_floor,
              default_unit_type: layout.default_unit_type,
            };
      }
      const resp = await api.post("/properties", payload);
      const created = resp.data?.data as {
        id?: number; code?: string;
        layout_generated?: { floors: number; units: number; buildings?: number };
      } | undefined;
      const gen = created?.layout_generated;
      const detail = gen
        ? (gen.buildings
            ? `${gen.buildings} building${gen.buildings === 1 ? "" : "s"} · ${gen.floors} floor${gen.floors === 1 ? "" : "s"} · ${gen.units} units`
            : `${gen.floors} floor${gen.floors === 1 ? "" : "s"} · ${gen.units} units`)
        : undefined;
      toast.success(`Property ${created?.code ?? ""} created`, detail);
      onSaved();
      if (genLayout && created?.id) {
        router.push(`/properties/${created.id}?tab=units`);
      }
    } catch (err: unknown) {
      toast.error("Save failed", errorMessage(err));
    } finally { setBusy(false); }
  };

  const structureInvalid = genLayout && mode === "compound" && (buildings.length === 0 || codesClash);

  return (
    <Modal open={open} onClose={onClose} title="New property" icon={Building2}
      description={step === "details"
        ? "Where it is and who it belongs to."
        : "Pick a unit type per building, then fill in what it needs."}
      size={step === "structure" && mode === "compound" ? "2xl" : "lg"}>
      <div className="mb-5 flex items-center gap-2 text-xs">
        <StepPill active={step === "details"} done={step === "structure"} label="Details" number={1} />
        <div className="h-px flex-1 bg-border" />
        <StepPill active={step === "structure"} done={false} label="Structure" number={2} />
      </div>

      {step === "details" && (
        <form onSubmit={(e) => { e.preventDefault(); setStep("structure"); }} className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <Field label="Name" span={2}>
              <input required autoFocus className={inputClass} value={String(form.name ?? "")}
                onChange={(e) => set("name", e.target.value)} />
            </Field>
            <Field label="Landlord">
              <select className={selectClass} value={String(form.landlord_id ?? "")} onChange={(e) => set("landlord_id", e.target.value ? Number(e.target.value) : null)}>
                <option value="">— None —</option>
                {landlords.map((l) => (
                  <option key={l.id} value={l.id}>
                    {l.name} ({l.code})
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Type">
              <select className={selectClass} value={String(form.property_type ?? "")} onChange={(e) => set("property_type", e.target.value)}>
                {propertyTypes.map((t) => <option key={t.code} value={t.code}>{t.name}</option>)}
              </select>
            </Field>
            <Field label="Building number"><input className={inputClass} onChange={(e) => set("building_number", e.target.value)} /></Field>
            <Field label="Zone"><input className={inputClass} onChange={(e) => set("zone", e.target.value)} /></Field>
            <Field label="Street"><input className={inputClass} onChange={(e) => set("street", e.target.value)} /></Field>
            <Field label="Area"><input className={inputClass} onChange={(e) => set("area", e.target.value)} /></Field>
            <Field label="City"><input className={inputClass} onChange={(e) => set("city", e.target.value)} /></Field>
            <Field label="Google map link"><input className={inputClass} onChange={(e) => set("map_link", e.target.value)} /></Field>
            <Field label="Ownership">
              <select className={selectClass} value={String(form.ownership_type ?? "rented")} onChange={(e) => set("ownership_type", e.target.value)}>
                {OWNERSHIP.map((o) => <option key={o} value={o}>{o.replaceAll("_", " ")}</option>)}
              </select>
            </Field>
            <Field label="Managed by"><input className={inputClass} onChange={(e) => set("managed_by", e.target.value)} /></Field>
          </div>
          <Field label="Remarks"><textarea className={textareaClass} onChange={(e) => set("remarks", e.target.value)} /></Field>

          <div className="flex justify-end gap-2 pt-2 border-t border-border">
            <button type="button" onClick={onClose} className="h-9 rounded-md border border-border bg-card/60 px-3 text-sm hover:bg-accent">Cancel</button>
            <button type="submit" disabled={!canContinue}
              className="h-9 inline-flex items-center gap-1.5 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50">
              Continue <ArrowRight className="h-3.5 w-3.5" />
            </button>
          </div>
        </form>
      )}

      {step === "structure" && (
        <form onSubmit={save} className="space-y-3">
          <div className="rounded-lg border border-border bg-card/40 p-3 space-y-3">
            <label className="inline-flex items-start gap-2 text-sm cursor-pointer">
              <input type="checkbox" checked={genLayout} onChange={(e) => setGenLayout(e.target.checked)} className="mt-0.5" />
              <span>
                <span className="font-medium">Generate floors and units now</span>
                <span className="block text-xs text-muted-foreground">
                  Builds the whole structure in one shot. You can still add, edit or remove floors / units afterwards.
                </span>
              </span>
            </label>

            {genLayout && (
              <>
                <div className="grid grid-cols-2 gap-2">
                  <ModeCard active={mode === "single"} icon={Home} title="One building"
                    hint="Floors and rooms, all in one structure."
                    onClick={() => setMode("single")} />
                  <ModeCard active={mode === "compound"} icon={Layers} title="Compound"
                    hint="Two or more buildings sharing one plot."
                    onClick={() => setMode("compound")} />
                </div>

                {mode === "single" ? (
                  <>
                    <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                      <Field label={`Number of floors (1-${MAX_FLOORS})`}>
                        <input type="number" min={1} max={MAX_FLOORS} className={inputClass}
                          value={layout.floors} onChange={(e) => setL("floors", Number(e.target.value))} />
                      </Field>
                      <Field label={`Rooms per floor (1-${MAX_UPF})`}>
                        <input type="number" min={1} max={MAX_UPF} className={inputClass}
                          value={layout.units_per_floor} onChange={(e) => setL("units_per_floor", Number(e.target.value))} />
                      </Field>
                      <Field label="Floor number prefix">
                        <input className={inputClass} value={layout.floor_prefix}
                          onChange={(e) => setL("floor_prefix", e.target.value)} placeholder='e.g. "F" or leave empty' />
                      </Field>
                      <Field label="Unit number prefix">
                        <input className={inputClass} value={layout.unit_prefix}
                          onChange={(e) => setL("unit_prefix", e.target.value)} placeholder="usually empty" />
                      </Field>
                      <Field label="Include ground floor">
                        <label className="flex items-center gap-2 h-9">
                          <input type="checkbox" checked={layout.ground_floor}
                            onChange={(e) => setL("ground_floor", e.target.checked)} />
                          <span className="text-sm">First floor becomes “G”</span>
                        </label>
                      </Field>
                      <Field label="Default unit type">
                        <select className={selectClass} value={layout.default_unit_type}
                          onChange={(e) => setL("default_unit_type", e.target.value)}>
                          {unitTypes.map((t) => <option key={t.code} value={t.code}>{t.name}</option>)}
                        </select>
                      </Field>
                    </div>
                    <div className="text-xs rounded-md bg-background/40 border border-border px-3 py-2 font-mono">
                      Will create <span className="font-semibold">{totals.floors}</span> floor{totals.floors === 1 ? "" : "s"},
                      {" "}<span className="font-semibold">{totals.rooms}</span> units.
                      {" "}First unit number: <span className="text-primary">{sample}</span>
                    </div>
                  </>
                ) : (
                  <>
                    <div className="space-y-3 max-h-[420px] overflow-y-auto pr-1">
                      {safeBuildings.map((b, i) => {
                        const bulkMode = bulkModeFor(b.unit_type);
                        return (
                          <div key={b.key} className="rounded-lg border border-border bg-background/40 p-3 space-y-3">
                            <div className="flex items-center gap-2">
                              <span className="h-6 w-6 shrink-0 rounded-md bg-primary/10 text-primary text-xs font-semibold grid place-items-center">
                                {b.resolvedCode}
                              </span>
                              <input className={inputClass + " h-8"} value={buildings[i].label}
                                placeholder={`Building ${b.resolvedCode}`}
                                onChange={(e) => setB(b.key, "label", e.target.value)} />
                              <input className={inputClass + " h-8 w-20 shrink-0"} value={buildings[i].code}
                                placeholder="code" maxLength={4}
                                onChange={(e) => setB(b.key, "code", e.target.value)} />
                              <button type="button" onClick={() => removeBuilding(b.key)}
                                disabled={buildings.length <= 1}
                                className="h-8 w-8 shrink-0 rounded-md grid place-items-center text-muted-foreground hover:bg-destructive/10 hover:text-destructive disabled:opacity-30 disabled:hover:bg-transparent">
                                <Trash2 className="h-3.5 w-3.5" />
                              </button>
                            </div>

                            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                              <MiniField label="Unit type">
                                <select className={selectClass + " h-8"} value={buildings[i].unit_type}
                                  onChange={(e) => setB(b.key, "unit_type", e.target.value)}>
                                  {unitTypes.map((t) => <option key={t.code} value={t.code}>{t.name}</option>)}
                                </select>
                              </MiniField>
                              {bulkMode === "floors" ? (
                                <>
                                  <MiniField label="Floors">
                                    <input type="number" min={1} max={MAX_FLOORS} className={inputClass + " h-8"}
                                      value={buildings[i].floors} onChange={(e) => setB(b.key, "floors", Number(e.target.value))} />
                                  </MiniField>
                                  <MiniField label="Rooms / floor">
                                    <input type="number" min={1} max={MAX_UPF} className={inputClass + " h-8"}
                                      value={buildings[i].units_per_floor} onChange={(e) => setB(b.key, "units_per_floor", Number(e.target.value))} />
                                  </MiniField>
                                </>
                              ) : (
                                <MiniField label="Number of units">
                                  <input type="number" min={0} max={MAX_STORES} className={inputClass + " h-8"}
                                    value={buildings[i].unit_count} onChange={(e) => setB(b.key, "unit_count", Number(e.target.value))} />
                                </MiniField>
                              )}
                            </div>

                            {bulkMode === "floors" ? (
                              <label className="inline-flex items-center gap-1.5 text-xs text-muted-foreground cursor-pointer">
                                <input type="checkbox" checked={buildings[i].ground_floor}
                                  onChange={(e) => setB(b.key, "ground_floor", e.target.checked)} />
                                First floor becomes “G”
                              </label>
                            ) : (
                              <div className="flex items-center gap-4">
                                <label className="inline-flex items-center gap-1.5 text-xs text-muted-foreground cursor-pointer">
                                  <input type="checkbox" checked={buildings[i].with_mezzanine}
                                    onChange={(e) => setB(b.key, "with_mezzanine", e.target.checked)} />
                                  Include mezzanine
                                </label>
                                <label className="inline-flex items-center gap-1.5 text-xs text-muted-foreground cursor-pointer">
                                  <input type="checkbox" checked={buildings[i].room_with_store}
                                    onChange={(e) => setB(b.key, "room_with_store", e.target.checked)} />
                                  Room with store
                                </label>
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>

                    <button type="button" onClick={addBuilding} disabled={buildings.length >= MAX_BUILDINGS}
                      className="inline-flex items-center gap-1.5 text-xs font-medium text-primary hover:underline disabled:opacity-40 disabled:no-underline">
                      <Plus className="h-3.5 w-3.5" /> Add another building
                    </button>

                    {codesClash && (
                      <div className="text-xs text-destructive inline-flex items-center gap-1.5">
                        <AlertTriangle className="h-3.5 w-3.5" /> Two buildings have the same code — give each a different one.
                      </div>
                    )}

                    <div className="text-xs rounded-md bg-background/40 border border-border px-3 py-2 flex flex-wrap gap-x-4 gap-y-1 font-mono">
                      <span><span className="font-semibold">{totals.buildings}</span> building{totals.buildings === 1 ? "" : "s"}</span>
                      <span><span className="font-semibold">{totals.floors}</span> floor{totals.floors === 1 ? "" : "s"}</span>
                      <span><span className="font-semibold">{totals.rooms}</span> rooms</span>
                      <span><span className="font-semibold">{totals.stores}</span> stores</span>
                      <span className="text-muted-foreground">= {totals.units} units total</span>
                    </div>
                  </>
                )}
              </>
            )}
          </div>

          <div className="flex justify-between gap-2 pt-2 border-t border-border">
            <button type="button" onClick={() => setStep("details")}
              className="h-9 inline-flex items-center gap-1.5 rounded-md border border-border bg-card/60 px-3 text-sm hover:bg-accent">
              <ArrowLeft className="h-3.5 w-3.5" /> Back
            </button>
            <button type="submit" disabled={busy || structureInvalid}
              className="h-9 inline-flex items-center gap-2 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50">
              <Sparkles className="h-4 w-4" />
              {busy ? "Saving…" : genLayout
                ? `Create + ${totals.units} units`
                : "Create"}
            </button>
          </div>
        </form>
      )}
    </Modal>
  );
}

function StepPill({ active, done, label, number }: {
  active: boolean; done: boolean; label: string; number: number;
}) {
  return (
    <div className={"inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 font-medium " +
      (active ? "bg-primary/10 text-primary" : done ? "text-emerald-600" : "text-muted-foreground")}>
      {done ? <CheckCircle2 className="h-3.5 w-3.5" /> : (
        <span className={"h-4 w-4 rounded-full grid place-items-center text-[10px] " +
          (active ? "bg-primary text-primary-foreground" : "bg-muted")}>{number}</span>
      )}
      {label}
    </div>
  );
}

function ModeCard({ active, icon: Icon, title, hint, onClick }: {
  active: boolean; icon: typeof Home; title: string; hint: string; onClick: () => void;
}) {
  return (
    <button type="button" onClick={onClick}
      className={"text-left rounded-lg border p-3 transition-colors " +
        (active ? "border-primary bg-primary/5" : "border-border bg-background/40 hover:bg-accent/40")}>
      <div className="flex items-center gap-2">
        <Icon className={"h-4 w-4 " + (active ? "text-primary" : "text-muted-foreground")} />
        <span className="text-sm font-medium">{title}</span>
        {active && <CheckCircle2 className="h-3.5 w-3.5 text-primary ml-auto" />}
      </div>
      <div className="mt-1 text-xs text-muted-foreground">{hint}</div>
    </button>
  );
}

function MiniField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <label className="text-[11px] text-muted-foreground">{label}</label>
      {children}
    </div>
  );
}
