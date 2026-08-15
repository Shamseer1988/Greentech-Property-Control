"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { RefreshCcw, Plus } from "lucide-react";
import type { ColumnDef } from "@tanstack/react-table";
import { api } from "@/lib/api";
import { Can } from "@/components/can";
import { Modal, Field, inputClass, selectClass, textareaClass } from "@/components/ui/dialog";
import { DataTable } from "@/components/ui/data-table";
import { PageHero } from "@/components/ui/page-hero";
import { money } from "@/lib/contract-types";
import { toast, errorMessage } from "@/components/ui/toast";

type Property  = { id: number; code: string; name: string };
type Landlord  = { id: number; code: string; name: string };

type LandlordRenewal = {
  id: number;
  transaction_number: string;
  property: Property | null;
  landlord: Landlord | null;
  renewal_date: string;
  old_expiry_date: string | null;
  new_start_date: string;
  new_expiry_date: string;
  old_monthly_rent: number | null;
  new_monthly_rent: number | null;
  remarks: string | null;
  status: "completed" | "pending_approval";
  created_at: string;
};

const STATUS_CLS: Record<string, string> = {
  completed:        "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400",
  pending_approval: "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400",
};

const STATUS_LABEL: Record<string, string> = {
  completed: "Completed",
  pending_approval: "Pending Approval",
};

type NewForm = {
  property_id: string;
  landlord_id: string;
  new_start_date: string;
  new_expiry_date: string;
  new_monthly_rent: string;
  agreement_number: string;
  payment_terms: string;
  remarks: string;
};

const EMPTY_FORM: NewForm = {
  property_id: "", landlord_id: "",
  new_start_date: "", new_expiry_date: "",
  new_monthly_rent: "", agreement_number: "",
  payment_terms: "", remarks: "",
};

