"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuth } from "@/lib/auth-store";
import { api } from "@/lib/api";
import { useCompanyName, useCompanyLogo } from "@/lib/public-settings";
import { visibleNavGroups, activeNavHref } from "@/lib/nav";

const COLLAPSED_KEY = "greentech.sidebar.collapsed";

export function Sidebar() {
  const pathname = usePathname();
  const has = useAuth((s) => s.has);
  const [pendingTotal, setPendingTotal] = useState(0);
  const companyName = useCompanyName();
  const logoUrl = useCompanyLogo();
  const [collapsed, setCollapsed] = useState(false);

  // Load persisted collapse state once on mount
  useEffect(() => {
    try {
      const stored = window.localStorage.getItem(COLLAPSED_KEY);
      if (stored === "1") setCollapsed(true);
    } catch { /* ignore */ }
  }, []);

  const toggle = () => {
    setCollapsed((c) => {
      const next = !c;
      try { window.localStorage.setItem(COLLAPSED_KEY, next ? "1" : "0"); } catch { /* ignore */ }
      return next;
    });
  };

  useEffect(() => {
    if (!has("approval.approve")) return;
    const fetch = () => {
      api.get("/approvals/counts")
        .then((r) => setPendingTotal(r.data.data?.total ?? 0))
        .catch(() => {});
    };
    fetch();
    const t = setInterval(fetch, 60_000);
    return () => clearInterval(t);
  }, []);  // eslint-disable-line react-hooks/exhaustive-deps

  const groups = visibleNavGroups(has);
  const activeHref = activeNavHref(pathname, groups);

  return (
    <aside
      className={cn(
        "hidden lg:flex shrink-0 flex-col border-r border-border bg-card/40 backdrop-blur-xl transition-all duration-200",
        collapsed ? "w-16" : "w-64",
      )}
    >
      <div className={cn("flex h-16 items-center gap-2 border-b border-border", collapsed ? "px-3 justify-center" : "px-6")}>
        {logoUrl ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={logoUrl} alt="" className="h-8 w-8 rounded-lg object-cover shrink-0" />
        ) : (
          <div className="h-8 w-8 rounded-lg bg-gradient-to-br from-primary to-blue-600 grid place-items-center text-primary-foreground font-bold shrink-0">
            {(companyName?.[0] ?? "G").toUpperCase()}
          </div>
        )}
        {!collapsed && (
          <div className="flex flex-col leading-tight min-w-0 flex-1">
            <span className="text-sm font-semibold truncate" title={companyName}>{companyName}</span>
            <span className="text-xs text-muted-foreground">Real Estate</span>
          </div>
        )}
      </div>
      <nav className={cn("flex-1 overflow-y-auto py-4 space-y-4", collapsed ? "px-2" : "px-3")}>
        {groups.map((group) => (
          <div key={group.label ?? "__top"} className="space-y-1">
            {group.label && !collapsed && (
              <div className="px-3 pb-1 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/70">
                {group.label}
              </div>
            )}
            {group.label && collapsed && (
              <div className="mx-2 my-1.5 border-t border-border" />
            )}
            {group.items.map((item) => {
              const Icon = item.icon;
              const active = item.href === activeHref;
              const badge = item.href === "/approvals" ? pendingTotal : 0;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  title={collapsed ? item.label : undefined}
                  className={cn(
                    "flex items-center gap-3 rounded-lg text-sm font-medium transition-colors",
                    collapsed ? "justify-center px-2 py-2" : "px-3 py-2",
                    active
                      ? "bg-primary/10 text-primary"
                      : "text-muted-foreground hover:bg-accent hover:text-foreground",
                  )}
                >
                  <Icon className="h-4 w-4 shrink-0" />
                  {!collapsed && (
                    <>
                      <span className="flex-1 truncate">{item.label}</span>
                      {badge > 0 && (
                        <span className="inline-flex items-center justify-center min-w-[20px] h-[20px] px-1.5 rounded-full bg-amber-500 text-white text-[10px] font-medium">
                          {badge > 99 ? "99+" : badge}
                        </span>
                      )}
                    </>
                  )}
                  {collapsed && badge > 0 && (
                    <span className="absolute -mt-4 ml-3 inline-flex items-center justify-center min-w-[16px] h-[16px] px-1 rounded-full bg-amber-500 text-white text-[9px] font-medium">
                      {badge > 9 ? "9+" : badge}
                    </span>
                  )}
                </Link>
              );
            })}
          </div>
        ))}
      </nav>
      <div className={cn("border-t border-border p-2 flex items-center gap-2", collapsed && "justify-center")}>
        <button
          onClick={toggle}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          className="h-8 w-8 grid place-items-center rounded-md border border-border bg-card/60 hover:bg-accent shrink-0"
        >
          {collapsed ? <PanelLeftOpen className="h-4 w-4" /> : <PanelLeftClose className="h-4 w-4" />}
        </button>
        {!collapsed && (
          <span className="text-xs text-muted-foreground">v0.2.0 · Phase 1</span>
        )}
      </div>
    </aside>
  );
}
