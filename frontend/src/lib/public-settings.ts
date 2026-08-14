"use client";

import { useEffect } from "react";
import { create } from "zustand";

export type AccentColor = "blue" | "emerald" | "violet" | "amber" | "rose";
export type TableDensity = "compact" | "comfortable" | "spacious";

type PublicSettings = {
  companyName: string;
  logoUrl: string | null;
  accentColor: AccentColor;
  glassmorphism: boolean;
  compactMode: boolean;
  sidebarDefaultCollapsed: boolean;
  tableDensity: TableDensity;
  loaded: boolean;
  load: () => Promise<void>;
};

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || "";

const DEFAULT_NAME = process.env.NEXT_PUBLIC_APP_NAME || "GreenTech Real Estate Portal";

export const usePublicSettings = create<PublicSettings>((set, get) => ({
  companyName: DEFAULT_NAME,
  logoUrl: null,
  accentColor: "blue",
  glassmorphism: true,
  compactMode: false,
  sidebarDefaultCollapsed: false,
  tableDensity: "comfortable",
  loaded: false,
  load: async () => {
    if (get().loaded) return;
    try {
      const resp = await fetch(`${BASE_URL}/api/v1/settings/public`);
      if (!resp.ok) return;
      const body = await resp.json();
      const data = body?.data ?? {};
      const accent = (data["ui.accent_color"] ?? "blue") as AccentColor;
      const density = (data["ui.table_density"] ?? "comfortable") as TableDensity;
      set({
        companyName: data["company.name"] || get().companyName,
        logoUrl: data["company.logo_url"] || null,
        accentColor: accent,
        glassmorphism: data["ui.glassmorphism"] !== false,
        compactMode: data["ui.compact_mode"] === true,
        sidebarDefaultCollapsed: data["ui.sidebar_default_collapsed"] === true,
        tableDensity: density,
        loaded: true,
      });
    } catch {
      set({ loaded: true });
    }
  },
}));

export function usePublicSettingsLoader() {
  const load = usePublicSettings((s) => s.load);
  const loaded = usePublicSettings((s) => s.loaded);
  useEffect(() => {
    if (!loaded) load();
  }, [loaded, load]);
}

export function useCompanyName() {
  usePublicSettingsLoader();
  return usePublicSettings((s) => s.companyName);
}

export function useCompanyLogo() {
  usePublicSettingsLoader();
  return usePublicSettings((s) => s.logoUrl);
}

export async function refreshPublicSettings() {
  usePublicSettings.setState({ loaded: false });
  await usePublicSettings.getState().load();
}
