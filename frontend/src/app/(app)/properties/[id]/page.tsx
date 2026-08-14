"use client";

import { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouteParams } from "@/lib/use-route-params";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import {
  ArrowLeft, Building2, Paperclip, FileText, Layers, DoorOpen,
  Calendar, AlertTriangle, Plus, Pencil, Trash2, Hash,
  SlidersHorizontal, Banknote,
} from "lucide-react";
import { api } from "@/lib/api";
import { keys } from "@/lib/query-keys";
import { Can } from "@/components/can";
import { Modal, Field, inputClass, selectClass, textareaClass } from "@/components/ui/dialog";
import { toast, errorMessage } from "@/components/ui/toast";
import { AttachmentsTab } from "@/components/attachments-tab";
import { PropertyMoneyTab } from "@/components/property-money-tab";
import { usePropertyTypes } from "@/lib/use-property-types";
import { useUnitTypes } from "@/lib/use-unit-types";

type Property = {
  id: number;
  code: string;
  name: string;
  property_type: string;
  building_number: string | null;
  zone: string | null;
  street: string | null;
  area: string | null;
  city: string | null;
  map_link: string | null;
  ownership_type: string;
  status: string;
  managed_by: string | null;
  floors_count: number;
  units_count: number;
  remarks: string | null;
  active_agreement: Agreement | null;
};

type Agreement = {
  id: number;
  agreement_number: string | null;
  start_date: string;
  expiry_date: string;
  monthly_rent: number | null;
  security_deposit: number | null;
  payment_terms: string | null;
  notice_period: string | null;
  renewal_status: string;
  reminder_days_before_expiry: number;
  is_active: boolean;
  remarks: string | null;
  landlord: { id: number; code: string; name: string };
};

type Landlord = { id: number; code: string; name: string };

type TabKey = "overview" | "money" | "agreement" | "floors" | "units" | "attachments";

const VALID_TABS: TabKey[] = ["overview", "money", "agreement", "floors", "units", "attachments"];

export default function PropertyDetail({ params }: { params: Promise<{ id: string }> }) {
  const { id } = useRouteParams(params);
  const searchParams = useSearchParams();
  const initialTab = (() => {
    const q = searchParams.get("tab") as TabKey | null;
    return q && VALID_TABS.includes(q) ? q : "overview";
  })();
  const [tab, setTab] = useState<TabKey>(initialTab);
  const qc = useQueryClient();
  const propertyQuery = useQuery({
    queryKey: keys.properties.detail(id),
    queryFn: async () => (await api.get(`/properties/${id}`)).data.data as Property,
  });
  const property = propertyQuery.data ?? null;
  const loading = propertyQuery.isLoading;
  const load = () => qc.invalidateQueries({ queryKey: keys.properties.detail(id) });
  const [showStatusModal, setShowStatusModal] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);

  if (loading || !property) {
    return <div className="text-sm text-muted-foreground animate-pulse">Loading property…</div>;
  }

  const tabs: { key: TabKey; label: string; icon: typeof FileText }[] = [
    { key: "overview", label: "Overview", icon: Building2 },
    { key: "money", label: "Rent & costs", icon: Banknote },
    { key: "agreement", label: "Agreement", icon: FileText },
    { key: "floors", label: "Floors", icon: Layers },
    { key: "units", label: "Units", icon: DoorOpen },
    { key: "attachments", label: "Attachments", icon: Paperclip },
  ];

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <Link href="/properties" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft className="h-3.5 w-3.5" /> Back to properties
        </Link>
        <div className="mt-2 flex items-start justify-between flex-wrap gap-3">
          <div>
            <h1 className="text-2xl lg:text-3xl font-semibold tracking-tight">{property.name}</h1>
            <p className="text-sm text-muted-foreground">
              <span className="font-mono">{property.code}</span> · <span className="capitalize">{property.property_type.replaceAll("_", " ")}</span> · {[property.area, property.city].filter(Boolean).join(", ") || "—"}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <span className={"rounded-full px-3 py-1 text-xs capitalize " + statusBadgeClass(property.status)}>
              {property.status.replace("_", " ")}
            </span>
            <Link
              href={`/properties/${property.id}/floor-plan`}
              className="h-8 inline-flex items-center gap-1 rounded-md border border-border bg-card/60 px-2 text-xs hover:bg-accent"
            >
              Floor plan →
            </Link>
            <Can perm="property.edit">
              <button
                type="button"
                onClick={() => setShowEditModal(true)}
                className="h-8 inline-flex items-center gap-1 rounded-md border border-border bg-card/60 px-2 text-xs hover:bg-accent"
              >
                <Pencil className="h-3.5 w-3.5" /> Edit
              </button>
            </Can>
            <Can perm="property.deactivate">
              <button
                type="button"
                onClick={() => setShowStatusModal(true)}
                className="h-8 inline-flex items-center gap-1 rounded-md border border-border bg-card/60 px-2 text-xs hover:bg-accent"
              >
                <SlidersHorizontal className="h-3.5 w-3.5" /> Change status
              </button>
            </Can>
          </div>
        </div>
      </div>

      <PropertyStatusModal
        open={showStatusModal}
        property={property}
        onClose={() => setShowStatusModal(false)}
        onChanged={async () => { setShowStatusModal(false); await load(); }}
      />

      <EditPropertyDialog
        open={showEditModal}
        property={property}
        onClose={() => setShowEditModal(false)}
        onSaved={async () => { setShowEditModal(false); await load(); }}
      />

      <div className="flex border-b border-border overflow-x-auto">
        {tabs.map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={
              "px-4 py-2 text-sm font-medium border-b-2 transition-colors inline-flex items-center gap-2 " +
              (tab === key ? "border-primary text-primary" : "border-transparent text-muted-foreground hover:text-foreground")
            }
          >
            <Icon className="h-4 w-4" /> {label}
          </button>
        ))}
      </div>

      {tab === "overview" && <OverviewTab property={property} />}
      {tab === "money" && <PropertyMoneyTab propertyId={property.id} />}
      {tab === "agreement" && <AgreementTab property={property} onUpdated={load} />}
      {tab === "floors" && <FloorsTab propertyId={property.id} />}
      {tab === "units" && <UnitsTab propertyId={property.id} />}
      {tab === "attachments" && <AttachmentsTab entityType="property" entityId={property.id} />}
    </div>
  );
}

