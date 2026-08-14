"use client";

import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouteParams } from "@/lib/use-route-params";
import {
  ArrowLeft, FileText, DoorOpen, Banknote, History, Paperclip,
  Plus, XCircle, RefreshCw, MinusCircle, PlusCircle, CalendarOff, CalendarClock, Hourglass,
} from "lucide-react";
import { api } from "@/lib/api";
import { keys } from "@/lib/query-keys";
import { Can } from "@/components/can";
import { Modal, Field, inputClass, selectClass, textareaClass } from "@/components/ui/dialog";
import { toast, errorMessage } from "@/components/ui/toast";
import { AttachmentsTab } from "@/components/attachments-tab";
import { ChequeGrid } from "@/components/cheque-grid";
import type { Contract, AvailableUnit } from "@/lib/contract-types";
import { AMENDMENT_LABEL, MODE_LABEL, STATUS_TONE, money } from "@/lib/contract-types";

type TabKey = "overview" | "units" | "cheques" | "amendments" | "attachments";

export default function ContractDetail({ params }: { params: Promise<{ id: string }> }) {
  const { id } = useRouteParams(params);
  const qc = useQueryClient();
  const [tab, setTab] = useState<TabKey>("overview");
  const [action, setAction] = useState<null | "rent" | "free" | "add" | "remove" | "cancel" | "renew" | "dates">(null);

  const contractQuery = useQuery({
    queryKey: keys.contracts.detail(id),
    queryFn: async () => (await api.get(`/contracts/${id}`)).data.data as Contract,
  });
  const contract = contractQuery.data ?? null;
  const loading = contractQuery.isLoading;
  const load = () => qc.invalidateQueries({ queryKey: keys.contracts.detail(id) });

  if (loading || !contract) {
    return <div className="text-sm text-muted-foreground animate-pulse">Loading contract…</div>;
  }

  const isActive = contract.status === "active";
  const canCorrectDates = isActive || contract.status === "expired";
  const tabs: { key: TabKey; label: string; icon: typeof FileText }[] = [
    { key: "overview", label: "Overview", icon: FileText },
    { key: "units", label: `Units (${contract.units_count ?? 0})`, icon: DoorOpen },
    ...(contract.payment_mode === "cheque"
      ? [{ key: "cheques" as TabKey, label: `Cheques (${contract.cheques?.length ?? 0})`, icon: Banknote }]
      : []),
    { key: "amendments", label: `History (${contract.amendments?.length ?? 0})`, icon: History },
    { key: "attachments", label: "Documents", icon: Paperclip },
  ];

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <Link href="/contracts" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft className="h-3.5 w-3.5" /> Back to contracts
        </Link>
        <div className="mt-2 flex items-start justify-between flex-wrap gap-3">
          <div>
            <h1 className="text-2xl lg:text-3xl font-semibold tracking-tight">
              {contract.client?.name}
            </h1>
            <p className="text-sm text-muted-foreground">
              <span className="font-mono">{contract.contract_number}</span>
              {" · "}{contract.property?.name}
              {" · "}{MODE_LABEL[contract.payment_mode] ?? contract.payment_mode}
            </p>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <span className={"rounded-full px-3 py-1 text-xs capitalize " + (STATUS_TONE[contract.status] ?? "")}>
              {contract.status}
            </span>
            {isActive && (
              <>
                <Can perm="contract.amend">
                  <button onClick={() => setAction("rent")}
                    className="h-8 inline-flex items-center gap-1 rounded-md border border-border bg-card/60 px-2 text-xs hover:bg-accent">
                    <Banknote className="h-3.5 w-3.5" /> Change rent
                  </button>
                  <button onClick={() => setAction("free")}
                    className="h-8 inline-flex items-center gap-1 rounded-md border border-border bg-card/60 px-2 text-xs hover:bg-accent">
                    <CalendarOff className="h-3.5 w-3.5" /> Free months
                  </button>
                  <button onClick={() => setAction("add")}
                    className="h-8 inline-flex items-center gap-1 rounded-md border border-border bg-card/60 px-2 text-xs hover:bg-accent">
                    <PlusCircle className="h-3.5 w-3.5" /> Add units
                  </button>
                  <button onClick={() => setAction("remove")}
                    className="h-8 inline-flex items-center gap-1 rounded-md border border-border bg-card/60 px-2 text-xs hover:bg-accent">
                    <MinusCircle className="h-3.5 w-3.5" /> Release units
                  </button>
                </Can>
                <Can perm="contract.create">
                  <button onClick={() => setAction("renew")}
                    className="h-8 inline-flex items-center gap-1 rounded-md border border-border bg-card/60 px-2 text-xs hover:bg-accent">
                    <RefreshCw className="h-3.5 w-3.5" /> Renew
                  </button>
                </Can>
                <Can perm="contract.cancel">
                  <button onClick={() => setAction("cancel")}
                    className="h-8 inline-flex items-center gap-1 rounded-md border border-destructive/40 text-destructive px-2 text-xs hover:bg-destructive/10">
                    <XCircle className="h-3.5 w-3.5" /> Cancel
                  </button>
                </Can>
              </>
            )}
            {canCorrectDates && (
              <Can perm="contract.amend">
                <button onClick={() => setAction("dates")}
                  className="h-8 inline-flex items-center gap-1 rounded-md border border-border bg-card/60 px-2 text-xs hover:bg-accent">
                  <CalendarClock className="h-3.5 w-3.5" /> Correct dates
                </button>
              </Can>
            )}
          </div>
        </div>
      </div>

      {(contract.pending_approvals?.length ?? 0) > 0 && (
        <div className="rounded-xl border border-amber-500/40 bg-amber-500/5 p-4 space-y-2">
          <div className="text-sm font-medium inline-flex items-center gap-2 text-amber-700 dark:text-amber-500">
            <Hourglass className="h-4 w-4" />
            Waiting for approval — nothing below has changed yet
          </div>
          {contract.pending_approvals?.map((p) => (
            <div key={p.id} className="text-xs flex items-baseline gap-2 flex-wrap">
              <span className="font-mono text-muted-foreground">{p.transaction_number}</span>
              <span className="rounded-full bg-amber-500/10 px-2 py-0.5">{p.module_label}</span>
              <span className="text-muted-foreground">{p.summary}</span>
            </div>
          ))}
          <Can perm="approval.approve">
            <Link href="/approvals"
              className="inline-block text-xs text-primary hover:underline pt-1">
              Go to approvals →
            </Link>
          </Can>
        </div>
      )}

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

      {tab === "overview" && <Overview contract={contract} />}
      {tab === "units" && <UnitsTab contract={contract} />}
      {tab === "cheques" && <ChequeGrid contract={contract} onChanged={load} />}
      {tab === "amendments" && <AmendmentsTab contract={contract} />}
      {tab === "attachments" && (
        <AttachmentsTab entityType="client_contract" entityId={contract.id} />
      )}

      <AmendmentDialog
        action={action}
        contract={contract}
        onClose={() => setAction(null)}
        onDone={async () => { setAction(null); await load(); }}
      />
    </div>
  );
}

