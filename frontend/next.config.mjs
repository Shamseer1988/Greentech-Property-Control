/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    // Server-side proxy target for /api/*. Order:
    //  1. BACKEND_INTERNAL_URL — set by the operator if backend lives on
    //     a different host. Server-only env (not NEXT_PUBLIC_*), never
    //     leaks into the client bundle.
    //  2. NEXT_PUBLIC_API_URL — for `npm run dev` against a remote API.
    //  3. localhost:5000 — same-host default (backend waitress on
    //     loopback, frontend talks to it over 127.0.0.1).
    const target =
      process.env.BACKEND_INTERNAL_URL ||
      process.env.NEXT_PUBLIC_API_URL ||
      "http://localhost:5000";
    return [
      {
        source: "/api/:path*",
        destination: `${target}/api/:path*`,
      },
    ];
  },
  async headers() {
    return [
      {
        // Force Cloudflare and browsers to NEVER cache API responses.
        // We do this in the backend too, but applying it at the edge guarantees
        // Cloudflare sees it before any internal Next.js proxying obscures it.
        source: "/api/:path*",
        headers: [
          {
            key: "Cache-Control",
            value: "no-store, no-cache, must-revalidate, max-age=0",
          },
          {
            key: "Pragma",
            value: "no-cache",
          },
        ],
      },
    ];
  },
};

export default nextConfig;
