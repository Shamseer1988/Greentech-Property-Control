"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Pencil, Paperclip, AlertTriangle } from "lucide-react";
import type { ColumnDef, PaginationState } from "@tanstack/react-table";
import { api } from "@/lib/api";
import { Can } from "@/components/can";
import { Modal, Field, inputClass, selectClass, textareaClass } from "@/components/ui/dialog";
import { DataTable } from "@/components/ui/data-table";
import { toast, errorMessage } from "@/components/ui/toast";
import { AttachmentsTab } from "@/components/attachments-tab";
import { useDebouncedValue } from "@/lib/use-debounce";
import { keys } from "@/lib/query-keys";

type Client = {
  id: number;
  code: string;
  name: string;
  name_ar: string | null;
  client_type: string;
  contact_person: string | null;
  mobile: string | null;
  alt_mobile: string | null;
  email: string | null;
  address: string | null;
  qid_cr_number: string | null;
  qid_cr_expiry_date: string | null;
  signatory_name: string | null;
  signatory_name_ar: string | null;
  signatory_id_number: string | null;
  signatory_title: string | null;
  signatory_mobile: string | null;
  status: string;
  remarks: string | null;
};

const STATUS_TONE: Record<string, string> = {
  active: "bg-emerald-500/10 text-emerald-600",
  inactive: "bg-muted text-muted-foreground",
  blacklisted: "bg-rose-500/10 text-rose-600",
};

function daysUntil(iso: string | null): number | null {
  if (!iso) return null;
  return Math.ceil((new Date(iso).getTime() - Date.now()) / 86400000);
}

