"use client";

import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  ToggleLeft, ToggleRight, Save, KeyRound, RefreshCw,
  Building2, Settings as Cog, Tag, Hash, CheckSquare, Bell, Mail,
  Palette, FileUp, Lock, HardDrive, ClipboardList, Send, Sparkles,
} from "lucide-react";
import { api } from "@/lib/api";
import { Can } from "@/components/can";
import { CompanyLogoUploader } from "@/components/company-logo-uploader";
import { BackupPanel } from "@/components/backup-panel";
import { NotificationRulesPanel, ConnectionTest } from "@/components/notification-rules-panel";
import { PropertyTypesPanel } from "@/components/property-types-panel";
import { UnitTypesPanel } from "@/components/unit-types-panel";
import { ExpenseCategoriesPanel } from "@/components/expense-categories-panel";
import { inputClass, selectClass, textareaClass } from "@/components/ui/dialog";
import { toast, errorMessage } from "@/components/ui/toast";

type FieldType = "string" | "textarea" | "bool" | "int" | "select" | "password";

type Setting = {
  key: string;
  label: string;
  type: FieldType;
  description: string | null;
  help: string | null;
  options: { value: string; label: string }[] | null;
  is_secret: boolean;
  value: unknown;
  is_set?: boolean;
};

type Section = {
  category: string;
  label: string;
  settings: Setting[];
};

const CATEGORY_ICON: Record<string, typeof Cog> = {
  company: Building2,
  property: Cog,
  expense: Tag,
  numbering: Hash,
  approval: CheckSquare,
  alerts: Bell,
  email: Mail,
  ui: Palette,
  import: FileUp,
  security: Lock,
  backup: HardDrive,
  audit: ClipboardList,
  notifications: Bell,
  telegram: Send,
  ai: Sparkles,
};