function OverviewTab({ property }: { property: Property }) {
  const Cell = ({ k, v }: { k: string; v: string | number | null | undefined }) => (
    <div>
      <div className="text-xs uppercase tracking-wide text-muted-foreground">{k}</div>
      <div className="text-sm font-medium">{v ?? "—"}</div>
    </div>
  );
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="glass rounded-xl p-4 lg:col-span-2 grid grid-cols-2 md:grid-cols-3 gap-4">
          <Cell k="Type" v={property.property_type.replaceAll("_", " ")} />
          <Cell k="Ownership" v={property.ownership_type.replaceAll("_", " ")} />
          <Cell k="Managed by" v={property.managed_by} />
          <Cell k="Building #" v={property.building_number} />
          <Cell k="Zone" v={property.zone} />
          <Cell k="Street" v={property.street} />
          <Cell k="Area" v={property.area} />
          <Cell k="City" v={property.city} />
          <Cell k="Floors" v={property.floors_count} />
          <Cell k="Units" v={property.units_count} />
          {property.remarks && (
            <div className="col-span-full">
              <div className="text-xs uppercase tracking-wide text-muted-foreground">Remarks</div>
              <div className="text-sm">{property.remarks}</div>
            </div>
          )}
        </div>
        <div className="glass rounded-xl p-4 space-y-3">
          <div className="text-sm font-semibold">Active agreement</div>
          {property.active_agreement ? (
            <AgreementCard ag={property.active_agreement} />
          ) : (
            <div className="text-sm text-muted-foreground">No active agreement on file.</div>
          )}
          {property.map_link && (
            <a href={property.map_link} target="_blank" rel="noreferrer"
              className="text-xs text-primary underline">Open on Google Maps ↗</a>
          )}
        </div>
      </div>
      <OccupancySnapshot propertyId={property.id} />
    </div>
  );
}

