import { beforeEach, describe, expect, it, vi } from "vitest";
import { refreshPublicSettings, usePublicSettings } from "./public-settings";

const ORIGINAL_FETCH = global.fetch;

describe("public settings store", () => {
  beforeEach(() => {
    usePublicSettings.setState({
      companyName: "GreenTech Real Estate Portal",
      logoUrl: null,
      accentColor: "blue",
      glassmorphism: true,
      compactMode: false,
      sidebarDefaultCollapsed: false,
      tableDensity: "comfortable",
      loaded: false,
    });
  });

  it("uses defaults before load", () => {
    const s = usePublicSettings.getState();
    expect(s.companyName).toBe("GreenTech Real Estate Portal");
    expect(s.accentColor).toBe("blue");
    expect(s.glassmorphism).toBe(true);
  });

  it("merges API response into the store", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        data: {
          "company.name": "GreenTech Real Estate",
          "company.logo_url": "https://example.com/logo.png",
          "ui.accent_color": "violet",
          "ui.glassmorphism": false,
          "ui.compact_mode": true,
          "ui.sidebar_default_collapsed": true,
          "ui.table_density": "compact",
        },
      }),
    }) as unknown as typeof fetch;

    await refreshPublicSettings();
    const s = usePublicSettings.getState();
    expect(s.companyName).toBe("GreenTech Real Estate");
    expect(s.logoUrl).toBe("https://example.com/logo.png");
    expect(s.accentColor).toBe("violet");
    expect(s.glassmorphism).toBe(false);
    expect(s.compactMode).toBe(true);
    expect(s.tableDensity).toBe("compact");
    expect(s.loaded).toBe(true);
    global.fetch = ORIGINAL_FETCH;
  });

  it("falls back gracefully when fetch fails", async () => {
    global.fetch = vi.fn().mockRejectedValue(new Error("network down")) as unknown as typeof fetch;
    await refreshPublicSettings();
    const s = usePublicSettings.getState();
    expect(s.loaded).toBe(true);
    expect(s.companyName).toBe("GreenTech Real Estate Portal");  // default kept
    global.fetch = ORIGINAL_FETCH;
  });
});