function Overview({ contract }: { contract: Contract }) {
  const Cell = ({ k, v }: { k: string; v: React.ReactNode }) => (
    <div>
      <div className="text-xs uppercase tracking-wide text-muted-foreground">{k}</div>
      <div className="text-sm font-medium">{v ?? "—"}</div>
    </div>
  );
  const days = Math.ceil((new Date(contract.expiry_date).getTime() - Date.now()) / 86400000);
  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
      <div className="glass rounded-xl p-4 lg:col-span-2 grid grid-cols-2 md:grid-cols-3 gap-4">
        <Cell k="Monthly rent" v={money(contract.monthly_rent)} />
        <Cell k="Payment mode" v={MODE_LABEL[contract.payment_mode] ?? contract.payment_mode} />
        <Cell k="Units held" v={contract.units_count ?? 0} />
        <Cell k="Start" v={<span className="font-mono text-xs">{contract.start_date}</span>} />
        <Cell k="Expiry" v={
          <span className={"font-mono text-xs " + (days < 0 ? "text-destructive" : days <= 60 ? "text-amber-600" : "")}>
            {contract.expiry_date}
          </span>
        } />
        <Cell k="Security deposit" v={money(contract.security_deposit)} />
        <Cell k="Opening balance" v={money(contract.opening_balance)} />
        {contract.cancellation_date && (
          <>
            <Cell k="Cancelled on" v={<span className="font-mono text-xs">{contract.cancellation_date}</span>} />
            <Cell k="Reason" v={contract.cancellation_reason} />
          </>
        )}
        {contract.remarks && (
          <div className="col-span-full">
            <div className="text-xs uppercase tracking-wide text-muted-foreground">Remarks</div>
            <div className="text-sm">{contract.remarks}</div>
          </div>
        )}
      </div>
      <div className="glass rounded-xl p-4 space-y-2">
        <div className="text-sm font-semibold">Term</div>
        <div className="text-3xl font-semibold">
          {days < 0 ? "Expired" : `${days}d`}
        </div>
        <div className="text-xs text-muted-foreground">
          {days < 0 ? `ended ${Math.abs(days)} days ago` : "remaining on this contract"}
        </div>
        {contract.renewed_to_id && (
          <Link href={`/contracts/${contract.renewed_to_id}`}
            className="text-xs text-primary hover:underline inline-block pt-2">
            Renewed as a new contract →
          </Link>
        )}
      </div>
    </div>
  );
}

