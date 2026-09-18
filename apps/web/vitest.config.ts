import { defineConfig } from "vitest/config";
import path from "node:path";
export default defineConfig({
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
      "@fleetpilot/ui": path.resolve(__dirname, "../../packages/ui/index.tsx"),
      "@fleetpilot/auth": path.resolve(
        __dirname,
        "../../packages/auth/index.ts",
      ),
      "@fleetpilot/types": path.resolve(
        __dirname,
        "../../packages/types/index.ts",
      ),
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./tests/setup.ts"],
    include: ["tests/**/*.test.ts", "tests/**/*.test.tsx"],
    maxWorkers: 1,
    globals: true,
  },
});
