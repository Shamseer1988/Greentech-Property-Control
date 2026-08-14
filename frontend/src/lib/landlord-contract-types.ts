/** Shared landlord-contract shapes + display helpers — mirrors
 *  contract-types.ts (the client-contract side). */

export type LandlordUnitRow = {
  id: number;
  unit_id: number;
  from_date: string;
  to_date: string | null;
  unit_rent: number | null;
  unit?: { id: number; unit_number: string; unit_type: string; floor_id: number };
};

export type LandlordAmendment = {
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
  old_security_deposit: number | null;
  new_security_deposit: number | null;
  reason: string | null;
  remarks: string | null;
};

export type LandlordContract = {
  id: number;
  contract_number: string;
  agreement_number: string | null;
  property_id: number;
  landlord_id: number;
  start_date: string;
  expiry_date: string;
  monthly_rent: number | null;
  security_deposit: number | null;
  payment_terms: string | null;
  notice_period: string | null;
  renewal_status: string;
  kahramaa_account: string | null;
  municipality_ref: string | null;
  reminder_days_before_expiry: number;
  payment_mode: string;
  opening_balance: number;
  status: string;
  is_active: boolean;
  cancellation_date: string | null;
  cancellation_reason: string | null;
  renewed_to_id: number | null;
  remarks: string | null;
  landlord?: { id: number; code: string; name: string };
  property?: { id: number; code: string; name: string };
  units?: LandlordUnitRow[];
  units_count?: number;
  units_as_of?: string;
  amendments?: LandlordAmendment[];
  days_left?: number;
};

export const LANDLORD_STATUS_TONE: Record<string, string> = {
  active: "bg-emerald-500/10 text-emerald-600",
  cancelled: "bg-rose-500/10 text-rose-600",
  expired: "bg-muted text-muted-foreground",
  renewed: "bg-sky-500/10 text-sky-600",
};

export const LANDLORD_AMENDMENT_LABEL: Record<string, string> = {
  rent_change: "Rent change",
  free_months: "Grace period (landlord)",
  units_added: "Units added",
  units_removed: "Units released",
  cancellation: "Cancellation",
  renewal: "Renewal",
  dates_correction: "Dates corrected",
  deposit_change: "Deposit change",
};
