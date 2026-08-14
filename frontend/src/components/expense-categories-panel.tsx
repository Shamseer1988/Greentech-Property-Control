"use client";

import { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { ColumnDef, PaginationState } from "@tanstack/react-table";
import { Plus, Pencil, Power } from "lucide-react";
import { api } from "@/lib/api";
import { keys } from "@/lib/query-keys";
import { Can } from "@/components/can";
import { DataTable } from "@/components/ui/data-table";
import { Modal, Field, inputClass, selectClass } from "@/components/ui/dialog";
import { toast, errorMessage } from "@/components/ui/toast";

type Category = {
  id: number; code: string; name: string; kind: string;
  is_property_wise: boolean; is_active: boolean; remarks: string | null;
};

const KIND_LABEL: Record<string, string> = {
  direct: "Property cost (direct)",
  indirect: "Company overhead (indirect)",
  income: "Income",
};

/** Settings → Expense categories — the categories that drive property
 *  P&L and the accounting import. Sequential `EX-0001`-style codes are
 *  assigned server-side on create; existing seeded categories (RENT_PAID,
 *  OTHER_INCOME, …) keep their own codes since P&L/report logic and the
 *  import auto-mapper compare against them literally. */
export function ExpenseCategoriesPanel() {
  const qc = useQueryClient();
  const [showDeactivated, setShowDeactivated] = useState(false);
  const [showNew, setShowNew] = useState(false);
  const [newForm, setNewForm] = useState({ name: "", kind: "indirect", is_property_wise: false });
  const [editing, setEditing] = useState<Category | null>(null);
  const [busyId, setBusyId] = useState<number | "new" | null>(null);
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 25 });

  useEffect(() => { setPagination((p) => ({ ...p, pageIndex: 0 })); }, [showDeactivated]);

  const listQuery = useQuery({
    queryKey: keys.expenseCategories.list({ showDeactivated, ...pagination }),
    queryFn: async () => {
      const params: Record<string, string | number> = {
        page: pagination.pageIndex + 1, per_page: pagination.pageSize,
      };
      if (!showDeactivated) params.active_only = 1;
      const resp = await api.get("/expenses/categories", { params });
      return resp.data as { data: Category[]; meta: { total_count: number; total_pages: number } };
    },
    placeholderData: (prev) => prev,
  });
  const rows = listQuery.data?.data ?? [];
  const meta = listQuery.data?.meta;

  const invalidate = () => qc.invalidateQueries({ queryKey: keys.expenseCategories.all() });

  const createCategory = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newForm.name.trim()) return;
    setBusyId("new");
    try {
      const resp = await api.post("/expenses/categories", newForm);
      toast.success(`Category ${resp.data?.data?.code ?? ""} created`);
      setNewForm({ name: "", kind: "indirect", is_property_wise: false });
      setShowNew(false);
      invalidate();
    } catch (err: unknown) {
      toast.error("Could not create category", errorMessage(err));
    } finally { setBusyId(null); }
  };

  const toggleActive = async (c: Category) => {
    setBusyId(c.id);
    try {
      await api.patch(`/expenses/categories/${c.id}`, { is_active: !c.is_active });
      toast.success(c.is_active ? `${c.code} deactivated` : `${c.code} activated`);
      invalidate();
    } catch (err: unknown) {
      toast.error("Could not update category", errorMessage(err));
    } finally { setBusyId(null); }
  };

  const columns = useMemo<ColumnDef<Category, unknown>[]>(() => [
    { accessorKey: "code", header: "Code", cell: (c) => <span className="font-mono text-xs">{c.getValue<string>()}</span> },
    { accessorKey: "name", header: "Name" },
    {
      accessorKey: "kind", header: "Kind",
      cell: (c) => <span className="text-xs text-muted-foreground">{KIND_LABEL[c.getValue<string>()] ?? c.getValue<string>()}</span>,
    },
    {
      accessorKey: "is_property_wise", header: "Property-wise",
      cell: (c) => <span className="text-xs">{c.getValue<boolean>() ? "Yes" : "—"}</span>,
    },
    {
      accessorKey: "is_active", header: "Active",
      cell: (c) => {
        const active = c.getValue<boolean>();
        return (
          <span className={"rounded-full px-2 py-0.5 text-xs " +
            (active ? "bg-emerald-500/10 text-emerald-600" : "bg-muted text-muted-foreground")}>
            {active ? "Active" : "Inactive"}
          </span>
        );
      },
    },
    {
      id: "actions", header: "", enableSorting: false,
      cell: (c) => {
        const r = c.row.original;
        return (
          <Can perm="expense.manage">
            <div className="flex items-center justify-end gap-1">
              <button type="button" onClick={() => setEditing(r)}
                aria-label={`Edit ${r.name}`}
                className="h-8 w-8 grid place-items-center rounded-md hover:bg-accent">
                <Pencil className="h-3.5 w-3.5" />
              </button>
              <button type="button" onClick={() => toggleActive(r)} disabled={busyId === r.id}
                aria-label={r.is_active ? `Deactivate ${r.name}` : `Activate ${r.name}`}
                title={r.is_active ? "Deactivate" : "Activate"}
                className={"h-8 w-8 grid place-items-center rounded-md hover:bg-accent disabled:opacity-40 " +
                  (r.is_active ? "text-emerald-600" : "text-muted-foreground")}>
                <Power className="h-3.5 w-3.5" />
              </button>
            </div>
          </Can>
        );
      },
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
  ], [busyId]);

  return (
    <div className="rounded-lg border border-border bg-card/40 p-3 space-y-3">
      <div className="flex justify-between items-center gap-2 flex-wrap">
        <div>
          <div className="text-sm font-medium">Expense categories</div>
          <p className="text-xs text-muted-foreground">
            Property costs feed a property&apos;s P&amp;L; company overhead stays at company level.
          </p>
        </div>
        <Can perm="expense.manage">
          <div className="flex items-center gap-3">
            <label className="inline-flex items-center gap-1.5 text-xs text-muted-foreground whitespace-nowrap">
              <input type="checkbox" checked={showDeactivated} onChange={(e) => setShowDeactivated(e.target.checked)} />
              Show deactivated
            </label>
            <button type="button" onClick={() => setShowNew((v) => !v)}
              className="inline-flex h-8 items-center gap-1.5 rounded-md border border-border bg-card/60 px-2.5 text-xs hover:bg-accent">
              <Plus className="h-3.5 w-3.5" /> New category
            </button>
          </div>
        </Can>
      </div>

      {showNew && (
        <form onSubmit={createCategory} className="rounded-lg border border-border bg-card/40 p-3 grid grid-cols-2 gap-2">
          <Field label="Name" span={2}>
            <input required className={inputClass} value={newForm.name}
              onChange={(e) => setNewForm((f) => ({ ...f, name: e.target.value }))} />
          </Field>
          <Field label="Kind">
            <select className={selectClass} value={newForm.kind}
              onChange={(e) => setNewForm((f) => ({ ...f, kind: e.target.value }))}>
              <option value="direct">Property cost (direct)</option>
              <option value="indirect">Company overhead (indirect)</option>
              <option value="income">Income</option>
            </select>
          </Field>
          <Field label="Property-wise">
            <label className="flex items-center gap-2 h-9">
              <input type="checkbox" checked={newForm.is_property_wise}
                onChange={(e) => setNewForm((f) => ({ ...f, is_property_wise: e.target.checked }))} />
              <span className="text-sm">Should name a property</span>
            </label>
          </Field>
          <div className="col-span-2 flex justify-end">
            <button type="submit" disabled={busyId === "new"}
              className="h-9 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground disabled:opacity-60">
              {busyId === "new" ? "Creating…" : "Create"}
            </button>
          </div>
        </form>
      )}

      <DataTable columns={columns} data={rows} loading={listQuery.isLoading}
        emptyMessage="No expense categories" maxBodyHeight="55vh"
        manualPagination pageCount={meta?.total_pages ?? 0} totalCount={meta?.total_count}
        pagination={pagination} onPaginationChange={setPagination} />

      <EditCategoryDialog category={editing} onClose={() => setEditing(null)}
        onSaved={() => { setEditing(null); invalidate(); }} />
    </div>
  );
}

