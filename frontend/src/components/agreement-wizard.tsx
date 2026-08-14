"use client";

import { useEffect, useMemo, useState } from "react";
import { Check, AlertTriangle, Download } from "lucide-react";
import { api } from "@/lib/api";
import { Modal, Field, inputClass, selectClass, textareaClass } from "@/components/ui/dialog";
import { toast, errorMessage } from "@/components/ui/toast";
import { AgreementPreview, type Clause } from "@/components/agreement-preview";

type Option = { id: number; code: string; name: string };
type PartyDetail = {
  id: number; code: string; name: string; name_ar: string | null;
  signatory_name: string | null; signatory_name_ar: string | null;
  signatory_id_number: string | null;
};
type Template = { slug: string; title: string; title_ar: string; party_roles: string[]; description: string };

const STEPS = ["Agreement type", "Party", "Template", "Terms", "Preview", "Result"];

/**
 * Six steps: which side of the deal GreenTech is on, which landlord or
 * client the document is for, which template, the deal terms, a
 * bilingual preview, then generate. Mirrors ContractWizard's plain
 * step-index pattern.
 */
export function AgreementWizard({ open, onClose, onGenerated, presetPartyRole, presetLandlordId, presetClientId }: {
  open: boolean;
  onClose: () => void;
  onGenerated: () => void;
  presetPartyRole?: "landlord" | "client";
  presetLandlordId?: number;
  presetClientId?: number;
}) {
  const [step, setStep] = useState(1);
  const [busy, setBusy] = useState(false);

  const [partyRole, setPartyRole] = useState<"landlord" | "client" | "">("");
  const [parties, setParties] = useState<Option[]>([]);
  const [partyId, setPartyId] = useState<number | "">("");
  const [partyDetail, setPartyDetail] = useState<PartyDetail | null>(null);

  const [templates, setTemplates] = useState<Template[]>([]);
  const [templateSlug, setTemplateSlug] = useState("");

  const [roomsDescription, setRoomsDescription] = useState("");
  const [roomsCount, setRoomsCount] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [contractPeriodMonths, setContractPeriodMonths] = useState("");
  const [electricityIncluded, setElectricityIncluded] = useState(false);
  const [waterIncluded, setWaterIncluded] = useState(false);
  const [freeMonthsCount, setFreeMonthsCount] = useState("0");
  const [freeMonthsMode, setFreeMonthsMode] = useState("start");
  const [freeMonthsSpecific, setFreeMonthsSpecific] = useState("");
  const [depositChequeRequired, setDepositChequeRequired] = useState(false);
  const [cancellationMode, setCancellationMode] = useState("no_cancellation");
  const [cancellationNoticeMonths, setCancellationNoticeMonths] = useState("2");
  const [rentAmount, setRentAmount] = useState("");
  const [rentFrequency, setRentFrequency] = useState("3");
  const [currency, setCurrency] = useState("QAR");
  const [remarks, setRemarks] = useState("");

  const [previewClauses, setPreviewClauses] = useState<Clause[] | null>(null);
  const [result, setResult] = useState<{ agreement_number: string; attachment_id: number } | null>(null);

  useEffect(() => {
    if (!open) return;
    setStep(presetPartyRole ? 2 : 1);
    setPartyRole(presetPartyRole ?? "");
    setPartyId(presetLandlordId ?? presetClientId ?? "");
    setPartyDetail(null);
    setTemplateSlug("");
    setRoomsDescription(""); setRoomsCount(""); setStartDate(""); setEndDate("");
    setContractPeriodMonths(""); setElectricityIncluded(false); setWaterIncluded(false);
    setFreeMonthsCount("0"); setFreeMonthsMode("start"); setFreeMonthsSpecific("");
    setDepositChequeRequired(false); setCancellationMode("no_cancellation");
    setCancellationNoticeMonths("2"); setRentAmount(""); setRentFrequency("3");
    setCurrency("QAR"); setRemarks("");
    setPreviewClauses(null); setResult(null);
  }, [open, presetPartyRole, presetLandlordId, presetClientId]);

  useEffect(() => {
    if (!open || !partyRole) return;
    const path = partyRole === "landlord" ? "/landlords" : "/clients";
    api.get(path, { params: { status: "active" } })
      .then((r) => setParties(r.data.data ?? [])).catch(() => setParties([]));
    api.get("/agreement-templates", { params: { party_role: partyRole } })
      .then((r) => setTemplates(r.data.data ?? [])).catch(() => setTemplates([]));
  }, [open, partyRole]);

  useEffect(() => {
    if (!partyId || !partyRole) { setPartyDetail(null); return; }
    const path = partyRole === "landlord" ? `/landlords/${partyId}` : `/clients/${partyId}`;
    api.get(path).then((r) => setPartyDetail(r.data.data)).catch(() => setPartyDetail(null));
  }, [partyId, partyRole]);

  const signatoryMissing = partyDetail && (
    !partyDetail.signatory_name || !partyDetail.signatory_name_ar || !partyDetail.signatory_id_number
  );

  const termPayload = useMemo(() => ({
    template_slug: templateSlug,
    party_role: partyRole || undefined,
    landlord_id: partyRole === "landlord" ? Number(partyId) : undefined,
    client_id: partyRole === "client" ? Number(partyId) : undefined,
    rooms_description: roomsDescription || null,
    rooms_count: roomsCount === "" ? null : Number(roomsCount),
    start_date: startDate || undefined,
    end_date: endDate || undefined,
    contract_period_months: contractPeriodMonths === "" ? null : Number(contractPeriodMonths),
    electricity_included: electricityIncluded,
    water_included: waterIncluded,
    free_months_count: Number(freeMonthsCount) || 0,
    free_months_mode: Number(freeMonthsCount) > 0 ? freeMonthsMode : null,
    free_months_specific: freeMonthsMode === "specific" && freeMonthsSpecific
      ? freeMonthsSpecific.split(",").map((s) => s.trim()).filter(Boolean) : null,
    deposit_cheque_required: depositChequeRequired,
    cancellation_mode: cancellationMode,
    cancellation_notice_months: cancellationMode === "notice_months" ? Number(cancellationNoticeMonths) : null,
    rent_amount: rentAmount === "" ? null : Number(rentAmount),
    rent_payment_frequency_months: Number(rentFrequency) || 1,
    currency,
    remarks: remarks || null,
  }), [templateSlug, partyRole, partyId, roomsDescription, roomsCount, startDate, endDate,
      contractPeriodMonths, electricityIncluded, waterIncluded, freeMonthsCount, freeMonthsMode,
      freeMonthsSpecific, depositChequeRequired, cancellationMode, cancellationNoticeMonths,
      rentAmount, rentFrequency, currency, remarks]);

  const step1Ready = partyRole !== "";
  const step2Ready = partyId !== "" && !signatoryMissing;
  const step3Ready = templateSlug !== "";
  const step4Ready = startDate !== "" && endDate !== "" && endDate >= startDate;

  const loadPreview = async () => {
    setBusy(true);
    try {
      const resp = await api.post("/agreements/preview", termPayload);
      setPreviewClauses(resp.data?.data?.clauses ?? []);
      setStep(5);
    } catch (err: unknown) {
      toast.error("Could not build the preview", errorMessage(err));
    } finally { setBusy(false); }
  };

  const generate = async () => {
    setBusy(true);
    try {
      const resp = await api.post("/agreements", termPayload);
      const data = resp.data?.data;
      setResult({ agreement_number: data.agreement_number, attachment_id: data.attachment_id });
      toast.success(`Agreement ${data.agreement_number} generated`);
      setStep(6);
      onGenerated();
    } catch (err: unknown) {
      toast.error("Could not generate the agreement", errorMessage(err));
    } finally { setBusy(false); }
  };

  return (
    <Modal open={open} onClose={onClose} title="Generate rental agreement" size="xl">
      <div className="space-y-4">
        <ol className="flex items-center gap-1.5 text-xs flex-wrap">
          {STEPS.map((label, i) => {
            const n = i + 1;
            const done = step > n;
            return (
              <li key={label} className={
                "inline-flex items-center gap-1.5 rounded-full px-2 py-1 " +
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

        {step === 1 && (
          <div className="grid grid-cols-2 gap-3">
            {(["landlord", "client"] as const).map((role) => (
              <button key={role} type="button" onClick={() => setPartyRole(role)}
                className={`rounded-lg border p-4 text-left transition-colors ${
                  partyRole === role ? "border-primary bg-primary/10" : "border-border bg-card/60 hover:bg-accent"
                }`}>
                <div className="font-medium text-sm">
                  {role === "landlord" ? "Landlord agreement" : "Client agreement"}
                </div>
                <div className="text-xs text-muted-foreground mt-1">
                  {role === "landlord"
                    ? "GreenTech rents a property FROM this landlord — GreenTech is the Tenant."
                    : "GreenTech rents a property TO this client — GreenTech is the Lessor."}
                </div>
              </button>
            ))}
          </div>
        )}

        {step === 2 && (
          <div className="space-y-3">
            <Field label={partyRole === "landlord" ? "Landlord" : "Client"}>
              <select className={selectClass} value={String(partyId)}
                onChange={(e) => setPartyId(e.target.value ? Number(e.target.value) : "")}>
                <option value="">Select…</option>
                {parties.map((p) => <option key={p.id} value={p.id}>{p.name} ({p.code})</option>)}
              </select>
            </Field>
            {partyDetail && (
              <div className="rounded-lg border border-border bg-card/40 p-3 text-xs space-y-1">
                <div><span className="text-muted-foreground">Name:</span> {partyDetail.name}
                  {partyDetail.name_ar && <span dir="rtl" className="ml-2">{partyDetail.name_ar}</span>}</div>
                <div><span className="text-muted-foreground">Signatory:</span>{" "}
                  {partyDetail.signatory_name || <span className="text-amber-600">not set</span>}
                  {partyDetail.signatory_name_ar && <span dir="rtl" className="ml-2">{partyDetail.signatory_name_ar}</span>}</div>
                <div><span className="text-muted-foreground">Signatory ID:</span>{" "}
                  {partyDetail.signatory_id_number || <span className="text-amber-600">not set</span>}</div>
              </div>
            )}
            {signatoryMissing && (
              <div className="text-xs text-amber-600 inline-flex items-start gap-1.5">
                <AlertTriangle className="h-3.5 w-3.5 mt-0.5 shrink-0" />
                This {partyRole} has no signatory on file. Fill in the signatory name, Arabic
                name and ID number on their record before an agreement can be generated.
              </div>
            )}
          </div>
        )}

        {step === 3 && (
          <div className="space-y-2">
            {templates.length === 0 ? (
              <div className="text-sm text-muted-foreground py-6 text-center">
                No templates available for this agreement type yet.
              </div>
            ) : templates.map((t) => (
              <button key={t.slug} type="button" onClick={() => setTemplateSlug(t.slug)}
                className={`w-full rounded-lg border p-3 text-left transition-colors ${
                  templateSlug === t.slug ? "border-primary bg-primary/10" : "border-border bg-card/60 hover:bg-accent"
                }`}>
                <div className="font-medium text-sm flex items-center justify-between">
                  <span>{t.title}</span>
                  <span dir="rtl" className="text-muted-foreground">{t.title_ar}</span>
                </div>
                <div className="text-xs text-muted-foreground mt-1">{t.description}</div>
              </button>
            ))}
          </div>
        )}

        {step === 4 && (
          <div className="grid grid-cols-2 gap-3 max-h-[420px] overflow-y-auto pr-1">
            <Field label="Rooms / property description" span={2}>
              <textarea className={textareaClass} value={roomsDescription}
                onChange={(e) => setRoomsDescription(e.target.value)}
                placeholder="e.g. 10 labour rooms in area 85, street 520, building no. 16" />
            </Field>
            <Field label="Number of rooms">
              <input type="number" className={inputClass} value={roomsCount}
                onChange={(e) => setRoomsCount(e.target.value)} />
            </Field>
            <Field label="Currency">
              <select className={selectClass} value={currency} onChange={(e) => setCurrency(e.target.value)}>
                <option value="QAR">QAR</option><option value="AED">AED</option>
                <option value="SAR">SAR</option><option value="USD">USD</option>
              </select>
            </Field>
            <Field label="Start date">
              <input type="date" className={inputClass} value={startDate}
                onChange={(e) => setStartDate(e.target.value)} />
            </Field>
            <Field label="End date">
              <input type="date" className={inputClass} value={endDate}
                onChange={(e) => setEndDate(e.target.value)} />
            </Field>
            <Field label="Contract period (months)">
              <input type="number" className={inputClass} value={contractPeriodMonths}
                onChange={(e) => setContractPeriodMonths(e.target.value)} placeholder="auto" />
            </Field>
            <Field label="Rent amount">
              <input type="number" step="0.01" className={inputClass} value={rentAmount}
                onChange={(e) => setRentAmount(e.target.value)} />
            </Field>
            <Field label="Paid every (months)">
              <input type="number" className={inputClass} value={rentFrequency}
                onChange={(e) => setRentFrequency(e.target.value)} />
            </Field>
            <Field label="Deposit cheque required">
              <select className={selectClass} value={depositChequeRequired ? "yes" : "no"}
                onChange={(e) => setDepositChequeRequired(e.target.value === "yes")}>
                <option value="no">No</option><option value="yes">Yes</option>
              </select>
            </Field>
            <Field label="Electricity included">
              <select className={selectClass} value={electricityIncluded ? "yes" : "no"}
                onChange={(e) => setElectricityIncluded(e.target.value === "yes")}>
                <option value="no">No</option><option value="yes">Yes</option>
              </select>
            </Field>
            <Field label="Water included">
              <select className={selectClass} value={waterIncluded ? "yes" : "no"}
                onChange={(e) => setWaterIncluded(e.target.value === "yes")}>
                <option value="no">No</option><option value="yes">Yes</option>
              </select>
            </Field>
            <Field label="Free months">
              <input type="number" min={0} className={inputClass} value={freeMonthsCount}
                onChange={(e) => setFreeMonthsCount(e.target.value)} />
            </Field>
            {Number(freeMonthsCount) > 0 && (
              <>
                <Field label="Free months apply">
                  <select className={selectClass} value={freeMonthsMode}
                    onChange={(e) => setFreeMonthsMode(e.target.value)}>
                    <option value="start">At contract start</option>
                    <option value="end">At contract end</option>
                    <option value="specific">Specific months</option>
                  </select>
                </Field>
                {freeMonthsMode === "specific" && (
                  <Field label="Which months (comma-separated)">
                    <input className={inputClass} value={freeMonthsSpecific}
                      onChange={(e) => setFreeMonthsSpecific(e.target.value)}
                      placeholder="March 2026, April 2026" />
                  </Field>
                )}
              </>
            )}
            <Field label="Cancellation terms" span={2}>
              <select className={selectClass} value={cancellationMode}
                onChange={(e) => setCancellationMode(e.target.value)}>
                <option value="no_cancellation">No early cancellation until contract end</option>
                <option value="notice_months">Cancellation allowed with advance notice</option>
              </select>
            </Field>
            {cancellationMode === "notice_months" && (
              <Field label="Notice period (months)">
                <input type="number" min={1} className={inputClass} value={cancellationNoticeMonths}
                  onChange={(e) => setCancellationNoticeMonths(e.target.value)} />
              </Field>
            )}
            <Field label="Remarks" span={2}>
              <textarea className={textareaClass} value={remarks} onChange={(e) => setRemarks(e.target.value)} />
            </Field>
          </div>
        )}

        {step === 5 && previewClauses && (
          <div className="max-h-[480px] overflow-y-auto pr-1">
            <AgreementPreview clauses={previewClauses} />
          </div>
        )}

        {step === 6 && result && (
          <div className="text-center py-8 space-y-3">
            <Check className="h-10 w-10 mx-auto text-emerald-600" />
            <div className="text-sm font-medium">Agreement {result.agreement_number} generated</div>
            <a href={`/api/v1/attachments/${result.attachment_id}/download`}
              target="_blank" rel="noreferrer"
              className="inline-flex items-center gap-1.5 h-9 rounded-md border border-border bg-card/60 px-3 text-sm hover:bg-accent">
              <Download className="h-3.5 w-3.5" /> Download .docx
            </a>
          </div>
        )}

        <div className="flex justify-between gap-2 pt-2 border-t border-border">
          <button type="button" onClick={onClose}
            className="h-9 rounded-md border border-border bg-card/60 px-3 text-sm">
            {step === 6 ? "Close" : "Cancel"}
          </button>
          <div className="flex gap-2">
            {step > 1 && step < 6 && (
              <button type="button" onClick={() => setStep(step - 1)}
                className="h-9 rounded-md border border-border bg-card/60 px-3 text-sm">
                Back
              </button>
            )}
            {step < 4 && (
              <button type="button"
                disabled={(step === 1 && !step1Ready) || (step === 2 && !step2Ready) || (step === 3 && !step3Ready)}
                onClick={() => setStep(step + 1)}
                className="h-9 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50">
                Next
              </button>
            )}
            {step === 4 && (
              <button type="button" disabled={!step4Ready || busy} onClick={loadPreview}
                className="h-9 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50">
                {busy ? "Building…" : "Preview"}
              </button>
            )}
            {step === 5 && (
              <button type="button" disabled={busy} onClick={generate}
                className="h-9 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-60">
                {busy ? "Generating…" : "Generate agreement"}
              </button>
            )}
          </div>
        </div>
      </div>
    </Modal>
  );
}
