"use client";

import { Fragment, useCallback, useEffect, useState } from "react";
import {
  Mail, Send, ChevronDown, ChevronRight, RotateCcw, PlayCircle, Eye,
  CheckCircle2, AlertTriangle, MinusCircle, Clock,
} from "lucide-react";
import { api } from "@/lib/api";
import { Can } from "@/components/can";
import { inputClass, selectClass } from "@/components/ui/dialog";
import { toast, errorMessage } from "@/components/ui/toast";

type Message = {
  id: number;
  channel: string;
  event: string | null;
  entity_type: string | null;
  entity_id: number | null;
  to_address: string | null;
  to_name: string | null;
  subject: string | null;
  body: string | null;
  status: string;
  error: string | null;
  sent_at: string | null;
  attempts: number;
  is_manual: boolean;
  created_at: string;
};

const STATUS_TONE: Record<string, string> = {
  sent: "bg-emerald-500/10 text-emerald-600",
  queued: "bg-sky-500/10 text-sky-600",
  skipped: "bg-muted text-muted-foreground",
  failed: "bg-rose-500/10 text-rose-600",
};

const STATUS_ICON: Record<string, typeof Mail> = {
  sent: CheckCircle2,
  queued: Clock,
  skipped: MinusCircle,
  failed: AlertTriangle,
};

/**
 * Everything the portal has said on the company's behalf — what went
 * out, what was only composed, and what failed and why. A "skipped" row
 * is not a fault: it is the draft the portal would have sent had
 * sending been switched on.
 */