export default function RenewalsPage() {
  const [records, setRecords] = useState<LandlordRenewal[]>([]);
  const [properties, setProperties] = useState<Property[]>([]);
  const [landlords, setLandlords] = useState<Landlord[]>([]);
  const [loading, setLoading] = useState(true);

  const [filterPropertyId, setFilterPropertyId] = useState("");
  const [filterLandlordId, setFilterLandlordId] = useState("");

  const [showNew, setShowNew] = useState(false);
  const [form, setForm] = useState<NewForm>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const params: Record<string, string> = {};
      if (filterPropertyId) params.property_id = filterPropertyId;
      if (filterLandlordId) params.landlord_id = filterLandlordId;
      const r = await api.get("/renewals", { params });
      setRecords(Array.isArray(r.data?.data) ? r.data.data : []);
    } catch {
      setRecords([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [filterPropertyId, filterLandlordId]); // eslint-disable-line

  useEffect(() => {
    Promise.all([
      api.get("/properties", { params: { active_only: "true", page_size: 500 } }),
      api.get("/landlords",  { params: { active_only: "true", page_size: 500 } }),
    ]).then(([p, l]) => {
      setProperties(Array.isArray(p.data?.data) ? p.data.data : []);
      setLandlords(Array.isArray(l.data?.data) ? l.data.data : []);
    }).catch(() => {});
  }, []);

  const handleNew = async () => {
    if (!form.property_id) { toast.error("Select a property"); return; }
    if (!form.landlord_id) { toast.error("Select a landlord"); return; }
    if (!form.new_start_date) { toast.error("Enter new start date"); return; }
    if (!form.new_expiry_date) { toast.error("Enter new expiry date"); return; }
    setSaving(true);
    try {
      await api.post("/renewals", {
        property_id:      Number(form.property_id),
        landlord_id:      Number(form.landlord_id),
        new_start_date:   form.new_start_date,
        new_expiry_date:  form.new_expiry_date,
        new_monthly_rent: form.new_monthly_rent ? Number(form.new_monthly_rent) : undefined,
        agreement_number: form.agreement_number || undefined,
        payment_terms:    form.payment_terms || undefined,
        remarks:          form.remarks || undefined,
      });
      toast.success("Renewal posted");
      setShowNew(false);
      setForm(EMPTY_FORM);
      await load();
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setSaving(false);
    }
  };

  const columns = useMemo<ColumnDef<LandlordRenewal, unknown>[]>(() => [
    {
      accessorKey: "transaction_number", header: "Ref#",
      cell: (c) => <span className="font-mono text-xs">{c.getValue<string>()}</span>,
    },
    {
      id: "property", header: "Property",
      cell: (c) => {
        const p = c.row.original.property;
        return p
          ? <div>
              <Link href={`/properties/${p.id}`} className="font-medium hover:text-primary">{p.name}</Link>
              <div className="font-mono text-xs text-muted-foreground">{p.code}</div>
            </div>
          : <span className="text-muted-foreground">—</span>;
      },
    },
    {
      id: "landlord", header: "Landlord",
      cell: (c) => {
        const l = c.row.original.landlord;
        return l
          ? <div>
              <Link href={`/landlords/${l.id}`} className="font-medium hover:text-primary">{l.name}</Link>
              <div className="font-mono text-xs text-muted-foreground">{l.code}</div>
            </div>
          : <span className="text-muted-foreground">—</span>;
      },
    },
    {
      accessorKey: "renewal_date", header: "Renewal Date",
      cell: (c) => <span className="text-xs font-mono">{c.getValue<string>()}</span>,
    },
    {
      accessorKey: "old_expiry_date", header: "Old Expiry",
      cell: (c) => <span className="text-xs font-mono">{c.getValue<string | null>() ?? "—"}</span>,
    },
    {
      id: "new_period", header: "New Period",
      cell: (c) => {
        const r = c.row.original;
        return (
          <div className="text-xs font-mono">
            <div>{r.new_start_date}</div>
            <div className="text-muted-foreground">→ {r.new_expiry_date}</div>
          </div>
        );
      },
    },
    {
      id: "rent", header: "Old → New Rent",
      cell: (c) => {
        const r = c.row.original;
        const oldR = r.old_monthly_rent != null ? money(r.old_monthly_rent) : "—";
        const newR = r.new_monthly_rent != null ? money(r.new_monthly_rent) : "—";
        return (
          <div className="text-xs">
            <span className="text-muted-foreground">{oldR}</span>
            <span className="mx-1">→</span>
            <span className="font-medium">{newR}</span>
          </div>
        );
      },
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
  ], []);

  const pendingCount = records.filter(r => r.status === "pending_approval").length;

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHero
        icon={RefreshCcw}
        title="Landlord Renewals"
        description="Renew property agreements with landlords — archives the old agreement and creates a new one."
        action={
          <Can perm="renewal.create">
            <button
              onClick={() => setShowNew(true)}
              className="inline-flex h-9 items-center gap-2 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:bg-primary/90"
            >
              <Plus className="h-4 w-4" /> New Renewal
            </button>
          </Can>
        }
      />

      {pendingCount > 0 && (
        <div className="glass rounded-xl px-4 py-3 inline-flex items-center gap-2 text-sm text-amber-700 dark:text-amber-400">
          <RefreshCcw className="h-4 w-4" />
          {pendingCount} renewal{pendingCount !== 1 ? "s" : ""} pending approval
        </div>
      )}

      {/* Filters */}
      <div className="glass rounded-xl p-4 flex flex-wrap gap-2 items-center">
        <select value={filterPropertyId} onChange={e => setFilterPropertyId(e.target.value)}
          className={selectClass + " !w-auto"}>
          <option value="">All properties</option>
          {properties.map(p => (
            <option key={p.id} value={p.id}>{p.name} ({p.code})</option>
          ))}
        </select>
        <select value={filterLandlordId} onChange={e => setFilterLandlordId(e.target.value)}
          className={selectClass + " !w-auto"}>
          <option value="">All landlords</option>
          {landlords.map(l => (
            <option key={l.id} value={l.id}>{l.name} ({l.code})</option>
          ))}
        </select>
      </div>

      <DataTable
        columns={columns}
        data={records}
        loading={loading}
        maxBodyHeight="65vh"
        getRowId={r => String(r.id)}
        emptyMessage="No renewals found. Use 'New Renewal' to renew a landlord agreement."
      />

      {/* New Renewal Modal */}
      <Modal open={showNew} onClose={() => setShowNew(false)} title="New Landlord Renewal" size="lg">
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <Field label="Property *">
              <select value={form.property_id} onChange={e => setForm(f => ({ ...f, property_id: e.target.value }))}
                className={selectClass}>
                <option value="">Select property…</option>
                {properties.map(p => (
                  <option key={p.id} value={p.id}>{p.name} ({p.code})</option>
                ))}
              </select>
            </Field>
            <Field label="Landlord *">
              <select value={form.landlord_id} onChange={e => setForm(f => ({ ...f, landlord_id: e.target.value }))}
                className={selectClass}>
                <option value="">Select landlord…</option>
                {landlords.map(l => (
                  <option key={l.id} value={l.id}>{l.name} ({l.code})</option>
                ))}
              </select>
            </Field>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Field label="New start date *">
              <input type="date" value={form.new_start_date}
                onChange={e => setForm(f => ({ ...f, new_start_date: e.target.value }))}
                className={inputClass} />
            </Field>
            <Field label="New expiry date *">
              <input type="date" value={form.new_expiry_date}
                onChange={e => setForm(f => ({ ...f, new_expiry_date: e.target.value }))}
                className={inputClass} />
            </Field>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Field label="New monthly rent">
              <input type="number" value={form.new_monthly_rent}
                onChange={e => setForm(f => ({ ...f, new_monthly_rent: e.target.value }))}
                placeholder="0.00" min="0" step="0.01"
                className={inputClass} />
            </Field>
            <Field label="Agreement number">
              <input value={form.agreement_number}
                onChange={e => setForm(f => ({ ...f, agreement_number: e.target.value }))}
                placeholder="Contract / ref number"
                className={inputClass} />
            </Field>
          </div>
          <Field label="Payment terms">
            <input value={form.payment_terms}
              onChange={e => setForm(f => ({ ...f, payment_terms: e.target.value }))}
              placeholder="e.g. 4 cheques / annual"
              className={inputClass} />
          </Field>
          <Field label="Remarks">
            <textarea value={form.remarks}
              onChange={e => setForm(f => ({ ...f, remarks: e.target.value }))}
              rows={2} className={textareaClass} />
          </Field>
          <p className="text-xs text-muted-foreground bg-muted/50 rounded-lg px-3 py-2">
            Posting this renewal archives the current active agreement for the selected property
            and creates a new one with the dates and rent above. If approval is required,
            the old agreement is not touched until an approver confirms.
          </p>
          <div className="flex justify-end gap-2 pt-2">
            <button onClick={() => setShowNew(false)}
              className="h-9 px-4 rounded-md border border-border text-sm hover:bg-accent">Cancel</button>
            <button onClick={handleNew} disabled={saving}
              className="h-9 px-4 rounded-md bg-primary text-primary-foreground text-sm hover:bg-primary/90 disabled:opacity-60">
              {saving ? "Posting…" : "Post Renewal"}
            </button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
