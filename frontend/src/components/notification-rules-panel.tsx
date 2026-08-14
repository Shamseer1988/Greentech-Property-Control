"use client";

import { useEffect, useState } from "react";
import {
  Bell, Mail, Send, Eye, Save, AlertTriangle, CheckCircle2, PlugZap,
} from "lucide-react";
import { api } from "@/lib/api";
import { Can } from "@/components/can";
import { inputClass, textareaClass } from "@/components/ui/dialog";
import { toast, errorMessage } from "@/components/ui/toast";

type Rule = {
  id: number;
  event: string;
  event_label: string;
  is_enabled: boolean;
  advance_days: number[];
  channels: string[];
  audiences: string[];
  extra_emails: string | null;
  staff_role_codes: string | null;
  subject_template: string | null;
  body_template: string | null;
};

type Meta = {
  channels: string[];
  audiences: string[];
  defaults: Record<string, { subject: string; body: string }>;
};

const CHANNEL_LABEL: Record<string, string> = {
  inapp: "In-app",
  email: "Email",
  telegram: "Telegram",
  push: "Browser push",
};

const AUDIENCE_LABEL: Record<string, string> = {
  staff: "Our staff",
  client: "The tenant",
  landlord: "The landlord",
};

/** Events where advance days count forward from the month start rather
 * than backward from a date — worth saying, because "7" means opposite
 * things on an expiry rule and a chase rule. */
const FORWARD_COUNTING = new Set(["rent_due"]);

