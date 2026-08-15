"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Wrench, Plus, CheckCircle2, XCircle, Building2 } from "lucide-react";
import type { ColumnDef } from "@tanstack/react-table";
import { api } from "@/lib/api";
import { Can } from "@/components/can";
import { Modal, Field, inputClass, selectClass, textareaClass } from "@/components/ui/dialog";
import { DataTable } from "@/components/ui/data-table";
import { PageHero } from "@/components/ui/page-hero";
import { toast, errorMessage } from "@/components/ui/toast";

type Property = { id: number; code: string; name: string };
type Unit = { id: number; unit_number: string; unit_type: string };

type MaintenanceRecord = {
  id: number;
  transaction_number: string;
  entity_type: "property" | "unit";
  entity_id: number;
  property_id: number | null;
  property: { id: number; code: string; name: string } | null;
  start_date: string;
  expected_end_date: string | null;
  actual_end_date: string | null;
  reason: string | null;
  prior_status: string;
  status: "in_progress" | "completed" | "cancelled";
  remarks: string | null;
  approved_by: number | null;
  created_at: string;
};

const STATUS_CLS: Record<string, string> = {
  in_progress: "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400",
  completed:   "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400",
  cancelled:   "bg-muted text-muted-foreground",
};

const STATUS_LABEL: Record<string, string> = {
  in_progress: "In Progress",
  completed: "Completed",
  cancelled: "Cancelled",
};

function today() {
  return new Date().toISOString().slice(0, 10);
}

type StartForm = {
  entity_type: "property" | "unit";
  property_id: string;
  unit_id: string;
  reason: string;
  start_date: string;
  expected_end_date: string;
  remarks: string;
};

type CompleteForm = {
  actual_end_date: string;
  remarks: string;
};