export default function ClientsPage() {
  const qc = useQueryClient();
  const [q, setQ] = useState("");
  const debouncedQ = useDebouncedValue(q);
  const [status, setStatus] = useState("");
  const [showDeactivated, setShowDeactivated] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<Client | null>(null);
  const [docsFor, setDocsFor] = useState<Client | null>(null);
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 25 });

  // An explicit status pick always wins; otherwise default to active-only
  // (hides inactive + blacklisted) unless "Show deactivated" is checked.
  const effectiveStatus = status || (showDeactivated ? "" : "active");

  useEffect(() => { setPagination((p) => ({ ...p, pageIndex: 0 })); }, [debouncedQ, effectiveStatus]);

  const listQuery = useQuery({
    queryKey: keys.clients.list({ q: debouncedQ, status: effectiveStatus, ...pagination }),
    queryFn: async () => {
      const params: Record<string, string | number> = {
        page: pagination.pageIndex + 1, per_page: pagination.pageSize,
      };
      if (debouncedQ) params.q = debouncedQ;
      if (effectiveStatus) params.status = effectiveStatus;
      const resp = await api.get("/clients", { params });
      return resp.data as { data: Client[]; meta: { total_count: number; total_pages: number } };
    },
    placeholderData: (prev) => prev,
  });
  const rows = listQuery.data?.data ?? [];
  const meta = listQuery.data?.meta;
  const invalidate = () => qc.invalidateQueries({ queryKey: keys.clients.all() });

  const columns = useMemo<ColumnDef<Client, unknown>[]>(() => [
    { accessorKey: "code", header: "Code", cell: (c) => <span className="font-mono text-xs">{c.getValue<string>()}</span> },
    {
      accessorKey: "name", header: "Name",
      cell: (c) => {
        const r = c.row.original;
        return (
          <div>
            <Link href={`/clients/${r.id}`} className="font-medium hover:text-primary">{r.name}</Link>
            {r.name_ar && <div className="text-xs text-muted-foreground" dir="rtl">{r.name_ar}</div>}
          </div>
        );
      },
    },
    { accessorKey: "client_type", header: "Type", cell: (c) => <span className="capitalize">{c.getValue<string>()}</span> },
    { accessorKey: "contact_person", header: "Contact", cell: (c) => c.getValue<string>() ?? "—" },
    { accessorKey: "mobile", header: "Mobile", cell: (c) => c.getValue<string>() ?? "—" },
    {
      id: "cr_qid", header: "CR / QID", accessorFn: (r) => r.qid_cr_number,
      cell: (c) => {
        const r = c.row.original;
        const days = daysUntil(r.qid_cr_expiry_date);
        const docWarn = days !== null && days <= 60;
        return (
          <div>
            <span className="font-mono text-xs">{r.qid_cr_number ?? "—"}</span>
            {r.qid_cr_expiry_date && (
              <div className={"text-xs inline-flex items-center gap-1 " + (docWarn ? "text-amber-600" : "text-muted-foreground")}>
                {docWarn && <AlertTriangle className="h-3 w-3" />}
                {days !== null && days < 0 ? `expired ${Math.abs(days)}d ago` : `expires ${r.qid_cr_expiry_date}`}
              </div>
            )}
          </div>
        );
      },
    },
    {
      accessorKey: "status", header: "Status",
      cell: (c) => (
        <span className={"rounded-full px-2 py-0.5 text-xs capitalize " + (STATUS_TONE[c.getValue<string>()] ?? "")}>
          {c.getValue<string>()}
        </span>
      ),
    },
    {
      id: "actions", header: "", enableSorting: false,
      cell: (c) => {
        const r = c.row.original;
        return (
          <div className="text-right whitespace-nowrap">
            <Can perm="attachment.view">
              <button onClick={() => setDocsFor(r)} aria-label={`Documents for ${r.name}`} title="Documents"
                className="h-8 w-8 grid place-items-center rounded-md hover:bg-accent inline-block">
                <Paperclip className="h-3.5 w-3.5" />
              </button>
            </Can>
            <Can perm="client.edit">
              <button onClick={() => { setEditing(r); setShowForm(true); }} aria-label={`Edit ${r.name}`}
                className="h-8 w-8 grid place-items-center rounded-md hover:bg-accent inline-block">
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
          <h1 className="text-2xl lg:text-3xl font-semibold tracking-tight">Clients</h1>
          <p className="text-sm text-muted-foreground">
            Tenants you let units to — companies and individuals, with their CR/QID and documents.
          </p>
        </div>
        <Can perm="client.create">
          <button
            onClick={() => { setEditing(null); setShowForm(true); }}
            className="inline-flex h-9 items-center gap-2 rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground hover:bg-primary/90"
          >
            <Plus className="h-4 w-4" /> New client
          </button>
        </Can>
      </div>

      <div className="glass rounded-xl p-4">
        <div className="flex items-center gap-2 flex-wrap">
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && listQuery.refetch()}
            placeholder="Search code, name (English or Arabic), CR/QID, mobile…"
            className="h-9 w-64 shrink-0 rounded-md border border-input bg-card/60 px-3 text-sm"
          />
          <select className={selectClass + " !w-auto shrink-0"} value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">All statuses</option>
            <option value="active">Active</option>
            <option value="inactive">Inactive</option>
            <option value="blacklisted">Blacklisted</option>
          </select>
          <label className="inline-flex items-center gap-1.5 text-xs text-muted-foreground shrink-0 whitespace-nowrap">
            <input type="checkbox" checked={showDeactivated} onChange={(e) => setShowDeactivated(e.target.checked)} />
            Show deactivated
          </label>
          <button onClick={() => listQuery.refetch()} className="h-9 shrink-0 rounded-md border border-border bg-card/60 px-3 text-sm hover:bg-accent">
            Search
          </button>
        </div>
      </div>

      <DataTable columns={columns} data={rows} loading={listQuery.isLoading} emptyMessage="No clients yet" maxBodyHeight="65vh"
        manualPagination pageCount={meta?.total_pages ?? 0} totalCount={meta?.total_count}
        pagination={pagination} onPaginationChange={setPagination} />

      <ClientDialog
        open={showForm}
        editing={editing}
        onClose={() => setShowForm(false)}
        onSaved={() => { setShowForm(false); invalidate(); }}
      />

      <Modal
        open={Boolean(docsFor)}
        onClose={() => setDocsFor(null)}
        title={docsFor ? `Documents — ${docsFor.name}` : ""}
        size="lg"
      >
        {docsFor && <AttachmentsTab entityType="client" entityId={docsFor.id} />}
      </Modal>
    </div>
  );
}

function ClientDialog({ open, editing, onClose, onSaved }: {
  open: boolean; editing: Client | null; onClose: () => void; onSaved: () => void;
}) {
  const [form, setForm] = useState<Partial<Client>>({});
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) {
      setForm(editing ?? { status: "active", client_type: "company" } as Partial<Client>);
    }
  }, [editing, open]);

  const set = <K extends keyof Client>(k: K, v: Client[K] | null | undefined) =>
    setForm((f) => ({ ...f, [k]: v }));

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      // Send only what the API accepts; blank strings become null so a
      // cleared field actually clears.
      const payload: Record<string, unknown> = {};
      const fields: (keyof Client)[] = [
        "name", "name_ar", "client_type", "contact_person", "mobile", "alt_mobile",
        "email", "address", "qid_cr_number", "qid_cr_expiry_date",
        "signatory_name", "signatory_name_ar", "signatory_id_number",
        "signatory_title", "signatory_mobile",
        "status", "remarks",
      ];
      for (const k of fields) {
        const v = form[k];
        if (v === undefined) continue;
        payload[k] = v === "" ? null : v;
      }

      if (editing) {
        const resp = await api.put(`/clients/${editing.id}`, payload);
        toast.success(`Client ${resp.data?.data?.code ?? editing.code} updated`);
      } else {
        const resp = await api.post("/clients", payload);
        toast.success(`Client ${resp.data?.data?.code ?? ""} created`);
      }
      onSaved();
    } catch (err: unknown) {
      toast.error("Save failed", errorMessage(err));
    } finally { setBusy(false); }
  };

  return (
    <Modal open={open} onClose={onClose} title={editing ? "Edit client" : "New client"} size="lg">
      <form onSubmit={save} className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <Field label="Name (English)" span={2}>
            <input required className={inputClass} value={String(form.name ?? "")}
              onChange={(e) => set("name", e.target.value)} />
          </Field>
          <Field label="Name (Arabic)" span={2}>
            <input className={inputClass} dir="rtl" value={String(form.name_ar ?? "")}
              onChange={(e) => set("name_ar", e.target.value)}
              placeholder="الاسم بالعربية" />
          </Field>
          <Field label="Type">
            <select className={selectClass} value={String(form.client_type ?? "company")}
              onChange={(e) => set("client_type", e.target.value)}>
              <option value="company">Company</option>
              <option value="individual">Individual</option>
            </select>
          </Field>
          <Field label="Status">
            <select className={selectClass} value={String(form.status ?? "active")}
              onChange={(e) => set("status", e.target.value)}>
              <option value="active">Active</option>
              <option value="inactive">Inactive</option>
              <option value="blacklisted">Blacklisted</option>
            </select>
          </Field>
          <Field label="CR / QID number">
            <input className={inputClass} value={String(form.qid_cr_number ?? "")}
              onChange={(e) => set("qid_cr_number", e.target.value)} />
          </Field>
          <Field label="CR / QID expiry">
            <input type="date" className={inputClass}
              value={String(form.qid_cr_expiry_date ?? "")}
              onChange={(e) => set("qid_cr_expiry_date", e.target.value)} />
          </Field>
          <Field label="Contact person" span={2}>
            <input className={inputClass} value={String(form.contact_person ?? "")}
              onChange={(e) => set("contact_person", e.target.value)} />
          </Field>
          <Field label="Mobile">
            <input className={inputClass} value={String(form.mobile ?? "")}
              onChange={(e) => set("mobile", e.target.value)} />
          </Field>
          <Field label="Alternate mobile">
            <input className={inputClass} value={String(form.alt_mobile ?? "")}
              onChange={(e) => set("alt_mobile", e.target.value)} />
          </Field>
          <Field label="Email" span={2}>
            <input type="email" className={inputClass} value={String(form.email ?? "")}
              onChange={(e) => set("email", e.target.value)} />
          </Field>
          <Field label="Address" span={2}>
            <textarea className={textareaClass} value={String(form.address ?? "")}
              onChange={(e) => set("address", e.target.value)} />
          </Field>
        </div>

        <div className="pt-1 border-t border-border">
          <div className="text-xs font-medium text-muted-foreground pt-2 pb-1">
            Signatory — required to generate a rental agreement for this client
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
          <textarea className={textareaClass} value={String(form.remarks ?? "")}
            onChange={(e) => set("remarks", e.target.value)} />
        </Field>

        <div className="text-xs text-muted-foreground">
          Contracts and unit allocation are added from the client&apos;s contract screen (Phase 2).
          Upload CR / QID copies from the paperclip button on the list.
        </div>

        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={onClose} className="h-9 rounded-md border border-border bg-card/60 px-3 text-sm">
            Cancel
          </button>
          <button type="submit" disabled={busy}
            className="h-9 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-60">
            {busy ? "Saving…" : editing ? "Save changes" : "Create client"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
