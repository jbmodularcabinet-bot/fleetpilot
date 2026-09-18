import {
  chromium,
  test,
  expect,
  type Page,
  type APIRequestContext,
} from "@playwright/test";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";
import { expectLockedV1 } from "./design-v1";

function verifyOriginals() {
  execFileSync(
    resolve(".venv/Scripts/python.exe"),
    ["scripts/verify-design-assets.py"],
    {
      encoding: "utf8",
      timeout: 30000,
    },
  );
}
test.beforeAll(verifyOriginals);
test.setTimeout(150000);
test.afterAll(verifyOriginals);
interface Fixture {
  email: string;
  driver_email: string;
  driver_user_id: string;
  organization_id: string;
}
interface Trip {
  id: string;
  version: number;
  trip_number: string;
  current_status: string;
}
const headers = { Origin: "http://localhost:3100" };
const actions = [
  "dispatch",
  "start_pickup",
  "arrive_pickup",
  "start_loading",
  "finish_loading",
  "depart_pickup",
  "arrive_delivery",
  "start_unloading",
  "finish_unloading",
];
function provision(label: string): Fixture {
  return JSON.parse(
    execFileSync(
      resolve(".venv/Scripts/python.exe"),
      ["scripts/api-task.py", "--test", "tests.e2e_setup", label, "--driver"],
      { encoding: "utf8", timeout: 60000 },
    ),
  );
}
async function login(page: Page, email: string, driver = false) {
  await page.request.post("/api/v1/auth/logout", { headers });
  await page.goto("/login");
  await page.getByLabel("Email address").fill(email);
  await page
    .getByLabel("Password", { exact: true })
    .fill(process.env.DEMO_PASSWORD!);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(driver ? /\/driver$/ : /\/dashboard$/, {
    timeout: 30000,
  });
}
async function post(api: APIRequestContext, path: string, data: unknown) {
  const r = await api.post(`/api/v1${path}`, { headers, data });
  expect(r.ok(), await r.text()).toBe(true);
  return r.json();
}
async function prepare(
  page: Page,
  fixture: Fixture,
  stop = "finish_unloading",
): Promise<Trip> {
  await login(page, fixture.email);
  const customer = await post(page.request, "/customers", {
    customer_code: "ACME-001",
    company_name: "ACME Logistics Client",
  });
  const vehicle = await post(page.request, "/vehicles", {
    unit_number: "TRK-001",
    plate_number: "ABC-1234",
    vehicle_type: "Wing van",
  });
  const driver = await post(page.request, "/drivers", {
    employee_number: "DRV-001",
    first_name: "Juan",
    last_name: "Dela Cruz",
    user_id: fixture.driver_user_id,
  });
  let trip = await post(page.request, "/trips", {
    customer_id: customer.id,
    vehicle_id: vehicle.id,
    driver_id: driver.id,
    pickup_name: "Warehouse A",
    pickup_address: "100 Test Road, Manila",
    delivery_name: "Customer Site B",
    delivery_address: "200 Test Road, Laguna",
    scheduled_pickup_at: "2030-02-10T08:00:00+08:00",
    scheduled_delivery_at: "2030-02-10T16:00:00+08:00",
  });
  for (const action of actions) {
    trip = await post(page.request, `/trips/${trip.id}/transition`, {
      expected_version: trip.version,
      action,
    });
    if (action === stop) break;
  }
  return trip;
}
async function signature(page: Page) {
  const canvas = page.getByLabel("Recipient signature drawing area");
  await canvas.evaluate((element) =>
    element.scrollIntoView({ block: "center" }),
  );
  const box = await canvas.boundingBox();
  expect(box).not.toBeNull();
  await page.mouse.move(box!.x + 15, box!.y + 35);
  await page.mouse.down();
  await page.mouse.move(box!.x + 55, box!.y + 65, { steps: 8 });
  await page.mouse.move(box!.x + 90, box!.y + 20, { steps: 8 });
  await page.mouse.up();
  await page
    .getByRole("checkbox", {
      name: "Recipient confirms this signature",
      exact: true,
    })
    .check();
}

