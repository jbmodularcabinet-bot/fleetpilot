import type { NextConfig } from "next";
import { z } from "zod";

const api = z
  .url()
  .parse(process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8000");
if (process.env.NODE_ENV === "production" && !process.env.API_INTERNAL_URL) {
  throw new Error(
    "API_INTERNAL_URL must be explicitly configured for production builds",
  );
}
const config: NextConfig = {
  output: "standalone",
  distDir: process.env.FLEETPILOT_E2E === "1" ? ".next-e2e" : ".next",
  transpilePackages: [
    "@fleetpilot/ui",
    "@fleetpilot/auth",
    "@fleetpilot/types",
  ],
  poweredByHeader: false,
  devIndicators: false,
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${api}/api/:path*` }];
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          {
            key: "Permissions-Policy",
            value: "camera=(), microphone=(), geolocation=()",
          },
        ],
      },
    ];
  },
};
export default config;
