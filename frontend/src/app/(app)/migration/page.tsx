"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import {
  FileSpreadsheet, AlertTriangle, CheckCircle2, ArrowRight, Play,
  Scale, Building2, Users, Wallet, Info,
} from "lucide-react";
import { api } from "@/lib/api";
import { Can } from "@/components/can";
import { inputClass } from "@/components/ui/dialog";
import { toast, errorMessage } from "@/components/ui/toast";
import { money } from "@/lib/contract-types";

type Problem = { where: string; detail: string; severity: string };

type Parsed = {
  ok: boolean;
  months: string[];
  problems: Problem[];
  summary: Record<string, number>;
};

type PlanBlock = {
  index: number;
  title: string;
  property_name: string;
  property_type: string;
  landlord_name: string;
  landlord_match: string;
  rooms: number;
  stores: number;
  tenants: { name: string }[];
};

type Plan = {
  blocks: PlanBlock[];
  problems: Problem[];
  summary: Record<string, number>;
};

type Line = {
  label: string;
  workbook: number | null;
  app: number | null;
  difference: number | null;
  matches: boolean | null;
};

type Report = {
  month: string;
  company: Line[];
  properties: Line[];
  summary: { checked: number; matching: number; differing: number; uncomparable: number };
};

type Step = "choose" | "review" | "done";

/**
 * The one-time move off the master workbook.
 *
 * Read → review → commit, as three separate acts. Nothing is written
 * until the last one, and the reconciliation afterwards is the point:
 * it puts the portal's figures beside the spreadsheet's own so the
 * operator can see they agree rather than being told they do.
 */
