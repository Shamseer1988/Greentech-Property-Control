/** Shared contract shapes + display helpers. */

export type ContractUnitRow = {
  id: number;
  unit_id: number;
  from_date: string;
  to_date: string | null;
  unit?: { id: number; unit_number: string; unit_type: string; floor_id: number };
};

export type Amendment = {
  id: number;
  amendment_number: string;
  sequence: number;
  amendment_type: string;
  effective_date: string;
  old_rent: number | null;
  new_rent: number | null;
  free_months: number | null;
  free_from_month: string | null;
  unit_ids: number[];
  old_start_date: string | null;
  new_start_date: string | null;
  old_expiry_date: string | null;
  new_expiry_date: string | null;
  reason: string | null;
  remarks: string | null;
};

export type Cheque = {
  id: number;
  cheque_number: string;
  bank_name: string | null;
  cheque_date: string;
  amount: number;
  is_security: boolean;
  for_month: string | null;
  status: string;
  replaces_cheque_id: number | null;
};

export type Contract = {
  id: number;
  contract_number: string;
  client_id: number;
  property_id: number;
  start_date: string;
  expiry_date: string;
  monthly_rent: number;
  payment_mode: string;
  security_deposit: number | null;
  opening_balance: number;
  status: string;
  cancellation_date: string | null;
  cancellation_reason: string | null;
  renewed_to_id: number | null;
  remarks: string | null;
  client?: { id: number; code: string; name: string; name_ar: string | null };
  property?: { id: number; code: string; name: string };
  units?: ContractUnitRow[];
  units_count?: number;
  units_as_of?: string;
  amendments?: Amendment[];
  cheques?: Cheque[];
  pending_approvals?: PendingApproval[];
  days_left?: number;
};

/** A change someone has asked for that hasn't been applied. Everything
 * else on the contract still reads as it did before the request. */
export type PendingApproval = {
  id: number;
  transaction_number: string;
  module: string;
  module_label: string;
  summary: string | null;
  requested_at: string;
};

export type AvailableUnit = {
  id: number;
  unit_number: string;
  unit_type: string;
  floor_id: number;
  occupancy_status: string;
  monthly_rent: number | null;
  is_shared_facility: boolean;
  is_facility: boolean;
  is_available: boolean;
  held_by: { contract_id: number; contract_number: string; client_name: string | null } | null;
};

export const MODE_LABEL: Record<string, string> = {
  cash: "Cash",
  cheque: "Cheque (PDC)",
  online: "Online",
};

export const STATUS_TONE: Record<string, string> = {
  active: "bg-emerald-500/10 text-emerald-600",
  cancelled: "bg-rose-500/10 text-rose-600",
  expired: "bg-muted text-muted-foreground",
  renewed: "bg-sky-500/10 text-sky-600",
};

export const CHEQUE_TONE: Record<string, string> = {
  received: "bg-slate-500/10 text-slate-600 dark:text-slate-300",
  deposited: "bg-sky-500/10 text-sky-600",
  cleared: "bg-emerald-500/10 text-emerald-600",
  bounced: "bg-rose-500/10 text-rose-600",
  replaced: "bg-amber-500/10 text-amber-600",
  returned: "bg-muted text-muted-foreground",
};

export const AMENDMENT_LABEL: Record<string, string> = {
  rent_change: "Rent change",
  free_months: "Free months",
  units_added: "Units added",
  units_removed: "Units released",
  cancellation: "Cancellation",
  renewal: "Renewal",
  dates_correction: "Dates corrected",
};

/** Format an amount for display. Currency comes from settings; the
 *  symbol is left to the caller so reports and screens stay consistent. */
export function money(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return value.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 2 });
}
