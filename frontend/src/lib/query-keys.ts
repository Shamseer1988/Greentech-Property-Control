/**
 * Centralized TanStack Query key factories (Phase 7).
 *
 * Why this exists: query keys are how Query identifies a cached entry.
 * Typos (`"properties"` vs `["properties", undefined]`) silently produce
 * separate cache entries that never reconcile. A factory module makes
 * the keys typed and grep-able, and gives mutations a single source of
 * truth to call when they invalidate ("after a successful create, what
 * lists do I need to refetch?").
 *
 * Migrated pages use this. Unmigrated pages keep their hand-rolled
 * fetch+useState until they're brought across — see the bottom of this
 * file for the running todo list.
 */

export const keys = {
  properties: {
    all: () => ["properties"] as const,
    list: (filters: Record<string, unknown> = {}) =>
      ["properties", "list", filters] as const,
    detail: (id: number | string) =>
      ["properties", "detail", String(id)] as const,
    occupancy: (id: number | string) =>
      ["properties", "occupancy", String(id)] as const,
  },
  landlords: {
    all: () => ["landlords"] as const,
    list: (filters: Record<string, unknown> = {}) =>
      ["landlords", "list", filters] as const,
  },
  clients: {
    all: () => ["clients"] as const,
    list: (filters: Record<string, unknown> = {}) =>
      ["clients", "list", filters] as const,
    detail: (id: number | string) => ["clients", "detail", String(id)] as const,
  },
  contracts: {
    all: () => ["contracts"] as const,
    list: (filters: Record<string, unknown> = {}) =>
      ["contracts", "list", filters] as const,
    detail: (id: number | string) => ["contracts", "detail", String(id)] as const,
  },
  landlordContracts: {
    all: () => ["landlord-contracts"] as const,
    list: (filters: Record<string, unknown> = {}) =>
      ["landlord-contracts", "list", filters] as const,
    detail: (id: number | string) => ["landlord-contracts", "detail", String(id)] as const,
  },
  agreements: {
    all: () => ["agreements"] as const,
    list: (filters: Record<string, unknown> = {}) =>
      ["agreements", "list", filters] as const,
    templates: (partyRole?: string) => ["agreements", "templates", partyRole ?? null] as const,
  },
  expenses: {
    all: () => ["expenses"] as const,
    list: (filters: Record<string, unknown> = {}) =>
      ["expenses", "list", filters] as const,
    categories: () => ["expenses", "categories"] as const,
    landlordPayments: (filters: Record<string, unknown> = {}) =>
      ["expenses", "landlord-payments", filters] as const,
  },
  audit: {
    all: () => ["audit"] as const,
    list: (filters: Record<string, unknown> = {}) =>
      ["audit", "list", filters] as const,
    facets: () => ["audit", "facets"] as const,
  },
  approvals: {
    all: () => ["approvals"] as const,
    list: (filters: Record<string, unknown> = {}) =>
      ["approvals", "list", filters] as const,
  },
  users: {
    all: () => ["users"] as const,
    list: () => ["users", "list"] as const,
    roles: () => ["users", "roles"] as const,
  },
  alerts: {
    all: () => ["alerts"] as const,
    list: (filters: Record<string, unknown> = {}) =>
      ["alerts", "list", filters] as const,
  },
  reports: {
    all: () => ["reports"] as const,
    catalog: () => ["reports", "catalog"] as const,
    run: (slug: string, filters: Record<string, unknown> = {}) =>
      ["reports", "run", slug, filters] as const,
  },
  collections: {
    statement: (id: number | string) => ["collections", "statement", String(id)] as const,
    receipts: (filters: Record<string, unknown> = {}) =>
      ["collections", "receipts", filters] as const,
  },
  dashboard: {
    summary: () => ["dashboard", "summary"] as const,
    byProperty: () => ["dashboard", "by-property"] as const,
    activity: () => ["dashboard", "activity"] as const,
    alerts: () => ["dashboard", "alerts"] as const,
    property: (id: number | string) => ["dashboard", "property", String(id)] as const,
    client: (id: number | string) => ["dashboard", "client", String(id)] as const,
    landlord: (id: number | string) => ["dashboard", "landlord", String(id)] as const,
    cashflowForecast: () => ["dashboard", "cashflow-forecast"] as const,
    renewalsAtRisk: () => ["dashboard", "renewals-at-risk"] as const,
    chequeAgeing: () => ["dashboard", "cheque-ageing"] as const,
  },
} as const;

/* ------------------------------------------------------------------
 * Pages still hand-rolled (migration TODO)
 * ------------------------------------------------------------------
 *  - app/(app)/settings/page.tsx — low churn, single-object fetch, not
 *    worth the migration cost.
 *
 * Migration recipe (copy from dashboard/page.tsx or landlords/page.tsx):
 *   1. Add a `keys.<resource>.list(filters)` factory above.
 *   2. Replace `useState + useEffect` with `useQuery({ queryKey, queryFn })`.
 *   3. Replace POST/PUT/DELETE handlers with `useMutation` that
 *      invalidates the list key on success.
 *   4. List pages backed by DataTable: pass `manualPagination`, `pageCount`,
 *      `totalCount`, `pagination`/`onPaginationChange` through to it once
 *      the backend route supports `page`/`per_page` (see
 *      app/utils/pagination.py) — the query key must include the page
 *      index so each page is cached separately.
 *   5. Loading/error/empty: DataTable's own `loading`/`emptyMessage` props
 *      for list pages; <Skeleton /> / <ErrorState /> / <EmptyState /> for
 *      everything else (detail pages, dashboard panels).
 * ------------------------------------------------------------------ */
