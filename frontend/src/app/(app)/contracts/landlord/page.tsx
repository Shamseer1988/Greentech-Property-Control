"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Key, AlertTriangle } from "lucide-react";
import type { ColumnDef } from "@tanstack/react-table";
import { api } from "@/lib/api";
import { selectClass } from "@/components/ui/dialog";
import { DataTable } from "@/components/ui/data-table";
import type { LandlordContract } from "@/lib/landlord-contract-types";
import { LANDLORD_STATUS_TONE } from "@/lib/landlord-contract-types";
import { money } from "@/lib/contract-types";
import { useDebouncedValue } from "@/lib/use-debounce";

const EXPIRY_PRESETS = [
  { value: "", label: "Any expiry" },
  { value: "-1", label: "Expired" },
  { value: "30", label: "Within 1 month" },
  { value: "90", label: "Within 3 months" },
  { value: "180", label: "Within 6 months" },
];

/**
 * Landlord contracts — what GreenTech pays to rent a property in, with
 * the exact units held, mirroring the client contract list. New
 * contracts are still created from a property's Agreement tab
 * (`/properties/[id]` → Agreement); this screen is where they're
 * managed afterwards — rent changes, unit changes, cancellation.
 */
export default function LandlordContractsPage() {
  const [rows, setRows] = useState<LandlordContract[]>([]);
  const [q, setQ] = useState("");
  const debouncedQ = useDebouncedValue(q);
  const [status, setStatus] = useState("active");
  const [expiresWithin, setExpiresWithin] = useState("");
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const params: Record<string, string> = {};
      if (q) params.q = q;
      if (status) params.status = status;
      if (expiresWithin) params.expires_within = expiresWithin;
      const resp = await api.get("/landlord-contracts", { params });
      setRows(Array.isArray(resp.data?.data) ? resp.data.data : []);
    } catch {
      setRows([]);
    } finally {
      setLoading(false);
    }
  };

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, [debouncedQ, status, expiresWithin]);

  const columns = useMemo<ColumnDef<LandlordContract, unknown>[]>(() => [
    {
      accessorKey: "contract_number", header: "Contract",
      cell: (c) => <Link href={`/contracts/landlord/${c.row.original.id}`} className="font-mono text-xs hover:text-primary">{c.getValue<string>()}</Link>,
    },
    {
      id: "landlord", header: "Landlord", accessorFn: (r) => r.landlord?.name ?? "",
      cell: (c) => {
        const r = c.row.original;
        return r.landlord ? (
          <Link href={`/landlords/${r.landlord.id}`} className="font-medium hover:text-primary">{r.landlord.name}</Link>
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
    {
      accessorKey: "units_count", header: "Units",
      cell: (c) => c.getValue<number>() || <span className="text-muted-foreground">whole property</span>,
    },
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
      cell: (c) => <span className={"rounded-full px-2 py-0.5 text-xs capitalize " + (LANDLORD_STATUS_TONE[c.getValue<string>()] ?? "")}>{c.getValue<string>()}</span>,
    },
  ], []);

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-end justify-between flex-wrap gap-2">
        <div>
          <h1 className="text-2xl lg:text-3xl font-semibold tracking-tight">Landlord Contracts</h1>
          <p className="text-sm text-muted-foreground">
            What GreenTech pays to rent each property, with the exact units held under each.
          </p>
        </div>
      </div>

      <div className="glass rounded-xl p-4">
        <div className="flex items-center gap-2 flex-wrap">
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && load()}
            placeholder="Search contract no., landlord, property…"
            className="h-9 w-64 shrink-0 rounded-md border border-input bg-card/60 px-3 text-sm"
          />
          <select className={selectClass + " !w-auto shrink-0"} value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">All statuses</option>
            <option value="active">Active</option>
            <option value="cancelled">Cancelled</option>
            <option value="expired">Expired</option>
            <option value="renewed">Renewed</option>
          </select>
          <select className={selectClass + " !w-auto shrink-0"} value={expiresWithin} onChange={(e) => setExpiresWithin(e.target.value)}>
            {EXPIRY_PRESETS.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
          </select>
          <button onClick={load} className="h-9 shrink-0 rounded-md border border-border bg-card/60 px-3 text-sm hover:bg-accent">Search</button>
        </div>
      </div>

      <DataTable columns={columns} data={rows} loading={loading} maxBodyHeight="65vh"
        emptyMessage={`No landlord contracts${status ? ` with status "${status}"` : ""} yet`} />

      {rows.length === 0 && !loading && (
        <div className="glass rounded-xl p-8 text-center space-y-2">
          <Key className="h-8 w-8 mx-auto text-muted-foreground" />
          <div className="text-sm text-muted-foreground">
            New landlord contracts are created from a property&apos;s Agreement tab. This screen
            manages them afterwards — rent changes, unit changes, cancellation.
          </div>
        </div>
      )}
    </div>
  );
}