export function NotificationRulesPanel() {
  const [rules, setRules] = useState<Rule[]>([]);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [loading, setLoading] = useState(true);
  const [openId, setOpenId] = useState<number | null>(null);
  const [drafts, setDrafts] = useState<Record<number, Partial<Rule>>>({});
  const [busy, setBusy] = useState<number | null>(null);
  const [preview, setPreview] = useState<{ rule: Rule; data: PreviewData } | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      const r = await api.get("/messaging/rules");
      setRules(r.data?.data ?? []);
      setMeta(r.data?.meta ?? null);
    } catch (err: unknown) {
      toast.error("Could not load the notification rules", errorMessage(err));
    } finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []);

  const draftOf = (rule: Rule): Rule => ({ ...rule, ...(drafts[rule.id] ?? {}) });
  const setDraft = (id: number, patch: Partial<Rule>) =>
    setDrafts((d) => ({ ...d, [id]: { ...(d[id] ?? {}), ...patch } }));
  const isDirty = (id: number) => Object.keys(drafts[id] ?? {}).length > 0;

  const save = async (rule: Rule) => {
    const body = draftOf(rule);
    setBusy(rule.id);
    try {
      await api.put(`/messaging/rules/${rule.id}`, {
        is_enabled: body.is_enabled,
        advance_days: body.advance_days,
        channels: body.channels,
        audiences: body.audiences,
        extra_emails: body.extra_emails,
        subject_template: body.subject_template,
        body_template: body.body_template,
      });
      toast.success(`${rule.event_label} saved`);
      setDrafts((d) => { const c = { ...d }; delete c[rule.id]; return c; });
      await load();
    } catch (err: unknown) {
      toast.error("Save failed", errorMessage(err));
    } finally { setBusy(null); }
  };

  const runPreview = async (rule: Rule) => {
    setBusy(rule.id);
    try {
      const r = await api.post(`/messaging/rules/${rule.id}/preview`, {});
      setPreview({ rule, data: r.data.data });
    } catch (err: unknown) {
      toast.error("Preview failed", errorMessage(err));
    } finally { setBusy(null); }
  };

  if (loading) {
    return <div className="text-sm text-muted-foreground animate-pulse">Loading rules…</div>;
  }

  return (
    <div className="space-y-4 pt-4 border-t border-border/60">
      <div>
        <h3 className="text-base font-semibold inline-flex items-center gap-2">
          <Bell className="h-4 w-4 text-primary" /> Notification rules
        </h3>
        <p className="text-xs text-muted-foreground mt-0.5">
          One rule per event. Each is off until you switch it on, and
          <span className="font-medium"> Preview</span> shows exactly who a rule
          would contact today without contacting them.
        </p>
      </div>

      <div className="space-y-2">
        {rules.map((raw) => {
          const rule = draftOf(raw);
          const open = openId === rule.id;
          return (
            <div key={rule.id}
              className={"rounded-lg border p-3 " +
                (rule.is_enabled ? "border-emerald-500/40 bg-emerald-500/5"
                  : "border-border bg-card/40")}>
              <div className="flex items-center justify-between gap-3 flex-wrap">
                <button onClick={() => setOpenId(open ? null : rule.id)}
                  className="text-left">
                  <div className="text-sm font-medium">{rule.event_label}</div>
                  <div className="text-[11px] text-muted-foreground">
                    {rule.is_enabled ? "On" : "Off"}
                    {rule.advance_days.length > 0 && (
                      <> · {FORWARD_COUNTING.has(rule.event) ? "day" : "day(s) before"}{" "}
                        {rule.advance_days.join(", ")}</>
                    )}
                    {rule.channels.length > 0 && (
                      <> · {rule.channels.map((c) => CHANNEL_LABEL[c] ?? c).join(", ")}</>
                    )}
                  </div>
                </button>
                <div className="flex items-center gap-2">
                  <label className="inline-flex items-center gap-1.5 text-xs cursor-pointer">
                    <input type="checkbox" checked={rule.is_enabled}
                      onChange={(e) => setDraft(rule.id, { is_enabled: e.target.checked })} />
                    Enabled
                  </label>
                  <button onClick={() => runPreview(raw)} disabled={busy === rule.id}
                    className="h-8 inline-flex items-center gap-1 rounded-md border border-border bg-card/60 px-2 text-xs hover:bg-accent disabled:opacity-60">
                    <Eye className="h-3.5 w-3.5" /> Preview
                  </button>
                  <button onClick={() => save(raw)}
                    disabled={!isDirty(rule.id) || busy === rule.id}
                    className="h-8 inline-flex items-center gap-1 rounded-md bg-primary px-2.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50">
                    <Save className="h-3.5 w-3.5" /> Save
                  </button>
                </div>
              </div>

              {open && (
                <div className="mt-3 pt-3 border-t border-border/60 grid grid-cols-1 md:grid-cols-2 gap-3">
                  <div className="space-y-1">
                    <label className="text-xs text-muted-foreground">
                      {FORWARD_COUNTING.has(rule.event)
                        ? "Days after the month starts (e.g. 7, 21)"
                        : "Days before (e.g. 60, 30, 7)"}
                    </label>
                    <input className={inputClass}
                      value={rule.advance_days.join(", ")}
                      onChange={(e) => setDraft(rule.id, {
                        advance_days: e.target.value.split(",")
                          .map((v) => parseInt(v.trim(), 10))
                          .filter((n) => Number.isFinite(n)),
                      })} />
                  </div>

                  <div className="space-y-1">
                    <label className="text-xs text-muted-foreground">Also email</label>
                    <input className={inputClass} placeholder="accounts@company.com"
                      value={rule.extra_emails ?? ""}
                      onChange={(e) => setDraft(rule.id, { extra_emails: e.target.value })} />
                  </div>

                  <Choices label="Channels" options={meta?.channels ?? []}
                    labels={CHANNEL_LABEL} selected={rule.channels}
                    onChange={(v) => setDraft(rule.id, { channels: v })} />
                  <Choices label="Who it goes to" options={meta?.audiences ?? []}
                    labels={AUDIENCE_LABEL} selected={rule.audiences}
                    onChange={(v) => setDraft(rule.id, { audiences: v })} />

                  <div className="md:col-span-2 space-y-1">
                    <label className="text-xs text-muted-foreground">
                      Subject — leave blank for the default
                    </label>
                    <input className={inputClass}
                      placeholder={meta?.defaults?.[rule.event]?.subject ?? ""}
                      value={rule.subject_template ?? ""}
                      onChange={(e) => setDraft(rule.id, { subject_template: e.target.value })} />
                  </div>
                  <div className="md:col-span-2 space-y-1">
                    <label className="text-xs text-muted-foreground">
                      Body — placeholders like {"{client_name}"} are filled in
                    </label>
                    <textarea className={textareaClass} rows={5}
                      placeholder={meta?.defaults?.[rule.event]?.body ?? ""}
                      value={rule.body_template ?? ""}
                      onChange={(e) => setDraft(rule.id, { body_template: e.target.value })} />
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {preview && (
        <PreviewDialog rule={preview.rule} data={preview.data}
          onClose={() => setPreview(null)} />
      )}
    </div>
  );
}

function Choices({ label, options, labels, selected, onChange }: {
  label: string;
  options: string[];
  labels: Record<string, string>;
  selected: string[];
  onChange: (next: string[]) => void;
}) {
  const toggle = (value: string) =>
    onChange(selected.includes(value)
      ? selected.filter((v) => v !== value)
      : [...selected, value]);
  return (
    <div className="space-y-1">
      <label className="text-xs text-muted-foreground">{label}</label>
      <div className="flex flex-wrap gap-1.5">
        {options.map((o) => (
          <button key={o} type="button" onClick={() => toggle(o)}
            className={"rounded-full px-2.5 py-1 text-xs border transition-colors " +
              (selected.includes(o)
                ? "border-primary bg-primary/10 text-primary"
                : "border-border bg-card/60 text-muted-foreground hover:bg-accent")}>
            {labels[o] ?? o}
          </button>
        ))}
      </div>
    </div>
  );
}

type PreviewData = {
  findings: number;
  results: { dedupe_key: string; deliveries: { channel: string; to: string }[] }[];
};

function PreviewDialog({ rule, data, onClose }: {
  rule: Rule; data: PreviewData; onClose: () => void;
}) {
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4">
      <div className="glass-strong w-full max-w-lg rounded-2xl p-5 space-y-3">
        <div>
          <h3 className="text-base font-semibold">{rule.event_label} — preview</h3>
          <p className="text-xs text-muted-foreground">
            What this rule would do today. Nothing has been sent or logged.
          </p>
        </div>

        {data.findings === 0 ? (
          <div className="rounded-lg border border-border bg-card/40 p-4 text-sm text-muted-foreground">
            Nothing matches today. That is normal — a rule only fires on the exact
            day something crosses one of its thresholds.
          </div>
        ) : (
          <div className="max-h-80 overflow-y-auto space-y-2">
            {data.results.map((r) => (
              <div key={r.dedupe_key} className="rounded-lg border border-border bg-card/40 p-2.5">
                <div className="font-mono text-[11px] text-muted-foreground">{r.dedupe_key}</div>
                {r.deliveries.length === 0 ? (
                  <div className="text-xs text-amber-600 inline-flex items-center gap-1 mt-1">
                    <AlertTriangle className="h-3 w-3" /> Nobody to send to — check
                    the channels and audience.
                  </div>
                ) : (
                  <ul className="mt-1 space-y-0.5">
                    {r.deliveries.map((d, i) => (
                      <li key={i} className="text-xs inline-flex items-center gap-1.5">
                        <Send className="h-3 w-3 text-muted-foreground" />
                        <span className="capitalize">{d.channel}</span>
                        <span className="text-muted-foreground">→ {d.to}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            ))}
          </div>
        )}

        <div className="flex justify-end">
          <button onClick={onClose}
            className="h-9 rounded-md border border-border bg-card/60 px-4 text-sm hover:bg-accent">
            Close
          </button>
        </div>
      </div>
    </div>
  );
}

/** Prove a channel's credentials work, without involving a client. */
export function ConnectionTest({ kind }: { kind: "email" | "telegram" | "ai" }) {
  const [to, setTo] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null);

  const run = async () => {
    setBusy(true);
    setResult(null);
    try {
      const body = kind === "email" ? { to } : {};
      const r = await api.post(`/messaging/test/${kind}`, body);
      setResult({ ok: true, text: r.data?.data?.reply ?? r.data?.message ?? "Worked." });
    } catch (err: unknown) {
      setResult({ ok: false, text: errorMessage(err) });
    } finally { setBusy(false); }
  };

  const label = kind === "email" ? "Send a test email"
    : kind === "telegram" ? "Post a test message"
      : "Test the AI connection";

  return (
    <Can perm="settings.manage">
      <div className="pt-4 mt-2 border-t border-border/60 space-y-2">
        <div className="text-sm font-medium inline-flex items-center gap-2">
          {kind === "email" ? <Mail className="h-4 w-4 text-primary" />
            : <PlugZap className="h-4 w-4 text-primary" />}
          {label}
        </div>
        <p className="text-xs text-muted-foreground">
          {kind === "email"
            ? "Goes to the address you type here, whatever the send switch is set to — so you can check the settings before turning sending on."
            : "Uses the credentials above without changing anything."}
        </p>
        <div className="flex items-center gap-2 flex-wrap">
          {kind === "email" && (
            <input className={inputClass + " max-w-xs"} type="email"
              placeholder="you@company.com" value={to}
              onChange={(e) => setTo(e.target.value)} />
          )}
          <button onClick={run} disabled={busy || (kind === "email" && !to)}
            className="h-9 rounded-md border border-border bg-card/60 px-3 text-sm hover:bg-accent disabled:opacity-60">
            {busy ? "Testing…" : "Test"}
          </button>
        </div>
        {result && (
          <div className={"rounded-lg border p-2.5 text-xs inline-flex items-start gap-1.5 " +
            (result.ok ? "border-emerald-500/40 bg-emerald-500/5 text-emerald-700 dark:text-emerald-400"
              : "border-rose-500/40 bg-rose-500/5 text-rose-700 dark:text-rose-400")}>
            {result.ok ? <CheckCircle2 className="h-3.5 w-3.5 mt-0.5 shrink-0" />
              : <AlertTriangle className="h-3.5 w-3.5 mt-0.5 shrink-0" />}
            <span>{result.text}</span>
          </div>
        )}
      </div>
    </Can>
  );
}
