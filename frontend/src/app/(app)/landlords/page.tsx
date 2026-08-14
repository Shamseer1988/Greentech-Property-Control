"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Pencil } from "lucide-react";
import type { ColumnDef, PaginationState } from "@tanstack/react-table";
import { api } from "@/lib/api";
import { Can } from "@/components/can";
import { Modal, Field, inputClass, selectClass, textareaClass } from "@/components/ui/dialog";
import { DataTable } from "@/components/ui/data-table";
import { toast, errorMessage } from "@/components/ui/toast";
import { useDebouncedValue } from "@/lib/use-debounce";
import { keys } from "@/lib/query-keys";

type Landlord = {
  id: number;
  code: string;
  name: string;
  name_ar: string | null;
  qid_cr_number: string | null;
  qid_cr_expiry_date: string | null;
  mobile: string | null;
  email: string | null;
  contact_person: string | null;
  address: string | null;
  agreement_expiry_date: string | null;
  signatory_name: string | null;
  signatory_name_ar: string | null;
  signatory_id_number: string | null;
  signatory_title: string | null;
  signatory_mobile: string | null;
  status: string;
  remarks: string | null;
};

const EXPIRY_PRESETS = [
  { value: "", label: "Any expiry" },
  { value: "-1", label: "Expired" },
  { value: "30", label: "Within 1 month" },
  { value: "90", label: "Within 3 months" },
  { value: "180", label: "Within 6 months" },
];

