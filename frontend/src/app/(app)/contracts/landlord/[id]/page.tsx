"use client";

import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouteParams } from "@/lib/use-route-params";
import {
  ArrowLeft, FileText, DoorOpen, History, Paperclip,
  XCircle, MinusCircle, PlusCircle, CalendarOff, CalendarClock, Banknote, Wallet,
} from "lucide-react";
import { api } from "@/lib/api";
import { keys } from "@/lib/query-keys";
import { Can } from "@/components/can";
import { Modal, Field, inputClass, selectClass, textareaClass } from "@/components/ui/dialog";
import { toast, errorMessage } from "@/components/ui/toast";
import { AttachmentsTab } from "@/components/attachments-tab";
import type { LandlordContract, LandlordUnitRow } from "@/lib/landlord-contract-types";
import { LANDLORD_AMENDMENT_LABEL, LANDLORD_STATUS_TONE } from "@/lib/landlord-contract-types";
import { money } from "@/lib/contract-types";

type TabKey = "overview" | "units" | "amendments" | "attachments";
type ActionKey = null | "rent" | "free" | "add" | "remove" | "deposit" | "cancel" | "dates";

type PropertyUnit = { id: number; unit_number: string; unit_type: string };

export default function LandlordContractDetail({ params }: { params: Promise<{ id: string }> }) {
  const { id } = useRouteParams(params);
  const qc = useQueryClient();
  const [tab, setTab] = useState<TabKey>("overview");
  const [action, setAction] = useState<ActionKey>(null);

  const contractQuery = useQuery({
    queryKey: keys.landlordContracts.detail(id),
    queryFn: async () => (await api.get(`/landlord-contracts/${id}`)).data.data as LandlordContract,
  });
  const contract = contractQuery.data ?? null;
  const loading = contractQuery.isLoading;
  const load = () => qc.invalidateQueries({ queryKey: keys.landlordContracts.detail(id) });

  if (loading || !contract) {
    return <div className="text-sm text-muted-foreground animate-pulse">Loading contract…</div>;
  }

  const isActive = contract.status === "active";
  const canCorrectDates = isActive || contract.status === "expired";
  const tabs: { key: TabKey; label: string; icon: typeof FileText }[] = [
    { key: "overview", label: "Overview", icon: FileText },
    { key: "units", label: `Units (${contract.units_count ?? 0})`, icon: DoorOpen },
    { key: "amendments", label: `History (${contract.amendments?.length ?? 0})`, icon: History },
    { key: "attachments", label: "Documents", icon: Paperclip },
  ];

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <Link href="/contracts/landlord" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft className="h-3.5 w-3.5" /> Back to landlord contracts
        </Link>
        <div className="mt-2 flex items-start justify-between flex-wrap gap-3">
          <div>
            <h1 className="text-2xl lg:text-3xl font-semibold tracking-tight">
              {contract.landlord?.name}
            </h1>
            <p className="text-sm text-muted-foreground">
              <span className="font-mono">{contract.contract_number}</span>
              {" · "}
              {contract.property && (
                <Link href={`/properties/${contract.property.id}`} className="hover:text-primary hover:underline">
                  {contract.property.name}
                </Link>
              )}
            </p>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <span className={"rounded-full px-3 py-1 text-xs capitalize " + (LANDLORD_STATUS_TONE[contract.status] ?? "")}>
              {contract.status}
            </span>
            {isActive && (
              <Can perm="property.amend">
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
                <button onClick={() => setAction("deposit")}
                  className="h-8 inline-flex items-center gap-1 rounded-md border border-border bg-card/60 px-2 text-xs hover:bg-accent">
                  <Wallet className="h-3.5 w-3.5" /> Deposit
                </button>
              </Can>
            )}
            {isActive && (
              <Can perm="property.cancel">
                <button onClick={() => setAction("cancel")}
                  className="h-8 inline-flex items-center gap-1 rounded-md border border-destructive/40 text-destructive px-2 text-xs hover:bg-destructive/10">
                  <XCircle className="h-3.5 w-3.5" /> Cancel
                </button>
              </Can>
            )}
            {canCorrectDates && (
              <Can perm="property.amend">
                <button onClick={() => setAction("dates")}
                  className="h-8 inline-flex items-center gap-1 rounded-md border border-border bg-card/60 px-2 text-xs hover:bg-accent">
                  <CalendarClock className="h-3.5 w-3.5" /> Correct dates
                </button>
              </Can>
            )}
          </div>
        </div>
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

      {tab === "overview" && <Overview contract={contract} />}
      {tab === "units" && <UnitsTab contract={contract} />}
      {tab === "amendments" && <AmendmentsTab contract={contract} />}
      {tab === "attachments" && (
        <AttachmentsTab entityType="property_agreement" entityId={contract.id} />
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

function Overview({ contract }: { contract: LandlordContract }) {
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
        <Cell k="Payment mode" v={<span className="capitalize">{contract.payment_mode}</span>} />
        <Cell k="Units held" v={contract.units_count || "whole property"} />
        <Cell k="Start" v={<span className="font-mono text-xs">{contract.start_date}</span>} />
        <Cell k="Expiry" v={
          <span className={"font-mono text-xs " + (days < 0 ? "text-destructive" : days <= 60 ? "text-amber-600" : "")}>
            {contract.expiry_date}
          </span>
        } />
        <Cell k="Security deposit" v={money(contract.security_deposit)} />
        <Cell k="Agreement no." v={contract.agreement_number} />
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
          <Link href={`/contracts/landlord/${contract.renewed_to_id}`}
            className="text-xs text-primary hover:underline inline-block pt-2">
            Renewed as a new contract →
          </Link>
        )}
        {!contract.renewed_to_id && contract.property && (
          <Link href={`/properties/${contract.property.id}`}
            className="text-xs text-primary hover:underline inline-block pt-2">
            Renew from the property&apos;s Agreement tab →
          </Link>
        )}
      </div>
    </div>
  );
}

