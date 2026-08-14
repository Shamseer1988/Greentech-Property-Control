"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";

export type Role = { id: number; code: string; name: string };

export type AuthUser = {
  id: number;
  username: string;
  email: string;
  full_name: string;
  is_active: boolean;
  is_super_user: boolean;
  roles: Role[];
  permissions: string[]; // codes; "*" means all
};

type AuthState = {
  user: AuthUser | null;
  hydrated: boolean;
  // True once we've made at least one /auth/me call (success or 401) and
  // know whether the cookie-authenticated session is real. AuthGuard
  // uses this to avoid a redirect flicker between persist-rehydrate and
  // the bootstrap call.
  bootstrapped: boolean;
  setUser: (user: AuthUser | null) => void;
  clear: () => void;
  setHydrated: (v: boolean) => void;
  setBootstrapped: (v: boolean) => void;
  has: (code: string) => boolean;
};

export const useAuth = create<AuthState>()(
  persist(
    (set, get) => ({
      user: null,
      hydrated: false,
      bootstrapped: false,
      setUser: (user) => set({ user }),
      clear: () => set({ user: null }),
      setHydrated: (v) => set({ hydrated: v }),
      setBootstrapped: (v) => set({ bootstrapped: v }),
      has: (code) => {
        const u = get().user;
        if (!u) return false;
        if (u.is_super_user) return true;
        if (u.permissions.includes("*")) return true;
        return u.permissions.includes(code);
      },
    }),
    {
      name: "greentech-auth",
      // Only the user profile is persisted now; JWTs live in httpOnly
      // cookies the browser manages for us, so there's nothing else
      // worth surviving a reload.
      partialize: (s) => ({ user: s.user }),
      onRehydrateStorage: () => (state) => state?.setHydrated(true),
    },
  ),
);