function EditCategoryDialog({ category, onClose, onSaved }: {
  category: Category | null; onClose: () => void; onSaved: () => void;
}) {
  const [form, setForm] = useState({ name: "", kind: "indirect", is_property_wise: false, remarks: "" });
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (category) {
      setForm({
        name: category.name, kind: category.kind,
        is_property_wise: category.is_property_wise, remarks: category.remarks ?? "",
      });
    }
  }, [category]);

  if (!category) return <Modal open={false} onClose={onClose} title="">{null}</Modal>;

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api.patch(`/expenses/categories/${category.id}`, form);
      toast.success(`${category.code} updated`);
      onSaved();
    } catch (err: unknown) {
      toast.error("Could not update category", errorMessage(err));
    } finally { setBusy(false); }
  };

  return (
    <Modal open onClose={onClose} title={`Edit — ${category.code}`}>
      <form onSubmit={save} className="space-y-3">
        <Field label="Name">
          <input required className={inputClass} value={form.name}
            onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Kind">
            <select className={selectClass} value={form.kind}
              onChange={(e) => setForm((f) => ({ ...f, kind: e.target.value }))}>
              <option value="direct">Property cost (direct)</option>
              <option value="indirect">Company overhead (indirect)</option>
              <option value="income">Income</option>
            </select>
          </Field>
          <Field label="Property-wise">
            <label className="flex items-center gap-2 h-9">
              <input type="checkbox" checked={form.is_property_wise}
                onChange={(e) => setForm((f) => ({ ...f, is_property_wise: e.target.checked }))} />
              <span className="text-sm">Should name a property</span>
            </label>
          </Field>
        </div>
        <Field label="Remarks">
          <input className={inputClass} value={form.remarks}
            onChange={(e) => setForm((f) => ({ ...f, remarks: e.target.value }))} />
        </Field>
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
