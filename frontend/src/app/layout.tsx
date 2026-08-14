import type { Metadata, Viewport } from "next";
import "./globals.css";
import { ThemeProvider } from "@/components/theme-provider";
import { ThemeBridge } from "@/components/theme-bridge";
import { ServiceWorkerRegister } from "@/components/sw-register";
import { ObservabilityInit } from "@/components/observability-init";
import { QueryProvider } from "@/components/query-provider";
import { Toaster } from "@/components/ui/toast";

export const metadata: Metadata = {
  title: {
    default: "GreenTech Real Estate Portal",
    template: "%s · GreenTech Real Estate",
  },
  description: "Property, contract and rent control for GreenTech real estate division",
  manifest: "/manifest.webmanifest",
  applicationName: "GreenTech Real Estate",
  appleWebApp: {
    capable: true,
    title: "GreenTech Portal",
    statusBarStyle: "black-translucent",
  },
  // Mirror the Apple PWA capability hint with the standard one so we don't
  // ship a deprecated-only tag.
  other: {
    "mobile-web-app-capable": "yes",
  },
  icons: {
    icon: [
      { url: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
      { url: "/icons/icon-512.png", sizes: "512x512", type: "image/png" },
    ],
    apple: [{ url: "/icons/icon-192.png", sizes: "192x192", type: "image/png" }],
  },
  formatDetection: { telephone: false },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f1f5f9" },
    { media: "(prefers-color-scheme: dark)", color: "#0b1220" },
  ],
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>
        <ThemeProvider attribute="class" defaultTheme="system" enableSystem disableTransitionOnChange>
          <ThemeBridge />
          <ServiceWorkerRegister />
          <ObservabilityInit />
          <QueryProvider>
            {children}
          </QueryProvider>
          <Toaster />
        </ThemeProvider>
      </body>
    </html>
  );
}
