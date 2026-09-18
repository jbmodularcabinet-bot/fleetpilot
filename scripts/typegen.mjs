import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
// Route type generation does not contact the API. Set an explicit local value
// for this tooling process without relaxing production build validation.
const next = fileURLToPath(new URL("../node_modules/next/dist/bin/next", import.meta.url));
const result = spawnSync(process.execPath, [next, "typegen"], { stdio: "inherit", windowsHide: true, env: { ...process.env, API_INTERNAL_URL: process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8000" } });
process.exit(result.status ?? 1);
