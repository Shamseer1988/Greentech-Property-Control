"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import Link from "next/link";
import { Bell, X, AlertOctagon, AlertTriangle, Info, CheckCheck, MailOpen } from "lucide-react";
import { api } from "@/lib/api";
import {
  useNotificationsFeed, useUnreadCount, useMarkAllRead, useMarkRead,
} from "@/lib/use-notifications";

type ExpiringDoc = {
  attachment_id: number; entity_type: string; entity_name: string | null;
  category: string | null; doc_number: string | null; expiry_date: string; days_left: number;
};

type AlertsPayload = {
  critical: {
    expired_agreements: { agreement_id: number; property_id: number; property_name: string | null; expiry_date: string; days_left: number }[];
    expiring_within_7_days: { agreement_id: number; property_id: number; property_name: string | null; expiry_date: string; days_left: number }[];
    expired_documents: ExpiringDoc[];
  };
  warning: {
    expiring_within_30_days: { agreement_id: number; property_id: number; property_name: string | null; expiry_date: string; days_left: number }[];
    documents_expiring_within_30_days: ExpiringDoc[];
  };
  info: { maintenance_in_progress: { id: number; transaction_number: string; entity_type: string; entity_id: number }[] };
  counts: { critical: number; warning: number; info: number };
};

export function NotificationBell() {
  const [open, setOpen] = useState(false);
  const [mounted, setMounted] = useState(false);
  const [data, setData] = useState<AlertsPayload | null>(null);
  const [loading, setLoading] = useState(false);

  // Phase 8b: personal notifications feed alongside the global alerts.
  const feedQ = useNotificationsFeed();
  const unreadQ = useUnreadCount();
  const markRead = useMarkRead();
  const markAll = useMarkAllRead();
  const personalUnread = unreadQ.data ?? 0;

  const refresh = async () => {
    setLoading(true);
    try {
      const r = await api.get("/dashboard/alerts");
      setData(r.data.data);
    } catch {
      setData(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    setMounted(true);
    refresh();
    const t = setInterval(refresh, 60_000);
    return () => clearInterval(t);
  }, []);

  // Lock body scroll + close on Escape while the drawer is open.
  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = prev;
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const critical = data?.counts.critical ?? 0;
  const warning = data?.counts.warning ?? 0;
  const total = critical + warning + personalUnread;

  // The drawer renders through a portal to <body> so it escapes any ancestor
  // that creates a containing block for `position: fixed` — notably the
  // topbar's `backdrop-blur` (backdrop-filter creates a new containing block
  // and would otherwise clip a fixed-positioned child to the topbar).
  const drawer = open && mounted
    ? createPortal(
        <div className="fixed inset-0 z-[100]">
          <div
            className="absolute inset-0 bg-black/40"
            onClick={() => setOpen(false)}
            aria-hidden="true"
          />
          <aside
            role="dialog"
            aria-label="Alerts"
            className="absolute right-0 top-0 h-full w-full sm:w-96 bg-card border-l border-border shadow-2xl flex flex-col"
          >
            <div className="flex items-center justify-between p-4 border-b border-border">
              <div>
                <div className="text-sm font-semibold">Alerts</div>
                <div className="text-xs text-muted-foreground">{loading ? "Refreshing…" : "Auto-refreshes every minute"}</div>
              </div>
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="h-8 w-8 grid place-items-center rounded-md hover:bg-accent"
                aria-label="Close"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              {!data ? (
                <div className="text-sm text-muted-foreground">Unable to load alerts.</div>
              ) : (data.counts.critical + data.counts.warning + data.counts.info === 0) ? (
                <div className="text-sm text-muted-foreground text-center py-10">All clear</div>
              ) : (
                <>
                  {data.critical.expired_agreements.length + data.critical.expiring_within_7_days.length + data.critical.expired_documents.length > 0 && (
                    <Group title="Critical" icon={AlertOctagon} tone="rose">
                      {data.critical.expired_agreements.map((a) => (
                        <Row key={`exp-${a.agreement_id}`}>
                          <Link href={`/properties/${a.property_id}`} onClick={() => setOpen(false)} className="font-medium hover:text-primary">{a.property_name}</Link>
                          <div className="text-xs text-rose-600">Expired {Math.abs(a.days_left)}d ago · {a.expiry_date}</div>
                        </Row>
                      ))}
                      {data.critical.expiring_within_7_days.map((a) => (
                        <Row key={`7-${a.agreement_id}`}>
                          <Link href={`/properties/${a.property_id}`} onClick={() => setOpen(false)} className="font-medium hover:text-primary">{a.property_name}</Link>
                          <div className="text-xs text-rose-600">Expires in {a.days_left}d · {a.expiry_date}</div>
                        </Row>
                      ))}
                      {data.critical.expired_documents.map((d) => (
                        <Row key={`doc-${d.attachment_id}`}>
                          <span className="font-medium">{d.entity_name ?? d.entity_type}</span>
                          <div className="text-xs text-rose-600">
                            {(d.category ?? "document").replaceAll("_", " ")} expired {Math.abs(d.days_left)}d ago
                          </div>
                        </Row>
                      ))}
                    </Group>
                  )}
                  {data.warning.expiring_within_30_days.length + data.warning.documents_expiring_within_30_days.length > 0 && (
                    <Group title="Warning" icon={AlertTriangle} tone="amber">
                      {data.warning.expiring_within_30_days.map((a) => (
                        <Row key={`30-${a.agreement_id}`}>
                          <Link href={`/properties/${a.property_id}`} onClick={() => setOpen(false)} className="font-medium hover:text-primary">{a.property_name}</Link>
                          <div className="text-xs text-amber-600">Expires in {a.days_left}d</div>
                        </Row>
                      ))}
                      {data.warning.documents_expiring_within_30_days.map((d) => (
                        <Row key={`docw-${d.attachment_id}`}>
                          <span className="font-medium">{d.entity_name ?? d.entity_type}</span>
                          <div className="text-xs text-amber-600">
                            {(d.category ?? "document").replaceAll("_", " ")} expires in {d.days_left}d
                          </div>
                        </Row>
                      ))}
                    </Group>
                  )}
                  {data.info.maintenance_in_progress.length > 0 && (
                    <Group title="In progress" icon={Info} tone="sky">
                      {data.info.maintenance_in_progress.slice(0, 10).map((m) => (
                        <Row key={`m-${m.id}`}>
                          <span className="font-medium capitalize">{m.entity_type} #{m.entity_id}</span>
                          <div className="text-xs text-sky-600 font-mono">{m.transaction_number}</div>
                        </Row>
                      ))}
                    </Group>
                  )}
                </>
              )}

              {/* Phase 8b personal notifications. Separate from the
                  shared alerts because these are addressed at the
                  signed-in user specifically. */}
              {feedQ.data && feedQ.data.rows.length > 0 && (
                <div className="space-y-2 pt-2">
                  <div className="flex items-center justify-between">
                    <div className="text-xs uppercase tracking-wide font-medium inline-flex items-center gap-1.5 text-foreground">
                      <MailOpen className="h-3.5 w-3.5" /> Notifications
                      {personalUnread > 0 && (
                        <span className="rounded-full bg-primary/10 text-primary px-1.5 text-[10px]">
                          {personalUnread} new
                        </span>
                      )}
                    </div>
                    {personalUnread > 0 && (
                      <button
                        type="button"
                        onClick={() => markAll.mutate()}
                        disabled={markAll.isPending}
                        className="inline-flex items-center gap-1 text-[10px] text-muted-foreground hover:text-foreground"
                      >
                        <CheckCheck className="h-3 w-3" /> Mark all read
                      </button>
                    )}
                  </div>
                  <div className="space-y-1">
                    {feedQ.data.rows.slice(0, 10).map((n) => {
                      const body = (
                        <div className={
                          "rounded-md border border-border px-3 py-2 text-sm " +
                          (n.is_read ? "bg-card/30 opacity-70" : "bg-card/60")
                        }>
                          <div className="font-medium">{n.title}</div>
                          {n.body && <div className="text-xs text-muted-foreground mt-0.5">{n.body}</div>}
                        </div>
                      );
                      return (
                        <div
                          key={n.id}
                          onClick={() => !n.is_read && markRead.mutate(n.id)}
                          className="cursor-pointer"
                        >
                          {n.link ? (
                            <Link href={n.link} onClick={() => setOpen(false)}>{body}</Link>
                          ) : body}
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
            <div className="p-3 border-t border-border">
              <Link href="/alerts" onClick={() => setOpen(false)} className="block text-center text-sm rounded-md border border-border bg-card/60 hover:bg-accent py-2">
                View all alerts
              </Link>
            </div>
          </aside>
        </div>,
        document.body,
      )
    : null;

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-label="Open notifications"
        aria-expanded={open}
        className="relative inline-flex h-9 w-9 items-center justify-center rounded-md border border-border bg-card/60 hover:bg-accent"
      >
        <Bell className="h-4 w-4" />
        {total > 0 && (
          <span className={
            "absolute -top-1 -right-1 min-w-[18px] h-[18px] px-1 grid place-items-center rounded-full text-[10px] font-medium text-white " +
            (critical > 0 ? "bg-rose-500" : "bg-amber-500")
          }>
            {total > 99 ? "99+" : total}
          </span>
        )}
      </button>
      {drawer}
    </>
  );
}

function Group({ title, icon: Icon, tone, children }: {
  title: string; icon: typeof AlertOctagon; tone: "rose" | "amber" | "sky"; children: React.ReactNode;
}) {
  const cls = tone === "rose" ? "text-rose-600" : tone === "amber" ? "text-amber-600" : "text-sky-600";
  return (
    <div className="space-y-2">
      <div className={"text-xs uppercase tracking-wide font-medium inline-flex items-center gap-1.5 " + cls}>
        <Icon className="h-3.5 w-3.5" /> {title}
      </div>
      <div className="space-y-1">{children}</div>
    </div>
  );
}

function Row({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-md border border-border bg-card/40 px-3 py-2 text-sm">
      {children}
    </div>
  );
}