function OccupancySnapshot({ propertyId }: { propertyId: number }) {
  const [units, setUnits] = useState<Unit[] | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api.get(`/properties/${propertyId}/units`)
      .then((r) => { if (!cancelled) setUnits(r.data.data); })
      .catch(() => { if (!cancelled) setUnits(null); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [propertyId]);

  if (loading) {
    return <div className="glass rounded-xl p-4 text-sm text-muted-foreground">Loading occupancy…</div>;
  }
  if (!units || units.length === 0) {
    return <div className="glass rounded-xl p-4 text-sm text-muted-foreground">No units registered yet.</div>;
  }
  const count = (s: string) => units.filter((r) => r.occupancy_status === s).length;
  const total = units.length;
  const occupied = count("occupied");
  const pct = total ? Math.round((occupied * 1000) / total) / 10 : 0;
  const counter = (label: string, value: number, tone: string) => (
    <div className={"rounded-md border px-3 py-2 " + tone}>
      <div className="text-lg font-semibold leading-none">{value}</div>
      <div className="text-[10px] uppercase tracking-wide mt-1">{label}</div>
    </div>
  );
  return (
    <div className="glass rounded-xl p-4 space-y-3">
      <div className="flex items-end justify-between flex-wrap gap-2">
        <div>
          <div className="text-sm font-semibold">Occupancy snapshot</div>
          <div className="text-xs text-muted-foreground">
            Live unit counts. From Phase 2, occupancy derives from active client contracts.
          </div>
        </div>
        <div className="inline-flex items-baseline gap-2">
          <span className="text-2xl font-semibold">{pct}%</span>
          <span className="text-xs text-muted-foreground">occupied of {total} unit{total === 1 ? "" : "s"}</span>
        </div>
      </div>
      <div className="grid grid-cols-3 sm:grid-cols-5 gap-2 text-center">
        {counter("Occupied", occupied, "bg-emerald-500/5 border-emerald-500/30 text-emerald-700 dark:text-emerald-400")}
        {counter("Empty", count("empty"), "bg-muted/30 border-border")}
        {counter("Maintenance", count("maintenance"), "bg-amber-500/5 border-amber-500/30 text-amber-700 dark:text-amber-400")}
        {counter("Blocked", count("blocked"), "bg-rose-500/5 border-rose-500/30 text-rose-700 dark:text-rose-400")}
        {counter("Total", total, "border-border bg-card/60")}
      </div>
    </div>
  );
}

function AgreementCard({ ag }: { ag: Agreement }) {
  const days = Math.ceil((new Date(ag.expiry_date).getTime() - Date.now()) / 86400000);
  const tone = days < 0 ? "text-destructive" : days <= 30 ? "text-amber-600" : "text-emerald-600";
  return (
    <div className="space-y-2 text-sm">
      <div>
        <div className="text-xs text-muted-foreground">Landlord</div>
        <div className="font-medium">{ag.landlord.name}</div>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <div>
          <div className="text-xs text-muted-foreground">Start</div>
          <div className="font-mono text-xs">{ag.start_date}</div>
        </div>
        <div>
          <div className="text-xs text-muted-foreground">Expiry</div>
          <div className={"font-mono text-xs " + tone}>{ag.expiry_date}</div>
        </div>
      </div>
      <div className={"text-xs flex items-center gap-1 " + tone}>
        {days < 0 ? <><AlertTriangle className="h-3 w-3" /> Expired {Math.abs(days)}d ago</> :
          days <= 30 ? <><AlertTriangle className="h-3 w-3" /> Expires in {days}d</> :
          <><Calendar className="h-3 w-3" /> {days}d remaining</>}
      </div>
      {ag.monthly_rent != null && (
        <div className="text-xs text-muted-foreground">Rent: <span className="text-foreground font-medium">{ag.monthly_rent.toLocaleString()}</span></div>
      )}
    </div>
  );
}

function AgreementTab({ property, onUpdated }: { property: Property; onUpdated: () => void }) {
  const [rows, setRows] = useState<Agreement[]>([]);
  const [landlords, setLandlords] = useState<Landlord[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [amending, setAmending] = useState<Agreement | null>(null);
  const active = rows.find((a) => a.is_active) ?? null;

  const load = async () => {
    setLoading(true);
    try {
      const [a, l] = await Promise.all([
        api.get(`/properties/${property.id}/agreements`),
        api.get("/landlords"),
      ]);
      setRows(a.data.data);
      setLandlords(l.data.data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [property.id]);  // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="text-sm text-muted-foreground">Agreements history — newest active first, then renewed.</div>
        <Can perm="property.edit">
          <div className="flex items-center gap-2">
            {active && (
              <button onClick={() => setAmending(active)} className="inline-flex h-9 items-center gap-2 rounded-md border border-border bg-card/60 px-3 text-sm hover:bg-accent">
                <Pencil className="h-4 w-4" /> Amend agreement
              </button>
            )}
            <button onClick={() => setShowForm(true)} className="inline-flex h-9 items-center gap-2 rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground hover:bg-primary/90">
              <Plus className="h-4 w-4" /> New / renew
            </button>
          </div>
        </Can>
      </div>

      <div className="glass rounded-xl overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-left text-xs text-muted-foreground border-b border-border">
            <tr>
              <th className="py-2 px-3">#</th>
              <th className="py-2 px-3">Landlord</th>
              <th className="py-2 px-3">Start</th>
              <th className="py-2 px-3">Expiry</th>
              <th className="py-2 px-3">Rent</th>
              <th className="py-2 px-3">Status</th>
              <th className="py-2 px-3">Renewal</th>
            </tr>
          </thead>
          <tbody>
            {loading ? <tr><td colSpan={7} className="py-10 text-center text-muted-foreground">Loading…</td></tr>
            : rows.length === 0 ? <tr><td colSpan={7} className="py-10 text-center text-muted-foreground">No agreements yet</td></tr>
            : rows.map((a) => (
              <tr key={a.id} className="border-b border-border/60">
                <td className="py-2 px-3 font-mono text-xs">{a.agreement_number ?? `AG-${a.id}`}</td>
                <td className="py-2 px-3">{a.landlord.name}</td>
                <td className="py-2 px-3 font-mono text-xs">{a.start_date}</td>
                <td className="py-2 px-3 font-mono text-xs">{a.expiry_date}</td>
                <td className="py-2 px-3">{a.monthly_rent?.toLocaleString() ?? "—"}</td>
                <td className="py-2 px-3">
                  <span className={"rounded-full px-2 py-0.5 text-xs " + (a.is_active ? "bg-emerald-500/10 text-emerald-600" : "bg-muted text-muted-foreground")}>
                    {a.is_active ? "Active" : "Archived"}
                  </span>
                </td>
                <td className="py-2 px-3 capitalize">{a.renewal_status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <AgreementDialog
        open={showForm}
        propertyId={property.id}
        landlords={landlords}
        onClose={() => setShowForm(false)}
        onSaved={async () => { setShowForm(false); await load(); onUpdated(); }}
      />

      <AgreementDialog
        open={Boolean(amending)}
        propertyId={property.id}
        landlords={landlords}
        prefillFrom={amending}
        onClose={() => setAmending(null)}
        onSaved={async () => { setAmending(null); await load(); onUpdated(); }}
      />
    </div>
  );
}

function AgreementDialog({ open, propertyId, landlords, prefillFrom, onClose, onSaved }: {
  open: boolean; propertyId: number; landlords: Landlord[]; prefillFrom?: Agreement | null;
  onClose: () => void; onSaved: () => void;
}) {
  const [form, setForm] = useState<Record<string, unknown>>({ reminder_days_before_expiry: 90 });
  const [busy, setBusy] = useState(false);
  const isAmend = Boolean(prefillFrom);

  useEffect(() => {
    if (!open) return;
    if (prefillFrom) {
      setForm({
        landlord_id: prefillFrom.landlord.id,
        agreement_number: prefillFrom.agreement_number ?? "",
        reminder_days_before_expiry: prefillFrom.reminder_days_before_expiry ?? 90,
        start_date: prefillFrom.start_date,
        expiry_date: prefillFrom.expiry_date,
        monthly_rent: prefillFrom.monthly_rent,
        security_deposit: prefillFrom.security_deposit,
        payment_terms: prefillFrom.payment_terms ?? "",
        notice_period: prefillFrom.notice_period ?? "",
        remarks: prefillFrom.remarks ?? "",
      });
    } else {
      setForm({ reminder_days_before_expiry: 90 });
    }
  }, [open, prefillFrom]);

  const set = (k: string, v: unknown) => setForm((f) => ({ ...f, [k]: v }));

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api.post(`/properties/${propertyId}/agreements`, form);
      toast.success(isAmend ? "Agreement amended" : "Agreement saved");
      onSaved();
    } catch (err: unknown) {
      toast.error("Save failed", errorMessage(err));
    } finally { setBusy(false); }
  };

  return (
    <Modal open={open} onClose={onClose} title={isAmend ? "Amend agreement" : "New / renew agreement"} size="lg">
      <form onSubmit={save} className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <Field label="Landlord" span={2}>
            <select required className={selectClass} value={String(form.landlord_id ?? "")} onChange={(e) => set("landlord_id", e.target.value ? Number(e.target.value) : undefined)}>
              <option value="">Select…</option>
              {landlords.map((l) => <option key={l.id} value={l.id}>{l.name} ({l.code})</option>)}
            </select>
          </Field>
          <Field label="Agreement number">
            <input className={inputClass} value={String(form.agreement_number ?? "")} onChange={(e) => set("agreement_number", e.target.value)} />
          </Field>
          <Field label="Reminder days">
            <input type="number" className={inputClass} value={Number(form.reminder_days_before_expiry ?? 90)} onChange={(e) => set("reminder_days_before_expiry", Number(e.target.value))} />
          </Field>
          <Field label="Start date">
            <input required type="date" className={inputClass} value={String(form.start_date ?? "")} onChange={(e) => set("start_date", e.target.value)} />
          </Field>
          <Field label="Expiry date">
            <input required type="date" className={inputClass} value={String(form.expiry_date ?? "")} onChange={(e) => set("expiry_date", e.target.value)} />
          </Field>
          <Field label="Monthly rent">
            <input type="number" step="0.01" className={inputClass} value={form.monthly_rent == null ? "" : Number(form.monthly_rent)} onChange={(e) => set("monthly_rent", e.target.value ? Number(e.target.value) : null)} />
          </Field>
          <Field label="Security deposit">
            <input type="number" step="0.01" className={inputClass} value={form.security_deposit == null ? "" : Number(form.security_deposit)} onChange={(e) => set("security_deposit", e.target.value ? Number(e.target.value) : null)} />
          </Field>
          <Field label="Payment terms">
            <input className={inputClass} value={String(form.payment_terms ?? "")} onChange={(e) => set("payment_terms", e.target.value)} />
          </Field>
          <Field label="Notice period">
            <input className={inputClass} value={String(form.notice_period ?? "")} onChange={(e) => set("notice_period", e.target.value)} />
          </Field>
          <Field label="Kahramaa account"><input className={inputClass} onChange={(e) => set("kahramaa_account", e.target.value)} /></Field>
          <Field label="Municipality ref"><input className={inputClass} onChange={(e) => set("municipality_ref", e.target.value)} /></Field>
        </div>
        <Field label="Remarks">
          <textarea className={textareaClass} value={String(form.remarks ?? "")} onChange={(e) => set("remarks", e.target.value)} />
        </Field>
        <div className="text-xs text-muted-foreground">
          {isAmend
            ? "This keeps the current agreement's details as a starting point — change what's different (e.g. the rent or expiry) and post. The current agreement is archived, not overwritten, so its old terms stay on record."
            : "Posting this will archive any existing active agreement on this property."}
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={onClose} className="h-9 rounded-md border border-border bg-card/60 px-3 text-sm">Cancel</button>
          <button type="submit" disabled={busy} className="h-9 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-60">
            {busy ? "Saving…" : isAmend ? "Post amendment" : "Post"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

type Floor = {
  id: number;
  property_id: number;
  floor_number: string;
  floor_name: string | null;
  floor_type: string | null;
  status: string;
  unit_count: number;
  remarks: string | null;
};

type Unit = {
  id: number;
  property_id: number;
  floor_id: number;
  unit_number: string;
  unit_name: string | null;
  unit_type: string;
  size: string | null;
  is_shared_facility: boolean;
  has_bathroom: boolean;
  has_ac: boolean;
  occupancy_status: string;
  monthly_rent: number | null;
  remarks: string | null;
};

const UNIT_STATUS_TONE: Record<string, string> = {
  empty: "bg-muted text-muted-foreground",
  occupied: "bg-emerald-500/10 text-emerald-600",
  maintenance: "bg-amber-500/10 text-amber-600",
  blocked: "bg-rose-500/10 text-rose-600",
};

function FloorsTab({ propertyId }: { propertyId: number }) {
  const [rows, setRows] = useState<Floor[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<Floor | null>(null);
  const [renumber, setRenumber] = useState<Floor | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      const resp = await api.get(`/properties/${propertyId}/floors`);
      setRows(resp.data.data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [propertyId]);  // eslint-disable-line react-hooks/exhaustive-deps

  const remove = async (f: Floor) => {
    if (!confirm(`Delete floor ${f.floor_number}?`)) return;
    try {
      await api.delete(`/floors/${f.id}`);
      toast.success(`Floor ${f.floor_number} deleted`);
      await load();
    } catch (err: unknown) {
      toast.error("Delete failed", errorMessage(err));
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="text-sm text-muted-foreground">Floors registered under this property.</div>
        <Can perm="floor.manage">
          <button onClick={() => { setEditing(null); setShowForm(true); }}
            className="inline-flex h-9 items-center gap-2 rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground hover:bg-primary/90">
            <Plus className="h-4 w-4" /> New floor
          </button>
        </Can>
      </div>

      <div className="glass rounded-xl overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-left text-xs text-muted-foreground border-b border-border">
            <tr>
              <th className="py-2 px-3">Number</th>
              <th className="py-2 px-3">Name</th>
              <th className="py-2 px-3">Type</th>
              <th className="py-2 px-3">Units</th>
              <th className="py-2 px-3">Status</th>
              <th className="py-2 px-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading ? <tr><td colSpan={6} className="py-10 text-center text-muted-foreground">Loading…</td></tr>
            : rows.length === 0 ? <tr><td colSpan={6} className="py-10 text-center text-muted-foreground">No floors yet</td></tr>
            : rows.map((f) => (
              <tr key={f.id} className="border-b border-border/60 hover:bg-accent/30">
                <td className="py-2 px-3 font-mono">{f.floor_number}</td>
                <td className="py-2 px-3">{f.floor_name ?? "—"}</td>
                <td className="py-2 px-3 capitalize">{f.floor_type ?? "—"}</td>
                <td className="py-2 px-3">{f.unit_count}</td>
                <td className="py-2 px-3">
                  <span className={"rounded-full px-2 py-0.5 text-xs " + (f.status === "active" ? "bg-emerald-500/10 text-emerald-600" : "bg-muted text-muted-foreground")}>
                    {f.status}
                  </span>
                </td>
                <td className="py-2 px-3 text-right">
                  <Can perm="unit.manage">
                    <button onClick={() => setRenumber(f)}
                      disabled={f.unit_count === 0}
                      title={f.unit_count === 0 ? "No units to renumber" : "Renumber all units on this floor"}
                      aria-label={`Renumber units on floor ${f.floor_number}`}
                      className="h-8 w-8 grid place-items-center rounded-md hover:bg-accent inline-block disabled:opacity-40 disabled:cursor-not-allowed">
                      <Hash className="h-3.5 w-3.5" />
                    </button>
                  </Can>
                  <Can perm="floor.manage">
                    <button onClick={() => { setEditing(f); setShowForm(true); }}
                      aria-label={`Edit floor ${f.floor_number}`}
                      className="h-8 w-8 grid place-items-center rounded-md hover:bg-accent inline-block">
                      <Pencil className="h-3.5 w-3.5" />
                    </button>
                    <button onClick={() => remove(f)}
                      aria-label={`Delete floor ${f.floor_number}`}
                      className="h-8 w-8 grid place-items-center rounded-md hover:bg-destructive/10 text-destructive inline-block">
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </Can>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <FloorDialog open={showForm} propertyId={propertyId} editing={editing}
        onClose={() => setShowForm(false)}
        onSaved={async () => { setShowForm(false); await load(); }}
      />
      <RenumberUnitsDialog
        propertyId={propertyId}
        floor={renumber}
        onClose={() => setRenumber(null)}
        onDone={async () => { setRenumber(null); await load(); }}
      />
    </div>
  );
}

type RenumberDiff = { unit_id: number; old_unit_number: string; new_unit_number: string };

function RenumberUnitsDialog({ propertyId, floor, onClose, onDone }: {
  propertyId: number;
  floor: Floor | null;
  onClose: () => void;
  onDone: () => void;
}) {
  const [prefix, setPrefix] = useState("");
  const [busy, setBusy] = useState(false);
  const [forceRequired, setForceRequired] = useState<{ occupied: number } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (floor) { setPrefix(""); setBusy(false); setForceRequired(null); setError(null); }
  }, [floor]);

  if (!floor) return <Modal open={false} onClose={onClose} title="">{null}</Modal>;

  // Mirror the backend numbering algorithm so the preview matches.
  const raw = floor.floor_number;
  let floorSeq: string;
  if (raw === "G" || (raw.startsWith("G") && raw.length > 1 && raw.slice(1).split("").every((c) => /[A-Za-z]/.test(c)))) {
    floorSeq = "G";
  } else {
    const digits = raw.replace(/[^0-9]/g, "");
    floorSeq = digits || raw;
  }
  const n = Math.max(0, floor.unit_count);
  const pad = Math.max(2, String(n).length);
  const sample = Array.from({ length: Math.min(n, 4) }, (_, i) =>
    `${prefix}${floorSeq}${String(i + 1).padStart(pad, "0")}`,
  );

  const submit = async (force: boolean) => {
    setBusy(true);
    setError(null);
    try {
      const resp = await api.post(
        `/properties/${propertyId}/floors/${floor.id}/renumber-units`,
        { unit_prefix: prefix, force },
      );
      const data = resp.data?.data as { renamed: number; diff?: RenumberDiff[] };
      toast.success(
        `${data.renamed} unit${data.renamed === 1 ? "" : "s"} renumbered`,
        data.diff && data.diff.length
          ? `${data.diff[0].old_unit_number} → ${data.diff[0].new_unit_number}${data.diff.length > 1 ? `, +${data.diff.length - 1} more` : ""}`
          : undefined,
      );
      onDone();
    } catch (err: unknown) {
      const e = err as { response?: { status?: number; data?: { details?: { force_required?: boolean; occupied?: number }; message?: string } } };
      if (e.response?.status === 409 && e.response.data?.details?.force_required) {
        setForceRequired({ occupied: e.response.data.details.occupied ?? 0 });
      } else {
        setError(errorMessage(err));
        toast.error("Renumber failed", errorMessage(err));
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal open={Boolean(floor)} onClose={onClose} title={`Renumber units — Floor ${floor.floor_number}`}>
      <div className="space-y-4">
        <div className="text-sm text-muted-foreground">
          Rewrites every unit number on this floor using
          {" "}<span className="font-mono">{`{prefix}${floorSeq}{nn}`}</span>.
        </div>
        <Field label="New unit prefix">
          <input
            autoFocus
            className={inputClass}
            value={prefix}
            onChange={(e) => { setPrefix(e.target.value); setForceRequired(null); }}
            placeholder='e.g. "R" or leave empty'
          />
        </Field>
        {n > 0 && (
          <div className="text-xs rounded-md bg-background/40 border border-border px-3 py-2 font-mono">
            Preview: {sample.join(", ")}{n > 4 ? `, …${prefix}${floorSeq}${String(n).padStart(pad, "0")}` : ""}
          </div>
        )}
        {forceRequired && (
          <div className="rounded-lg border-2 border-amber-500/60 bg-amber-500/5 p-3 space-y-2 text-sm">
            <div className="flex items-center gap-2 font-medium text-amber-700 dark:text-amber-400">
              <AlertTriangle className="h-4 w-4" />
              {forceRequired.occupied} unit{forceRequired.occupied === 1 ? "" : "s"} occupied on this floor
            </div>
            <div className="text-xs text-muted-foreground">
              Occupied units keep their contracts — only the numbers change. The audit log records the force flag.
            </div>
          </div>
        )}
        {error && <div className="text-xs text-destructive">{error}</div>}
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={onClose}
            className="h-9 rounded-md border border-border bg-card/60 px-3 text-sm">
            Cancel
          </button>
          {forceRequired ? (
            <button type="button" disabled={busy} onClick={() => submit(true)}
              className="h-9 rounded-md bg-amber-600 px-4 text-sm font-medium text-white hover:bg-amber-700 disabled:opacity-60">
              {busy ? "Forcing…" : "Force renumber"}
            </button>
          ) : (
            <button type="button" disabled={busy} onClick={() => submit(false)}
              className="h-9 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-60">
              {busy ? "Renumbering…" : `Renumber ${n} unit${n === 1 ? "" : "s"}`}
            </button>
          )}
        </div>
      </div>
    </Modal>
  );
}

function FloorDialog({ open, propertyId, editing, onClose, onSaved }: {
  open: boolean; propertyId: number; editing: Floor | null; onClose: () => void; onSaved: () => void;
}) {
  const [form, setForm] = useState<Partial<Floor>>({});
  const [busy, setBusy] = useState(false);
  useEffect(() => { setForm(editing ?? { status: "active" }); }, [editing, open]);

  const set = <K extends keyof Floor>(k: K, v: Floor[K] | null | undefined) => setForm((f) => ({ ...f, [k]: v }));

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      if (editing) {
        await api.put(`/floors/${editing.id}`, form);
        toast.success(`Floor ${editing.floor_number} updated`);
      } else {
        const resp = await api.post(`/properties/${propertyId}/floors`, form);
        toast.success(`Floor ${resp.data?.data?.floor_number ?? ""} created`);
      }
      onSaved();
    } catch (err: unknown) {
      toast.error("Save failed", errorMessage(err));
    } finally { setBusy(false); }
  };

  return (
    <Modal open={open} onClose={onClose} title={editing ? "Edit floor" : "New floor"}>
      <form onSubmit={save} className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <Field label="Number"><input required className={inputClass} value={form.floor_number ?? ""} onChange={(e) => set("floor_number", e.target.value)} /></Field>
          <Field label="Name"><input className={inputClass} value={form.floor_name ?? ""} onChange={(e) => set("floor_name", e.target.value)} /></Field>
          <Field label="Type"><input className={inputClass} value={form.floor_type ?? ""} onChange={(e) => set("floor_type", e.target.value)} placeholder="residential, mezzanine…" /></Field>
          <Field label="Status">
            <select className={selectClass} value={form.status ?? "active"} onChange={(e) => set("status", e.target.value)}>
              <option value="active">Active</option>
              <option value="inactive">Inactive</option>
            </select>
          </Field>
        </div>
        <Field label="Remarks"><textarea className={textareaClass} value={form.remarks ?? ""} onChange={(e) => set("remarks", e.target.value)} /></Field>
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={onClose} className="h-9 rounded-md border border-border bg-card/60 px-3 text-sm">Cancel</button>
          <button type="submit" disabled={busy} className="h-9 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-60">
            {busy ? "Saving…" : "Save"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function UnitsTab({ propertyId }: { propertyId: number }) {
  const [floors, setFloors] = useState<Floor[]>([]);
  const [units, setUnits] = useState<Unit[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeFloor, setActiveFloor] = useState<number | "all">("all");
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<Unit | null>(null);
  const [createInFloorId, setCreateInFloorId] = useState<number | null>(null);
  const { types: unitTypes } = useUnitTypes();
  const facilityCodes = useMemo(
    () => new Set(unitTypes.filter((t) => t.is_facility).map((t) => t.code)), [unitTypes]);

  const load = async () => {
    setLoading(true);
    try {
      const [f, r] = await Promise.all([
        api.get(`/properties/${propertyId}/floors`),
        api.get(`/properties/${propertyId}/units`),
      ]);
      setFloors(f.data.data);
      setUnits(r.data.data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [propertyId]);  // eslint-disable-line react-hooks/exhaustive-deps

  const filtered = activeFloor === "all" ? units : units.filter((r) => r.floor_id === activeFloor);
  const byFloor = (id: number) => floors.find((f) => f.id === id);

  const remove = async (r: Unit) => {
    if (!confirm(`Delete unit ${r.unit_number}?`)) return;
    try {
      await api.delete(`/units/${r.id}`);
      toast.success(`Unit ${r.unit_number} deleted`);
      await load();
    } catch (err: unknown) {
      toast.error("Delete failed", errorMessage(err));
    }
  };

  if (loading) return <div className="glass rounded-xl p-10 text-center text-muted-foreground">Loading…</div>;
  if (floors.length === 0) {
    return (
      <div className="glass rounded-xl p-10 text-center text-sm text-muted-foreground">
        Add floors first, then create units under each floor.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 flex-wrap">
        <button onClick={() => setActiveFloor("all")}
          className={"h-8 px-3 rounded-md border text-sm " + (activeFloor === "all" ? "bg-primary text-primary-foreground border-primary" : "border-border bg-card/60 hover:bg-accent")}>
          All floors
        </button>
        {floors.map((f) => (
          <button key={f.id} onClick={() => setActiveFloor(f.id)}
            className={"h-8 px-3 rounded-md border text-sm " + (activeFloor === f.id ? "bg-primary text-primary-foreground border-primary" : "border-border bg-card/60 hover:bg-accent")}>
            Floor {f.floor_number}{f.floor_name ? ` · ${f.floor_name}` : ""} <span className="text-xs opacity-70">({f.unit_count})</span>
          </button>
        ))}
        <div className="ml-auto" />
        <Can perm="unit.manage">
          <button onClick={() => {
              setEditing(null);
              setCreateInFloorId(activeFloor === "all" ? floors[0].id : activeFloor);
              setShowForm(true);
            }}
            className="inline-flex h-9 items-center gap-2 rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground hover:bg-primary/90">
            <Plus className="h-4 w-4" /> New unit
          </button>
        </Can>
      </div>

      {filtered.length === 0 ? (
        <div className="glass rounded-xl p-10 text-center text-sm text-muted-foreground">No units on this floor yet.</div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
          {filtered.map((r) => {
            const f = byFloor(r.floor_id);
            return (
              <div key={r.id} className="glass rounded-xl p-4">
                <div className="flex items-center justify-between gap-2">
                  <div>
                    <div className="text-sm font-semibold">
                      {facilityCodes.has(r.unit_type) ? "" : "Unit "}{r.unit_number}{r.unit_name ? ` · ${r.unit_name}` : ""}
                    </div>
                    <div className="text-xs text-muted-foreground capitalize">
                      Floor {f?.floor_number} · {r.unit_type.replaceAll("_", " ")}
                      {facilityCodes.has(r.unit_type) && (r.is_shared_facility ? " · shared" : " · dedicated")}
                    </div>
                  </div>
                  <span className={"rounded-full px-2 py-0.5 text-xs " + (UNIT_STATUS_TONE[r.occupancy_status] ?? "bg-muted text-muted-foreground")}>
                    {r.occupancy_status.replace("_", " ")}
                  </span>
                </div>
                <div className="mt-2 text-xs text-muted-foreground">
                  {[
                    r.size,
                    r.monthly_rent != null ? `Rent ${r.monthly_rent.toLocaleString()}` : null,
                    r.has_bathroom ? "Bathroom" : null,
                    r.has_ac ? "AC" : null,
                  ].filter(Boolean).join(" · ")}
                </div>
                <Can perm="unit.manage">
                  <div className="mt-3 flex justify-end gap-1">
                    <button onClick={() => { setEditing(r); setCreateInFloorId(r.floor_id); setShowForm(true); }}
                      aria-label={`Edit unit ${r.unit_number}`}
                      className="h-8 w-8 grid place-items-center rounded-md hover:bg-accent">
                      <Pencil className="h-3.5 w-3.5" />
                    </button>
                    <button onClick={() => remove(r)}
                      aria-label={`Delete unit ${r.unit_number}`}
                      className="h-8 w-8 grid place-items-center rounded-md hover:bg-destructive/10 text-destructive">
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </Can>
              </div>
            );
          })}
        </div>
      )}

      <UnitDialog
        open={showForm}
        floorId={createInFloorId}
        floors={floors}
        editing={editing}
        unitTypes={unitTypes}
        onClose={() => setShowForm(false)}
        onSaved={async () => { setShowForm(false); await load(); }}
      />
    </div>
  );
}

function UnitDialog({ open, floorId, floors, editing, unitTypes, onClose, onSaved }: {
  open: boolean; floorId: number | null; floors: Floor[]; editing: Unit | null;
  unitTypes: { code: string; name: string; is_facility: boolean }[];
  onClose: () => void; onSaved: () => void;
}) {
  const [form, setForm] = useState<Record<string, unknown>>({});
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (editing) {
      setForm(editing as unknown as Record<string, unknown>);
    } else {
      setForm({ unit_type: "room", size: "", is_shared_facility: false, has_bathroom: false, has_ac: true });
    }
  }, [editing, open]);

  const set = (k: string, v: unknown) => setForm((f) => ({ ...f, [k]: v }));
  const isFacility = unitTypes.find((t) => t.code === String(form.unit_type ?? ""))?.is_facility ?? false;

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      if (editing) {
        await api.put(`/units/${editing.id}`, form);
        toast.success(`Unit ${editing.unit_number} updated`);
      } else {
        if (!floorId) throw new Error("No floor selected");
        const resp = await api.post(`/floors/${floorId}/units`, form);
        toast.success(`Unit ${resp.data?.data?.unit_number ?? ""} created`);
      }
      onSaved();
    } catch (err: unknown) {
      toast.error("Save failed", errorMessage(err));
    } finally { setBusy(false); }
  };

  return (
    <Modal open={open} onClose={onClose} title={editing ? `Edit unit ${editing.unit_number}` : "New unit"}>
      <form onSubmit={save} className="space-y-4">
        <div className="grid grid-cols-2 gap-3">
          {!editing && (
            <Field label="Floor" span={2}>
              <select className={selectClass} value={floorId ?? ""} disabled>
                {floors.map((f) => <option key={f.id} value={f.id}>Floor {f.floor_number}</option>)}
              </select>
            </Field>
          )}
          <Field label="Unit number"><input required className={inputClass} value={String(form.unit_number ?? "")} onChange={(e) => set("unit_number", e.target.value)} /></Field>
          <Field label="Name"><input className={inputClass} value={String(form.unit_name ?? "")} onChange={(e) => set("unit_name", e.target.value)} placeholder="Optional" /></Field>
          <Field label="Type">
            <select className={selectClass} value={String(form.unit_type ?? "room")} onChange={(e) => set("unit_type", e.target.value)}>
              {unitTypes.map((t) => <option key={t.code} value={t.code}>{t.name}</option>)}
            </select>
          </Field>
          <Field label="Size">
            <input className={inputClass} value={String(form.size ?? "")} onChange={(e) => set("size", e.target.value)}
              placeholder={["store", "shop", "supermarket", "cafeteria"].includes(String(form.unit_type)) ? "e.g. 450 Sqm" : "e.g. 4/4"} />
          </Field>
          <Field label="Monthly rent"><input type="number" step="0.01" className={inputClass} value={form.monthly_rent != null ? String(form.monthly_rent) : ""} onChange={(e) => set("monthly_rent", e.target.value ? Number(e.target.value) : null)} placeholder="Optional" /></Field>
          <Field label="Amenities" span={2}>
            <div className="flex items-center gap-4 h-9 flex-wrap">
              {isFacility && (
                <label className="inline-flex items-center gap-1.5 text-sm">
                  <input type="checkbox" checked={Boolean(form.is_shared_facility)} onChange={(e) => set("is_shared_facility", e.target.checked)} />
                  Shared facility (common to the property)
                </label>
              )}
              <label className="inline-flex items-center gap-1.5 text-sm">
                <input type="checkbox" checked={Boolean(form.has_bathroom)} onChange={(e) => set("has_bathroom", e.target.checked)} />
                Attached bathroom
              </label>
              <label className="inline-flex items-center gap-1.5 text-sm">
                <input type="checkbox" checked={Boolean(form.has_ac)} onChange={(e) => set("has_ac", e.target.checked)} />
                AC
              </label>
            </div>
          </Field>
        </div>

        <Field label="Remarks">
          <textarea className={textareaClass} value={String(form.remarks ?? "")} onChange={(e) => set("remarks", e.target.value)} />
        </Field>
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={onClose} className="h-9 rounded-md border border-border bg-card/60 px-3 text-sm">Cancel</button>
          <button
            type="submit"
            disabled={busy}
            className="h-9 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-60"
          >
            {busy ? "Saving…" : editing ? "Save changes" : "Create unit"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

const STATUS_OPTIONS: { value: string; label: string; tone: string; help: string }[] = [
  { value: "active",      label: "Active",       tone: "border-emerald-500 bg-emerald-500/5 text-emerald-700 dark:text-emerald-400", help: "Property is operational. New contracts are allowed." },
  { value: "on_hold",     label: "On hold",      tone: "border-amber-500 bg-amber-500/5 text-amber-700 dark:text-amber-400",          help: "Temporarily paused. New contracts blocked. Existing occupants stay until released." },
  { value: "maintenance", label: "Maintenance",  tone: "border-sky-500 bg-sky-500/5 text-sky-700 dark:text-sky-400",                  help: "Property is under repair. New contracts blocked." },
  { value: "inactive",    label: "Inactive",     tone: "border-rose-500 bg-rose-500/5 text-rose-700 dark:text-rose-400",              help: "Permanently retired (lease ended, handed back, demolished). New contracts blocked." },
];

const REASON_OPTIONS = [
  { value: "agreement_expired",  label: "Agreement expired / not renewed" },
  { value: "renovation",         label: "Renovation / major repair" },
  { value: "ownership_dispute",  label: "Ownership dispute" },
  { value: "end_of_lease",       label: "End of lease — handed back to landlord" },
  { value: "regulatory_hold",    label: "Regulatory / municipality hold" },
  { value: "other",              label: "Other (explain in remarks)" },
];

type BlockedDetails = {
  blocked: true;
  occupied: number;
  sample_units: { unit_id: number; unit_number: string; unit_type: string }[];
};

function PropertyStatusModal({ open, property, onClose, onChanged }: {
  open: boolean; property: Property; onClose: () => void; onChanged: () => void;
}) {
  const [target, setTarget] = useState<string>(property.status);
  const [reason, setReason] = useState<string>("agreement_expired");
  const [remarks, setRemarks] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const [snapshot, setSnapshot] = useState<{ occupied: number } | null>(null);
  const [blocked, setBlocked] = useState<BlockedDetails | null>(null);

  useEffect(() => {
    if (!open) return;
    setTarget(property.status);
    setReason("agreement_expired");
    setRemarks("");
    setBlocked(null);
    api.get(`/properties/${property.id}/occupancy-snapshot`)
      .then((r) => setSnapshot(r.data.data))
      .catch(() => setSnapshot(null));
  }, [open, property.id, property.status]);

  const movingAway = target !== "active" && target !== property.status;
  const needsReason = movingAway;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (target === property.status) return;
    setBusy(true);
    setBlocked(null);
    try {
      const resp = await api.post(`/properties/${property.id}/status`, {
        status: target,
        reason: needsReason ? reason : "",
        remarks: remarks || null,
      });
      toast.success(resp.data?.message ?? `Property set to ${target}`);
      onChanged();
    } catch (err: unknown) {
      const e = err as { response?: { status?: number; data?: { message?: string; details?: BlockedDetails } } };
      if (e.response?.status === 409 && e.response.data?.details?.blocked) {
        setBlocked(e.response.data.details);
      } else {
        toast.error("Status change failed", errorMessage(err));
      }
    } finally { setBusy(false); }
  };

  return (
    <Modal open={open} onClose={onClose} title={`Change status — ${property.name}`} size="lg">
      <form onSubmit={submit} className="space-y-4">
        <div className="rounded-lg border border-border bg-card/40 p-3 text-xs text-muted-foreground">
          Currently <span className="font-medium capitalize text-foreground">{property.status.replace("_", " ")}</span>
          {snapshot && (
            <>
              {" · "}
              <span className="font-medium text-foreground">{snapshot.occupied}</span> occupied unit{snapshot.occupied === 1 ? "" : "s"}
            </>
          )}
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          {STATUS_OPTIONS.map((s) => {
            const selected = target === s.value;
            const isCurrent = s.value === property.status;
            return (
              <button
                key={s.value}
                type="button"
                disabled={isCurrent}
                onClick={() => setTarget(s.value)}
                className={
                  "text-left rounded-lg border-2 px-3 py-2 transition-colors " +
                  (selected ? s.tone : "border-border bg-card/30 hover:bg-accent/30") +
                  (isCurrent ? " opacity-50 cursor-not-allowed" : "")
                }
              >
                <div className="text-sm font-medium flex items-center gap-2">
                  {s.label}
                  {isCurrent && <span className="text-[10px] uppercase tracking-wide opacity-70">(current)</span>}
                </div>
                <div className="text-xs text-muted-foreground mt-0.5">{s.help}</div>
              </button>
            );
          })}
        </div>

        {needsReason && (
          <>
            <Field label="Reason">
              <select className={selectClass} value={reason} onChange={(e) => setReason(e.target.value)}>
                {REASON_OPTIONS.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
              </select>
            </Field>
            <Field label="Remarks (optional)">
              <textarea className={textareaClass} rows={2} value={remarks} onChange={(e) => setRemarks(e.target.value)} />
            </Field>
          </>
        )}

        {blocked && (
          <div className="rounded-lg border-2 border-rose-500/60 bg-rose-500/5 p-3 space-y-2">
            <div className="flex items-center gap-2 text-rose-600 text-sm font-medium">
              <AlertTriangle className="h-4 w-4" />
              Cannot change status — {blocked.occupied} unit{blocked.occupied === 1 ? "" : "s"} occupied
            </div>
            <div className="text-xs text-muted-foreground">
              Release or cancel the contracts on these units first, then try again.
            </div>
            {blocked.sample_units.length > 0 && (
              <ul className="text-xs space-y-1">
                {blocked.sample_units.map((s) => (
                  <li key={s.unit_id} className="rounded-md bg-card/60 px-2 py-1">
                    Unit <span className="font-mono">{s.unit_number}</span>
                    {" "}<span className="text-muted-foreground capitalize">({s.unit_type.replaceAll("_", " ")})</span>
                  </li>
                ))}
                {blocked.occupied > blocked.sample_units.length && (
                  <li className="text-muted-foreground">…and {blocked.occupied - blocked.sample_units.length} more.</li>
                )}
              </ul>
            )}
          </div>
        )}

        <div className="flex justify-end gap-2 pt-1">
          <button type="button" onClick={onClose} className="h-9 rounded-md border border-border bg-card/60 px-3 text-sm">Close</button>
          <button
            type="submit"
            disabled={busy || target === property.status || (needsReason && !reason)}
            className="h-9 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-60"
          >
            {busy ? "Saving…" : "Apply status"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

const EDIT_OWNERSHIP = ["rented", "company_owned", "temporary"];

function EditPropertyDialog({ open, property, onClose, onSaved }: {
  open: boolean; property: Property; onClose: () => void; onSaved: () => void;
}) {
  const { types: propertyTypes } = usePropertyTypes();
  const [form, setForm] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  // The property's current type may since have been deactivated — keep it
  // selectable (and visibly correct) on its own edit form even though it
  // no longer appears for new properties.
  const typeOptions = propertyTypes.some((t) => t.code === property.property_type)
    ? propertyTypes
    : [...propertyTypes, { id: -1, code: property.property_type, name: `${property.property_type.replaceAll("_", " ")} (inactive)`, is_active: false }];

  useEffect(() => {
    if (!open) return;
    setForm({
      name: property.name,
      property_type: property.property_type,
      building_number: property.building_number ?? "",
      zone: property.zone ?? "",
      street: property.street ?? "",
      area: property.area ?? "",
      city: property.city ?? "",
      map_link: property.map_link ?? "",
      ownership_type: property.ownership_type,
      managed_by: property.managed_by ?? "",
      remarks: property.remarks ?? "",
    });
  }, [open, property]);

  const set = (k: string, v: string) => setForm((f) => ({ ...f, [k]: v }));

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      const payload: Record<string, string | null> = {};
      for (const [k, v] of Object.entries(form)) payload[k] = v === "" ? null : v;
      await api.put(`/properties/${property.id}`, payload);
      toast.success("Property updated");
      onSaved();
    } catch (err: unknown) {
      toast.error("Save failed", errorMessage(err));
    } finally { setBusy(false); }
  };

  return (
    <Modal open={open} onClose={onClose} title={`Edit — ${property.name}`} size="lg">
      <form onSubmit={submit} className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <Field label="Name" span={2}>
            <input required className={inputClass} value={form.name ?? ""}
              onChange={(e) => set("name", e.target.value)} />
          </Field>
          <Field label="Type">
            <select className={selectClass} value={form.property_type ?? ""} onChange={(e) => set("property_type", e.target.value)}>
              {typeOptions.map((t) => <option key={t.code} value={t.code}>{t.name}</option>)}
            </select>
          </Field>
          <Field label="Ownership">
            <select className={selectClass} value={form.ownership_type ?? "rented"} onChange={(e) => set("ownership_type", e.target.value)}>
              {EDIT_OWNERSHIP.map((o) => <option key={o} value={o}>{o.replaceAll("_", " ")}</option>)}
            </select>
          </Field>
          <Field label="Building number">
            <input className={inputClass} value={form.building_number ?? ""} onChange={(e) => set("building_number", e.target.value)} />
          </Field>
          <Field label="Zone">
            <input className={inputClass} value={form.zone ?? ""} onChange={(e) => set("zone", e.target.value)} />
          </Field>
          <Field label="Street">
            <input className={inputClass} value={form.street ?? ""} onChange={(e) => set("street", e.target.value)} />
          </Field>
          <Field label="Area">
            <input className={inputClass} value={form.area ?? ""} onChange={(e) => set("area", e.target.value)} />
          </Field>
          <Field label="City">
            <input className={inputClass} value={form.city ?? ""} onChange={(e) => set("city", e.target.value)} />
          </Field>
          <Field label="Google map link" span={2}>
            <input className={inputClass} value={form.map_link ?? ""} onChange={(e) => set("map_link", e.target.value)} />
          </Field>
          <Field label="Managed by" span={2}>
            <input className={inputClass} value={form.managed_by ?? ""} onChange={(e) => set("managed_by", e.target.value)} />
          </Field>
        </div>
        <Field label="Remarks">
          <textarea className={textareaClass} value={form.remarks ?? ""} onChange={(e) => set("remarks", e.target.value)} />
        </Field>
        <div className="text-xs text-muted-foreground">
          Status and agreement terms are edited separately (Change status / Agreement tab). This form is the property&apos;s own details only.
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={onClose} className="h-9 rounded-md border border-border bg-card/60 px-3 text-sm">Cancel</button>
          <button type="submit" disabled={busy}
            className="h-9 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-60">
            {busy ? "Saving…" : "Save changes"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function statusBadgeClass(s: string): string {
  if (s === "active") return "bg-emerald-500/10 text-emerald-600";
  if (s === "on_hold") return "bg-amber-500/10 text-amber-600";
  if (s === "maintenance") return "bg-sky-500/10 text-sky-600";
  return "bg-muted text-muted-foreground";
}