export default function LandlordsPage() {
  const qc = useQueryClient();
  const [q, setQ] = useState("");
  const debouncedQ = useDebouncedValue(q);
  const [status, setStatus] = useState("");
  const [showDeactivated, setShowDeactivated] = useState(false);
  const [expiresWithin, setExpiresWithin] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<Landlord | null>(null);
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 25 });

  // An explicit status pick always wins; otherwise default to active-only
  // unless "Show deactivated" is checked.
  const effectiveStatus = status || (showDeactivated ? "" : "active");
  const filters = { q: debouncedQ, status: effectiveStatus, expiresWithin };

  // A filter change invalidates the page the user was on — jumping back
  // to page 1 is the only sane behavior when the result set just changed
  // shape, and avoids landing on a now-nonexistent page.
  useEffect(() => { setPagination((p) => ({ ...p, pageIndex: 0 })); }, [debouncedQ, effectiveStatus, expiresWithin]);

  const listQuery = useQuery({
    queryKey: keys.landlords.list({ ...filters, ...pagination }),
    queryFn: async () => {
      const params: Record<string, string | number> = {
        page: pagination.pageIndex + 1, per_page: pagination.pageSize,
      };
      if (debouncedQ) params.q = debouncedQ;
      if (effectiveStatus) params.status = effectiveStatus;
      if (expiresWithin) params.expires_within = expiresWithin;
      const resp = await api.get("/landlords", { params });
      return resp.data as { data: Landlord[]; meta: { total_count: number; total_pages: number } };
    },
    placeholderData: (prev) => prev,
  });
  const rows = listQuery.data?.data ?? [];
  const meta = listQuery.data?.meta;

  const invalidate = () => qc.invalidateQueries({ queryKey: keys.landlords.all() });

  const columns = useMemo<ColumnDef<Landlord, unknown>[]>(() => [
    { accessorKey: "code", header: "Code", cell: (c) => <span className="font-mono text-xs">{c.getValue<string>()}</span> },
    {
      accessorKey: "name", header: "Name",
      cell: (c) => {
        const r = c.row.original;
        return (
          <div>
            <Link href={`/landlords/${r.id}`} className="font-medium hover:text-primary">{r.name}</Link>
            {r.name_ar && <div className="text-xs text-muted-foreground" dir="rtl">{r.name_ar}</div>}
          </div>
        );
      },
    },
    { accessorKey: "qid_cr_number", header: "QID/CR", cell: (c) => <span className="font-mono text-xs">{c.getValue<string>() ?? "—"}</span> },
    { accessorKey: "mobile", header: "Mobile", cell: (c) => c.getValue<string>() ?? "—" },
    { accessorKey: "email", header: "Email", cell: (c) => c.getValue<string>() ?? "—" },
    { accessorKey: "agreement_expiry_date", header: "Agreement expiry", cell: (c) => c.getValue<string>() ?? "—" },
    { accessorKey: "status", header: "Status", cell: (c) => <span className="capitalize">{c.getValue<string>()}</span> },
    {
      id: "actions", header: "", enableSorting: false,
      cell: (c) => {
        const r = c.row.original;
        return (
          <div className="text-right">
            <Can perm="landlord.edit">
              <button
                onClick={() => { setEditing(r); setShowForm(true); }}
                aria-label={`Edit ${r.name}`}
                className="h-8 w-8 grid place-items-center rounded-md hover:bg-accent">
                <Pencil className="h-3.5 w-3.5" />
              </button>
            </Can>
          </div>
        );
      },
    },
  ], []);

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-end justify-between flex-wrap gap-2">
        <div>
          <h1 className="text-2xl lg:text-3xl font-semibold tracking-tight">Landlords</h1>
          <p className="text-sm text-muted-foreground">Property owners with their current agreement, expiry tracking and attached PDFs.</p>
        </div>
        <Can perm="landlord.create">
          <button
            onClick={() => { setEditing(null); setShowForm(true); }}
            className="inline-flex h-9 items-center gap-2 rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground hover:bg-primary/90"
          >
            <Plus className="h-4 w-4" /> New landlord
          </button>
        </Can>
      </div>

      <div className="glass rounded-xl p-4">
        <div className="flex items-center gap-2 flex-wrap">
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && listQuery.refetch()}
            placeholder="Search code, name, QID/CR, mobile…"
            className="h-9 w-64 shrink-0 rounded-md border border-input bg-card/60 px-3 text-sm"
          />
          <select value={status} onChange={(e) => setStatus(e.target.value)} className={selectClass + " !w-auto shrink-0"}>
            <option value="">All statuses</option>
            <option value="active">Active</option>
            <option value="inactive">Inactive</option>
          </select>
          <select value={expiresWithin} onChange={(e) => setExpiresWithin(e.target.value)} className={selectClass + " !w-auto shrink-0"}>
            {EXPIRY_PRESETS.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
          </select>
          <label className="inline-flex items-center gap-1.5 text-xs text-muted-foreground shrink-0 whitespace-nowrap">
            <input type="checkbox" checked={showDeactivated} onChange={(e) => setShowDeactivated(e.target.checked)} />
            Show deactivated
          </label>
          <button onClick={() => listQuery.refetch()} className="h-9 shrink-0 rounded-md border border-border bg-card/60 px-3 text-sm hover:bg-accent">Search</button>
        </div>
      </div>

      <DataTable columns={columns} data={rows} loading={listQuery.isLoading} emptyMessage="No landlords yet" maxBodyHeight="65vh"
        manualPagination pageCount={meta?.total_pages ?? 0} totalCount={meta?.total_count}
        pagination={pagination} onPaginationChange={setPagination} />

      <LandlordDialog open={showForm} editing={editing}
        onClose={() => setShowForm(false)}
        onSaved={() => { setShowForm(false); invalidate(); }}
      />
    </div>
  );
}