async function readyOffline(page: Page, trip: Trip) {
  await page.goto(`/driver/trips/${trip.id}`);
  await expect(
    page.getByRole("heading", { name: trip.trip_number, exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Delivery evidence", { exact: true }),
  ).toBeVisible();
  await page.evaluate(async () => {
    await navigator.serviceWorker.ready;
  });
  await expect
    .poll(() =>
      page.evaluate(
        async () =>
          !!(await (
            await caches.open("fleetpilot-driver-shell-v1")
          ).match("/driver-offline")),
      ),
    )
    .toBe(true);
  await page.reload();
  await expect
    .poll(() => page.evaluate(() => !!navigator.serviceWorker.controller))
    .toBe(true);
  await expect(
    page.getByRole("heading", { name: trip.trip_number, exact: true }),
  ).toBeVisible();
}

test("Offline milestones survive reopen and sync once in order", async ({
  page,
  context,
}) => {
  const fixture = provision("offline-milestones");
  const trip = await prepare(page, fixture, "dispatch");
  await login(page, fixture.driver_email, true);
  await readyOffline(page, trip);
  await context.setOffline(true);
  await page.reload();
  await expect(
    page.getByRole("heading", { name: trip.trip_number, exact: true }),
  ).toBeVisible();
  page.on("dialog", (d) => d.accept());
  for (const name of [
    "Start / en route to pickup",
    "Arrived at pickup",
    "Start loading",
  ]) {
    await page.getByRole("button", { name, exact: true }).click();
    await expect(
      page.getByText(
        "Saved locally. The status badge shows the last server-confirmed state.",
      ),
    ).toBeVisible();
  }
  await expect(page.getByText(/3 actions saved locally/)).toBeVisible();
  await page.close();
  const reopened = await context.newPage();
  await reopened.goto(`/driver/trips/${trip.id}`);
  await expect(
    reopened.getByRole("button", { name: "Loading complete", exact: true }),
  ).toBeVisible();
  await expect(reopened.getByText(/3 actions saved locally/)).toBeVisible();
  await context.setOffline(false);
  await expect(reopened.getByText(/Synced · no pending actions/)).toBeVisible({
    timeout: 45000,
  });
  const events = await (
    await reopened.request.get(`/api/v1/driver/trips/${trip.id}/milestones`)
  ).json();
  expect(
    events.slice(-3).map((e: { milestone_type: string }) => e.milestone_type),
  ).toEqual(["EN_ROUTE_TO_PICKUP", "ARRIVED_PICKUP", "LOADING_STARTED"]);
  expect(
    events.filter(
      (e: { milestone_type: string }) => e.milestone_type === "LOADING_STARTED",
    ),
  ).toHaveLength(1);
  await reopened.setViewportSize({ width: 390, height: 844 });
  await expectLockedV1(reopened, true);
  await reopened.screenshot({
    path: "test-results/batch7-offline-driver.png",
    fullPage: true,
  });
});

for (const issue of [false, true])
  test(`Offline ${issue ? "exception" : "POD"} evidence survives reopen and replays once`, async ({
    page,
    context,
  }) => {
    const fixture = provision(issue ? "offline-issue" : "offline-pod");
    const trip = await prepare(
      page,
      fixture,
      issue ? "arrive_delivery" : "finish_unloading",
    );
    await login(page, fixture.driver_email, true);
    await readyOffline(page, trip);
    await context.setOffline(true);
    if (issue) {
      await page
        .getByRole("button", { name: "Report delivery issue", exact: true })
        .click();
      await page
        .getByLabel("Delivery issue", { exact: true })
        .selectOption("RECIPIENT_UNAVAILABLE");
      await page
        .getByLabel("Exception notes", { exact: true })
        .fill("Recipient contact unreachable.");
      await page
        .getByLabel("Exception photos (optional)")
        .setInputFiles("tests/fixtures/delivery.png");
    } else {
      await page
        .getByLabel("Recipient name", { exact: true })
        .fill("Maria Santos");
      await page
        .getByLabel("Recipient role", { exact: true })
        .fill("Receiving Staff");
      await page
        .getByLabel("Delivery notes", { exact: true })
        .fill("Cargo received in good condition.");
      await page
        .getByLabel("Delivery photos (at least one required)")
        .setInputFiles("tests/fixtures/delivery.png");
      await signature(page);
      await page
        .getByRole("checkbox", {
          name: "I confirm the cargo was delivered to this recipient.",
          exact: true,
        })
        .check();
    }
    await expect(
      page.getByText("Draft saved locally.", { exact: true }),
    ).toBeVisible();
    await page
      .getByRole("button", {
        name: issue ? "Submit delivery issue" : "Submit proof of delivery",
        exact: true,
      })
      .click();
    await expect(page.getByText(/actions saved locally/)).toBeVisible();
    await page.close();
    const reopened = await context.newPage();
    await reopened.goto(`/driver/trips/${trip.id}`);
    await expect(
      reopened.getByText(/Saved\/selected photos: delivery.png/),
    ).toBeVisible();
    if (!issue) {
      await expect(
        reopened.getByLabel("Recipient name", { exact: true }),
      ).toHaveValue("Maria Santos");
      await expect(reopened.getByText(/Signature retained/)).toBeVisible();
    }
    await context.setOffline(false);
    await expect(reopened.getByText(/Synced · no pending actions/)).toBeVisible(
      { timeout: 45000 },
    );
    const h = await (
      await reopened.request.get(`/api/v1/trips/${trip.id}/delivery-attempts`)
    ).json();
    expect(h.total).toBe(1);
    expect(h.items[0].evidence).toHaveLength(issue ? 1 : 2);
    expect(h.items[0].status).toBe(issue ? "FAILED" : "DELIVERED");
    const state = await (
      await reopened.request.get(`/api/v1/driver/trips/${trip.id}`)
    ).json();
    expect(state.current_status === "DELIVERED").toBe(!issue);
    await reopened.reload();
    await expect(
      reopened.getByText(/Synced · no pending actions/),
    ).toBeVisible();
    await reopened.setViewportSize({ width: 768, height: 1024 });
    await expectLockedV1(reopened, true);
  });

test("PWA manifest, private caches and storage failure", async ({
  page,
  context,
}) => {
  const fixture = provision("offline-storage");
  const trip = await prepare(page, fixture, "dispatch");
  await login(page, fixture.driver_email, true);
  await readyOffline(page, trip);
  const manifest = await (
    await page.request.get("/manifest.webmanifest")
  ).json();
  expect(manifest.name).toBe("FleetPilot Driver");
  expect(manifest.display).toBe("standalone");
  expect(manifest.icons[0].src).toBe("/driver-icon.svg");
  const cdp = await context.newCDPSession(page);
  await cdp.send("Page.enable");
  const install = await cdp.send("Page.getInstallabilityErrors");
  const installabilityErrorIds = install.installabilityErrors.map(
    (e) => e.errorId,
  );
  // Chromium versions differ on whether an incognito context reports
  // `in-incognito` here. Reject any product/PWA installability error while
  // allowing that browser-context-only diagnostic to be absent or present.
  expect(
    installabilityErrorIds.filter((errorId) => errorId !== "in-incognito"),
  ).toEqual([]);
  const urls = await page.evaluate(async () => {
    const cache = await caches.open("fleetpilot-driver-shell-v1");
    return (await cache.keys()).map((r) => new URL(r.url).pathname);
  });
  expect(urls).toContain("/driver-offline");
  expect(
    urls.some((u) => u.startsWith("/api/") || u.startsWith("/dashboard")),
  ).toBe(false);
  await context.setOffline(true);
  page.on("dialog", (d) => d.accept());
  await page.evaluate(() => {
    IDBObjectStore.prototype.put = function () {
      throw new DOMException("Synthetic quota failure", "QuotaExceededError");
    };
  });
  await page
    .getByRole("button", { name: "Start / en route to pickup", exact: true })
    .click();
  await expect(
    page
      .getByRole("alert")
      .filter({ hasText: /Not saved|Unable to save locally/ }),
  ).toBeVisible();
  const count = await page.evaluate(
    () =>
      new Promise<number>((resolve, reject) => {
        const r = indexedDB.open("fleetpilot-driver-v1");
        r.onsuccess = () => {
          const q = r.result
            .transaction("actions")
            .objectStore("actions")
            .count();
          q.onsuccess = () => {
            resolve(q.result);
            r.result.close();
          };
        };
        r.onerror = () => reject(r.error);
      }),
  );
  expect(count).toBe(0);
});

test("Installability in a persistent Chrome profile", async () => {
  const persistent = await chromium.launchPersistentContext(
    resolve(`.runtime/batch7-install-${Date.now()}`),
    {
      channel: process.env.PLAYWRIGHT_CHANNEL || "chrome",
      headless: true,
      baseURL: "http://localhost:3100",
    },
  );
  try {
    const page = await persistent.newPage();
    const fixture = provision("pwa-install");
    const trip = await prepare(page, fixture, "dispatch");
    await login(page, fixture.driver_email, true);
    await readyOffline(page, trip);
    const cdp = await persistent.newCDPSession(page);
    await cdp.send("Page.enable");
    await expect
      .poll(
        async () =>
          (await cdp.send("Page.getInstallabilityErrors")).installabilityErrors,
        { timeout: 15000 },
      )
      .toEqual([]);
    await persistent.setOffline(true);
    await page.reload();
    await expect(
      page.getByRole("heading", { name: trip.trip_number, exact: true }),
    ).toBeVisible();
  } finally {
    await persistent.close();
  }
});

test("IndexedDB compatible upgrade preserves pending records and binary evidence", async ({
  page,
}) => {
  await page.goto("/login");
  await page.evaluate(
    () =>
      new Promise<void>((resolve, reject) => {
        const r = indexedDB.open("fleetpilot-driver-v1", 1);
        r.onupgradeneeded = () => {
          for (const name of ["meta", "snapshots", "actions"])
            r.result.createObjectStore(name);
        };
        r.onsuccess = () => {
          const db = r.result;
          const tx = db.transaction("actions", "readwrite");
          tx.objectStore("actions").put(
            {
              id: "legacy-pending",
              status: "PENDING",
              file: new Blob(["preserve-me"], { type: "image/png" }),
            },
            "legacy-pending",
          );
          tx.oncomplete = () => {
            db.close();
            resolve();
          };
          tx.onerror = () => reject(tx.error);
        };
      }),
  );
  await page.goto("/driver-offline");
  await expect(
    page.getByText(/Reconnect and sign in to unlock saved work/),
  ).toBeVisible();
  const result = await page.evaluate(
    () =>
      new Promise<{ version: number; text: string; status: string }>(
        (resolve, reject) => {
          const r = indexedDB.open("fleetpilot-driver-v1");
          r.onsuccess = () => {
            const db = r.result;
            const q = db
              .transaction("actions")
              .objectStore("actions")
              .get("legacy-pending");
            q.onsuccess = async () => {
              resolve({
                version: db.version,
                text: await q.result.file.text(),
                status: q.result.status,
              });
              db.close();
            };
          };
          r.onerror = () => reject(r.error);
        },
      ),
  );
  expect(result).toEqual({
    version: 2,
    text: "preserve-me",
    status: "PENDING",
  });
});

test("Stale queued action needs review; logout clears all driver data", async ({
  page,
  context,
}) => {
  const fixture = provision("offline-conflict");
  const trip = await prepare(page, fixture, "dispatch");
  await login(page, fixture.driver_email, true);
  await readyOffline(page, trip);
  await context.setOffline(true);
  page.on("dialog", (d) => d.accept());
  await page
    .getByRole("button", { name: "Start / en route to pickup", exact: true })
    .click();
  await expect(page.getByText(/1 actions saved locally/)).toBeVisible();
  // A separate authorized write advances the authoritative version while the page is offline.
  const r = await page.request.post(
    `/api/v1/driver/trips/${trip.id}/transition`,
    {
      headers,
      data: { expected_version: trip.version, action: "start_pickup" },
    },
  );
  expect(r.ok()).toBe(true);
  await context.setOffline(false);
  await expect(
    page.getByRole("alert").filter({ hasText: /Needs attention/ }),
  ).toBeVisible({ timeout: 45000 });
  await page.goto("/driver/profile");
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(page).toHaveURL(/\/login$/);
  const counts = await page.evaluate(
    () =>
      new Promise<number[]>((resolve, reject) => {
        const r = indexedDB.open("fleetpilot-driver-v1");
        r.onsuccess = async () => {
          const db = r.result;
          const result = await Promise.all(
            ["meta", "actions", "drafts", "snapshots"].map(
              (s) =>
                new Promise<number>((done) => {
                  const q = db.transaction(s).objectStore(s).count();
                  q.onsuccess = () => done(q.result);
                }),
            ),
          );
          db.close();
          resolve(result);
        };
        r.onerror = () => reject(r.error);
      }),
  );
  expect(counts).toEqual([0, 0, 0, 0]);
  await login(page, "juan@example.com", true);
  await expect(page.getByText(trip.trip_number, { exact: true })).toHaveCount(
    0,
  );
  expect(
    (await page.request.get(`/api/v1/driver/trips/${trip.id}`)).status(),
  ).toBe(404);
});

test("Twenty queued commands and photos survive a compatible worker update", async ({
  page,
  context,
}) => {
  const fixture = provision("offline-twenty");
  const trip = await prepare(page, fixture, "dispatch");
  await login(page, fixture.driver_email, true);
  await readyOffline(page, trip);
  page.on("dialog", (d) => d.accept());
  await context.setOffline(true);
  for (const name of [
    "Start / en route to pickup",
    "Arrived at pickup",
    "Start loading",
    "Loading complete",
    "Depart pickup",
    "Arrived at delivery",
    "Start unloading",
    "Unloading complete",
  ]) {
    await page.getByRole("button", { name, exact: true }).click();
  }
  await page.getByLabel("Recipient name", { exact: true }).fill("Maria Santos");
  await page
    .getByLabel("Delivery photos (at least one required)")
    .setInputFiles(Array(10).fill("tests/fixtures/delivery.png"));
  await page
    .getByRole("checkbox", {
      name: "I confirm the cargo was delivered to this recipient.",
      exact: true,
    })
    .check();
  await page
    .getByRole("button", { name: "Submit proof of delivery", exact: true })
    .click();
  await expect(page.getByText(/20 actions saved locally/)).toBeVisible();
  const before = await (
    await page.request.get(`/api/v1/driver/trips/${trip.id}`)
  ).json();
  expect(before.current_status).toBe("DISPATCHED");
  // Hold the same browser lock so reconnect cannot drain the queue during the update check.
  await page.evaluate(
    () =>
      new Promise<void>((resolve) => {
        void navigator.locks.request(
          "fleetpilot-driver-sync",
          () =>
            new Promise<void>((release) => {
              (window as unknown as { releaseSync: () => void }).releaseSync =
                release;
              resolve();
            }),
        );
      }),
  );
  await context.setOffline(false);
  await page.evaluate(async () => {
    const r = await navigator.serviceWorker.register(
      "/driver-worker.js?compatible-v2",
      { scope: "/driver" },
    );
    await r.update();
  });
  await expect
    .poll(() =>
      page.evaluate(
        async () =>
          !!(await navigator.serviceWorker.getRegistration("/driver"))?.waiting,
      ),
    )
    .toBe(true);
  await expect(page.getByText(/20 actions saved locally/)).toBeVisible();
  await page.close();
  const reopened = await context.newPage();
  await reopened.goto(`/driver/trips/${trip.id}`);
  await expect(reopened.getByText(/Synced · no pending actions/)).toBeVisible({
    timeout: 60000,
  });
  const history = await (
    await reopened.request.get(`/api/v1/trips/${trip.id}/delivery-attempts`)
  ).json();
  expect(history.total).toBe(1);
  expect(history.items[0].evidence).toHaveLength(10);
  expect(history.items[0].status).toBe("DELIVERED");
});

test("Supported background sync processes a queue with the Driver page closed", async ({
  page,
  context,
}) => {
  const fixture = provision("offline-background");
  const trip = await prepare(page, fixture, "dispatch");
  await login(page, fixture.driver_email, true);
  await readyOffline(page, trip);
  const monitor = await context.newPage();
  await monitor.goto("/login");
  const cdp = await context.newCDPSession(monitor);
  let registrationId = "";
  cdp.on("ServiceWorker.workerRegistrationUpdated", (event) => {
    registrationId =
      event.registrations.find(
        (r) => r.scopeURL === "http://localhost:3100/driver",
      )?.registrationId || registrationId;
  });
  await cdp.send("ServiceWorker.enable");
  await expect.poll(() => registrationId).not.toBe("");
  await context.setOffline(true);
  page.on("dialog", (d) => d.accept());
  await page
    .getByRole("button", { name: "Start / en route to pickup", exact: true })
    .click();
  await expect(page.getByText(/1 actions saved locally/)).toBeVisible();
  await page.close();
  await context.setOffline(false);
  const worker = context.serviceWorkers()[0];
  expect(
    await worker.evaluate(() => ({
      online: navigator.onLine,
      locks: !!navigator.locks,
    })),
  ).toEqual({ online: true, locks: true });
  const workerErrors: string[] = [];
  context.on("console", (message) => {
    if (message.type() === "error") workerErrors.push(message.text());
  });
  await cdp.send("ServiceWorker.dispatchSyncEvent", {
    origin: "http://localhost:3100",
    registrationId,
    tag: "fleetpilot-driver-sync",
    lastChance: false,
  });
  await expect
    .poll(
      async () =>
        (
          await (
            await monitor.request.get(`/api/v1/driver/trips/${trip.id}`)
          ).json()
        ).current_milestone,
      {
        timeout: 30000,
        message: `Background worker errors: ${workerErrors.join("; ")}`,
      },
    )
    .toBe("EN_ROUTE_TO_PICKUP");
  const events = await (
    await monitor.request.get(`/api/v1/driver/trips/${trip.id}/milestones`)
  ).json();
  expect(
    events.filter(
      (e: { milestone_type: string }) =>
        e.milestone_type === "EN_ROUTE_TO_PICKUP",
    ),
  ).toHaveLength(1);
});

test("Lost successful response retries the same command without duplicate milestones", async ({
  page,
}) => {
  test.setTimeout(90000);
  const fixture = provision("offline-lost-response");
  const trip = await prepare(page, fixture, "dispatch");
  await login(page, fixture.driver_email, true);
  await readyOffline(page, trip);
  const keys: string[] = [];
  let dropped = false;
  await page.route(
    `**/api/v1/driver/sync/${trip.id}/transition`,
    async (route) => {
      keys.push(route.request().headers()["idempotency-key"]);
      const response = await route.fetch();
      if (!dropped) {
        expect(response.status()).toBe(200);
        dropped = true;
        await route.abort("failed");
      } else await route.fulfill({ response });
    },
  );
  page.on("dialog", (d) => d.accept());
  await page
    .getByRole("button", { name: "Start / en route to pickup", exact: true })
    .click();
  await expect.poll(() => dropped).toBe(true);
  await expect
    .poll(() => keys.length, { timeout: 60000 })
    .toBeGreaterThanOrEqual(2);
  expect(new Set(keys).size).toBe(1);
  await expect(page.getByText(/Synced · no pending actions/)).toBeVisible();
  const events = await (
    await page.request.get(`/api/v1/driver/trips/${trip.id}/milestones`)
  ).json();
  expect(
    events.filter(
      (e: { milestone_type: string }) =>
        e.milestone_type === "EN_ROUTE_TO_PICKUP",
    ),
  ).toHaveLength(1);
});
