"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Upload, Wallet, ListTree, XCircle, Link2, Settings2 } from "lucide-react";
import { api } from "@/lib/api";
import { Can } from "@/components/can";
import { Modal, Field, inputClass, selectClass, textareaClass } from "@/components/ui/dialog";
import { toast, errorMessage } from "@/components/ui/toast";
import { ImportWizard } from "@/components/import-wizard";
import { money } from "@/lib/contract-types";
import { keys } from "@/lib/query-keys";

type Category = {
  id: number; code: string; name: string; kind: string;
  is_property_wise: boolean; is_active: boolean;
};
type Property = { id: number; code: string; name: string };
type Landlord = { id: number; code: string; name: string };

type Expense = {
  id: number;
  period_month: string;
  amount: number;
  source: string;
  ledger_name: string | null;
  status: string;
  void_reason: string | null;
  reference: string | null;
  remarks: string | null;
  category?: { id: number; name: string; kind: string };
  property?: { id: number; code: string; name: string };
};

type Payment = {
  id: number;
  voucher_number: string;
  period_month: string;
  payment_date: string;
  amount: number;
  mode: string;
  reference: string | null;
  status: string;
  void_reason: string | null;
  landlord?: { id: number; name: string };
  property?: { id: number; code: string; name: string };
};

type Tab = "expenses" | "payments" | "imports";

function currentMonth() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

type ExpensesPageData = {
  expenses: Expense[]; expenseTotal: number;
  payments: Payment[]; paymentTotal: number;
  batches: Record<string, unknown>[];
  categories: Category[]; properties: Property[]; landlords: Landlord[];
};

