import {
  ArrowRightLeft,
  Mail,
  LayoutDashboard,
  Building2,
  Users,
  FileSignature,
  Banknote,
  Wallet,
  TrendingUp,
  FileSpreadsheet,
  Settings,
  Shield,
  Bell,
  ClipboardList,
  Key,
  FileKey2,
  CheckSquare,
  Layers,
  FileText,
} from "lucide-react";

export type NavItem = { href: string; label: string; icon: typeof LayoutDashboard; perm?: string };

/** `label: null` renders with no section header — used for the single
 *  top-level item (Dashboard) that doesn't belong under a heading. */
export type NavGroup = { label: string | null; items: NavItem[] };

// Single source of truth for both the desktop rail (sidebar.tsx) and the
// mobile drawer (mobile-nav.tsx) — they used to carry a byte-identical
// copy of this array each, which is exactly the kind of drift a shared
// module exists to prevent.
export const navGroups: NavGroup[] = [
  {
    label: null,
    items: [
      { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard, perm: "dashboard.view" },
    ],
  },
  {
    label: "Master",
    items: [
      { href: "/properties", label: "Properties", icon: Building2, perm: "property.view" },
      { href: "/landlords", label: "Landlords", icon: Key, perm: "landlord.view" },
      { href: "/clients", label: "Clients", icon: Users, perm: "client.view" },
    ],
  },
  {
    label: "Contracts",
    items: [
      { href: "/contracts/landlord", label: "Landlord Contracts", icon: FileKey2, perm: "property.view" },
      { href: "/contracts", label: "Client Contracts", icon: FileSignature, perm: "contract.view" },
      { href: "/agreements", label: "Agreements", icon: FileText, perm: "agreement.view" },
    ],
  },
  {
    label: "Transactions",
    items: [
      { href: "/collections", label: "Collections", icon: Banknote, perm: "rent.view" },
      { href: "/transactions/bulk", label: "Bulk Entry", icon: Layers, perm: "receipt.create" },
      { href: "/expenses", label: "Expenses", icon: Wallet, perm: "expense.view" },
      { href: "/approvals", label: "Approvals", icon: CheckSquare, perm: "approval.approve" },
    ],
  },
  {
    label: "Profit & Loss",
    items: [
      { href: "/pnl/dashboard", label: "P&L Dashboard", icon: TrendingUp, perm: "expense.view" },
      { href: "/pnl", label: "Property P&L", icon: Building2, perm: "expense.view" },
    ],
  },
  {
    label: "Insight",
    items: [
      { href: "/reports", label: "Reports", icon: FileSpreadsheet, perm: "report.view" },
      { href: "/alerts", label: "Alerts", icon: Bell },
      { href: "/messages", label: "Messages", icon: Mail, perm: "notification.view" },
      { href: "/audit", label: "Audit Log", icon: ClipboardList, perm: "audit.view" },
    ],
  },
  {
    label: "Admin",
    items: [
      { href: "/users", label: "Users & Roles", icon: Shield, perm: "user.view" },
      { href: "/migration", label: "Migration", icon: ArrowRightLeft, perm: "settings.manage" },
      { href: "/settings", label: "Settings", icon: Settings, perm: "settings.view" },
    ],
  },
];

/** Groups filtered to what this user can see, with empty groups dropped
 *  entirely so a permission gap never leaves a bare, childless heading. */
export function visibleNavGroups(has: (perm: string) => boolean): NavGroup[] {
  return navGroups
    .map((g) => ({ ...g, items: g.items.filter((n) => !n.perm || has(n.perm)) }))
    .filter((g) => g.items.length > 0);
}

/** Which nav href is "active" for a given pathname, picking the single
 *  longest (most specific) match rather than every href that happens to
 *  be a string prefix. Needed because `/contracts` (Client Contracts)
 *  is itself a path-prefix of `/contracts/landlord` (Landlord
 *  Contracts) — naive `startsWith` would light up both at once. */
export function activeNavHref(pathname: string | null, groups: NavGroup[]): string | null {
  if (!pathname) return null;
  const hrefs = groups.flatMap((g) => g.items.map((i) => i.href));
  const matches = hrefs.filter((h) => pathname === h || pathname.startsWith(h + "/"));
  if (matches.length === 0) return null;
  return matches.reduce((best, h) => (h.length > best.length ? h : best));
}