export default function MaintenancePage() {
  const [records, setRecords] = useState<MaintenanceRecord[]>([]);
  const [properties, setProperties] = useState<Property[]>([]);
  const [units, setUnits] = useState<Unit[]>([]);
  const [loading, setLoading] = useState(true);

  const [filterStatus, setFilterStatus] = useState("");
  const [filterEntityType, setFilterEntityType] = useState("");
  const [filterPropertyId, setFilterPropertyId] = useState("");

  const [showStart, setShowStart] = useState(false);
  const [startForm, setStartForm] = useState<StartForm>({
    entity_type: "property", property_id: "", unit_id: "",
    reason: "", start_date: today(), expected_end_date: "", remarks: "",
  });
  const [loadingUnits, setLoadingUnits] = useState(false);
  const [saving, setSaving] = useState(false);

  const [completeTarget, setCompleteTarget] = useState<MaintenanceRecord | null>(null);
  const [completeForm, setCompleteForm] = useState<CompleteForm>({ actual_end_date: today(), remarks: "" });
  const [completing, setCompleting] = useState(false);

  const [cancelTarget, setCancelTarget] = useState<MaintenanceRecord | null>(null);
  const [cancelling, setCancelling] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const params: Record<string, string> = {};
      if (filterStatus) params.status = filterStatus;
      if (filterEntityType) params.entity_type = filterEntityType;
      if (filterPropertyId) params.property_id = filterPropertyId;
      const r = await api.get("/maintenance", { params });
      setRecords(Array.isArray(r.data?.data) ? r.data.data : []);
    } catch {
      setRecords([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [filterStatus, filterEntityType, filterPropertyId]); // eslint-disable-line

  useEffect(() => {
    api.get("/properties", { params: { active_only: "true", page_size: 500 } })
      .then(r => setProperties(Array.isArray(r.data?.data) ? r.data.data : []))
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (startForm.entity_type !== "unit" || !startForm.property_id) {
      setUnits([]);
      return;
    }
    setLoadingUnits(true);
    api.get(`/properties/${startForm.property_id}/units`)
      .then(r => setUnits(Array.isArray(r.data?.data) ? r.data.data : []))
      .catch(() => setUnits([]))
      .finally(() => setLoadingUnits(false));
  }, [startForm.entity_type, startForm.property_id]);

  const handleStart = async () => {
    const entityId = startForm.entity_type === "property"
      ? Number(startForm.property_id)
      : Number(startForm.unit_id);
    if (!entityId) {
      toast.error(startForm.entity_type === "unit" ? "Select a property and unit" : "Select a property");
      return;
    }
    setSaving(true);
    try {
      await api.post("/maintenance", {
        entity_type: startForm.entity_type,
        entity_id: entityId,
        reason: startForm.reason || undefined,
        start_date: startForm.start_date || undefined,
        expected_end_date: startForm.expected_end_date || undefined,
        remarks: startForm.remarks || undefined,
      });
      toast.success("Maintenance started");
      setShowStart(false);
      setStartForm({ entity_type: "property", property_id: "", unit_id: "", reason: "", start_date: today(), expected_end_date: "", remarks: "" });
      await load();
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setSaving(false);
    }
  };

  const handleComplete = async () => {
    if (!completeTarget) return;
    setCompleting(true);
    try {
      await api.post(`/maintenance/${completeTarget.id}/complete`, {
        actual_end_date: completeForm.actual_end_date || undefined,
        remarks: completeForm.remarks || undefined,
      });
      toast.success("Maintenance completed");
      setCompleteTarget(null);
      await load();
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setCompleting(false);
    }
  };

  const handleCancel = async () => {
    if (!cancelTarget) return;
    setCancelling(true);
    try {
      await api.post(`/maintenance/${cancelTarget.id}/cancel`);
      toast.success("Maintenance cancelled");
      setCancelTarget(null);
      await load();
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setCancelling(false);
    }
  };

  const columns = useMemo<ColumnDef<MaintenanceRecord, unknown>[]>(() => [
    {
      accessorKey: "transaction_number", header: "Ref#",
      cell: (c) => <span className="font-mono text-xs">{c.getValue<string>()}</span>,
    },
    {
      id: "entity_type", header: "Type",
      cell: (c) => {
        const r = c.row.original;
        return (
          <span className={`inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full font-medium ${
            r.entity_type === "property"
              ? "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400"
              : "bg-violet-100 text-violet-700 dark:bg-violet-900/30 dark:text-violet-400"
          }`}>
            <Building2 className="h-3 w-3" />
            {r.entity_type === "property" ? "Property" : "Unit"}
          </span>
        );
      },
    },
    {
      id: "entity", header: "Entity",
      cell: (c) => {
        const r = c.row.original;
        if (r.entity_type === "property") {
          const p = r.property;
          return p
            ? <div>
                <Link href={`/properties/${p.id}`} className="font-medium hover:text-primary">{p.name}</Link>
                <div className="font-mono text-xs text-muted-foreground">{p.code}</div>
              </div>
            : <span className="text-muted-foreground">—</span>;
        }
        return (
          <div>
            <span className="font-medium">Unit #{r.entity_id}</span>
            {r.property && (
              <div className="font-mono text-xs text-muted-foreground">
                <Link href={`/properties/${r.property.id}`} className="hover:text-primary">{r.property.code}</Link>
              </div>
            )}
          </div>
        );
      },
    },
    {
      accessorKey: "start_date", header: "Start",
      cell: (c) => <span className="text-xs font-mono">{c.getValue<string>()}</span>,
    },
    {
      accessorKey: "expected_end_date", header: "Exp. End",
      cell: (c) => <span className="text-xs font-mono">{c.getValue<string | null>() ?? "—"}</span>,
    },
    {
      accessorKey: "actual_end_date", header: "Actual End",
      cell: (c) => <span className="text-xs font-mono">{c.getValue<string | null>() ?? "—"}</span>,
    },
    {
      accessorKey: "reason", header: "Reason",
      cell: (c) => <span className="text-sm">{c.getValue<string | null>() ?? "—"}</span>,
    },
    {
      accessorKey: "status", header: "Status",
      cell: (c) => {
        const s = c.getValue<string>();
        return (
          <span className={`inline-block text-xs px-2 py-0.5 rounded-full font-medium ${STATUS_CLS[s] ?? ""}`}>
            {STATUS_LABEL[s] ?? s}
          </span>
        );
      },
    },
    {
      id: "actions", header: "", enableSorting: false,
      cell: (c) => {
        const r = c.row.original;
        if (r.status !== "in_progress") return null;
        return (
          <Can perm="maintenance.manage">
            <div className="flex items-center gap-1 justify-end">
              <button
                onClick={() => { setCompleteTarget(r); setCompleteForm({ actual_end_date: today(), remarks: "" }); }}
                title="Mark completed"
                className="h-8 w-8 inline-flex items-center justify-center rounded-md hover:bg-emerald-100 dark:hover:bg-emerald-900/30 text-emerald-600"
              >
                <CheckCircle2 className="h-4 w-4" />
              </button>
              <button
                onClick={() => setCancelTarget(r)}
                title="Cancel maintenance"
                className="h-8 w-8 inline-flex items-center justify-center rounded-md hover:bg-muted text-muted-foreground"
              >
                <XCircle className="h-4 w-4" />
              </button>
            </div>
          </Can>
        );
      },
    },
  ], []); // eslint-disable-line

  const inProgress = records.filter(r => r.status === "in_progress").length;

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHero
        icon={Wrench}
        title="Maintenance"
        description="Track property and unit maintenance windows — start, complete, or cancel."
        action={
          <Can perm="maintenance.manage">
            <button
              onClick={() => setShowStart(true)}
              className="inline-flex h-9 items-center gap-2 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:bg-primary/90"
            >
              <Plus className="h-4 w-4" /> Start Maintenance
            </button>
          </Can>
        }
      />

      {inProgress > 0 && (
        <div className="glass rounded-xl px-4 py-3 inline-flex items-center gap-2 text-sm text-amber-700 dark:text-amber-400">
          <Wrench className="h-4 w-4" />
          {inProgress} record{inProgress !== 1 ? "s" : ""} currently in progress
        </div>
      )}

      {/* Filters */}
      <div className="glass rounded-xl p-4 flex flex-wrap gap-2 items-center">
        <select value={filterStatus} onChange={e => setFilterStatus(e.target.value)}
          className={selectClass + " !w-auto"}>
          <option value="">All statuses</option>
          <option value="in_progress">In Progress</option>
          <option value="completed">Completed</option>
          <option value="cancelled">Cancelled</option>
        </select>
        <select value={filterEntityType} onChange={e => setFilterEntityType(e.target.value)}
          className={selectClass + " !w-auto"}>
          <option value="">All types</option>
          <option value="property">Property</option>
          <option value="unit">Unit</option>
        </select>
        <select value={filterPropertyId} onChange={e => setFilterPropertyId(e.target.value)}
          className={selectClass + " !w-auto"}>
          <option value="">All properties</option>
          {properties.map(p => (
            <option key={p.id} value={p.id}>{p.name} ({p.code})</option>
          ))}
        </select>
      </div>

      <DataTable
        columns={columns}
        data={records}
        loading={loading}
        maxBodyHeight="65vh"
        getRowId={r => String(r.id)}
        emptyMessage="No maintenance records found. Use 'Start Maintenance' to log a new one."
      />

      {/* Start Maintenance Modal */}
      <Modal open={showStart} onClose={() => setShowStart(false)} title="Start Maintenance">
        <div className="space-y-4">
          <Field label="Entity type">
            <select
              value={startForm.entity_type}
              onChange={e => setStartForm(f => ({ ...f, entity_type: e.target.value as "property" | "unit", unit_id: "" }))}
              className={selectClass}
            >
              <option value="property">Property</option>
              <option value="unit">Unit</option>
            </select>
          </Field>
          <Field label="Property *">
            <select
              value={startForm.property_id}
              onChange={e => setStartForm(f => ({ ...f, property_id: e.target.value, unit_id: "" }))}
              className={selectClass}
            >
              <option value="">Select property…</option>
              {properties.map(p => (
                <option key={p.id} value={p.id}>{p.name} ({p.code})</option>
              ))}
            </select>
          </Field>
          {startForm.entity_type === "unit" && (
            <Field label="Unit *">
              <select
                value={startForm.unit_id}
                onChange={e => setStartForm(f => ({ ...f, unit_id: e.target.value }))}
                className={selectClass}
                disabled={!startForm.property_id || loadingUnits}
              >
                <option value="">{loadingUnits ? "Loading units…" : "Select unit…"}</option>
                {units.map(u => (
                  <option key={u.id} value={u.id}>#{u.unit_number} — {u.unit_type}</option>
                ))}
              </select>
            </Field>
          )}
          <Field label="Reason">
            <input
              value={startForm.reason}
              onChange={e => setStartForm(f => ({ ...f, reason: e.target.value }))}
              placeholder="e.g. Plumbing repair, AC servicing"
              className={inputClass}
            />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Start date">
              <input type="date" value={startForm.start_date}
                onChange={e => setStartForm(f => ({ ...f, start_date: e.target.value }))}
                className={inputClass} />
            </Field>
            <Field label="Expected end date">
              <input type="date" value={startForm.expected_end_date}
                onChange={e => setStartForm(f => ({ ...f, expected_end_date: e.target.value }))}
                className={inputClass} />
            </Field>
          </div>
          <Field label="Remarks">
            <textarea value={startForm.remarks}
              onChange={e => setStartForm(f => ({ ...f, remarks: e.target.value }))}
              rows={2} className={textareaClass} />
          </Field>
          <div className="flex justify-end gap-2 pt-2">
            <button onClick={() => setShowStart(false)}
              className="h-9 px-4 rounded-md border border-border text-sm hover:bg-accent">Cancel</button>
            <button onClick={handleStart} disabled={saving}
              className="h-9 px-4 rounded-md bg-primary text-primary-foreground text-sm hover:bg-primary/90 disabled:opacity-60">
              {saving ? "Saving…" : "Start"}
            </button>
          </div>
        </div>
      </Modal>

      {/* Complete Modal */}
      <Modal
        open={Boolean(completeTarget)}
        onClose={() => setCompleteTarget(null)}
        title={`Complete — ${completeTarget?.transaction_number ?? ""}`}
      >
        <div className="space-y-4">
          <Field label="Actual end date">
            <input type="date" value={completeForm.actual_end_date}
              onChange={e => setCompleteForm(f => ({ ...f, actual_end_date: e.target.value }))}
              className={inputClass} />
          </Field>
          <Field label="Closing remarks">
            <textarea value={completeForm.remarks}
              onChange={e => setCompleteForm(f => ({ ...f, remarks: e.target.value }))}
              rows={2} className={textareaClass} />
          </Field>
          <div className="flex justify-end gap-2 pt-2">
            <button onClick={() => setCompleteTarget(null)}
              className="h-9 px-4 rounded-md border border-border text-sm hover:bg-accent">Cancel</button>
            <button onClick={handleComplete} disabled={completing}
              className="h-9 px-4 rounded-md bg-emerald-600 text-white text-sm hover:bg-emerald-700 disabled:opacity-60">
              {completing ? "Saving…" : "Mark Completed"}
            </button>
          </div>
        </div>
      </Modal>

      {/* Cancel Confirm Modal */}
      <Modal open={Boolean(cancelTarget)} onClose={() => setCancelTarget(null)} title="Cancel Maintenance">
        <div className="space-y-4">
          <p className="text-sm text-muted-foreground">
            Cancel maintenance{" "}
            <span className="font-mono font-medium text-foreground">{cancelTarget?.transaction_number}</span>?
            The entity&apos;s status will not be restored — use this only as a correction if the record was logged in error.
          </p>
          <div className="flex justify-end gap-2 pt-2">
            <button onClick={() => setCancelTarget(null)}
              className="h-9 px-4 rounded-md border border-border text-sm hover:bg-accent">Keep</button>
            <button onClick={handleCancel} disabled={cancelling}
              className="h-9 px-4 rounded-md bg-destructive text-destructive-foreground text-sm hover:bg-destructive/90 disabled:opacity-60">
              {cancelling ? "Cancelling…" : "Yes, Cancel"}
            </button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
