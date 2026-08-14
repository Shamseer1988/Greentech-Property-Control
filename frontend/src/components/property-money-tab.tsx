"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from "recharts";
import { Banknote, Wallet, Receipt, TrendingUp, TrendingDown } from "lucide-react";
import { api } from "@/lib/api";
import { inputClass } from "@/components/ui/dialog";
import { Stat, Section, EmptyRow, Money, DaysPill } from "@/components/dashboard-bits";
import { money, MODE_LABEL } from "@/lib/contract-types";

type Data = {
  units: { total: number; occupied: number; empty: number; occupancy_percent: number };
  contracts: {
    contract_id: number; contract_number: string; client_id: number;
    client_name: string; payment_mode: string; monthly_rent: number;
    expiry_date: string; days_left: number; units: string[];
  }[];
  month: string;
  pnl: {
    rent_charged: number; rent_collected: number; rent_paid: number;
    expenses: Record<string, number>; expense_total: number;
    profit: number; cash_profit: number;
  } | null;
  trend: { month: string; rent_charged: number; rent_paid: number;
           expense_total: number; profit: number }[];
};

function currentMonth() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

/**
 * The workbook's block for one building: who is in it, what it charged,
 * what the landlord took, what it cost to run, and the twelve-month
 * shape of its margin.
 */
export function PropertyMoneyTab({ propertyId }: { propertyId: number }) {
  const [data, setData] = useState<Data | null>(null);
  const [month, setMonth] = useState(currentMonth());
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.get(`/dashboard/property/${propertyId}`, { params: { month: `${month}-01` } })
      .then((r) => setData(r.data.data))
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [propertyId, month]);

  if (loading) {
    return <div className="text-sm text-muted-foreground animate-pulse">Loading…</div>;
  }
  if (!data) {
    return <div className="glass rounded-xl p-6 text-sm text-muted-foreground">
      Could not load this property&apos;s figures.
    </div>;
  }

  const pnl = data.pnl;
  const categories = Object.entries(pnl?.expenses ?? {}).filter(([, v]) => v);
  const trend = data.trend.map((t) => ({ ...t, label: t.month.slice(2, 7) }));

  return (
    <div className="space-y-4 animate-fade-in">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="text-sm text-muted-foreground">
          {data.units.occupied} of {data.units.total} units let
          ({data.units.occupancy_percent}%)
        </div>
        <input type="month" className={inputClass + " w-auto"} value={month}
          onChange={(e) => setMonth(e.target.value)} />
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat label="Rent charged" value={money(pnl?.rent_charged ?? 0)}
          sub={`${money(pnl?.rent_collected ?? 0)} collected`} icon={Banknote} />
        <Stat label="Paid to landlord" value={money(pnl?.rent_paid ?? 0)}
          sub="this month" icon={Wallet} />
        <Stat label="Running costs" value={money(pnl?.expense_total ?? 0)}
          sub={`${categories.length} categor${categories.length === 1 ? "y" : "ies"}`}
          icon={Receipt} />
        <Stat label="Margin" value={money(pnl?.profit ?? 0)}
          sub="charged less rent and costs"
          icon={(pnl?.profit ?? 0) >= 0 ? TrendingUp : TrendingDown}
          tone={(pnl?.profit ?? 0) >= 0 ? "emerald" : "rose"} />
      </div>

      <Section title="Margin over the last 12 months">
        {trend.every((t) => !t.rent_charged && !t.rent_paid && !t.expense_total) ? (
          <EmptyRow>Nothing recorded for this property yet.</EmptyRow>
        ) : (
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={trend} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
              <XAxis dataKey="label" tick={{ fontSize: 11 }}
                stroke="hsl(var(--muted-foreground))" />
              <YAxis tick={{ fontSize: 11 }} stroke="hsl(var(--muted-foreground))" />
              <Tooltip
                formatter={(v: number) => money(v)}
                contentStyle={{ background: "hsl(var(--card))",
                  border: "1px solid hsl(var(--border))", borderRadius: 8, fontSize: 12 }} />
              <Line type="monotone" dataKey="rent_charged" name="Charged"
                stroke="#3b82f6" strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="profit" name="Margin"
                stroke="#10b981" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        )}
      </Section>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Section title="Who is in the building">
          {data.contracts.length === 0 ? (
            <EmptyRow>No active contracts.</EmptyRow>
          ) : (
            <ul className="divide-y divide-border/60">
              {data.contracts.map((c) => (
                <li key={c.contract_id} className="py-2 flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <Link href={`/clients/${c.client_id}`}
                      className="text-sm hover:text-primary block truncate">
                      {c.client_name}
                    </Link>
                    <div className="text-[11px] text-muted-foreground">
                      <Link href={`/contracts/${c.contract_id}`} className="font-mono hover:text-primary">
                        {c.contract_number}
                      </Link>
                      {" · "}{MODE_LABEL[c.payment_mode] ?? c.payment_mode}
                      {c.units.length > 0 && ` · units ${c.units.join(", ")}`}
                    </div>
                  </div>
                  <div className="text-right shrink-0">
                    <div className="text-sm">{money(c.monthly_rent)}</div>
                    <DaysPill days={c.days_left} />
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Section>

        <Section title={`Running costs — ${month}`}>
          {categories.length === 0 ? (
            <EmptyRow>No costs allocated to this property this month.</EmptyRow>
          ) : (
            <div className="space-y-1">
              {categories.sort(([, a], [, b]) => b - a).map(([name, value]) => (
                <div key={name} className="flex justify-between text-sm">
                  <span className="text-muted-foreground">{name}</span>
                  <span>{money(value)}</span>
                </div>
              ))}
              <div className="flex justify-between pt-2 border-t border-border text-sm font-semibold">
                <span>Total</span>
                <span>{money(pnl?.expense_total ?? 0)}</span>
              </div>
            </div>
          )}
        </Section>
      </div>

      {pnl && (
        <Section title="From rent to margin">
          <div className="space-y-1 text-sm">
            <Row label="Rent charged to clients" value={pnl.rent_charged} />
            <Row label="Less rent paid to the landlord" value={-pnl.rent_paid} />
            <Row label="Less running costs" value={-pnl.expense_total} />
            <div className="flex justify-between pt-2 border-t border-border font-semibold">
              <span>Margin</span>
              <Money value={pnl.profit} signed />
            </div>
          </div>
        </Section>
      )}
    </div>
  );
}

function Row({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex justify-between">
      <span className="text-muted-foreground">{label}</span>
      <span>{money(value)}</span>
    </div>
  );
}