export default function MigrationPage() {
  const [file, setFile] = useState<File | null>(null);
  const [parsed, setParsed] = useState<Parsed | null>(null);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [names, setNames] = useState<Record<number, string>>({});
  const [result, setResult] = useState<Record<string, number> | null>(null);
  const [report, setReport] = useState<Report | null>(null);
  const [month, setMonth] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [step, setStep] = useState<Step>("choose");
  const inputRef = useRef<HTMLInputElement>(null);

  const form = (extra?: Record<string, string>) => {
    const fd = new FormData();
    if (file) fd.append("file", file);
    for (const [k, v] of Object.entries(extra ?? {})) fd.append(k, v);
    return fd;
  };

  const read = async (chosen: File) => {
    setBusy("parse");
    setFile(chosen);
    try {
      const fd = new FormData();
      fd.append("file", chosen);
      const p = await api.post("/migration/parse", fd);
      setParsed(p.data.data);

      const fd2 = new FormData();
      fd2.append("file", chosen);
      const pl = await api.post("/migration/plan", fd2);
      setPlan(pl.data.data);
      setMonth((p.data.data.months ?? []).slice(-2, -1)[0]?.slice(0, 7) ?? "");
      setStep("review");
    } catch (err: unknown) {
      toast.error("Could not read that workbook", errorMessage(err));
      setFile(null);
    } finally { setBusy(null); }
  };

  const commit = async () => {
    if (!confirm(
      "Write the workbook into the portal?\n\n" +
      "This creates the landlords, properties, rooms, tenants, contracts and " +
      "opening balances. It is safe to run twice — anything already there is " +
      "reused — but take a backup first if this database has real data in it."
    )) return;
    setBusy("commit");
    try {
      const overrides = JSON.stringify({ property_names: names });
      const r = await api.post("/migration/commit",
        form({ overrides, confirm_existing: "true" }),
        { timeout: 600_000 });
      setResult(r.data.data.created);
      setStep("done");
      toast.success("Migration complete", r.data.message ?? "");
      await reconcile();
    } catch (err: unknown) {
      toast.error("Migration failed — nothing was written", errorMessage(err));
    } finally { setBusy(null); }
  };

  const reconcile = async () => {
    setBusy("reconcile");
    try {
      const r = await api.post("/migration/reconcile",
        form(month ? { month } : {}), { timeout: 600_000 });
      setReport(r.data.data);
    } catch (err: unknown) {
      toast.error("Could not reconcile", errorMessage(err));
    } finally { setBusy(null); }
  };

  const blockers = (plan?.problems ?? []).filter((p) => p.severity === "blocker");
  const warnings = (plan?.problems ?? []).filter((p) => p.severity !== "blocker");

  return (
    <Can perm="settings.manage" fallback={
      <div className="glass rounded-xl p-6 text-sm">
        Only an operator with <span className="font-mono">settings.manage</span> can
        run the migration.
      </div>
    }>
      <div className="space-y-6 animate-fade-in">
        <div>
          <h1 className="text-2xl lg:text-3xl font-semibold tracking-tight">
            Move off the workbook
          </h1>
          <p className="text-sm text-muted-foreground">
            Read the master file, check what was understood, then write it in.
            Nothing is saved until you press the last button.
          </p>
        </div>

        <Steps step={step} />

        {step === "choose" && (
          <label className="glass rounded-xl flex flex-col items-center justify-center gap-2 border-2 border-dashed border-border p-10 cursor-pointer hover:bg-accent/20">
            <FileSpreadsheet className="h-9 w-9 text-muted-foreground" />
            <div className="text-sm font-medium">
              {busy === "parse" ? "Reading…" : "Choose the master workbook (.xlsm)"}
            </div>
            <div className="text-xs text-muted-foreground max-w-md text-center">
              The file with the <span className="font-mono">New-2026</span> and{" "}
              <span className="font-mono">LANDLOARD</span> sheets. It is read in
              memory and never stored.
            </div>
            <input ref={inputRef} type="file" accept=".xlsm,.xlsx" className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) void read(f);
                e.currentTarget.value = "";
              }} />
          </label>
        )}

        {step !== "choose" && parsed && plan && (
          <>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <Tile icon={Building2} label="Properties" value={plan.summary.properties} />
              <Tile icon={Users} label="Tenancies" value={plan.summary.contracts} />
              <Tile icon={Wallet} label="Old debts" value={plan.summary.receivables} />
              <Tile icon={FileSpreadsheet} label="Rooms" value={plan.summary.units} />
            </div>

            {blockers.length > 0 && (
              <Panel tone="rose" icon={AlertTriangle}
                title={`${blockers.length} thing(s) must be fixed in the workbook first`}>
                <ul className="space-y-1 text-xs">
                  {blockers.map((p, i) => (
                    <li key={i}>
                      <span className="font-mono text-muted-foreground">{p.where}</span>{" "}
                      {p.detail}
                    </li>
                  ))}
                </ul>
              </Panel>
            )}

            {warnings.length > 0 && (
              <Panel tone="amber" icon={Info}
                title={`${warnings.length} thing(s) worth checking`}>
                <p className="text-xs text-muted-foreground mb-2">
                  None of these stop the migration. They are places where the
                  workbook was ambiguous and a choice was made for you.
                </p>
                <ul className="space-y-1 text-xs max-h-56 overflow-y-auto">
                  {warnings.map((p, i) => (
                    <li key={i}>
                      <span className="font-mono text-muted-foreground">{p.where}</span>{" "}
                      {p.detail}
                    </li>
                  ))}
                </ul>
              </Panel>
            )}

            {step === "review" && (
              <div className="glass rounded-xl p-4 space-y-3">
                <div>
                  <h2 className="text-sm font-semibold">Properties to create</h2>
                  <p className="text-xs text-muted-foreground">
                    Names are taken from the block headings. Rename any of them
                    now — this is what the staff will see everywhere afterwards.
                  </p>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead className="text-left text-xs text-muted-foreground border-b border-border">
                      <tr>
                        <th className="py-2 pr-3">Name in the portal</th>
                        <th className="py-2 pr-3">Workbook heading</th>
                        <th className="py-2 pr-3">Landlord</th>
                        <th className="py-2 pr-3 text-right">Rooms</th>
                        <th className="py-2 pr-3 text-right">Tenancies</th>
                      </tr>
                    </thead>
                    <tbody>
                      {plan.blocks.map((b) => (
                        <tr key={b.index} className="border-b border-border/60">
                          <td className="py-1.5 pr-3">
                            <input className={inputClass + " h-8 w-40"}
                              value={names[b.index] ?? b.property_name}
                              onChange={(e) => setNames((n) =>
                                ({ ...n, [b.index]: e.target.value }))} />
                          </td>
                          <td className="py-1.5 pr-3 text-xs text-muted-foreground max-w-xs truncate">
                            {b.title}
                          </td>
                          <td className="py-1.5 pr-3 text-xs">
                            {b.landlord_name}
                            {b.landlord_match !== "exact" && (
                              <span className="ml-1 rounded-full bg-amber-500/10 text-amber-600 px-1.5 py-0.5 text-[10px]">
                                {b.landlord_match === "fuzzy" ? "guessed" : "new"}
                              </span>
                            )}
                          </td>
                          <td className="py-1.5 pr-3 text-right">{b.rooms + b.stores}</td>
                          <td className="py-1.5 pr-3 text-right">{b.tenants.length}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                <div className="flex items-center justify-between gap-2 pt-2 border-t border-border">
                  <button onClick={() => { setStep("choose"); setFile(null); setParsed(null); }}
                    className="h-9 rounded-md border border-border bg-card/60 px-3 text-sm">
                    Choose another file
                  </button>
                  <button onClick={commit} disabled={busy !== null || blockers.length > 0}
                    className="h-9 inline-flex items-center gap-2 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50">
                    <Play className="h-4 w-4" />
                    {busy === "commit" ? "Writing…" : "Write it in"}
                  </button>
                </div>
              </div>
            )}
          </>
        )}

        {step === "done" && result && (
          <Panel tone="emerald" icon={CheckCircle2} title="Migration complete">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
              {Object.entries(result).filter(([, v]) => v > 0).map(([k, v]) => (
                <div key={k} className="rounded-md border border-border bg-card/40 p-2">
                  <div className="text-muted-foreground capitalize">
                    {k.replaceAll("_", " ")}
                  </div>
                  <div className="text-base font-semibold">{v}</div>
                </div>
              ))}
            </div>
          </Panel>
        )}

        {step === "done" && (
          <div className="glass rounded-xl p-4 space-y-3">
            <div className="flex items-end justify-between gap-2 flex-wrap">
              <div>
                <h2 className="text-sm font-semibold inline-flex items-center gap-2">
                  <Scale className="h-4 w-4 text-primary" /> The parallel run
                </h2>
                <p className="text-xs text-muted-foreground">
                  The portal&apos;s figures beside the workbook&apos;s own, for one
                  month. This is the check that decides whether the spreadsheet
                  can be retired.
                </p>
              </div>
              <div className="flex items-center gap-2">
                <input type="month" className={inputClass + " w-auto"} value={month}
                  onChange={(e) => setMonth(e.target.value)} />
                <button onClick={reconcile} disabled={busy !== null}
                  className="h-9 rounded-md border border-border bg-card/60 px-3 text-sm hover:bg-accent disabled:opacity-60">
                  {busy === "reconcile" ? "Comparing…" : "Compare"}
                </button>
              </div>
            </div>

            {report && (
              <>
                <div className={"rounded-lg border p-3 text-sm " +
                  (report.summary.differing === 0
                    ? "border-emerald-500/40 bg-emerald-500/5"
                    : "border-amber-500/40 bg-amber-500/5")}>
                  {report.summary.differing === 0
                    ? `Every one of the ${report.summary.matching} figures checked for ${report.month.slice(0, 7)} agrees with the workbook.`
                    : `${report.summary.differing} of ${report.summary.checked} figures differ. Each one is shown below with both numbers.`}
                </div>
                <Comparison title="Company" lines={report.company} />
                <Comparison title="Profit by property" lines={report.properties} />
              </>
            )}
          </div>
        )}
      </div>
    </Can>
  );
}

function Steps({ step }: { step: Step }) {
  const items: { key: Step; label: string }[] = [
    { key: "choose", label: "Read the file" },
    { key: "review", label: "Check what was understood" },
    { key: "done", label: "Write it in and compare" },
  ];
  const order = items.findIndex((i) => i.key === step);
  return (
    <div className="flex items-center gap-2 text-xs">
      {items.map((item, i) => (
        <div key={item.key} className="inline-flex items-center gap-2">
          <span className={"rounded-full px-2.5 py-1 " +
            (i <= order ? "bg-primary/10 text-primary" : "bg-muted text-muted-foreground")}>
            {i + 1}. {item.label}
          </span>
          {i < items.length - 1 && <ArrowRight className="h-3 w-3 text-muted-foreground" />}
        </div>
      ))}
    </div>
  );
}

function Tile({ icon: Icon, label, value }: {
  icon: typeof Building2; label: string; value: number | undefined;
}) {
  return (
    <div className="glass rounded-xl p-4">
      <div className="flex items-center justify-between">
        <span className="text-sm text-muted-foreground">{label}</span>
        <Icon className="h-4 w-4 text-muted-foreground" />
      </div>
      <div className="mt-1 text-2xl font-semibold">{value ?? 0}</div>
    </div>
  );
}

function Panel({ tone, icon: Icon, title, children }: {
  tone: "rose" | "amber" | "emerald";
  icon: typeof Info; title: string; children: React.ReactNode;
}) {
  const cls = {
    rose: "border-rose-500/40 bg-rose-500/5 text-rose-700 dark:text-rose-400",
    amber: "border-amber-500/40 bg-amber-500/5 text-amber-700 dark:text-amber-500",
    emerald: "border-emerald-500/40 bg-emerald-500/5 text-emerald-700 dark:text-emerald-400",
  }[tone];
  return (
    <div className={"rounded-xl border p-4 space-y-2 " + cls}>
      <div className="text-sm font-medium inline-flex items-center gap-2">
        <Icon className="h-4 w-4" /> {title}
      </div>
      <div className="text-foreground">{children}</div>
    </div>
  );
}

function Comparison({ title, lines }: { title: string; lines: Line[] }) {
  return (
    <div>
      <div className="text-xs font-medium text-muted-foreground mb-1">{title}</div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-left text-xs text-muted-foreground border-b border-border">
            <tr>
              <th className="py-1.5 pr-3">Line</th>
              <th className="py-1.5 pr-3 text-right">Workbook</th>
              <th className="py-1.5 pr-3 text-right">Portal</th>
              <th className="py-1.5 pr-3 text-right">Difference</th>
              <th className="py-1.5 pr-3"></th>
            </tr>
          </thead>
          <tbody>
            {lines.map((l) => (
              <tr key={l.label} className="border-b border-border/60">
                <td className="py-1.5 pr-3">{l.label}</td>
                <td className="py-1.5 pr-3 text-right">
                  {l.workbook === null ? "—" : money(l.workbook)}
                </td>
                <td className="py-1.5 pr-3 text-right">
                  {l.app === null ? "—" : money(l.app)}
                </td>
                <td className={"py-1.5 pr-3 text-right " +
                  (l.matches === false ? "text-rose-600 font-medium" : "")}>
                  {l.difference === null ? "—" : money(l.difference)}
                </td>
                <td className="py-1.5 pr-3">
                  {l.matches === null ? (
                    <span className="text-xs text-muted-foreground">not in the sheet</span>
                  ) : l.matches ? (
                    <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                  ) : (
                    <AlertTriangle className="h-4 w-4 text-rose-600" />
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
