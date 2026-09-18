import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";
import { fileURLToPath } from "node:url";
export default defineConfig([
  ...nextVitals,
  ...nextTs,
  {
    settings: {
      next: { rootDir: fileURLToPath(new URL("./apps/web/", import.meta.url)) },
    },
    rules: {
      // Auth and organization switches intentionally discard the client router cache.
      "@next/next/no-location-assign-relative-destination": "off",
    },
  },
  globalIgnores([
    "**/.next/**",
    "**/.next-e2e/**",
    "**/next-env.d.ts",
    ".venv/**",
    ".runtime/**",
    "node_modules/**",
    "playwright-report/**",
    "test-results/**",
  ]),
]);
