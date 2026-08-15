"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft, ArrowRight, Building2, MapPin, AlertTriangle, Layers, Trash2,
  CheckCircle2, Home, Sparkles, Plus,
} from "lucide-react";
import { api } from "@/lib/api";
import { Can } from "@/components/can";
import { Field, inputClass, selectClass, textareaClass } from "@/components/ui/dialog";
import { toast, errorMessage } from "@/components/ui/toast";
import { EmptyState } from "@/components/ui/states";
import { PageHero } from "@/components/ui/page-hero";
import { usePropertyTypes } from "@/lib/use-property-types";
import { useUnitTypes } from "@/lib/use-unit-types";
import { keys } from "@/lib/query-keys";

type LandlordOption = { id: number; code: string; name: string };

const OWNERSHIP = ["rented", "company_owned", "temporary"];

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

type StructureMode = "single" | "compound";

/** Full-page "New property" flow — Details and Structure render together
 * (no step-clicking) with a sticky live-preview/checkout-style panel on
 * the right, reachable at /properties/new instead of the old popup. */
export default function NewPropertyPage() {
  const router = useRouter();
  const qc = useQueryClient();
  const { types: propertyTypes } = usePropertyTypes();
  const { types: unitTypes } = useUnitTypes();
  const unitTypeByCode = useMemo(
    () => Object.fromEntries(unitTypes.map((t) => [t.code, t])), [unitTypes]);
  const bulkModeFor = (code: string) => unitTypeByCode[code]?.bulk_mode ?? "floors";
  const unitsForBuilding = (b: BuildingSpec) => bulkModeFor(b.unit_type) === "floors"
    ? b.floors * b.units_per_floor
    : b.unit_count + (b.room_with_store ? b.unit_count : 0) + (b.with_mezzanine ? 1 : 0);

  const [section, setSection] = useState<"details" | "structure">("details");
  const [form, setForm] = useState<Record<string, unknown>>({ property_type: "full_building", ownership_type: "rented" });
  const [landlords, setLandlords] = useState<LandlordOption[]>([]);
  const [busy, setBusy] = useState(false);
  const [genLayout, setGenLayout] = useState(true);
  const [mode, setMode] = useState<StructureMode>("single");
  const [layout, setLayout] = useState<LayoutSpec>(DEFAULT_LAYOUT);
  const [buildings, setBuildings] = useState<BuildingSpec[]>([newBuilding(0), newBuilding(1)]);

  useEffect(() => {
    api.get("/landlords").then((r) => setLandlords(r.data.data)).catch(() => setLandlords([]));
  }, []);

  const set = (k: string, v: unknown) => setForm((f) => ({ ...f, [k]: v }));
  const setL = <K extends keyof LayoutSpec>(k: K, v: LayoutSpec[K]) => setLayout((l) => ({ ...l, [k]: v }));
  const setB = <K extends keyof BuildingSpec>(key: string, k: K, v: BuildingSpec[K]) =>
    setBuildings((rows) => rows.map((r) => (r.key === key ? { ...r, [k]: v } : r)));

  const name = String(form.name ?? "").trim();

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
    // Enter-key (or a stray submit) while still on the details section
    // should advance to Structure, not silently create the property with
    // whatever default structure settings happen to be sitting unseen.
    if (section !== "structure") { setSection("structure"); return; }
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
      qc.invalidateQueries({ queryKey: keys.properties.all() });
      if (created?.id) {
        router.push(genLayout ? `/properties/${created.id}?tab=units` : `/properties/${created.id}`);
      } else {
        router.push("/properties");
      }
    } catch (err: unknown) {
      toast.error("Save failed", errorMessage(err));
    } finally { setBusy(false); }
  };

  const structureInvalid = genLayout && mode === "compound" && (buildings.length === 0 || codesClash);
  const detailsValid = name.length > 0 && !!form.property_type;
  const canSubmit = detailsValid && !structureInvalid;

  const selectedLandlord = landlords.find((l) => l.id === form.landlord_id);
  const selectedType = propertyTypes.find((t) => t.code === form.property_type);

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <Link href="/properties" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft className="h-3.5 w-3.5" /> Back to properties
        </Link>
      </div>

      <PageHero icon={Building2} title="New property"
        description="Add a building, camp, villa or store — and optionally generate its floors and units right away." />

      <Can perm="property.create" fallback={
        <EmptyState icon={Building2} title="You don't have permission to create properties"
          hint="Ask an administrator to grant the property.create permission." />
      }>
        <form onSubmit={save} className="grid grid-cols-1 lg:grid-cols-[1fr_360px] gap-6 items-start">
          <div className="space-y-6 min-w-0">
            <div className="flex items-center gap-2 text-xs font-medium">
              <button type="button" onClick={() => setSection("details")}
                className={"inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 " +
                  (section === "details" ? "bg-primary/10 text-primary" : "text-muted-foreground hover:text-foreground")}>
                <span className={"h-4 w-4 rounded-full grid place-items-center text-[10px] " +
                  (section === "details" ? "bg-primary text-primary-foreground" : "bg-muted")}>1</span>
                Property details
              </button>
              <div className="h-px flex-1 bg-border" />
              <button type="button" disabled={!detailsValid} onClick={() => detailsValid && setSection("structure")}
                className={"inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 disabled:opacity-40 disabled:cursor-not-allowed " +
                  (section === "structure" ? "bg-primary/10 text-primary" : "text-muted-foreground hover:text-foreground")}>
                <span className={"h-4 w-4 rounded-full grid place-items-center text-[10px] " +
                  (section === "structure" ? "bg-primary text-primary-foreground" : "bg-muted")}>2</span>
                Structure creation
              </button>
            </div>

            {section === "details" && (
            <div className="glass rounded-xl p-5 sm:p-6 space-y-4">
              <h2 className="text-sm font-semibold">Basic details</h2>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <Field label="Name" span={2}>
                  <input required autoFocus className={inputClass} value={String(form.name ?? "")}
                    onChange={(e) => set("name", e.target.value)} />
                </Field>
                <Field label="Landlord">
                  <select className={selectClass} value={String(form.landlord_id ?? "")}
                    onChange={(e) => set("landlord_id", e.target.value ? Number(e.target.value) : null)}>
                    <option value="">— None —</option>
                    {landlords.map((l) => (
                      <option key={l.id} value={l.id}>{l.name} ({l.code})</option>
                    ))}
                  </select>
                </Field>
                <Field label="Type">
                  <select className={selectClass} value={String(form.property_type ?? "")}
                    onChange={(e) => set("property_type", e.target.value)}>
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
                  <select className={selectClass} value={String(form.ownership_type ?? "rented")}
                    onChange={(e) => set("ownership_type", e.target.value)}>
                    {OWNERSHIP.map((o) => <option key={o} value={o}>{o.replaceAll("_", " ")}</option>)}
                  </select>
                </Field>
                <Field label="Managed by"><input className={inputClass} onChange={(e) => set("managed_by", e.target.value)} /></Field>
              </div>
              <Field label="Remarks"><textarea className={textareaClass} onChange={(e) => set("remarks", e.target.value)} /></Field>
              <div className="flex justify-end pt-2 border-t border-border">
                <button type="button" disabled={!detailsValid} onClick={() => setSection("structure")}
                  className="h-9 inline-flex items-center gap-1.5 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50">
                  Continue to structure <ArrowRight className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>
            )}

            {section === "structure" && (
            <div className="glass rounded-xl p-5 sm:p-6 space-y-4">
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-semibold">Structure</h2>
                <button type="button" onClick={() => setSection("details")}
                  className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground">
                  <ArrowLeft className="h-3.5 w-3.5" /> Back to details
                </button>
              </div>
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
                      <div className="space-y-3">
                        {safeBuildings.map((b, i) => {
                          const bulkMode = bulkModeFor(b.unit_type);
                          return (
                            <div key={b.key} className="rounded-lg border border-border bg-background/40 p-3 space-y-3">
                              <div className="flex items-center gap-2">
                                <span className="h-6 w-6 shrink-0 rounded-md bg-primary/10 text-primary text-xs font-semibold grid place-items-center">
                                  {b.resolvedCode}
                                </span>
                                <input className={inputClass + " h-8 min-w-0 flex-1"} value={buildings[i].label}
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
                    </>
                  )}
                </>
              )}
            </div>
            )}
          </div>

          <div className="lg:sticky lg:top-6">
            <div className="glass-strong rounded-xl p-5 space-y-4">
              <div className="flex items-center gap-2">
                <div className="h-9 w-9 rounded-lg bg-primary/10 grid place-items-center shrink-0">
                  <Building2 className="h-4 w-4 text-primary" />
                </div>
                <div className="min-w-0">
                  <div className="font-medium leading-tight truncate">{name || "Untitled property"}</div>
                  <div className="text-xs text-muted-foreground capitalize truncate">{selectedType?.name ?? "—"}</div>
                </div>
              </div>

              {(Boolean(form.area) || Boolean(form.city)) && (
                <div className="text-xs text-muted-foreground flex items-center gap-1">
                  <MapPin className="h-3 w-3" />
                  {[form.area, form.city].filter(Boolean).join(", ")}
                </div>
              )}
              {selectedLandlord && (
                <div className="text-xs text-muted-foreground">Landlord: {selectedLandlord.name}</div>
              )}

              <div className="border-t border-border pt-3 space-y-1.5 text-xs">
                <div className="text-[10px] uppercase tracking-wide text-muted-foreground font-medium">Structure</div>
                {genLayout ? (
                  <>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Buildings</span>
                      <span className="font-semibold">{totals.buildings}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Floors</span>
                      <span className="font-semibold">{totals.floors}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Rooms</span>
                      <span className="font-semibold">{totals.rooms}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Stores</span>
                      <span className="font-semibold">{totals.stores}</span>
                    </div>
                    <div className="flex justify-between pt-1.5 mt-1 border-t border-border/60 font-semibold">
                      <span>Total units</span>
                      <span className="text-primary">{totals.units}</span>
                    </div>
                    {mode === "compound" && safeBuildings.length > 0 && (
                      <div className="pt-2 space-y-1">
                        {safeBuildings.map((b) => (
                          <div key={b.key} className="flex justify-between text-muted-foreground">
                            <span className="truncate pr-2">{b.resolvedCode} · {unitTypeByCode[b.unit_type]?.name ?? b.unit_type}</span>
                            <span className="shrink-0">{unitsForBuilding(b)}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </>
                ) : (
                  <div className="text-muted-foreground">No structure generated yet — add floors and units afterwards.</div>
                )}
              </div>

              {codesClash && (
                <div className="text-xs text-destructive inline-flex items-center gap-1.5">
                  <AlertTriangle className="h-3.5 w-3.5 shrink-0" /> Fix the duplicate building code above to continue.
                </div>
              )}

              <button type="submit" disabled={busy || !canSubmit}
                className="w-full h-10 inline-flex items-center justify-center gap-2 rounded-md bg-primary text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50">
                <Sparkles className="h-4 w-4" />
                {busy ? "Creating…" : genLayout ? `Create + ${totals.units} units` : "Create property"}
              </button>
              <Link href="/properties" className="block text-center text-xs text-muted-foreground hover:text-foreground">
                Cancel
              </Link>
            </div>
          </div>
        </form>
      </Can>
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
