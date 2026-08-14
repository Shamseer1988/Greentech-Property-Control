"use client";

import { useEffect, useState } from "react";
import { Plus } from "lucide-react";
import { api } from "@/lib/api";
import { Can } from "@/components/can";
import { Field, inputClass } from "@/components/ui/dialog";
import { toast, errorMessage } from "@/components/ui/toast";

type PropType = { id: number; code: string; name: string; is_active: boolean };

/** Settings → Property panel for the property_types master — same
 *  deactivate-only / "Show deactivated" pattern as expense categories
 *  (`expenses/page.tsx`'s CategoriesDialog), just laid out inline since
 *  it already lives inside the Settings category body rather than a
 *  separate modal. */
export function PropertyTypesPanel() {
  const [types, setTypes] = useState<PropType[]>([]);
  const [loading, setLoading] = useState(true);
  const [showDeactivated, setShowDeactivated] = useState(false);
  const [showNew, setShowNew] = useState(false);
  const [newName, setNewName] = useState("");
  const [busy, setBusy] = useState<number | "new" | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      const r = await api.get("/properties/types");
      setTypes(r.data.data ?? []);
    } finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []);

  const visible = showDeactivated ? types : types.filter((t) => t.is_active);

  const create = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newName.trim()) return;
    setBusy("new");
    try {
      await api.post("/properties/types", { name: newName.trim() });
      toast.success("Property type created");
      setNewName("");
      setShowNew(false);
      await load();
    } catch (err: unknown) {
      toast.error("Could not create property type", errorMessage(err));
    } finally { setBusy(null); }
  };

  const toggleActive = async (t: PropType) => {
    setBusy(t.id);
    try {
      await api.patch(`/properties/types/${t.id}`, { is_active: !t.is_active });
      await load();
    } catch (err: unknown) {
      toast.error("Could not update property type", errorMessage(err));
    } finally { setBusy(null); }
  };

  const rename = async (t: PropType, name: string) => {
    if (!name.trim() || name === t.name) return;
    setBusy(t.id);
    try {
      await api.patch(`/properties/types/${t.id}`, { name: name.trim() });
      await load();
    } catch (err: unknown) {
      toast.error("Could not rename property type", errorMessage(err));
    } finally { setBusy(null); }
  };

  return (
    <div className="rounded-lg border border-border bg-card/40 p-3 space-y-3">
      <div className="flex justify-between items-center gap-2 flex-wrap">
        <div>
          <div className="text-sm font-medium">Property types</div>
          <p className="text-xs text-muted-foreground">
            Offered when creating or editing a property. Deactivate instead of delete —
            existing properties keep whatever type they were given.
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
        <form onSubmit={create} className="flex items-end gap-2">
          <Field label="Name">
            <input required className={inputClass} value={newName}
              onChange={(e) => setNewName(e.target.value)} placeholder="e.g. Warehouse" />
          </Field>
          <button type="submit" disabled={busy === "new"}
            className="h-9 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground disabled:opacity-60">
            {busy === "new" ? "Creating…" : "Create"}
          </button>
        </form>
      )}

      <div className="rounded-lg overflow-hidden border border-border/60">
        <table className="w-full text-sm">
          <thead className="text-left text-xs text-muted-foreground border-b border-border bg-card/60">
            <tr>
              <th className="py-2 px-3">Code</th>
              <th className="py-2 px-3">Name</th>
              <th className="py-2 px-3 text-right">Active</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={3} className="py-6 text-center text-muted-foreground">Loading…</td></tr>
            ) : visible.length === 0 ? (
              <tr><td colSpan={3} className="py-6 text-center text-muted-foreground">No property types.</td></tr>
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
