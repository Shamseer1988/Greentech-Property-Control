"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ReactQueryDevtools } from "@tanstack/react-query-devtools";
import { useState } from "react";

/**
 * Phase 7 — TanStack Query setup.
 *
 * One QueryClient per browser session. Stored in useState so React 18
 * Strict Mode's double-render doesn't trash the cache between renders.
 *
 * Defaults:
 *   - staleTime 30s — list/detail pages can mount adjacent and reuse
 *     the cached entry without an immediate refetch storm.
 *   - retry 1 — axios already retries 401s through its refresh
 *     interceptor; Query's own retry is for network blips.
 *   - refetchOnWindowFocus off — coming back to the tab shouldn't
 *     hammer the API just because the user alt-tabbed.
 */
export function QueryProvider({ children }: { children: React.ReactNode }) {
  const [client] = useState(() => new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        gcTime: 5 * 60_000,
        retry: 1,
        refetchOnWindowFocus: false,
      },
      mutations: {
        retry: 0,
      },
    },
  }));
  return (
    <QueryClientProvider client={client}>
      {children}
      {process.env.NODE_ENV === "development" && <ReactQueryDevtools initialIsOpen={false} />}
    </QueryClientProvider>
  );
}
