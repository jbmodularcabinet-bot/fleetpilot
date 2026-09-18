// Match the standalone Docker artifact assembly for local production browser tests.
import { cpSync } from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

const web = resolve(import.meta.dirname, "../apps/web");
const standalone = resolve(web, ".next/standalone/apps/web");
cpSync(resolve(web, ".next/static"), resolve(standalone, ".next/static"), {
  recursive: true,
});
cpSync(resolve(web, "public"), resolve(standalone, "public"), {
  recursive: true,
});
process.env.HOSTNAME = "127.0.0.1";
process.env.PORT = "3100";
await import(pathToFileURL(resolve(standalone, "server.js")).href);