export default function SettingsPage() {
  const searchParams = useSearchParams();
  const [sections, setSections] = useState<Section[]>([]);
  const [activeTab, setActiveTab] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<Record<string, Record<string, unknown>>>({});
  const [savingCategory, setSavingCategory] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const r = await api.get("/settings/catalog");
      const fresh: Section[] = r.data.data.sections;
      setSections(fresh);
      const wanted = searchParams.get("tab");
      const initial = (wanted && fresh.some((s) => s.category === wanted))
        ? wanted : (fresh[0]?.category ?? null);
      setActiveTab((prev) => prev ?? initial);
    } finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []);  // eslint-disable-line react-hooks/exhaustive-deps

  const active = useMemo(
    () => sections.find((s) => s.category === activeTab) ?? null,
    [sections, activeTab],
  );

  const get = (key: string, fallback: unknown): unknown => {
    if (!active) return fallback;
    const local = drafts[active.category]?.[key];
    if (local !== undefined) return local;
    return fallback;
  };

  const setDraft = (key: string, value: unknown) => {
    if (!active) return;
    setDrafts((d) => ({
      ...d,
      [active.category]: { ...(d[active.category] ?? {}), [key]: value },
    }));
  };

  const isDirty = active ? Object.keys(drafts[active.category] ?? {}).length > 0 : false;

  const save = async () => {
    if (!active || !isDirty) return;
    setSavingCategory(active.category);
    try {
      await api.put("/settings", { settings: drafts[active.category] });
      setDrafts((d) => {
        const copy = { ...d };
        delete copy[active.category];
        return copy;
      });
      toast.success(`${active.label} settings saved`);
      await load();
    } catch (err: unknown) {
      toast.error("Save failed", errorMessage(err));
    } finally {
      setSavingCategory(null);
    }
  };

  const reset = () => {
    if (!active) return;
    setDrafts((d) => {
      const copy = { ...d };
      delete copy[active.category];
      return copy;
    });
  };

  if (loading) return <div className="text-sm text-muted-foreground animate-pulse">Loading settings…</div>;

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h1 className="text-2xl lg:text-3xl font-semibold tracking-tight">System Settings</h1>
        <p className="text-sm text-muted-foreground">
          Company branding, defaults, approval workflow, alerts, email, UI, security, backup and audit configuration.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[220px_1fr] gap-4">
        <aside className="glass rounded-xl p-2 h-fit">
          <ul className="space-y-1">
            {sections.map((s) => {
              const Icon = CATEGORY_ICON[s.category] ?? Cog;
              const dirty = (drafts[s.category] && Object.keys(drafts[s.category]).length > 0) ?? false;
              const isActive = s.category === activeTab;
              return (
                <li key={s.category}>
                  <button
                    onClick={() => setActiveTab(s.category)}
                    className={
                      "w-full inline-flex items-center gap-2 rounded-md px-3 py-2 text-sm " +
                      (isActive
                        ? "bg-primary/10 text-primary"
                        : "text-muted-foreground hover:bg-accent hover:text-foreground")
                    }
                  >
                    <Icon className="h-4 w-4" />
                    <span className="flex-1 text-left">{s.label}</span>
                    {dirty && <span className="h-2 w-2 rounded-full bg-amber-500" />}
                  </button>
                </li>
              );
            })}
          </ul>
        </aside>

        <section className="glass rounded-xl p-4 space-y-4">
          {!active ? (
            <div className="text-sm text-muted-foreground">Select a category.</div>
          ) : (
            <>
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h2 className="text-lg font-semibold">{active.label}</h2>
                  <p className="text-xs text-muted-foreground">
                    {active.settings.length} setting{active.settings.length === 1 ? "" : "s"} in this category.
                  </p>
                </div>
                <Can perm="settings.manage">
                  <div className="flex items-center gap-2">
                    {isDirty && (
                      <button onClick={reset}
                        className="h-9 inline-flex items-center gap-1 rounded-md border border-border bg-card/60 px-3 text-xs hover:bg-accent">
                        <RefreshCw className="h-3.5 w-3.5" /> Reset
                      </button>
                    )}
                    <button onClick={save} disabled={!isDirty || savingCategory === active.category}
                      className="h-9 inline-flex items-center gap-1 rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-60">
                      <Save className="h-4 w-4" />
                      {savingCategory === active.category ? "Saving…" : "Save changes"}
                    </button>
                  </div>
                </Can>
              </div>


              <div className="space-y-3">
                {active.category === "company" && <CompanyLogoUploader />}
                {active.settings
                  .filter((s) => !(active.category === "company" && s.key === "company.logo_url"))
                  .map((s) => (
                    <Field key={s.key} setting={s}
                      value={get(s.key, s.value)}
                      onChange={(v) => setDraft(s.key, v)}
                    />
                  ))}
                {active.category === "property" && (
                  <>
                    <PropertyTypesPanel />
                    <UnitTypesPanel />
                  </>
                )}
                {active.category === "expense" && <ExpenseCategoriesPanel />}
                {active.category === "backup" && <BackupPanel />}
                {active.category === "email" && <ConnectionTest kind="email" />}
                {active.category === "telegram" && <ConnectionTest kind="telegram" />}
                {active.category === "ai" && <ConnectionTest kind="ai" />}
                {active.category === "notifications" && <NotificationRulesPanel />}
              </div>
            </>
          )}
        </section>
      </div>
    </div>
  );
}

function Field({ setting, value, onChange }: {
  setting: Setting; value: unknown; onChange: (v: unknown) => void;
}) {
  const id = `setting-${setting.key}`;
  return (
    <div className="rounded-lg border border-border bg-card/40 p-3 grid grid-cols-1 md:grid-cols-[1fr_minmax(220px,320px)] gap-3 items-start">
      <div>
        <label htmlFor={id} className="block text-sm font-medium">{setting.label}</label>
        {setting.description && (
          <div className="text-xs text-muted-foreground mt-0.5">{setting.description}</div>
        )}
        {setting.help && (
          <div className="text-[11px] text-muted-foreground mt-1 font-mono">{setting.help}</div>
        )}
        <div className="text-[10px] text-muted-foreground mt-1 font-mono">{setting.key}</div>
      </div>
      <div>
        <Input id={id} setting={setting} value={value} onChange={onChange} />
      </div>
    </div>
  );
}