function UnitsTab({ contract }: { contract: Contract }) {
  const rows = contract.units ?? [];
  return (
    <div className="glass rounded-xl overflow-x-auto">
      <div className="px-4 pt-3 text-xs text-muted-foreground">
        Units held as of {contract.units_as_of ?? "today"}. Releasing a unit closes its
        row — the history stays, so past months still show who held it.
      </div>
      <table className="w-full text-sm mt-2">
        <thead className="text-left text-xs text-muted-foreground border-b border-border">
          <tr>
            <th className="py-2 px-3">Unit</th>
            <th className="py-2 px-3">Type</th>
            <th className="py-2 px-3">Held from</th>
            <th className="py-2 px-3">Until</th>
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr><td colSpan={4} className="py-10 text-center text-muted-foreground">
              No units held.
            </td></tr>
          ) : rows.map((a) => (
            <tr key={a.id} className="border-b border-border/60">
              <td className="py-2 px-3 font-mono">{a.unit?.unit_number}</td>
              <td className="py-2 px-3 capitalize">{a.unit?.unit_type.replaceAll("_", " ")}</td>
              <td className="py-2 px-3 font-mono text-xs">{a.from_date}</td>
              <td className="py-2 px-3 font-mono text-xs">{a.to_date ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AmendmentsTab({ contract }: { contract: Contract }) {
  const rows = contract.amendments ?? [];
  return (
    <div className="glass rounded-xl overflow-x-auto">
      <div className="px-4 pt-3 text-xs text-muted-foreground">
        Every change is a dated amendment — nothing is overwritten, so any past month
        can be reproduced exactly.
      </div>
      <table className="w-full text-sm mt-2">
        <thead className="text-left text-xs text-muted-foreground border-b border-border">
          <tr>
            <th className="py-2 px-3">#</th>
            <th className="py-2 px-3">Amendment</th>
            <th className="py-2 px-3">Type</th>
            <th className="py-2 px-3">Effective</th>
            <th className="py-2 px-3">Detail</th>
            <th className="py-2 px-3">Reason</th>
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr><td colSpan={6} className="py-10 text-center text-muted-foreground">
              No amendments — the contract is as originally signed.
            </td></tr>
          ) : rows.map((a) => (
            <tr key={a.id} className="border-b border-border/60">
              <td className="py-2 px-3">{a.sequence}</td>
              <td className="py-2 px-3 font-mono text-xs">{a.amendment_number}</td>
              <td className="py-2 px-3">{AMENDMENT_LABEL[a.amendment_type] ?? a.amendment_type}</td>
              <td className="py-2 px-3 font-mono text-xs">{a.effective_date}</td>
              <td className="py-2 px-3 text-xs">
                {a.amendment_type === "rent_change" && (
                  <>{money(a.old_rent)} → <span className="font-medium">{money(a.new_rent)}</span></>
                )}
                {a.amendment_type === "free_months" && (
                  <>{a.free_months} month{a.free_months === 1 ? "" : "s"} from {a.free_from_month}</>
                )}
                {(a.amendment_type === "units_added" || a.amendment_type === "units_removed") && (
                  <>{a.unit_ids.length} unit{a.unit_ids.length === 1 ? "" : "s"}</>
                )}
                {a.amendment_type === "dates_correction" && (
                  <div className="space-y-0.5">
                    {a.old_start_date !== a.new_start_date && (
                      <div>start: {a.old_start_date} → <span className="font-medium">{a.new_start_date}</span></div>
                    )}
                    {a.old_expiry_date !== a.new_expiry_date && (
                      <div>expiry: {a.old_expiry_date} → <span className="font-medium">{a.new_expiry_date}</span></div>
                    )}
                  </div>
                )}
              </td>
              <td className="py-2 px-3 text-xs text-muted-foreground">{a.reason ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AmendmentDialog({ action, contract, onClose, onDone }: {
  action: null | "rent" | "free" | "add" | "remove" | "cancel" | "renew" | "dates";
  contract: Contract;
  onClose: () => void;
  onDone: () => void;
}) {
  const [form, setForm] = useState<Record<string, string>>({});
  const [picked, setPicked] = useState<Set<number>>(new Set());
  const [available, setAvailable] = useState<AvailableUnit[]>([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!action) return;
    setForm({});
    setPicked(new Set());
    if (action === "add") {
      api.get("/contracts/available-units", { params: { property_id: contract.property_id } })
        .then((r) => setAvailable((r.data.data ?? []).filter((u: AvailableUnit) => u.is_available)))
        .catch(() => setAvailable([]));
    }
  }, [action, contract.property_id]);

  if (!action) return <Modal open={false} onClose={onClose} title="">{null}</Modal>;

  const set = (k: string, v: string) => setForm((f) => ({ ...f, [k]: v }));
  const toggle = (id: number) => setPicked((prev) => {
    const next = new Set(prev);
    if (next.has(id)) next.delete(id); else next.add(id);
    return next;
  });

  const CONFIG = {
    rent: { title: "Change rent", verb: "Apply change" },
    free: { title: "Grant free months", verb: "Grant" },
    add: { title: "Add units to this contract", verb: "Add units" },
    remove: { title: "Release units", verb: "Release" },
    cancel: { title: "Cancel this contract", verb: "Cancel contract" },
    renew: { title: "Renew this contract", verb: "Renew" },
    dates: { title: "Correct contract dates", verb: "Save correction" },
  }[action];

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      const base = `/contracts/${contract.id}`;
      let resp;
      if (action === "rent") {
        resp = await api.post(`${base}/amendments/rent`, {
          new_rent: Number(form.new_rent), effective_date: form.effective_date,
          reason: form.reason || null,
        });
      } else if (action === "free") {
        resp = await api.post(`${base}/amendments/free-months`, {
          months: Number(form.months), from_month: form.from_month,
          reason: form.reason || null,
        });
      } else if (action === "add") {
        resp = await api.post(`${base}/amendments/add-units`, {
          unit_ids: [...picked], effective_date: form.effective_date,
          reason: form.reason || null,
        });
      } else if (action === "remove") {
        resp = await api.post(`${base}/amendments/remove-units`, {
          unit_ids: [...picked], effective_date: form.effective_date,
          reason: form.reason || null,
        });
      } else if (action === "cancel") {
        resp = await api.post(`${base}/cancel`, {
          effective_date: form.effective_date, reason: form.reason,
          remarks: form.remarks || null,
        });
      } else if (action === "renew") {
        resp = await api.post(`${base}/renew`, {
          new_start_date: form.new_start_date, new_expiry_date: form.new_expiry_date,
          new_monthly_rent: form.new_monthly_rent ? Number(form.new_monthly_rent) : null,
        });
      } else if (action === "dates") {
        resp = await api.post(`${base}/amendments/dates`, {
          new_start_date: form.new_start_date || null,
          new_expiry_date: form.new_expiry_date || null,
          reason: form.reason, remarks: form.remarks || null,
        });
      }
      // 202 means an approver has to agree first — don't tell the
      // operator it's done when the contract hasn't moved.
      if (resp?.status === 202) {
        toast.success("Sent for approval", resp.data?.message ?? "");
      } else {
        toast.success(`${CONFIG.title} — done`);
      }
      onDone();
    } catch (err: unknown) {
      toast.error("Could not apply", errorMessage(err));
    } finally { setBusy(false); }
  };

  const held = contract.units ?? [];
  const canSubmit =
    action === "rent" ? form.new_rent && form.effective_date
    : action === "free" ? form.months && form.from_month
    : action === "add" ? picked.size > 0 && form.effective_date
    : action === "remove" ? picked.size > 0 && picked.size < held.length && form.effective_date
    : action === "cancel" ? form.effective_date && form.reason
    : action === "dates" ? (form.new_start_date || form.new_expiry_date) && form.reason
    : form.new_start_date && form.new_expiry_date;

  return (
    <Modal open onClose={onClose} title={CONFIG.title}>
      <form onSubmit={submit} className="space-y-3">
        {action === "rent" && (
          <div className="grid grid-cols-2 gap-3">
            <Field label="Current rent">
              <input className={inputClass} value={money(contract.monthly_rent)} disabled />
            </Field>
            <Field label="New rent">
              <input required type="number" step="0.01" className={inputClass}
                value={form.new_rent ?? ""} onChange={(e) => set("new_rent", e.target.value)} />
            </Field>
            <Field label="Effective from" span={2}>
              <input required type="date" className={inputClass}
                value={form.effective_date ?? ""} onChange={(e) => set("effective_date", e.target.value)} />
            </Field>
          </div>
        )}

        {action === "free" && (
          <div className="grid grid-cols-2 gap-3">
            <Field label="Number of months">
              <input required type="number" min={1} className={inputClass}
                value={form.months ?? ""} onChange={(e) => set("months", e.target.value)} />
            </Field>
            <Field label="Starting month">
              <input required type="date" className={inputClass}
                value={form.from_month ?? ""} onChange={(e) => set("from_month", e.target.value)} />
            </Field>
          </div>
        )}

        {(action === "add" || action === "remove") && (
          <>
            <Field label="Effective date">
              <input required type="date" className={inputClass}
                value={form.effective_date ?? ""} onChange={(e) => set("effective_date", e.target.value)} />
            </Field>
            <div className="space-y-1.5">
              <div className="text-xs text-muted-foreground">
                {action === "add" ? "Available units in this property" : "Units currently held"}
              </div>
              <div className="grid grid-cols-4 sm:grid-cols-6 gap-1.5 max-h-48 overflow-y-auto">
                {(action === "add"
                  ? available.map((u) => ({ id: u.id, label: u.unit_number }))
                  : held.map((a) => ({ id: a.unit_id, label: a.unit?.unit_number ?? String(a.unit_id) }))
                ).map((u) => (
                  <button key={u.id} type="button" onClick={() => toggle(u.id)}
                    className={
                      "rounded-md border p-1.5 text-xs font-mono transition-colors " +
                      (picked.has(u.id)
                        ? "border-primary bg-primary/10 text-primary"
                        : "border-border bg-card/60 hover:bg-accent")
                    }>
                    {u.label}
                  </button>
                ))}
              </div>
              {action === "remove" && picked.size >= held.length && held.length > 0 && (
                <div className="text-xs text-destructive">
                  That would release every unit — cancel the contract instead.
                </div>
              )}
            </div>
          </>
        )}

        {action === "cancel" && (
          <>
            <Field label="Effective date">
              <input required type="date" className={inputClass}
                value={form.effective_date ?? ""} onChange={(e) => set("effective_date", e.target.value)} />
            </Field>
            <Field label="Reason">
              <select required className={selectClass} value={form.reason ?? ""}
                onChange={(e) => set("reason", e.target.value)}>
                <option value="">Select…</option>
                <option value="client vacated">Client vacated</option>
                <option value="non-payment">Non-payment</option>
                <option value="mutual agreement">Mutual agreement</option>
                <option value="breach of terms">Breach of terms</option>
                <option value="other">Other</option>
              </select>
            </Field>
            <Field label="Remarks">
              <textarea className={textareaClass} value={form.remarks ?? ""}
                onChange={(e) => set("remarks", e.target.value)} />
            </Field>
            <div className="text-xs text-muted-foreground">
              All {held.length} unit{held.length === 1 ? "" : "s"} will be released on that date
              and become available to other clients.
            </div>
          </>
        )}

        {action === "renew" && (
          <div className="grid grid-cols-2 gap-3">
            <Field label="New start date">
              <input required type="date" className={inputClass}
                value={form.new_start_date ?? ""} onChange={(e) => set("new_start_date", e.target.value)} />
            </Field>
            <Field label="New expiry date">
              <input required type="date" className={inputClass}
                value={form.new_expiry_date ?? ""} onChange={(e) => set("new_expiry_date", e.target.value)} />
            </Field>
            <Field label="New monthly rent" span={2}>
              <input type="number" step="0.01" className={inputClass}
                value={form.new_monthly_rent ?? ""}
                onChange={(e) => set("new_monthly_rent", e.target.value)}
                placeholder={`Unchanged (${money(contract.monthly_rent)})`} />
            </Field>
            <div className="col-span-2 text-xs text-muted-foreground">
              The same {held.length} unit{held.length === 1 ? "" : "s"} carry over to the new
              contract; this one is marked renewed.
            </div>
          </div>
        )}

        {action === "dates" && (
          <div className="grid grid-cols-2 gap-3">
            <Field label="Current start date">
              <input className={inputClass} value={contract.start_date} disabled />
            </Field>
            <Field label="Current expiry date">
              <input className={inputClass} value={contract.expiry_date} disabled />
            </Field>
            <Field label="Corrected start date">
              <input type="date" className={inputClass}
                value={form.new_start_date ?? ""} onChange={(e) => set("new_start_date", e.target.value)} />
            </Field>
            <Field label="Corrected expiry date">
              <input type="date" className={inputClass}
                value={form.new_expiry_date ?? ""} onChange={(e) => set("new_expiry_date", e.target.value)} />
            </Field>
            <Field label="Reason" span={2}>
              <input required className={inputClass} placeholder="e.g. wrong start date entered at signing"
                value={form.reason ?? ""} onChange={(e) => set("reason", e.target.value)} />
            </Field>
            <Field label="Remarks" span={2}>
              <textarea className={textareaClass} value={form.remarks ?? ""}
                onChange={(e) => set("remarks", e.target.value)} />
            </Field>
            <div className="col-span-2 text-xs text-muted-foreground">
              For fixing a data-entry mistake on the original dates — this stays the same
              contract number and does not touch which units it holds. For a genuine new
              term, use Renew instead. Leave a date blank to leave it unchanged.
            </div>
          </div>
        )}

        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={onClose}
            className="h-9 rounded-md border border-border bg-card/60 px-3 text-sm">Cancel</button>
          <button type="submit" disabled={busy || !canSubmit}
            className={
              "h-9 rounded-md px-4 text-sm font-medium disabled:opacity-60 " +
              (action === "cancel"
                ? "bg-destructive text-destructive-foreground hover:bg-destructive/90"
                : "bg-primary text-primary-foreground hover:bg-primary/90")
            }>
            {busy ? "Working…" : CONFIG.verb}
          </button>
        </div>
      </form>
    </Modal>
  );
}