function UnitsTab({ contract }: { contract: LandlordContract }) {
  const rows = contract.units ?? [];
  return (
    <div className="glass rounded-xl overflow-x-auto">
      <div className="px-4 pt-3 text-xs text-muted-foreground">
        Units sourced from this landlord as of {contract.units_as_of ?? "today"}. Empty means
        the whole property, not tracked unit-by-unit. Releasing a unit closes its row — the
        history stays.
      </div>
      <table className="w-full text-sm mt-2">
        <thead className="text-left text-xs text-muted-foreground border-b border-border">
          <tr>
            <th className="py-2 px-3">Unit</th>
            <th className="py-2 px-3">Type</th>
            <th className="py-2 px-3">Held from</th>
            <th className="py-2 px-3">Until</th>
            <th className="py-2 px-3 text-right">Unit rent</th>
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr><td colSpan={5} className="py-10 text-center text-muted-foreground">
              No units tracked — this contract covers the whole property.
            </td></tr>
          ) : rows.map((a: LandlordUnitRow) => (
            <tr key={a.id} className="border-b border-border/60">
              <td className="py-2 px-3 font-mono">{a.unit?.unit_number}</td>
              <td className="py-2 px-3 capitalize">{a.unit?.unit_type.replaceAll("_", " ")}</td>
              <td className="py-2 px-3 font-mono text-xs">{a.from_date}</td>
              <td className="py-2 px-3 font-mono text-xs">{a.to_date ?? "—"}</td>
              <td className="py-2 px-3 text-right">{a.unit_rent != null ? money(a.unit_rent) : "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AmendmentsTab({ contract }: { contract: LandlordContract }) {
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
              <td className="py-2 px-3">{LANDLORD_AMENDMENT_LABEL[a.amendment_type] ?? a.amendment_type}</td>
              <td className="py-2 px-3 font-mono text-xs">{a.effective_date}</td>
              <td className="py-2 px-3 text-xs">
                {a.amendment_type === "rent_change" && (
                  <>{money(a.old_rent)} → <span className="font-medium">{money(a.new_rent)}</span></>
                )}
                {a.amendment_type === "deposit_change" && (
                  <>{money(a.old_security_deposit)} → <span className="font-medium">{money(a.new_security_deposit)}</span></>
                )}
                {a.amendment_type === "free_months" && (
                  <>{a.free_months} month{a.free_months === 1 ? "" : "s"} from {a.free_from_month}</>
                )}
                {(a.amendment_type === "units_added" || a.amendment_type === "units_removed" || a.amendment_type === "renewal") && (
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
  action: ActionKey;
  contract: LandlordContract;
  onClose: () => void;
  onDone: () => void;
}) {
  const [form, setForm] = useState<Record<string, string>>({});
  const [picked, setPicked] = useState<Set<number>>(new Set());
  const [propertyUnits, setPropertyUnits] = useState<PropertyUnit[]>([]);
  const [warnings, setWarnings] = useState<{ unit_number: string; contract_number: string; client: string | null }[] | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!action) return;
    setForm({});
    setPicked(new Set());
    setWarnings(null);
    if (action === "add") {
      api.get(`/properties/${contract.property_id}/units`)
        .then((r) => setPropertyUnits(r.data.data ?? []))
        .catch(() => setPropertyUnits([]));
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
    free: { title: "Grant free months (landlord's grace period)", verb: "Save" },
    add: { title: "Add units to this contract", verb: "Add units" },
    remove: { title: "Release units", verb: "Release" },
    deposit: { title: "Update security deposit", verb: "Save" },
    cancel: { title: "Cancel this contract", verb: "Cancel contract" },
    dates: { title: "Correct contract dates", verb: "Save correction" },
  }[action];

  const submit = async (e: React.FormEvent, acknowledgeWarnings = false) => {
    e.preventDefault();
    setBusy(true);
    try {
      const base = `/landlord-contracts/${contract.id}`;
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
          unit_rent: form.unit_rent ? Number(form.unit_rent) : null,
          reason: form.reason || null,
        });
      } else if (action === "remove") {
        try {
          resp = await api.post(`${base}/amendments/remove-units`, {
            unit_ids: [...picked], effective_date: form.effective_date,
            reason: form.reason || null, acknowledge_warnings: acknowledgeWarnings,
          });
        } catch (err: unknown) {
          const axiosErr = err as { response?: { status?: number; data?: { data?: { warnings?: typeof warnings } } } };
          if (axiosErr.response?.status === 409 && axiosErr.response.data?.data?.warnings) {
            setWarnings(axiosErr.response.data.data.warnings ?? []);
            setBusy(false);
            return;
          }
          throw err;
        }
      } else if (action === "deposit") {
        resp = await api.post(`${base}/amendments/deposit`, {
          new_deposit: Number(form.new_deposit), effective_date: form.effective_date,
          reason: form.reason || null,
        });
      } else if (action === "cancel") {
        resp = await api.post(`${base}/cancel`, {
          effective_date: form.effective_date, reason: form.reason,
          remarks: form.remarks || null,
        });
      } else if (action === "dates") {
        resp = await api.post(`${base}/amendments/dates`, {
          new_start_date: form.new_start_date || null,
          new_expiry_date: form.new_expiry_date || null,
          reason: form.reason, remarks: form.remarks || null,
        });
      }
      toast.success(`${CONFIG.title} — done`);
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
    : action === "remove" ? picked.size > 0 && form.effective_date
    : action === "deposit" ? form.new_deposit && form.effective_date
    : action === "cancel" ? form.effective_date && form.reason
    : (form.new_start_date || form.new_expiry_date) && form.reason;

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
            <div className="col-span-2 text-xs text-muted-foreground">
              A grace period the landlord granted us — months we don&apos;t owe rent for.
            </div>
          </div>
        )}

        {action === "deposit" && (
          <div className="grid grid-cols-2 gap-3">
            <Field label="Current deposit">
              <input className={inputClass} value={money(contract.security_deposit)} disabled />
            </Field>
            <Field label="New deposit">
              <input required type="number" step="0.01" className={inputClass}
                value={form.new_deposit ?? ""} onChange={(e) => set("new_deposit", e.target.value)} />
            </Field>
            <Field label="Effective from" span={2}>
              <input required type="date" className={inputClass}
                value={form.effective_date ?? ""} onChange={(e) => set("effective_date", e.target.value)} />
            </Field>
            <Field label="Reason" span={2}>
              <input className={inputClass} placeholder="e.g. renewal top-up"
                value={form.reason ?? ""} onChange={(e) => set("reason", e.target.value)} />
            </Field>
          </div>
        )}

        {action === "add" && (
          <>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Effective date">
                <input required type="date" className={inputClass}
                  value={form.effective_date ?? ""} onChange={(e) => set("effective_date", e.target.value)} />
              </Field>
              <Field label="Per-unit rent (optional)">
                <input type="number" step="0.01" className={inputClass}
                  placeholder="Informational only"
                  value={form.unit_rent ?? ""} onChange={(e) => set("unit_rent", e.target.value)} />
              </Field>
            </div>
            <div className="space-y-1.5">
              <div className="text-xs text-muted-foreground">Units in this property</div>
              <div className="grid grid-cols-4 sm:grid-cols-6 gap-1.5 max-h-48 overflow-y-auto">
                {propertyUnits.map((u) => (
                  <button key={u.id} type="button" onClick={() => toggle(u.id)}
                    className={
                      "rounded-md border p-1.5 text-xs font-mono transition-colors " +
                      (picked.has(u.id)
                        ? "border-primary bg-primary/10 text-primary"
                        : "border-border bg-card/60 hover:bg-accent")
                    }>
                    {u.unit_number}
                  </button>
                ))}
              </div>
              <div className="text-[11px] text-muted-foreground">
                A unit already sourced from another active landlord contract will be rejected on save.
              </div>
            </div>
          </>
        )}

        {action === "remove" && (
          <>
            <Field label="Effective date">
              <input required type="date" className={inputClass}
                value={form.effective_date ?? ""} onChange={(e) => set("effective_date", e.target.value)} />
            </Field>
            <Field label="Reason">
              <input className={inputClass} value={form.reason ?? ""}
                onChange={(e) => set("reason", e.target.value)} placeholder="e.g. landlord reclaimed the floor" />
            </Field>
            <div className="space-y-1.5">
              <div className="text-xs text-muted-foreground">Units currently held</div>
              <div className="grid grid-cols-4 sm:grid-cols-6 gap-1.5 max-h-48 overflow-y-auto">
                {held.map((a) => (
                  <button key={a.unit_id} type="button" onClick={() => toggle(a.unit_id)}
                    className={
                      "rounded-md border p-1.5 text-xs font-mono transition-colors " +
                      (picked.has(a.unit_id)
                        ? "border-primary bg-primary/10 text-primary"
                        : "border-border bg-card/60 hover:bg-accent")
                    }>
                    {a.unit?.unit_number ?? a.unit_id}
                  </button>
                ))}
              </div>
            </div>
            {warnings && warnings.length > 0 && (
              <div className="rounded-lg border border-amber-500/40 bg-amber-500/5 p-3 space-y-2 text-xs">
                <div className="font-medium text-amber-700 dark:text-amber-500">
                  Still held by a client — release anyway?
                </div>
                {warnings.map((w, i) => (
                  <div key={i} className="text-muted-foreground">
                    {w.unit_number} — held by {w.client ?? "a client"} on contract{" "}
                    <span className="font-mono">{w.contract_number}</span>
                  </div>
                ))}
                <button type="button" disabled={busy}
                  onClick={(e) => submit(e, true)}
                  className="h-8 rounded-md bg-amber-500 px-3 text-xs font-medium text-white hover:bg-amber-600 disabled:opacity-60">
                  Release anyway
                </button>
              </div>
            )}
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
                <option value="landlord sold the property">Landlord sold the property</option>
                <option value="mutual agreement">Mutual agreement</option>
                <option value="relocating">GreenTech relocating</option>
                <option value="breach of terms">Breach of terms</option>
                <option value="other">Other</option>
              </select>
            </Field>
            <Field label="Remarks">
              <textarea className={textareaClass} value={form.remarks ?? ""}
                onChange={(e) => set("remarks", e.target.value)} />
            </Field>
            <div className="text-xs text-muted-foreground">
              {held.length > 0
                ? `All ${held.length} tracked unit${held.length === 1 ? "" : "s"} will be released on that date.`
                : "This contract has no unit-level tracking (whole property)."}
            </div>
          </>
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
              contract number. For a genuine new term, renew from the property&apos;s
              Agreement tab instead. Leave a date blank to leave it unchanged.
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