function Input({ id, setting, value, onChange }: {
  id: string; setting: Setting; value: unknown; onChange: (v: unknown) => void;
}) {
  if (setting.type === "bool") {
    const on = Boolean(value);
    return (
      <Can perm="settings.manage" fallback={
        <div className="h-9 grid place-items-center text-muted-foreground">
          {on ? <ToggleRight className="h-6 w-6 text-primary" /> : <ToggleLeft className="h-6 w-6" />}
        </div>
      }>
        <button id={id} type="button" onClick={() => onChange(!on)}
          className="h-9 inline-flex items-center gap-2 rounded-md border border-border bg-card/60 px-3 text-sm hover:bg-accent">
          {on ? <ToggleRight className="h-5 w-5 text-primary" /> : <ToggleLeft className="h-5 w-5 text-muted-foreground" />}
          <span>{on ? "On" : "Off"}</span>
        </button>
      </Can>
    );
  }
  if (setting.type === "select" && setting.options) {
    return (
      <Can perm="settings.manage" fallback={<div className="text-sm text-muted-foreground">{String(value ?? "")}</div>}>
        <select id={id} className={selectClass} value={String(value ?? "")} onChange={(e) => onChange(e.target.value)}>
          {setting.options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
      </Can>
    );
  }
  if (setting.type === "textarea") {
    return (
      <Can perm="settings.manage" fallback={<div className="text-sm text-muted-foreground whitespace-pre-wrap">{String(value ?? "")}</div>}>
        <textarea id={id} className={textareaClass} value={String(value ?? "")} onChange={(e) => onChange(e.target.value)} />
      </Can>
    );
  }
  if (setting.type === "password") {
    return (
      <Can perm="settings.manage" fallback={<div className="text-sm text-muted-foreground">{setting.is_set ? "•••••• (set)" : "Not set"}</div>}>
        <div className="space-y-1">
          <div className="relative">
            <input id={id} type="password" className={inputClass + " pl-9"} placeholder={setting.is_set ? "•••••• (leave blank to keep)" : ""}
              value={typeof value === "string" ? value : ""} onChange={(e) => onChange(e.target.value)} />
            <KeyRound className="h-4 w-4 text-muted-foreground absolute left-3 top-1/2 -translate-y-1/2" />
          </div>
          <div className="text-[10px] text-muted-foreground">
            {setting.is_set ? "A value is set. Leave blank to keep it." : "No value set."}
          </div>
        </div>
      </Can>
    );
  }
  if (setting.type === "int") {
    return (
      <Can perm="settings.manage" fallback={<div className="text-sm text-muted-foreground">{String(value ?? "")}</div>}>
        <input id={id} type="number" className={inputClass} value={value === null || value === undefined ? "" : String(value)}
          onChange={(e) => onChange(e.target.value === "" ? "" : Number(e.target.value))} />
      </Can>
    );
  }
  // String fallthrough. Surfacing setting.help inside the input as a
  // placeholder makes it obvious where to type — the help line below the
  // field was being mistaken for the field itself on long-description
  // settings like backup.folder.
  return (
    <Can perm="settings.manage" fallback={
      <div className="h-9 px-3 grid items-center rounded-md border border-dashed border-border bg-muted/30 text-sm text-muted-foreground">
        {value ? String(value) : "(not set — read-only)"}
      </div>
    }>
      <input
        id={id}
        type="text"
        className={inputClass}
        value={String(value ?? "")}
        onChange={(e) => onChange(e.target.value)}
        placeholder={setting.help ?? ""}
      />
    </Can>
  );
}
