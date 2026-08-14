"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export type UnitType = {
  id: number; code: string; name: string;
  is_facility: boolean; bulk_mode: "floors" | "count";
  is_active: boolean;
};

export function useUnitTypes() {
  const [types, setTypes] = useState<UnitType[]>([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    api.get("/units/types", { params: { active_only: 1 } })
      .then((r) => setTypes(r.data.data ?? []))
      .catch(() => setTypes([]))
      .finally(() => setLoading(false));
  }, []);
  return { types, loading };
}
