import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export type PropertyType = { id: number; code: string; name: string; is_active: boolean };

/** Active property types for pickers — replaces the two hardcoded arrays
 *  that used to duplicate the backend's `PROPERTY_TYPES` set. Managed
 *  from Settings → Property Types. */
export function usePropertyTypes() {
  const [types, setTypes] = useState<PropertyType[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get("/properties/types", { params: { active_only: 1 } })
      .then((r) => setTypes(r.data.data ?? []))
      .catch(() => setTypes([]))
      .finally(() => setLoading(false));
  }, []);

  return { types, loading };
}
