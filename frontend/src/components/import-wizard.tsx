"use client";

import { useEffect, useState } from "react";
import { Upload, CheckCircle2, AlertTriangle, FileSpreadsheet } from "lucide-react";
import { api } from "@/lib/api";
import { Modal, Field, inputClass, selectClass } from "@/components/ui/dialog";
import { toast, errorMessage } from "@/components/ui/toast";
import { money } from "@/lib/contract-types";

type Category = { id: number; code: string; name: string; kind: string; is_property_wise: boolean };
type Property = { id: number; code: string; name: string };

type Line = {
  section: string;
  ledger_name: string;
  amount: number;
  row: number;
  category_id: number | null;
  category_name: string | null;
  category_kind: string | null;
  is_property_wise: boolean;
  is_mapped: boolean;
};

type Check = {
  section: string; label: string; parsed: number;
  reported: number | null; matches: boolean; difference: number | null;
};

type Preview = {
  file_hash: string;
  original_name: string;
  period_from: string;
  period_to: string;
  period_month: string;
  lines: Line[];
  reconciliation: { sums: Record<string, number>; checks: Check[]; all_match: boolean;
                    computed_net_profit: number | null; reported_net_profit: number | null };
  duplicate_of: string | null;
};

const SECTION_LABEL: Record<string, string> = {
  income: "Revenue",
  direct: "Direct (property) costs",
  indirect: "Company overhead",
};

/**
 * Upload → see exactly what was read and whether it reconciles → map any
 * unknown ledger → post. Nothing is written until the last step, and the
 * server refuses to post if the file's own totals disagree with its lines.
 */
