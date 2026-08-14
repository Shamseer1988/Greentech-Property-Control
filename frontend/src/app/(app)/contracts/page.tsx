"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, FileSignature, AlertTriangle } from "lucide-react";
import type { ColumnDef, PaginationState } from "@tanstack/react-table";
import { api } from "@/lib/api";
import { Can } from "@/components/can";
import { selectClass } from "@/components/ui/dialog";
import { DataTable } from "@/components/ui/data-table";
import { ContractWizard } from "@/components/contract-wizard";
import type { Contract } from "@/lib/contract-types";
import { MODE_LABEL, STATUS_TONE, money } from "@/lib/contract-types";
import { useDebouncedValue } from "@/lib/use-debounce";
import { keys } from "@/lib/query-keys";

const EXPIRY_PRESETS = [
  { value: "", label: "Any expiry" },
  { value: "-1", label: "Expired" },
  { value: "30", label: "Within 1 month" },
  { value: "90", label: "Within 3 months" },
  { value: "180", label: "Within 6 months" },
];

export default function ContractsPage() {
  const qc = useQueryClient();
  const [q, setQ] = useState("");
  const debouncedQ = useDebouncedValue(q);
  const [status, setStatus] = useState("active");
  const [mode, setMode] = useState("");
  const [expiresWithin, setExpiresWithin] = useState("");
  const [showWizard, setShowWizard] = useState(false);
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 25 });

  useEffect(() => { setPagination((p) => ({ ...p, pageIndex: 0 })); }, [debouncedQ, status, mode, expiresWithin]);

  const listQuery = useQuery({
    queryKey: keys.contracts.list({ q: debouncedQ, status, mode, expiresWithin, ...pagination }),
    queryFn: async () => {
      const params: Record<string, string | number> = {
        page: pagination.pageIndex + 1, per_page: pagination.pageSize,
      };
      if (debouncedQ) params.q = debouncedQ;
      if (status) params.status = status;
      if (mode) params.mode = mode;
      if (expiresWithin) params.expires_within = expiresWithin;
      const resp = await api.get("/contracts", { params });
      return resp.data as { data: Contract[]; meta: { total_count: number; total_pages: number } };
    },
    placeholderData: (prev) => prev,
  });
  const rows = listQuery.data?.data ?? [];
  const meta = listQuery.data?.meta;
  const loading = listQuery.isLoading;
  const load = () => listQuery.refetch();
  const invalidate = () => qc.invalidateQueries({ queryKey: keys.contracts.all() });

  const columns = useMemo<ColumnDef<Contract, unknown>[]>(() => [
    {
      accessorKey: "contract_number", header: "Contract",
      cell: (c) => <Link href={`/contracts/${c.row.original.id}`} className="font-mono text-xs hover:text-primary">{c.getValue<string>()}</Link>,
    },
    {
      id: "client", header: "Client", accessorFn: (r) => r.client?.name ?? "",
      cell: (c) => {
        const r = c.row.original;
        return r.client ? (
          <div>
            <Link href={`/clients/${r.client.id}`} className="font-medium hover:text-primary">{r.client.name}</Link>
            {r.client.name_ar && <div className="text-xs text-muted-foreground" dir="rtl">{r.client.name_ar}</div>}
          </div>
        ) : "—";
      },
    },
    {
      id: "property", header: "Property", accessorFn: (r) => r.property?.name ?? "",
      cell: (c) => {
        const r = c.row.original;
        return r.property ? (
          <Link href={`/properties/${r.property.id}`} className="text-xs hover:text-primary hover:underline">{r.property.name}</Link>
        ) : "—";
      },
    },
    { accessorKey: "units_count", header: "Units", cell: (c) => c.getValue<number>() ?? "—" },
    { accessorKey: "payment_mode", header: "Mode", cell: (c) => MODE_LABEL[c.getValue<string>()] ?? c.getValue<string>() },
    { accessorKey: "monthly_rent", header: "Rent", cell: (c) => <span className="font-medium">{money(c.getValue<number>())}</span> },
    {
      accessorKey: "expiry_date", header: "Expiry",
      cell: (c) => {
        const r = c.row.original;
        const expiringSoon = r.status === "active" && r.days_left !== undefined && r.days_left <= 60;
        return (
          <div>
            <span className="font-mono text-xs">{r.expiry_date}</span>
            {expiringSoon && (
              <div className="text-xs text-amber-600 inline-flex items-center gap-1">
                <AlertTriangle className="h-3 w-3" />
                {r.days_left! < 0 ? `expired ${Math.abs(r.days_left!)}d ago` : `${r.days_left}d left`}
              </div>
            )}
          </div>
        );
      },
    },
    {
      accessorKey: "status", header: "Status",
      cell: (c) => <span className={"rounded-full px-2 py-0.5 text-xs capitalize " + (STATUS_TONE[c.getValue<string>()] ?? "")}>{c.getValue<string>()}</span>,
    },
  ], []);

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-end justify-between flex-wrap gap-2">
        <div>
          <h1 className="text-2xl lg:text-3xl font-semibold tracking-tight">Contracts</h1>
          <p className="text-sm text-muted-foreground">
            Client agreements with the exact units they hold, payment mode and expiry.
          </p>
        </div>
        <Can perm="contract.create">
          <button
            onClick={() => setShowWizard(true)}
            className="inline-flex h-9 items-center gap-2 rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground hover:bg-primary/90"
          >
            <Plus className="h-4 w-4" /> New contract
          </button>
        </Can>
      </div>

      <div className="glass rounded-xl p-4">
        <div className="flex items-center gap-2 flex-wrap">
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && load()}
            placeholder="Search contract no., client, property…"
            className="h-9 w-64 shrink-0 rounded-md border border-input bg-card/60 px-3 text-sm"
          />
          <select className={selectClass + " !w-auto shrink-0"} value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">All statuses</option>
            <option value="active">Active</option>
            <option value="cancelled">Cancelled</option>
            <option value="expired">Expired</option>
            <option value="renewed">Renewed</option>
          </select>
          <select className={selectClass + " !w-auto shrink-0"} value={mode} onChange={(e) => setMode(e.target.value)}>
            <option value="">All modes</option>
            <option value="cash">Cash</option>
            <option value="cheque">Cheque (PDC)</option>
            <option value="online">Online</option>
          </select>
          <select className={selectClass + " !w-auto shrink-0"} value={expiresWithin} onChange={(e) => setExpiresWithin(e.target.value)}>
            {EXPIRY_PRESETS.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
          </select>
          <button onClick={load} className="h-9 shrink-0 rounded-md border border-border bg-card/60 px-3 text-sm hover:bg-accent">Search</button>
        </div>
      </div>

      <DataTable columns={columns} data={rows} loading={loading} maxBodyHeight="65vh"
        emptyMessage={`No contracts${status ? ` with status "${status}"` : ""} yet`}
        manualPagination pageCount={meta?.total_pages ?? 0} totalCount={meta?.total_count}
        pagination={pagination} onPaginationChange={setPagination} />

      {rows.length === 0 && !loading && (
        <div className="glass rounded-xl p-8 text-center space-y-2">
          <FileSignature className="h-8 w-8 mx-auto text-muted-foreground" />
          <div className="text-sm text-muted-foreground">
            A contract ties a client to the exact unit numbers they rent. Create one to start
            tracking rent, cheques and expiry.
          </div>
        </div>
      )}

      <ContractWizard
        open={showWizard}
        onClose={() => setShowWizard(false)}
        onCreated={() => { setShowWizard(false); invalidate(); }}
      />
    </div>
  );
}
