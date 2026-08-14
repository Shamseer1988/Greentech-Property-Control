"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { AnimatePresence, motion } from "framer-motion";
import { Menu, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuth } from "@/lib/auth-store";
import { api } from "@/lib/api";
import { useCompanyName, useCompanyLogo } from "@/lib/public-settings";
import { visibleNavGroups, activeNavHref } from "@/lib/nav";

export function MobileNav() {
  const [open, setOpen] = useState(false);
  const [mounted, setMounted] = useState(false);
  const pathname = usePathname();
  const has = useAuth((s) => s.has);
  const companyName = useCompanyName();
  const logoUrl = useCompanyLogo();
  const [pendingTotal, setPendingTotal] = useState(0);

  useEffect(() => { setMounted(true); }, []);

  useEffect(() => {
    if (!has("approval.approve")) return;
    api.get("/approvals/counts")
      .then((r) => setPendingTotal(r.data.data?.total ?? 0))
      .catch(() => {});
  }, [pathname]);  // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { setOpen(false); }, [pathname]);

  // Lock body scroll + close on Escape while the drawer is open.
  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = prev;
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const groups = visibleNavGroups(has);
  const activeHref = activeNavHref(pathname, groups);

  // Portal the drawer to <body>: the topbar uses backdrop-blur which
  // creates a containing block for `position: fixed`, otherwise the
  // drawer gets clipped to the topbar strip instead of covering the page.
  const drawer = mounted ? createPortal(
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }}
          className="fixed inset-0 z-[100] lg:hidden"
        >
            <div className="absolute inset-0 bg-black/40" onClick={() => setOpen(false)} />
            <motion.aside
              initial={{ x: -320 }} animate={{ x: 0 }} exit={{ x: -320 }}
              transition={{ type: "spring", stiffness: 320, damping: 32 }}
              className="absolute left-0 top-0 h-full w-72 bg-card border-r border-border flex flex-col shadow-2xl"
            >
              <div className="flex h-16 items-center gap-2 px-4 border-b border-border">
                {logoUrl ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={logoUrl} alt="" className="h-8 w-8 rounded-lg object-cover" />
                ) : (
                  <div className="h-8 w-8 rounded-lg bg-gradient-to-br from-primary to-blue-600 grid place-items-center text-primary-foreground font-bold">
                    {(companyName?.[0] ?? "G").toUpperCase()}
                  </div>
                )}
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-semibold truncate">{companyName}</div>
                  <div className="text-xs text-muted-foreground">Real Estate</div>
                </div>
                <button
                  onClick={() => setOpen(false)}
                  className="h-8 w-8 grid place-items-center rounded-md hover:bg-accent"
                  aria-label="Close navigation"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
              <nav className="flex-1 overflow-y-auto px-3 py-4 space-y-4">
                {groups.map((group) => (
                  <div key={group.label ?? "__top"} className="space-y-1">
                    {group.label && (
                      <div className="px-3 pb-1 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/70">
                        {group.label}
                      </div>
                    )}
                    {group.items.map((item) => {
                      const Icon = item.icon;
                      const active = item.href === activeHref;
                      const badge = item.href === "/approvals" ? pendingTotal : 0;
                      return (
                        <Link
                          key={item.href}
                          href={item.href}
                          className={cn(
                            "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                            active
                              ? "bg-primary/10 text-primary"
                              : "text-muted-foreground hover:bg-accent hover:text-foreground",
                          )}
                        >
                          <Icon className="h-4 w-4" />
                          <span className="flex-1">{item.label}</span>
                          {badge > 0 && (
                            <span className="inline-flex items-center justify-center min-w-[20px] h-[20px] px-1.5 rounded-full bg-amber-500 text-white text-[10px] font-medium">
                              {badge > 99 ? "99+" : badge}
                            </span>
                          )}
                        </Link>
                      );
                    })}
                  </div>
                ))}
              </nav>
              <div className="p-3 text-xs text-muted-foreground border-t border-border">
                v0.2.0 · Phase 1
              </div>
            </motion.aside>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body,
  ) : null;

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="lg:hidden inline-flex h-9 w-9 items-center justify-center rounded-md border border-border bg-card/60 hover:bg-accent"
        aria-label="Open navigation"
        aria-expanded={open}
      >
        <Menu className="h-4 w-4" />
      </button>
      {drawer}
    </>
  );
}