function LandlordDialog({ open, editing, onClose, onSaved }: {
  open: boolean; editing: Landlord | null; onClose: () => void; onSaved: () => void;
}) {
  const [form, setForm] = useState<Partial<Landlord>>({});
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) {
      setForm(editing ?? { status: "active" } as Partial<Landlord>);
    }
  }, [editing, open]);

  const set = <K extends keyof Landlord>(k: K, v: Landlord[K] | null | undefined) =>
    setForm((f) => ({ ...f, [k]: v }));

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      // Send only what the API accepts; blank strings become null so a
      // cleared field actually clears.
      const payload: Record<string, unknown> = {};
      const fields: (keyof Landlord)[] = [
        "name", "name_ar", "qid_cr_number", "qid_cr_expiry_date",
        "mobile", "email", "contact_person", "address",
        "signatory_name", "signatory_name_ar", "signatory_id_number",
        "signatory_title", "signatory_mobile",
        "status", "remarks",
      ];
      for (const k of fields) {
        const v = form[k];
        if (v === undefined) continue;
        payload[k] = v === "" ? null : v;
      }

      let savedCode: string;
      if (editing) {
        const resp = await api.put(`/landlords/${editing.id}`, payload);
        savedCode = resp.data?.data?.code ?? editing.code;
        toast.success(`Landlord ${savedCode} updated`);
      } else {
        const resp = await api.post("/landlords", payload);
        savedCode = resp.data?.data?.code ?? "";
        toast.success(`Landlord ${savedCode} created`);
      }
      onSaved();
    } catch (err: unknown) {
      toast.error("Save failed", errorMessage(err));
    } finally { setBusy(false); }
  };

  return (
    <Modal open={open} onClose={onClose} title={editing ? "Edit landlord" : "New landlord"} size="lg">
      <form onSubmit={save} className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <Field label="Name (English)" span={2}>
            <input required className={inputClass} value={String(form.name ?? "")} onChange={(e) => set("name", e.target.value)} />
          </Field>
          <Field label="Name (Arabic)" span={2}>
            <input className={inputClass} dir="rtl" value={String(form.name_ar ?? "")}
              onChange={(e) => set("name_ar", e.target.value)} placeholder="الاسم بالعربية" />
          </Field>
          <Field label="QID / CR">
            <input className={inputClass} value={String(form.qid_cr_number ?? "")} onChange={(e) => set("qid_cr_number", e.target.value)} />
          </Field>
          <Field label="QID / CR expiry">
            <input type="date" className={inputClass} value={String(form.qid_cr_expiry_date ?? "")}
              onChange={(e) => set("qid_cr_expiry_date", e.target.value)} />
          </Field>
          <Field label="Status">
            <select className={selectClass} value={String(form.status ?? "active")} onChange={(e) => set("status", e.target.value)}>
              <option value="active">Active</option>
              <option value="inactive">Inactive</option>
            </select>
          </Field>
          <Field label="Mobile">
            <input className={inputClass} value={String(form.mobile ?? "")} onChange={(e) => set("mobile", e.target.value)} />
          </Field>
          <Field label="Email">
            <input type="email" className={inputClass} value={String(form.email ?? "")} onChange={(e) => set("email", e.target.value)} />
          </Field>
          <Field label="Contact person" span={2}>
            <input className={inputClass} value={String(form.contact_person ?? "")} onChange={(e) => set("contact_person", e.target.value)} />
          </Field>
          <Field label="Address" span={2}>
            <textarea className={textareaClass} value={String(form.address ?? "")} onChange={(e) => set("address", e.target.value)} />
          </Field>
        </div>

        <div className="pt-1 border-t border-border">
          <div className="text-xs font-medium text-muted-foreground pt-2 pb-1">
            Signatory — required to generate a rental agreement for this landlord
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Signatory name (English)">
              <input className={inputClass} value={String(form.signatory_name ?? "")}
                onChange={(e) => set("signatory_name", e.target.value)} />
            </Field>
            <Field label="Signatory name (Arabic)">
              <input className={inputClass} dir="rtl" value={String(form.signatory_name_ar ?? "")}
                onChange={(e) => set("signatory_name_ar", e.target.value)} placeholder="اسم الموقّع بالعربية" />
            </Field>
            <Field label="Signatory ID number">
              <input className={inputClass} value={String(form.signatory_id_number ?? "")}
                onChange={(e) => set("signatory_id_number", e.target.value)} />
            </Field>
            <Field label="Signatory title">
              <input className={inputClass} value={String(form.signatory_title ?? "")}
                onChange={(e) => set("signatory_title", e.target.value)} placeholder="e.g. General Manager" />
            </Field>
            <Field label="Signatory mobile" span={2}>
              <input className={inputClass} value={String(form.signatory_mobile ?? "")}
                onChange={(e) => set("signatory_mobile", e.target.value)} />
            </Field>
          </div>
        </div>

        <Field label="Remarks">
          <textarea className={textareaClass} value={String(form.remarks ?? "")} onChange={(e) => set("remarks", e.target.value)} />
        </Field>

        <div className="text-xs text-muted-foreground">
          Agreements (start date, expiry, rent, PDF) are managed on each property&apos;s detail page.
        </div>

        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={onClose} className="h-9 rounded-md border border-border bg-card/60 px-3 text-sm">Cancel</button>
          <button type="submit" disabled={busy} className="h-9 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-60">
            {busy ? "Saving…" : editing ? "Save changes" : "Create landlord"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