export function ImportWizard({ open, properties, categories, onClose, onImported }: {
  open: boolean;
  properties: Property[];
  categories: Category[];
  onClose: () => void;
  onImported: () => void;
}) {
  const [preview, setPreview] = useState<Preview | null>(null);
  const [mappings, setMappings] = useState<Record<string, number>>({});
  const [allocations, setAllocations] = useState<Record<string, number>>({});
  const [uploading, setUploading] = useState(false);
  const [posting, setPosting] = useState(false);
  const [force, setForce] = useState(false);

  useEffect(() => {
    if (!open) return;
    setPreview(null);
    setMappings({});
    setAllocations({});
    setForce(false);
  }, [open]);

  const upload = async (file: File) => {
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const resp = await api.post("/expenses/import/preview", fd);
      const data: Preview = resp.data.data;
      setPreview(data);
      setMappings(Object.fromEntries(
        data.lines.filter((l) => l.category_id).map((l) => [l.ledger_name, l.category_id as number])));
    } catch (err: unknown) {
      toast.error("Could not read that file", errorMessage(err));
    } finally { setUploading(false); }
  };

  const post = async () => {
    if (!preview) return;
    setPosting(true);
    try {
      const resp = await api.post("/expenses/import/post", {
        file_hash: preview.file_hash,
        mappings,
        allocations,
        force,
      });
      const b = resp.data?.data;
      toast.success(`Imported ${b?.lines_imported ?? 0} line(s)`,
        `Batch ${b?.batch_number ?? ""} for ${preview.period_month.slice(0, 7)}`);
      onImported();
    } catch (err: unknown) {
      toast.error("Import failed", errorMessage(err));
    } finally { setPosting(false); }
  };

  const unmapped = preview
    ? preview.lines.filter((l) => !mappings[l.ledger_name])
    : [];
  const canPost = preview !== null && unmapped.length === 0
    && (preview.reconciliation.all_match || force)
    && (!preview.duplicate_of || force);

  return (
    <Modal open={open} onClose={onClose} title="Import accounting P&L" size="lg">
      <div className="space-y-4">
        {!preview ? (
          <div className="space-y-3">
            <label className="flex flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed border-border bg-card/40 p-8 cursor-pointer hover:bg-accent/30">
              <FileSpreadsheet className="h-8 w-8 text-muted-foreground" />
              <div className="text-sm font-medium">
                {uploading ? "Reading…" : "Choose the P&L export (.xlsx)"}
              </div>
              <div className="text-xs text-muted-foreground text-center max-w-sm">
                The Trading and Profit &amp; Loss report from your accounting software.
                Nothing is saved until you review what was read.
              </div>
              <input type="file" accept=".xlsx,.xls" className="hidden"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) upload(f);
                  e.currentTarget.value = "";
                }} />
            </label>
          </div>
        ) : (
          <>
            <div className="rounded-lg border border-border bg-card/40 p-3 text-xs space-y-1">
              <div className="font-medium">{preview.original_name}</div>
              <div className="text-muted-foreground">
                Period {preview.period_from} → {preview.period_to} · posts to{" "}
                <span className="font-mono">{preview.period_month.slice(0, 7)}</span> ·{" "}
                {preview.lines.length} ledger lines
              </div>
            </div>

            {/* Reconciliation — the reason to trust the import */}
            <div className={
              "rounded-lg border p-3 space-y-1.5 " +
              (preview.reconciliation.all_match
                ? "border-emerald-500/40 bg-emerald-500/5"
                : "border-rose-500/40 bg-rose-500/5")
            }>
              <div className="text-xs font-medium inline-flex items-center gap-1.5">
                {preview.reconciliation.all_match
                  ? <><CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" /> Totals match the file</>
                  : <><AlertTriangle className="h-3.5 w-3.5 text-rose-600" /> Totals do not match</>}
              </div>
              {preview.reconciliation.checks.map((c) => (
                <div key={c.section} className="flex justify-between text-xs">
                  <span className="text-muted-foreground">{c.label}</span>
                  <span className={c.matches ? "" : "text-rose-600"}>
                    {money(c.parsed)}
                    {c.reported !== null && !c.matches && (
                      <span className="text-muted-foreground"> (file says {money(c.reported)})</span>
                    )}
                  </span>
                </div>
              ))}
              {preview.reconciliation.reported_net_profit !== null && (
                <div className="flex justify-between text-xs pt-1 border-t border-border/60">
                  <span className="font-medium">Net profit</span>
                  <span className="font-medium">
                    {money(preview.reconciliation.reported_net_profit)}
                  </span>
                </div>
              )}
            </div>

            {preview.duplicate_of && (
              <div className="rounded-lg border border-amber-500/40 bg-amber-500/5 p-3 text-xs">
                This exact file was already imported as{" "}
                <span className="font-mono">{preview.duplicate_of}</span>. Importing again
                would double-count the month.
              </div>
            )}

            {unmapped.length > 0 && (
              <div className="rounded-lg border border-amber-500/40 bg-amber-500/5 p-3 text-xs">
                {unmapped.length} ledger{unmapped.length === 1 ? "" : "s"} need a category
                before this can post. Your choice is remembered for next month.
              </div>
            )}

            <div className="max-h-72 overflow-y-auto space-y-3">
              {["income", "direct", "indirect"].map((section) => {
                const rows = preview.lines.filter((l) => l.section === section);
                if (rows.length === 0) return null;
                return (
                  <div key={section}>
                    <div className="text-xs font-medium text-muted-foreground mb-1">
                      {SECTION_LABEL[section]}
                      {section === "income" && " — not imported (the portal raises its own rent)"}
                    </div>
                    <table className="w-full text-xs">
                      <tbody>
                        {rows.map((l) => (
                          <tr key={l.ledger_name} className="border-b border-border/60">
                            <td className="py-1.5 pr-2 font-mono">{l.ledger_name}</td>
                            <td className="py-1.5 pr-2 text-right whitespace-nowrap">
                              {money(l.amount)}
                            </td>
                            <td className="py-1.5 pr-2 w-48">
                              <select
                                className={selectClass + " h-7 text-xs"}
                                value={mappings[l.ledger_name] ?? ""}
                                onChange={(e) => setMappings((prev) => ({
                                  ...prev,
                                  [l.ledger_name]: Number(e.target.value),
                                }))}
                              >
                                <option value="">Choose category…</option>
                                {categories.map((c) => (
                                  <option key={c.id} value={c.id}>{c.name}</option>
                                ))}
                              </select>
                            </td>
                            <td className="py-1.5 w-40">
                              {section === "direct" && (
                                <select
                                  className={selectClass + " h-7 text-xs"}
                                  value={allocations[l.ledger_name] ?? ""}
                                  onChange={(e) => setAllocations((prev) => ({
                                    ...prev,
                                    [l.ledger_name]: Number(e.target.value),
                                  }))}
                                >
                                  <option value="">Allocate later</option>
                                  {properties.map((p) => (
                                    <option key={p.id} value={p.id}>{p.name}</option>
                                  ))}
                                </select>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                );
              })}
            </div>

            {(!preview.reconciliation.all_match || preview.duplicate_of) && (
              <label className="inline-flex items-start gap-2 text-xs cursor-pointer">
                <input type="checkbox" checked={force} className="mt-0.5"
                  onChange={(e) => setForce(e.target.checked)} />
                <span>
                  Import anyway — I understand{" "}
                  {preview.duplicate_of ? "this file was already imported" : "the totals don't reconcile"}.
                </span>
              </label>
            )}
          </>
        )}

        <div className="flex justify-between gap-2 pt-2 border-t border-border">
          <button type="button" onClick={onClose}
            className="h-9 rounded-md border border-border bg-card/60 px-3 text-sm">
            Cancel
          </button>
          <div className="flex gap-2">
            {preview && (
              <button type="button" onClick={() => setPreview(null)}
                className="h-9 rounded-md border border-border bg-card/60 px-3 text-sm">
                Choose another file
              </button>
            )}
            <button type="button" disabled={!canPost || posting} onClick={post}
              className="h-9 inline-flex items-center gap-2 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50">
              <Upload className="h-4 w-4" />
              {posting ? "Importing…" : preview
                ? `Import ${preview.lines.filter((l) => l.section !== "income").length} line(s)`
                : "Import"}
            </button>
          </div>
        </div>
      </div>
    </Modal>
  );
}
