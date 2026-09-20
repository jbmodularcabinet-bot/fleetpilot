import fs from "node:fs/promises";
import path from "node:path";
import assert from "node:assert/strict";
import { performance } from "node:perf_hooks";
import { fileURLToPath, pathToFileURL } from "node:url";
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const old = "C:/Users/User/Documents/ChatGPT/FleetPilot";
const { chromium } = await import(
  pathToFileURL(path.join(old, "node_modules/playwright/index.mjs")).href
);
const authorized = JSON.parse(
  await fs.readFile(
    path.join(root, ".runtime/batch16/authorized-demo-origin.json"),
    "utf8",
  ),
);
const base = authorized.origin;
assert(
  new URL(base).protocol === "https:" && new URL(base).origin === base,
  "Use the exact approved HTTPS demo origin",
);
const config = Object.fromEntries(
  (await fs.readFile(path.join(old, ".env"), "utf8"))
    .split(/\r?\n/)
    .filter((l) => l.includes("=") && !l.trim().startsWith("#"))
    .map((l) => {
      const i = l.indexOf("=");
      return [
        l.slice(0, i).trim(),
        l
          .slice(i + 1)
          .trim()
          .replace(/^["']|["']$/g, ""),
      ];
    }),
);
const query = "dataset=synthetic&date_from=2026-09-21&date_to=2026-09-24";
const output = path.join(
  root,
  ".runtime/batch16/demo-security-performance.json",
);
const browser = await chromium.launch({ channel: "chrome", headless: true });
const checks = [];
let benchmark;
async function check(name, run) {
  try {
    await run();
    checks.push({ name, status: "PASS" });
    console.log("PASS " + name);
  } catch (e) {
    checks.push({ name, status: "FAIL", error: e.message });
    console.log("FAIL " + name + ": " + e.message);
  }
}
async function login(email) {
  const context = await browser.newContext();
  const response = await context.request.post(base + "/api/v1/auth/login", {
    headers: { Origin: base },
    form: { username: email, password: config.DEMO_PASSWORD },
  });
  assert.equal(response.status(), 204);
  return context;
}
try {
  const owner = await login("carlo@example.com");
  await check("HTTPS session cookie flags", async () => {
    const cookies = await owner.cookies();
    const session = cookies.find((c) => c.name === "fp_session");
    assert(session);
    assert(session.secure && session.httpOnly);
    assert.equal(session.sameSite, "Lax");
  });
  await check("Exact origin allowed; unrelated origin rejected", async () => {
    const bad = await owner.request.post(base + "/api/v1/auth/login", {
      headers: { Origin: "https://unrelated.invalid" },
      form: {},
    });
    assert.equal(bad.status(), 403);
    assert.equal((await bad.json()).error.code, "csrf_rejected");
    const allowed = await owner.request.post(base + "/api/v1/auth/login", {
      headers: { Origin: base },
      form: {},
    });
    assert.equal(allowed.status(), 422);
  });
  await check("Public driver financial access denied", async () => {
    const driver = await login("juan@example.com");
    try {
      const response = await driver.request.get(
        base + "/api/v1/reports/trip-contribution?" + query,
      );
      assert.equal(response.status(), 403);
      const csv = await driver.request.get(
        base + "/api/v1/reports/trip-contribution?" + query + "&format=csv",
      );
      assert.equal(csv.status(), 403);
    } finally {
      await driver.close();
    }
  });
  await check("Public cross-tenant financial filter rejected", async () => {
    const other = await login("other-owner@example.com");
    try {
      const response = await other.request.get(
        base +
          "/api/v1/reports/trip-contribution?date_from=2026-09-21&date_to=2026-09-24&trip_id=a60a03eb-30d9-432b-b741-545a490c10a4",
      );
      assert.equal(response.status(), 404);
    } finally {
      await other.close();
    }
  });
  await check("Invalid or expired session cannot export", async () => {
    const invalid = await browser.newContext();
    try {
      await invalid.addCookies([
        {
          name: "fp_session",
          value: "synthetic-invalid-session",
          url: base,
          secure: true,
          httpOnly: true,
          sameSite: "Lax",
        },
      ]);
      const response = await invalid.request.get(
        base + "/api/v1/reports/trip-contribution?" + query + "&format=csv",
      );
      assert.equal(response.status(), 401);
    } finally {
      await invalid.close();
    }
  });
  await check("Four-trip public demo responsiveness budget", async () => {
    const samples = [];
    let maximumBytes = 0;
    const began = performance.now();
    for (let batch = 0; batch < 10; batch++)
      await Promise.all(
        [0, 1].map(async () => {
          const start = performance.now();
          const response = await owner.request.get(
            base + "/api/v1/intelligence/overview?" + query,
          );
          assert.equal(response.status(), 200);
          const body = await response.body();
          maximumBytes = Math.max(maximumBytes, body.length);
          assert.equal(JSON.parse(body).summary.trip_count, 4);
          samples.push(performance.now() - start);
        }),
      );
    samples.sort((a, b) => a - b);
    const percentile = (p) =>
      Math.round(samples[Math.ceil(p * samples.length) - 1] * 100) / 100;
    benchmark = {
      dataset_trips: 4,
      samples: 20,
      concurrency: 2,
      transport: "Public HTTPS tunnel including network and web/API forwarding",
      p50_ms: percentile(0.5),
      p95_ms: percentile(0.95),
      max_ms: Math.round(samples.at(-1) * 100) / 100,
      maximum_response_bytes: maximumBytes,
      elapsed_ms: Math.round((performance.now() - began) * 100) / 100,
      acceptance_p95_ms: 2500,
      production_capacity_verified: false,
      large_1000_trip_10000_expense_test: "NOT RUN",
    };
    assert(
      benchmark.p95_ms <= 2500,
      `p95 ${benchmark.p95_ms}ms exceeds the predeclared 2500ms demo budget`,
    );
  });
  await owner.close();
} finally {
  await browser.close();
  const result = {
    origin: base,
    checked_at: new Date().toISOString(),
    passed: checks.filter((c) => c.status === "PASS").length,
    failed: checks.filter((c) => c.status === "FAIL").length,
    checks,
    benchmark,
  };
  await fs.writeFile(output, JSON.stringify(result, null, 2));
  console.log(JSON.stringify(result));
  process.exitCode = result.failed ? 1 : 0;
}
