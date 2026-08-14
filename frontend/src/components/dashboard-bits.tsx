"use client";

import Link from "next/link";
import type { LucideIcon } from "lucide-react";
import { money } from "@/lib/contract-types";

/** Small shared pieces for the entity dashboards, so the property,
 * client and landlord pages read as one family rather than three
 * separately-invented layouts. */

export function Stat({ label, value, sub, icon: Icon, tone, href }: {
  label: string;
  value: string | number;
  sub?: string;
  icon?: LucideIcon;
  tone?: "emerald" | "amber" | "rose";
  href?: string;
}) {
  const toneCls =
    tone === "emerald" ? "text-emerald-600" :
    tone === "amber" ? "text-amber-600" :
    tone === "rose" ? "text-rose-600" : "";
  const body = (
    <>
      <div className="flex items-center justify-between">
        <span className="text-sm text-muted-foreground">{label}</span>
        {Icon && <Icon className="h-4 w-4 text-muted-foreground" />}
      </div>
      <div className={"mt-1 text-xl font-semibold " + toneCls}>{value}</div>
      {sub && <div className="mt-0.5 text-xs text-muted-foreground">{sub}</div>}
    </>
  );
  const cls = "glass rounded-xl p-4 block " +
    (href ? "hover:bg-accent/30 transition-colors" : "");
  return href ? <Link href={href} className={cls}>{body}</Link>
    : <div className={cls}>{body}</div>;
}

export function Section({ title, action, children }: {
  title: string; action?: React.ReactNode; children: React.ReactNode;
}) {
  return (
    <div className="glass rounded-xl p-4 space-y-3">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-sm font-semibold">{title}</h2>
        {action}
      </div>
      {children}
    </div>
  );
}

export function EmptyRow({ children }: { children: React.ReactNode }) {
  return <div className="py-6 text-center text-sm text-muted-foreground">{children}</div>;
}

export function Money({ value, signed }: { value: number; signed?: boolean }) {
  const cls = !signed ? "" : value >= 0 ? "text-emerald-600" : "text-rose-600";
  return <span className={cls}>{money(value)}</span>;
}

/** Days-left pill, red once overdue, amber inside a month. */
export function DaysPill({ days }: { days: number }) {
  const cls = days < 0 ? "bg-rose-500/10 text-rose-600"
    : days <= 30 ? "bg-amber-500/10 text-amber-600"
      : days <= 60 ? "bg-sky-500/10 text-sky-600"
        : "bg-muted text-muted-foreground";
  return (
    <span className={"rounded-full px-2 py-0.5 text-xs whitespace-nowrap " + cls}>
      {days < 0 ? `${-days}d overdue` : `${days}d left`}
    </span>
  );
}