export default function ExpensesPage() {
  const qc = useQueryClient();
  const [tab, setTab] = useState<Tab>("expenses");
  const [month, setMonth] = useState(currentMonth());
  const [showExpense, setShowExpense] = useState(false);
  const [showPayment, setShowPayment] = useState(false);
  const [showImport, setShowImport] = useState(false);
  const [showVoidedExpenses, setShowVoidedExpenses] = useState(false);
  const [showVoidedPayments, setShowVoidedPayments] = useState(false);
  const [allocating, setAllocating] = useState<Expense | null>(null);

  const filters = { month, showVoidedExpenses, showVoidedPayments };
  const pageQuery = useQuery({
    queryKey: keys.expenses.list(filters),
    queryFn: async (): Promise<ExpensesPageData> => {
      const [e, p, b, c, pr, l] = await Promise.all([
        api.get("/expenses", { params: {
          month: `${month}-01`, ...(showVoidedExpenses ? {} : { status: "posted" }) } }),
        api.get("/expenses/landlord-payments", { params: {
          month: `${month}-01`, ...(showVoidedPayments ? {} : { status: "posted" }) } }),
        api.get("/expenses/import/batches"),
        api.get("/expenses/categories"),
        api.get("/properties"),
        api.get("/landlords"),
      ]);
      return {
        expenses: e.data?.data ?? [], expenseTotal: e.data?.meta?.total ?? 0,
        payments: p.data?.data ?? [], paymentTotal: p.data?.meta?.total ?? 0,
        batches: b.data?.data ?? [],
        categories: c.data?.data ?? [], properties: pr.data?.data ?? [], landlords: l.data?.data ?? [],
      };
    },
  });
  const load = () => qc.invalidateQueries({ queryKey: keys.expenses.all() });
  const loading = pageQuery.isLoading;
  const { expenses = [], payments = [], batches = [], categories = [], properties = [], landlords = [],
          expenseTotal = 0, paymentTotal = 0 } = pageQuery.data ?? {};

  const activeCategories = categories.filter((c) => c.is_active);
  const unallocated = expenses.filter((e) => !e.property && e.category?.kind === "direct" && e.status === "posted");

  const tabs: { key: Tab; label: string; icon: typeof Wallet }[] = [
    { key: "expenses", label: `Expenses (${expenses.length})`, icon: ListTree },
    { key: "payments", label: `Landlord payments (${payments.length})`, icon: Wallet },
    { key: "imports", label: "Imports", icon: Upload },
  ];

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-end justify-between flex-wrap gap-2">
        <div>
          <h1 className="text-2xl lg:text-3xl font-semibold tracking-tight">Expenses</h1>
          <p className="text-sm text-muted-foreground">
            Property costs, landlord rent paid, and the month-end import from your
            accounting software.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <input type="month" className={inputClass + " w-auto"} value={month}
            onChange={(e) => setMonth(e.target.value)} />
          <Can perm="expense.manage">
            <Link href="/settings?tab=expense"
              className="inline-flex h-9 items-center gap-2 rounded-md border border-border bg-card/60 px-3 text-sm hover:bg-accent">
              <Settings2 className="h-4 w-4" /> Manage categories
            </Link>
          </Can>
          <Can perm="expense.import">
            <button onClick={() => setShowImport(true)}
              className="inline-flex h-9 items-center gap-2 rounded-md border border-border bg-card/60 px-3 text-sm hover:bg-accent">
              <Upload className="h-4 w-4" /> Import P&amp;L
            </button>
          </Can>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        <Stat label="Expenses this month" value={money(expenseTotal)} />
        <Stat label="Landlord rent paid" value={money(paymentTotal)} />
        <Stat label="Unallocated direct costs" value={String(unallocated.length)}
          tone={unallocated.length > 0 ? "amber" : undefined}
          sub={unallocated.length > 0 ? "not yet on a property" : "all allocated"} />
      </div>

      <div className="flex border-b border-border overflow-x-auto">
        {tabs.map(({ key, label, icon: Icon }) => (
          <button key={key} onClick={() => setTab(key)}
            className={
              "px-4 py-2 text-sm font-medium border-b-2 transition-colors inline-flex items-center gap-2 " +
              (tab === key ? "border-primary text-primary" : "border-transparent text-muted-foreground hover:text-foreground")
            }>
            <Icon className="h-4 w-4" /> {label}
          </button>
        ))}
      </div>

      {tab === "expenses" && (
        <>
          <div className="flex justify-between items-center">
            <label className="inline-flex items-center gap-1.5 text-xs text-muted-foreground whitespace-nowrap">
              <input type="checkbox" checked={showVoidedExpenses} onChange={(e) => setShowVoidedExpenses(e.target.checked)} />
              Show voided
            </label>
            <Can perm="expense.manage">
              <button onClick={() => setShowExpense(true)}
                className="inline-flex h-9 items-center gap-2 rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground hover:bg-primary/90">
                <Plus className="h-4 w-4" /> Record expense
              </button>
            </Can>
          </div>
          <div className="glass rounded-xl overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-xs text-muted-foreground border-b border-border">
                <tr>
                  <th className="py-2 px-3">Category</th>
                  <th className="py-2 px-3">Property</th>
                  <th className="py-2 px-3">Source</th>
                  <th className="py-2 px-3 text-right">Amount</th>
                  <th className="py-2 px-3">Status</th>
                  <th className="py-2 px-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr><td colSpan={6} className="py-10 text-center text-muted-foreground">Loading…</td></tr>
                ) : expenses.length === 0 ? (
                  <tr><td colSpan={6} className="py-10 text-center text-muted-foreground">
                    No expenses for this month. Import the accounting P&amp;L or record one manually.
                  </td></tr>
                ) : expenses.map((e) => (
                  <tr key={e.id} className={"border-b border-border/60 " + (e.status === "voided" ? "opacity-60" : "")}>
                    <td className={"py-2 px-3 " + (e.status === "voided" ? "line-through" : "")}>
                      {e.category?.name}
                      {e.ledger_name && (
                        <div className="text-[11px] text-muted-foreground font-mono">{e.ledger_name}</div>
                      )}
                    </td>
                    <td className="py-2 px-3">
                      {e.property ? e.property.name : (
                        <span className={e.category?.kind === "direct"
                          ? "text-amber-600 text-xs" : "text-muted-foreground text-xs"}>
                          {e.category?.kind === "direct" ? "unallocated" : "company"}
                        </span>
                      )}
                    </td>
                    <td className="py-2 px-3 capitalize text-xs text-muted-foreground">{e.source}</td>
                    <td className={"py-2 px-3 text-right font-medium " + (e.status === "voided" ? "line-through" : "")}>
                      {money(e.amount)}
                    </td>
                    <td className="py-2 px-3">
                      <span className={
                        "rounded-full px-2 py-0.5 text-xs capitalize " +
                        (e.status === "voided" ? "bg-rose-500/10 text-rose-600"
                          : "bg-emerald-500/10 text-emerald-600")}>
                        {e.status}
                      </span>
                      {e.void_reason && (
                        <div className="text-[11px] text-muted-foreground">{e.void_reason}</div>
                      )}
                    </td>
                    <td className="py-2 px-3 text-right whitespace-nowrap">
                      {e.status === "posted" && (
                        <Can perm="expense.manage">
                          {e.category?.kind === "direct" && (
                            <button onClick={() => setAllocating(e)} title="Allocate to a property"
                              className="h-8 w-8 grid place-items-center rounded-md hover:bg-accent inline-block">
                              <Link2 className="h-3.5 w-3.5" />
                            </button>
                          )}
                          <ExpenseVoidButton expense={e} onDone={load} />
                        </Can>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {tab === "payments" && (
        <>
          <div className="flex justify-between items-center">
            <label className="inline-flex items-center gap-1.5 text-xs text-muted-foreground whitespace-nowrap">
              <input type="checkbox" checked={showVoidedPayments} onChange={(e) => setShowVoidedPayments(e.target.checked)} />
              Show voided
            </label>
            <Can perm="expense.manage">
              <button onClick={() => setShowPayment(true)}
                className="inline-flex h-9 items-center gap-2 rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground hover:bg-primary/90">
                <Plus className="h-4 w-4" /> Pay landlord
              </button>
            </Can>
          </div>
          <div className="glass rounded-xl overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-xs text-muted-foreground border-b border-border">
                <tr>
                  <th className="py-2 px-3">Voucher</th>
                  <th className="py-2 px-3">Landlord</th>
                  <th className="py-2 px-3">Property</th>
                  <th className="py-2 px-3">Paid</th>
                  <th className="py-2 px-3 text-right">Amount</th>
                  <th className="py-2 px-3">Status</th>
                  <th className="py-2 px-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {payments.length === 0 ? (
                  <tr><td colSpan={7} className="py-10 text-center text-muted-foreground">
                    No landlord payments recorded for this month.
                  </td></tr>
                ) : payments.map((p) => (
                  <tr key={p.id} className="border-b border-border/60">
                    <td className="py-2 px-3 font-mono text-xs">{p.voucher_number}</td>
                    <td className="py-2 px-3">{p.landlord?.name}</td>
                    <td className="py-2 px-3 text-xs">{p.property?.name}</td>
                    <td className="py-2 px-3 font-mono text-xs">{p.payment_date}</td>
                    <td className="py-2 px-3 text-right font-medium">{money(p.amount)}</td>
                    <td className="py-2 px-3">
                      <span className={
                        "rounded-full px-2 py-0.5 text-xs capitalize " +
                        (p.status === "voided" ? "bg-rose-500/10 text-rose-600"
                          : "bg-emerald-500/10 text-emerald-600")}>
                        {p.status}
                      </span>
                      {p.void_reason && (
                        <div className="text-[11px] text-muted-foreground">{p.void_reason}</div>
                      )}
                    </td>
                    <td className="py-2 px-3 text-right">
                      {p.status === "posted" && (
                        <Can perm="expense.manage">
                          <VoidButton payment={p} onDone={load} />
                        </Can>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {tab === "imports" && (
        <div className="glass rounded-xl overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-muted-foreground border-b border-border">
              <tr>
                <th className="py-2 px-3">Batch</th>
                <th className="py-2 px-3">File</th>
                <th className="py-2 px-3">Period</th>
                <th className="py-2 px-3 text-right">Lines</th>
                <th className="py-2 px-3 text-right">Net profit (file)</th>
                <th className="py-2 px-3">Status</th>
              </tr>
            </thead>
            <tbody>
              {batches.length === 0 ? (
                <tr><td colSpan={6} className="py-10 text-center text-muted-foreground">
                  Nothing imported yet.
                </td></tr>
              ) : batches.map((b) => (
                <tr key={String(b.id)} className="border-b border-border/60">
                  <td className="py-2 px-3 font-mono text-xs">{String(b.batch_number)}</td>
                  <td className="py-2 px-3 text-xs">{String(b.original_name)}</td>
                  <td className="py-2 px-3 font-mono text-xs">
                    {String(b.period_from)} → {String(b.period_to)}
                  </td>
                  <td className="py-2 px-3 text-right">{String(b.lines_imported)}</td>
                  <td className="py-2 px-3 text-right">
                    {b.reported_net_profit ? money(Number(b.reported_net_profit)) : "—"}
                  </td>
                  <td className="py-2 px-3">
                    <span className={
                      "rounded-full px-2 py-0.5 text-xs capitalize " +
                      (b.status === "voided" ? "bg-rose-500/10 text-rose-600"
                        : "bg-emerald-500/10 text-emerald-600")}>
                      {String(b.status)}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <ExpenseDialog open={showExpense} categories={activeCategories} properties={properties}
        month={month} onClose={() => setShowExpense(false)}
        onSaved={async () => { setShowExpense(false); await load(); }} />

      <PaymentDialog open={showPayment} landlords={landlords} properties={properties}
        month={month} onClose={() => setShowPayment(false)}
        onSaved={async () => { setShowPayment(false); await load(); }} />

      <AllocateDialog expense={allocating} properties={properties}
        onClose={() => setAllocating(null)}
        onSaved={async () => { setAllocating(null); await load(); }} />

      <ImportWizard open={showImport} properties={properties} categories={activeCategories}
        onClose={() => setShowImport(false)}
        onImported={async () => { setShowImport(false); await load(); }} />
    </div>
  );
}

function Stat({ label, value, sub, tone }: {
  label: string; value: string; sub?: string; tone?: "amber";
}) {
  return (
    <div className="glass rounded-xl p-4">
      <div className="text-sm text-muted-foreground">{label}</div>
      <div className={"mt-1 text-2xl font-semibold " + (tone === "amber" ? "text-amber-600" : "")}>
        {value}
      </div>
      {sub && <div className="mt-1 text-xs text-muted-foreground">{sub}</div>}
    </div>
  );
}

function VoidButton({ payment, onDone }: { payment: Payment; onDone: () => void }) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api.post(`/expenses/landlord-payments/${payment.id}/void`, { reason });
      toast.success(`Voucher ${payment.voucher_number} voided`);
      setOpen(false);
      onDone();
    } catch (err: unknown) {
      toast.error("Could not void", errorMessage(err));
    } finally { setBusy(false); }
  };

  return (
    <>
      <button onClick={() => setOpen(true)} title="Void voucher"
        className="h-8 w-8 grid place-items-center rounded-md hover:bg-destructive/10 text-destructive inline-block">
        <XCircle className="h-3.5 w-3.5" />
      </button>
      <Modal open={open} onClose={() => setOpen(false)}
        title={`Void ${payment.voucher_number}`}>
        <form onSubmit={submit} className="space-y-3">
          <Field label="Reason">
            <input required className={inputClass} value={reason}
              onChange={(e) => setReason(e.target.value)} />
          </Field>
          <div className="flex justify-end gap-2 pt-2">
            <button type="button" onClick={() => setOpen(false)}
              className="h-9 rounded-md border border-border bg-card/60 px-3 text-sm">Cancel</button>
            <button type="submit" disabled={busy || !reason.trim()}
              className="h-9 rounded-md bg-destructive px-4 text-sm font-medium text-destructive-foreground disabled:opacity-60">
              {busy ? "Voiding…" : "Void voucher"}
            </button>
          </div>
        </form>
      </Modal>
    </>
  );
}

function ExpenseDialog({ open, categories, properties, month, onClose, onSaved }: {
  open: boolean; categories: Category[]; properties: Property[]; month: string;
  onClose: () => void; onSaved: () => void;
}) {
  const [form, setForm] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (open) setForm({ period_month: `${month}-01` }); }, [open, month]);

  const set = (k: string, v: string) => setForm((f) => ({ ...f, [k]: v }));
  const category = categories.find((c) => String(c.id) === form.category_id);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api.post("/expenses", {
        category_id: Number(form.category_id),
        property_id: form.property_id ? Number(form.property_id) : null,
        period_month: form.period_month,
        amount: Number(form.amount),
        reference: form.reference || null,
        remarks: form.remarks || null,
      });
      toast.success("Expense recorded");
      onSaved();
    } catch (err: unknown) {
      toast.error("Could not record the expense", errorMessage(err));
    } finally { setBusy(false); }
  };

  return (
    <Modal open={open} onClose={onClose} title="Record expense">
      <form onSubmit={submit} className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <Field label="Category" span={2}>
            <select required className={selectClass} value={form.category_id ?? ""}
              onChange={(e) => set("category_id", e.target.value)}>
              <option value="">Select…</option>
              <optgroup label="Property costs">
                {categories.filter((c) => c.kind === "direct").map((c) => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </optgroup>
              <optgroup label="Company overhead">
                {categories.filter((c) => c.kind === "indirect").map((c) => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </optgroup>
            </select>
          </Field>
          <Field label="Property" span={2}>
            <select className={selectClass} value={form.property_id ?? ""}
              onChange={(e) => set("property_id", e.target.value)}>
              <option value="">— Company level —</option>
              {properties.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
            {category?.kind === "direct" && !form.property_id && (
              <div className="text-[11px] text-amber-600 mt-1">
                Property costs should name a property, or they can&apos;t reach its P&amp;L.
              </div>
            )}
          </Field>
          <Field label="Month">
            <input required type="date" className={inputClass} value={form.period_month ?? ""}
              onChange={(e) => set("period_month", e.target.value)} />
          </Field>
          <Field label="Amount">
            <input required type="number" step="0.01" className={inputClass}
              value={form.amount ?? ""} onChange={(e) => set("amount", e.target.value)} />
          </Field>
          <Field label="Reference" span={2}>
            <input className={inputClass} value={form.reference ?? ""}
              onChange={(e) => set("reference", e.target.value)} placeholder="Invoice / bill no." />
          </Field>
        </div>
        <Field label="Remarks">
          <textarea className={textareaClass} value={form.remarks ?? ""}
            onChange={(e) => set("remarks", e.target.value)} />
        </Field>
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={onClose}
            className="h-9 rounded-md border border-border bg-card/60 px-3 text-sm">Cancel</button>
          <button type="submit" disabled={busy}
            className="h-9 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground disabled:opacity-60">
            {busy ? "Saving…" : "Record expense"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function PaymentDialog({ open, landlords, properties, month, onClose, onSaved }: {
  open: boolean; landlords: Landlord[]; properties: Property[]; month: string;
  onClose: () => void; onSaved: () => void;
}) {
  const [form, setForm] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (open) setForm({ period_month: `${month}-01`, mode: "cheque",
                        payment_date: new Date().toISOString().slice(0, 10) });
  }, [open, month]);

  const set = (k: string, v: string) => setForm((f) => ({ ...f, [k]: v }));

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      const resp = await api.post("/expenses/landlord-payments", {
        landlord_id: Number(form.landlord_id),
        property_id: Number(form.property_id),
        period_month: form.period_month,
        payment_date: form.payment_date,
        amount: Number(form.amount),
        mode: form.mode,
        reference: form.reference || null,
      });
      toast.success(`Voucher ${resp.data?.data?.voucher_number ?? ""} posted`);
      onSaved();
    } catch (err: unknown) {
      toast.error("Could not post the payment", errorMessage(err));
    } finally { setBusy(false); }
  };

  return (
    <Modal open={open} onClose={onClose} title="Pay landlord">
      <form onSubmit={submit} className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <Field label="Landlord" span={2}>
            <select required className={selectClass} value={form.landlord_id ?? ""}
              onChange={(e) => set("landlord_id", e.target.value)}>
              <option value="">Select…</option>
              {landlords.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
            </select>
          </Field>
          <Field label="Property" span={2}>
            <select required className={selectClass} value={form.property_id ?? ""}
              onChange={(e) => set("property_id", e.target.value)}>
              <option value="">Select…</option>
              {properties.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </Field>
          <Field label="Rent month">
            <input required type="date" className={inputClass} value={form.period_month ?? ""}
              onChange={(e) => set("period_month", e.target.value)} />
          </Field>
          <Field label="Paid on">
            <input required type="date" className={inputClass} value={form.payment_date ?? ""}
              onChange={(e) => set("payment_date", e.target.value)} />
          </Field>
          <Field label="Amount">
            <input required type="number" step="0.01" className={inputClass}
              value={form.amount ?? ""} onChange={(e) => set("amount", e.target.value)} />
          </Field>
          <Field label="Mode">
            <select className={selectClass} value={form.mode ?? "cheque"}
              onChange={(e) => set("mode", e.target.value)}>
              <option value="cheque">Cheque</option>
              <option value="cash">Cash</option>
              <option value="online">Online</option>
            </select>
          </Field>
          <Field label="Reference" span={2}>
            <input className={inputClass} value={form.reference ?? ""}
              onChange={(e) => set("reference", e.target.value)} placeholder="Cheque no." />
          </Field>
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={onClose}
            className="h-9 rounded-md border border-border bg-card/60 px-3 text-sm">Cancel</button>
          <button type="submit" disabled={busy}
            className="h-9 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground disabled:opacity-60">
            {busy ? "Posting…" : "Post voucher"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function AllocateDialog({ expense, properties, onClose, onSaved }: {
  expense: Expense | null; properties: Property[]; onClose: () => void; onSaved: () => void;
}) {
  const [propertyId, setPropertyId] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { setPropertyId(expense?.property ? String(expense.property.id) : ""); }, [expense]);

  if (!expense) return <Modal open={false} onClose={onClose} title="">{null}</Modal>;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api.post(`/expenses/${expense.id}/allocate`, {
        property_id: propertyId ? Number(propertyId) : null,
      });
      toast.success("Expense allocated");
      onSaved();
    } catch (err: unknown) {
      toast.error("Could not allocate", errorMessage(err));
    } finally { setBusy(false); }
  };

  return (
    <Modal open onClose={onClose} title="Allocate to a property">
      <form onSubmit={submit} className="space-y-3">
        <div className="rounded-lg border border-border bg-card/40 p-3 text-xs">
          <div>{expense.category?.name} — <strong>{money(expense.amount)}</strong></div>
          {expense.ledger_name && (
            <div className="text-muted-foreground font-mono mt-1">{expense.ledger_name}</div>
          )}
        </div>
        <Field label="Property">
          <select className={selectClass} value={propertyId}
            onChange={(e) => setPropertyId(e.target.value)}>
            <option value="">— Leave unallocated —</option>
            {properties.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </Field>
        <div className="text-xs text-muted-foreground">
          Allocating puts this cost into that property&apos;s profit &amp; loss for the month.
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={onClose}
            className="h-9 rounded-md border border-border bg-card/60 px-3 text-sm">Cancel</button>
          <button type="submit" disabled={busy}
            className="h-9 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground disabled:opacity-60">
            {busy ? "Saving…" : "Allocate"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function ExpenseVoidButton({ expense, onDone }: { expense: Expense; onDone: () => void }) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api.post(`/expenses/${expense.id}/void`, { reason });
      toast.success("Expense voided");
      setOpen(false);
      onDone();
    } catch (err: unknown) {
      toast.error("Could not void", errorMessage(err));
    } finally { setBusy(false); }
  };

  return (
    <>
      <button onClick={() => setOpen(true)} title="Void expense"
        className="h-8 w-8 grid place-items-center rounded-md hover:bg-destructive/10 text-destructive inline-block">
        <XCircle className="h-3.5 w-3.5" />
      </button>
      <Modal open={open} onClose={() => setOpen(false)}
        title={`Void ${expense.category?.name ?? "expense"} — ${money(expense.amount)}`}>
        <form onSubmit={submit} className="space-y-3">
          <div className="text-xs text-muted-foreground">
            Voiding doesn&apos;t delete this row — it stays visible, struck through, and drops
            out of the property P&amp;L. To correct the amount, void this one and record a fresh
            expense.
          </div>
          <Field label="Reason">
            <input required className={inputClass} value={reason}
              onChange={(e) => setReason(e.target.value)} />
          </Field>
          <div className="flex justify-end gap-2 pt-2">
            <button type="button" onClick={() => setOpen(false)}
              className="h-9 rounded-md border border-border bg-card/60 px-3 text-sm">Cancel</button>
            <button type="submit" disabled={busy || !reason.trim()}
              className="h-9 rounded-md bg-destructive px-4 text-sm font-medium text-destructive-foreground disabled:opacity-60">
              {busy ? "Voiding…" : "Void expense"}
            </button>
          </div>
        </form>
      </Modal>
    </>
  );
}

