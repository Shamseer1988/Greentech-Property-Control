"use client";

import { useEffect, useMemo, useState } from "react";
import { Check, Lock, AlertTriangle } from "lucide-react";
import { api } from "@/lib/api";
import { Modal, Field, inputClass, selectClass, textareaClass } from "@/components/ui/dialog";
import { toast, errorMessage } from "@/components/ui/toast";
import type { AvailableUnit } from "@/lib/contract-types";
import { money } from "@/lib/contract-types";

type Option = { id: number; code: string; name: string };
type Floor = { id: number; floor_number: string };

/**
 * Three steps: who and where, which exact units, then the money.
 * The unit picker is the point of the whole screen — occupied units are
 * visibly locked and cannot be selected, so double-letting is impossible
 * from the UI as well as the API.
 */
export function ContractWizard({ open, onClose, onCreated, presetClientId, presetPropertyId }: {
  open: boolean;
  onClose: () => void;
  onCreated: (contractId: number) => void;
  presetClientId?: number;
  presetPropertyId?: number;
}) {
  const [step, setStep] = useState(1);
  const [clients, setClients] = useState<Option[]>([]);
  const [properties, setProperties] = useState<Option[]>([]);
  const [floors, setFloors] = useState<Floor[]>([]);
  const [units, setUnits] = useState<AvailableUnit[]>([]);
  const [loadingUnits, setLoadingUnits] = useState(false);
  const [busy, setBusy] = useState(false);

  const [clientId, setClientId] = useState<number | "">("");
  const [propertyId, setPropertyId] = useState<number | "">("");
  const [startDate, setStartDate] = useState("");
  const [expiryDate, setExpiryDate] = useState("");
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [monthlyRent, setMonthlyRent] = useState("");
  const [paymentMode, setPaymentMode] = useState("cash");
  const [securityDeposit, setSecurityDeposit] = useState("");
  const [openingBalance, setOpeningBalance] = useState("");
  const [remarks, setRemarks] = useState("");

  useEffect(() => {
    if (!open) return;
    setStep(1);
    setClientId(presetClientId ?? "");
    setPropertyId(presetPropertyId ?? "");
    setStartDate("");
    setExpiryDate("");
    setSelected(new Set());
    setMonthlyRent("");
    setPaymentMode("cash");
    setSecurityDeposit("");
    setOpeningBalance("");
    setRemarks("");
    api.get("/clients", { params: { status: "active" } })
      .then((r) => setClients(r.data.data ?? [])).catch(() => setClients([]));
    api.get("/properties", { params: { status: "active" } })
      .then((r) => setProperties(r.data.data ?? [])).catch(() => setProperties([]));
  }, [open, presetClientId, presetPropertyId]);

  // Availability depends on the start date — a unit free in March may be
  // taken today, so we ask the server for the picture on that date.
  useEffect(() => {
    if (!open || !propertyId) return;
    setLoadingUnits(true);
    const params: Record<string, string> = { property_id: String(propertyId) };
    if (startDate) params.on = startDate;
    Promise.all([
      api.get("/contracts/available-units", { params }),
      api.get(`/properties/${propertyId}/floors`),
    ])
      .then(([u, f]) => {
        setUnits(u.data.data ?? []);
        setFloors(f.data.data ?? []);
        // Drop any selection that just became unavailable.
        setSelected((prev) => {
          const stillOk = new Set(
            (u.data.data ?? []).filter((x: AvailableUnit) => x.is_available).map((x: AvailableUnit) => x.id),
          );
          return new Set([...prev].filter((id) => stillOk.has(id)));
        });
      })
      .catch(() => { setUnits([]); setFloors([]); })
      .finally(() => setLoadingUnits(false));
  }, [open, propertyId, startDate]);

  const byFloor = useMemo(() => {
    const map = new Map<number, AvailableUnit[]>();
    for (const u of units) {
      if (!map.has(u.floor_id)) map.set(u.floor_id, []);
      map.get(u.floor_id)!.push(u);
    }
    return map;
  }, [units]);

  const selectedUnits = units.filter((u) => selected.has(u.id));
  const suggestedRent = selectedUnits.reduce((sum, u) => sum + (u.monthly_rent ?? 0), 0);

  const toggle = (u: AvailableUnit) => {
    if (!u.is_available) return;
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(u.id)) next.delete(u.id); else next.add(u.id);
      return next;
    });
  };

  const step1Ready = clientId !== "" && propertyId !== "" && startDate && expiryDate
    && expiryDate >= startDate;
  const step2Ready = selected.size > 0;

  const submit = async () => {
    setBusy(true);
    try {
      const resp = await api.post("/contracts", {
        client_id: Number(clientId),
        property_id: Number(propertyId),
        unit_ids: [...selected],
        start_date: startDate,
        expiry_date: expiryDate,
        monthly_rent: Number(monthlyRent),
        payment_mode: paymentMode,
        security_deposit: securityDeposit === "" ? null : Number(securityDeposit),
        opening_balance: openingBalance === "" ? 0 : Number(openingBalance),
        remarks: remarks || null,
      });
      const created = resp.data?.data;
      toast.success(`Contract ${created?.contract_number ?? ""} created`,
        `${selected.size} unit${selected.size === 1 ? "" : "s"} allocated`);
      onCreated(created?.id);
    } catch (err: unknown) {
      toast.error("Could not create the contract", errorMessage(err));
    } finally { setBusy(false); }
  };

  return (
    <Modal open={open} onClose={onClose} title="New contract" size="lg">
      <div className="space-y-4">
        <ol className="flex items-center gap-2 text-xs">
          {["Client & dates", "Units", "Rent & terms"].map((label, i) => {
            const n = i + 1;
            const done = step > n;
            return (
              <li key={label} className={
                "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 " +
                (step === n ? "bg-primary/10 text-primary font-medium"
                  : done ? "text-emerald-600" : "text-muted-foreground")
              }>
                <span className="grid place-items-center h-4 w-4 rounded-full border text-[10px]">
                  {done ? <Check className="h-3 w-3" /> : n}
                </span>
                {label}
              </li>
            );
          })}
        </ol>

        {/* ---------------------------------------------- step 1 */}
        {step === 1 && (
          <div className="grid grid-cols-2 gap-3">
            <Field label="Client" span={2}>
              <select className={selectClass} value={String(clientId)}
                onChange={(e) => setClientId(e.target.value ? Number(e.target.value) : "")}>
                <option value="">Select a client…</option>
                {clients.map((c) => <option key={c.id} value={c.id}>{c.name} ({c.code})</option>)}
              </select>
            </Field>
            <Field label="Property" span={2}>
              <select className={selectClass} value={String(propertyId)}
                onChange={(e) => { setPropertyId(e.target.value ? Number(e.target.value) : ""); setSelected(new Set()); }}>
                <option value="">Select a property…</option>
                {properties.map((p) => <option key={p.id} value={p.id}>{p.name} ({p.code})</option>)}
              </select>
            </Field>
            <Field label="Start date">
              <input type="date" className={inputClass} value={startDate}
                onChange={(e) => setStartDate(e.target.value)} />
            </Field>
            <Field label="Expiry date">
              <input type="date" className={inputClass} value={expiryDate}
                onChange={(e) => setExpiryDate(e.target.value)} />
            </Field>
            {startDate && expiryDate && expiryDate < startDate && (
              <div className="col-span-2 text-xs text-destructive">
                Expiry must be on or after the start date.
              </div>
            )}
          </div>
        )}

        {/* ---------------------------------------------- step 2 */}
        {step === 2 && (
          <div className="space-y-3">
            <div className="flex items-center justify-between flex-wrap gap-2">
              <div className="text-sm text-muted-foreground">
                Pick the exact units this client rents. Occupied units are locked.
              </div>
              <div className="text-sm">
                <span className="font-semibold">{selected.size}</span> selected
              </div>
            </div>

            {loadingUnits ? (
              <div className="text-sm text-muted-foreground py-8 text-center">Loading units…</div>
            ) : units.length === 0 ? (
              <div className="text-sm text-muted-foreground py-8 text-center">
                This property has no units yet — add floors and units first.
              </div>
            ) : (
              <div className="space-y-3 max-h-[320px] overflow-y-auto pr-1">
                {floors.map((f) => {
                  const list = byFloor.get(f.id) ?? [];
                  if (list.length === 0) return null;
                  return (
                    <div key={f.id}>
                      <div className="text-xs font-medium text-muted-foreground mb-1.5">
                        Floor {f.floor_number}
                      </div>
                      <div className="grid grid-cols-4 sm:grid-cols-6 md:grid-cols-8 gap-1.5">
                        {list.map((u) => {
                          const isSel = selected.has(u.id);
                          const locked = !u.is_available;
                          return (
                            <button
                              key={u.id}
                              type="button"
                              disabled={locked}
                              onClick={() => toggle(u)}
                              title={
                                locked
                                  ? (u.held_by
                                      ? `Held by ${u.held_by.client_name ?? u.held_by.contract_number}`
                                      : u.is_shared_facility ? "Shared facility" : `Unit is ${u.occupancy_status}`)
                                  : `${u.unit_number} · ${u.unit_type.replaceAll("_", " ")}`
                              }
                              className={
                                "rounded-md border p-1.5 text-center transition-colors " +
                                (isSel
                                  ? "border-primary bg-primary/10 text-primary"
                                  : locked
                                    ? "border-border bg-muted/40 text-muted-foreground cursor-not-allowed opacity-70"
                                    : "border-border bg-card/60 hover:bg-accent")
                              }
                            >
                              <div className="text-xs font-mono font-semibold truncate flex items-center justify-center gap-1">
                                {locked && <Lock className="h-3 w-3 shrink-0" />}
                                {u.unit_number}
                              </div>
                              <div className="text-[9px] capitalize truncate">
                                {u.unit_type.replaceAll("_", " ")}
                              </div>
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}

            {selectedUnits.length > 0 && (
              <div className="text-xs text-muted-foreground">
                Selected: {selectedUnits.map((u) => u.unit_number).join(", ")}
              </div>
            )}
          </div>
        )}

        {/* ---------------------------------------------- step 3 */}
        {step === 3 && (
          <div className="grid grid-cols-2 gap-3">
            <div className="col-span-2 rounded-lg border border-border bg-card/40 p-3 text-xs space-y-1">
              <div>
                <span className="text-muted-foreground">Client:</span>{" "}
                {clients.find((c) => c.id === clientId)?.name}
              </div>
              <div>
                <span className="text-muted-foreground">Units:</span>{" "}
                <span className="font-mono">{selectedUnits.map((u) => u.unit_number).join(", ")}</span>
              </div>
              <div>
                <span className="text-muted-foreground">Term:</span> {startDate} → {expiryDate}
              </div>
            </div>

            <Field label="Monthly rent">
              <input type="number" step="0.01" className={inputClass} value={monthlyRent}
                onChange={(e) => setMonthlyRent(e.target.value)} />
              {suggestedRent > 0 && monthlyRent === "" && (
                <button type="button" onClick={() => setMonthlyRent(String(suggestedRent))}
                  className="text-[11px] text-primary mt-1 hover:underline">
                  Use unit rents: {money(suggestedRent)}
                </button>
              )}
            </Field>
            <Field label="Payment mode">
              <select className={selectClass} value={paymentMode}
                onChange={(e) => setPaymentMode(e.target.value)}>
                <option value="cash">Cash (monthly)</option>
                <option value="cheque">Cheque (PDC)</option>
                <option value="online">Online transfer</option>
              </select>
            </Field>
            <Field label={paymentMode === "cheque" ? "Security deposit (cash)" : "Security deposit"}>
              <input type="number" step="0.01" className={inputClass} value={securityDeposit}
                onChange={(e) => setSecurityDeposit(e.target.value)} placeholder="Optional" />
            </Field>
            <Field label="Opening balance">
              <input type="number" step="0.01" className={inputClass} value={openingBalance}
                onChange={(e) => setOpeningBalance(e.target.value)} placeholder="0" />
            </Field>
            <Field label="Remarks" span={2}>
              <textarea className={textareaClass} value={remarks}
                onChange={(e) => setRemarks(e.target.value)} />
            </Field>
            {paymentMode === "cheque" && (
              <div className="col-span-2 text-xs text-muted-foreground inline-flex items-start gap-1.5">
                <AlertTriangle className="h-3.5 w-3.5 mt-0.5 shrink-0 text-amber-600" />
                After creating the contract you&apos;ll be able to enter the 12 rent cheques
                plus the security cheque from its PDC tab.
              </div>
            )}
          </div>
        )}

        {/* ---------------------------------------------- footer */}
        <div className="flex justify-between gap-2 pt-2 border-t border-border">
          <button type="button" onClick={onClose}
            className="h-9 rounded-md border border-border bg-card/60 px-3 text-sm">
            Cancel
          </button>
          <div className="flex gap-2">
            {step > 1 && (
              <button type="button" onClick={() => setStep(step - 1)}
                className="h-9 rounded-md border border-border bg-card/60 px-3 text-sm">
                Back
              </button>
            )}
            {step < 3 ? (
              <button type="button"
                disabled={(step === 1 && !step1Ready) || (step === 2 && !step2Ready)}
                onClick={() => setStep(step + 1)}
                className="h-9 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50">
                Next
              </button>
            ) : (
              <button type="button" disabled={busy || !monthlyRent} onClick={submit}
                className="h-9 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-60">
                {busy ? "Creating…" : `Create contract (${selected.size} units)`}
              </button>
            )}
          </div>
        </div>
      </div>
    </Modal>
  );
}
