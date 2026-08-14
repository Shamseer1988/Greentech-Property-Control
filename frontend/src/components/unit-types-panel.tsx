"use client";

import { useEffect, useState } from "react";
import { Plus } from "lucide-react";
import { api } from "@/lib/api";
import { Can } from "@/components/can";
import { Field, inputClass, selectClass } from "@/components/ui/dialog";
import { toast, errorMessage } from "@/components/ui/toast";

type UnitType = {
  id: number; code: string; name: string;
  is_facility: boolean; bulk_mode: "floors" | "count"; is_active: boolean;
};

/** Settings → Property panel for the unit_types master — same
 *  deactivate-only / "Show deactivated" pattern as `PropertyTypesPanel`,
 *  extended with `is_facility` and `bulk_mode` (Floors vs Count), the two
 *  fields the property layout wizard reads to decide how a building of
 *  this type generates its floors/units. */
export function UnitTypesPanel() {
  const [types, setTypes] = useState<UnitType[]>([]);
  const [loading, setLoading] = useState(true);
  const [showDeactivated, setShowDeactivated] = useState(false);
  const [showNew, setShowNew] = useState(false);
  const [newForm, setNewForm] = useState({ name: "", is_facility: false, bulk_mode: "floors" });
  const [busy, setBusy] = useState<number | "new" | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      const r = await api.get("/units/types");
      setTypes(r.data.data ?? []);
    } finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []);

  const visible = showDeactivated ? types : types.filter((t) => t.is_active);

  const create = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newForm.name.trim()) return;
    setBusy("new");
    try {
      await api.post("/units/types", newForm);
      toast.success("Unit type created");
      setNewForm({ name: "", is_facility: false, bulk_mode: "floors" });
      setShowNew(false);
      await load();
    } catch (err: unknown) {
      toast.error("Could not create unit type", errorMessage(err));
    } finally { setBusy(null); }
  };

  const toggleActive = async (t: UnitType) => {
    setBusy(t.id);
    try {
      await api.patch(`/units/types/${t.id}`, { is_active: !t.is_active });
      await load();
    } catch (err: unknown) {
      toast.error("Could not update unit type", errorMessage(err));
    } finally { setBusy(null); }
  };

  const rename = async (t: UnitType, name: string) => {
    if (!name.trim() || name === t.name) return;
    setBusy(t.id);
    try {
      await api.patch(`/units/types/${t.id}`, { name: name.trim() });
      await load();
    } catch (err: unknown) {
      toast.error("Could not rename unit type", errorMessage(err));
    } finally { setBusy(null); }
  };

  const setBulkMode = async (t: UnitType, bulk_mode: string) => {
    if (bulk_mode === t.bulk_mode) return;
    setBusy(t.id);
    try {
      await api.patch(`/units/types/${t.id}`, { bulk_mode });
      await load();
    } catch (err: unknown) {
      toast.error("Could not update unit type", errorMessage(err));
    } finally { setBusy(null); }
  };

  const setFacility = async (t: UnitType, is_facility: boolean) => {
    setBusy(t.id);
    try {
      await api.patch(`/units/types/${t.id}`, { is_facility });
      await load();
    } catch (err: unknown) {
      toast.error("Could not update unit type", errorMessage(err));
    } finally { setBusy(null); }
  };

  return (
    <div className="rounded-lg border border-border bg-card/40 p-3 space-y-3">
      <div className="flex justify-between items-center gap-2 flex-wrap">
        <div>
          <div className="text-sm font-medium">Unit types</div>
          <p className="text-xs text-muted-foreground">
            Offered when creating a unit, and when generating a property&apos;s floors —
            &quot;Floors&quot; types walk floors x rooms-per-floor, &quot;Count&quot; types (store, shop…)
            are a flat quantity with no floor breakdown.
          </p>
        </div>
        <Can perm="settings.manage">
          <div className="flex items-center gap-3">
            <label className="inline-flex items-center gap-1.5 text-xs text-muted-foreground whitespace-nowrap">
              <input type="checkbox" checked={showDeactivated} onChange={(e) => setShowDeactivated(e.target.checked)} />
              Show deactivated
            </label>
            <button type="button" onClick={() => setShowNew((v) => !v)}
              className="inline-flex h-8 items-center gap-1.5 rounded-md border border-border bg-card/60 px-2.5 text-xs hover:bg-accent">
              <Plus className="h-3.5 w-3.5" /> New type
            </button>
          </div>
        </Can>
      </div>

      {showNew && (
        <form onSubmit={create} className="rounded-lg border border-border bg-card/40 p-3 grid grid-cols-2 gap-2">
          <Field label="Name" span={2}>
            <input required className={inputClass} value={newForm.name}
              onChange={(e) => setNewForm((f) => ({ ...f, name: e.target.value }))} placeholder="e.g. Warehouse" />
          </Field>
          <Field label="Generation mode">
            <select className={selectClass} value={newForm.bulk_mode}
              onChange={(e) => setNewForm((f) => ({ ...f, bulk_mode: e.target.value }))}>
              <option value="floors">Floors (floors + rooms/floor)</option>
              <option value="count">Count (flat quantity)</option>
            </select>
          </Field>
          <Field label="Is facility">
            <label className="flex items-center gap-2 h-9">
              <input type="checkbox" checked={newForm.is_facility}
                onChange={(e) => setNewForm((f) => ({ ...f, is_facility: e.target.checked }))} />
              <span className="text-sm">Shared/dedicated facility, not let on its own</span>
            </label>
          </Field>
          <div className="col-span-2 flex justify-end">
            <button type="submit" disabled={busy === "new"}
              className="h-9 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground disabled:opacity-60">
              {busy === "new" ? "Creating…" : "Create"}
            </button>
          </div>
        </form>
      )}

      <div className="rounded-lg overflow-hidden border border-border/60">
        <table className="w-full text-sm">
          <thead className="text-left text-xs text-muted-foreground border-b border-border bg-card/60">
            <tr>
              <th className="py-2 px-3">Code</th>
              <th className="py-2 px-3">Name</th>
              <th className="py-2 px-3">Generation mode</th>
              <th className="py-2 px-3">Facility</th>
              <th className="py-2 px-3 text-right">Active</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={5} className="py-6 text-center text-muted-foreground">Loading…</td></tr>
            ) : visible.length === 0 ? (
              <tr><td colSpan={5} className="py-6 text-center text-muted-foreground">No unit types.</td></tr>
            ) : visible.map((t) => (
              <tr key={t.id} className={"border-b border-border/60 last:border-0 " + (!t.is_active ? "opacity-50" : "")}>
                <td className="py-2 px-3 font-mono text-xs">{t.code}</td>
                <td className="py-2 px-3">
                  <Can perm="settings.manage" fallback={<span>{t.name}</span>}>
                    <input
                      defaultValue={t.name}
                      disabled={busy === t.id}
                      onBlur={(e) => rename(t, e.target.value)}
                      className="bg-transparent border-0 focus:outline-none focus:ring-1 focus:ring-ring rounded px-1 -mx-1 w-full"
                    />
                  </Can>
                </td>
                <td className="py-2 px-3">
                  <Can perm="settings.manage" fallback={<span className="text-xs capitalize">{t.bulk_mode}</span>}>
                    <select className={selectClass + " h-8 text-xs"} value={t.bulk_mode} disabled={busy === t.id}
                      onChange={(e) => setBulkMode(t, e.target.value)}>
                      <option value="floors">Floors</option>
                      <option value="count">Count</option>
                    </select>
                  </Can>
                </td>
                <td className="py-2 px-3">
                  <Can perm="settings.manage" fallback={<span className="text-xs">{t.is_facility ? "Yes" : "—"}</span>}>
                    <input type="checkbox" checked={t.is_facility} disabled={busy === t.id}
                      onChange={(e) => setFacility(t, e.target.checked)} />
                  </Can>
                </td>
                <td className="py-2 px-3 text-right">
                  <Can perm="settings.manage" fallback={
                    <span className={"rounded-full px-2 py-0.5 text-xs " +
                      (t.is_active ? "bg-emerald-500/10 text-emerald-600" : "bg-muted text-muted-foreground")}>
                      {t.is_active ? "Active" : "Inactive"}
                    </span>
                  }>
                    <button type="button" onClick={() => toggleActive(t)} disabled={busy === t.id}
                      className={"rounded-full px-2 py-0.5 text-xs " +
                        (t.is_active ? "bg-emerald-500/10 text-emerald-600" : "bg-muted text-muted-foreground")}>
                      {t.is_active ? "Active" : "Inactive"}
                    </button>
                  </Can>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