export default function MessagesPage() {
  const [rows, setRows] = useState<Message[]>([]);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [channel, setChannel] = useState("");
  const [status, setStatus] = useState("");
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState<number | null>(null);
  const [busy, setBusy] = useState<number | null>(null);
  const [sweeping, setSweeping] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, string> = { limit: "300" };
      if (channel) params.channel = channel;
      if (status) params.status = status;
      const r = await api.get("/messaging/messages", { params });
      setRows(r.data?.data ?? []);
      setCounts(r.data?.meta?.status_counts ?? {});
    } catch (err: unknown) {
      toast.error("Could not load the message log", errorMessage(err));
    } finally { setLoading(false); }
  }, [channel, status]);

  useEffect(() => { load(); }, [load]);

  const sweep = async (dryRun: boolean) => {
    if (!dryRun && !confirm(
      "Run the notification sweep now?\n\n" +
      "Any rule that is switched on will send for real to whoever it is " +
      "addressed to. Use Preview first if you are not sure."
    )) return;
    setSweeping(true);
    try {
      const r = await api.post("/messaging/sweep", { dry_run: dryRun });
      const data = r.data?.data;
      toast.success(
        dryRun ? "Preview complete" : "Sweep complete",
        `${data?.findings ?? 0} finding(s) across ${data?.rules_evaluated ?? 0} rule(s)`);
      if (!dryRun) await load();
    } catch (err: unknown) {
      toast.error("Sweep failed", errorMessage(err));
    } finally { setSweeping(false); }
  };

  const retry = async (message: Message) => {
    setBusy(message.id);
    try {
      const r = await api.post(`/messaging/messages/${message.id}/retry`);
      toast.success(r.data?.message ?? "Retried");
      await load();
    } catch (err: unknown) {
      toast.error("Retry failed", errorMessage(err));
    } finally { setBusy(null); }
  };

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-end justify-between flex-wrap gap-2">
        <div>
          <h1 className="text-2xl lg:text-3xl font-semibold tracking-tight">Messages</h1>
          <p className="text-sm text-muted-foreground">
            Every reminder and email the portal has sent — or would have sent,
            if sending is still switched off.
          </p>
        </div>
        <Can perm="notification.send">
          <div className="flex items-center gap-2">
            <button onClick={() => sweep(true)} disabled={sweeping}
              className="h-9 inline-flex items-center gap-1.5 rounded-md border border-border bg-card/60 px-3 text-sm hover:bg-accent disabled:opacity-60">
              <Eye className="h-4 w-4" /> Preview sweep
            </button>
            <button onClick={() => sweep(false)} disabled={sweeping}
              className="h-9 inline-flex items-center gap-1.5 rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-60">
              <PlayCircle className="h-4 w-4" />
              {sweeping ? "Running…" : "Run sweep now"}
            </button>
          </div>
        </Can>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {(["sent", "queued", "skipped", "failed"] as const).map((s) => {
          const Icon = STATUS_ICON[s];
          return (
            <button key={s} onClick={() => setStatus(status === s ? "" : s)}
              className={"glass rounded-xl p-4 text-left transition-colors " +
                (status === s ? "ring-1 ring-primary" : "hover:bg-accent/30")}>
              <div className="flex items-center justify-between">
                <span className="text-sm text-muted-foreground capitalize">{s}</span>
                <Icon className="h-4 w-4 text-muted-foreground" />
              </div>
              <div className="mt-1 text-2xl font-semibold">{counts[s] ?? 0}</div>
            </button>
          );
        })}
      </div>

      <div className="glass rounded-xl p-4">
        <div className="flex items-end gap-2 flex-wrap mb-3">
          <label className="flex flex-col gap-1">
            <span className="text-[11px] text-muted-foreground">Channel</span>
            <select className={selectClass + " !w-auto"} value={channel}
              onChange={(e) => setChannel(e.target.value)}>
              <option value="">All</option>
              <option value="email">Email</option>
              <option value="telegram">Telegram</option>
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-[11px] text-muted-foreground">Status</span>
            <select className={selectClass + " !w-auto"} value={status}
              onChange={(e) => setStatus(e.target.value)}>
              <option value="">All</option>
              <option value="sent">Sent</option>
              <option value="queued">Queued</option>
              <option value="skipped">Skipped</option>
              <option value="failed">Failed</option>
            </select>
          </label>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-muted-foreground border-b border-border">
              <tr>
                <th className="py-2 pr-2 w-6"></th>
                <th className="py-2 pr-3">When</th>
                <th className="py-2 pr-3">Channel</th>
                <th className="py-2 pr-3">To</th>
                <th className="py-2 pr-3">Subject</th>
                <th className="py-2 pr-3">Event</th>
                <th className="py-2 pr-3">Status</th>
                <th className="py-2 pr-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={8} className="py-10 text-center text-muted-foreground">
                  Loading…
                </td></tr>
              ) : rows.length === 0 ? (
                <tr><td colSpan={8} className="py-10 text-center text-muted-foreground">
                  Nothing has been sent yet. Switch a rule on in{" "}
                  <span className="font-medium">Settings → Notifications</span>.
                </td></tr>
              ) : rows.map((m) => {
                const isOpen = open === m.id;
                return (
                  <Fragment key={m.id}>
                    <tr onClick={() => setOpen(isOpen ? null : m.id)}
                      className="border-b border-border/60 hover:bg-accent/30 cursor-pointer">
                      <td className="py-2 pr-2 text-muted-foreground">
                        {isOpen ? <ChevronDown className="h-3.5 w-3.5" />
                          : <ChevronRight className="h-3.5 w-3.5" />}
                      </td>
                      <td className="py-2 pr-3 font-mono text-xs whitespace-nowrap">
                        {(m.sent_at ?? m.created_at)?.slice(0, 16).replace("T", " ")}
                      </td>
                      <td className="py-2 pr-3 capitalize">{m.channel}</td>
                      <td className="py-2 pr-3">
                        <div className="truncate max-w-[16rem]">{m.to_name ?? m.to_address ?? "—"}</div>
                        {m.to_name && (
                          <div className="text-[11px] text-muted-foreground truncate max-w-[16rem]">
                            {m.to_address}
                          </div>
                        )}
                      </td>
                      <td className="py-2 pr-3 max-w-sm truncate">{m.subject ?? "—"}</td>
                      <td className="py-2 pr-3 text-xs text-muted-foreground">
                        {m.is_manual ? "manual" : (m.event ?? "—")}
                      </td>
                      <td className="py-2 pr-3">
                        <span className={"rounded-full px-2 py-0.5 text-xs " +
                          (STATUS_TONE[m.status] ?? "bg-muted text-muted-foreground")}>
                          {m.status}
                        </span>
                      </td>
                      <td className="py-2 pr-3 text-right">
                        {m.status !== "sent" && (
                          <Can perm="notification.send">
                            <button disabled={busy === m.id}
                              onClick={(e) => { e.stopPropagation(); retry(m); }}
                              className="inline-flex items-center gap-1 text-xs rounded-md border border-border px-2 py-1 hover:bg-accent disabled:opacity-60">
                              <RotateCcw className="h-3 w-3" /> Retry
                            </button>
                          </Can>
                        )}
                      </td>
                    </tr>
                    {isOpen && (
                      <tr className="border-b border-border/60 bg-card/30">
                        <td colSpan={8} className="p-3 space-y-2">
                          {m.error && (
                            <div className="rounded-lg border border-amber-500/40 bg-amber-500/5 p-2.5 text-xs">
                              {m.error}
                            </div>
                          )}
                          <pre className="rounded-md border border-border bg-card/40 p-3 text-xs whitespace-pre-wrap">
                            {m.body ?? "(no body)"}
                          </pre>
                          <div className="text-[11px] text-muted-foreground">
                            Attempt(s): {m.attempts}
                            {m.entity_type && ` · about ${m.entity_type} #${m.entity_id}`}
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
