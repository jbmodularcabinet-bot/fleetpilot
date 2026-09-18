import type { Identity } from "@fleetpilot/types";
import type { TripRecord } from "./trips";

export const DB_NAME = "fleetpilot-driver-v1";
export const STORES = ["meta", "snapshots", "actions", "drafts"] as const;
type Store = (typeof STORES)[number];
export interface Owner {
  user_id: string;
  organization_id: string;
  driver_id: string | null;
  verified_at: string;
  offline_seconds: number;
  identity: Identity;
  locked?: boolean;
}
export interface Action {
  id: string;
  owner: string;
  trip: string;
  command: string;
  payload: Record<string, unknown>;
  expected_version: number;
  captured: string;
  sequence: number;
  resource?: string;
  depends?: string;
  file?: Blob;
  filename?: string;
  evidence_type?: string;
  status: "PENDING" | "SYNCING" | "SYNCED" | "FAILED" | "CONFLICTED";
  retries: number;
  next_attempt_at?: number;
  last_attempt_at?: string;
  error?: string;
  result?: Record<string, unknown>;
}
export interface Draft {
  mode: "pod" | "issue";
  recipient: string;
  role: string;
  notes: string;
  confirmed: boolean;
  kind: string;
  files: File[];
  signature: File | null;
}
let opening: Promise<IDBDatabase> | undefined;
export function openDB(): Promise<IDBDatabase> {
  if (!opening)
    opening = new Promise((resolve, reject) => {
      const request = indexedDB.open(DB_NAME, 2);
      request.onupgradeneeded = () => {
        // Additive upgrade. Never delete pending records on app/schema updates.
        for (const name of STORES)
          if (!request.result.objectStoreNames.contains(name))
            request.result.createObjectStore(name);
      };
      request.onsuccess = () => {
        request.result.onversionchange = () => {
          request.result.close();
          opening = undefined;
        };
        resolve(request.result);
      };
      request.onerror = () => {
        opening = undefined;
        reject(new Error("Local storage is unavailable. Nothing was saved."));
      };
      request.onblocked = () =>
        reject(
          new Error("Close other FleetPilot tabs and retry storage setup."),
        );
    });
  return opening;
}
async function read<T>(store: Store, key?: string): Promise<T> {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(store, "readonly");
    const req =
      key === undefined
        ? tx.objectStore(store).getAll()
        : tx.objectStore(store).get(key);
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(new Error("Cannot read saved driver data."));
  });
}
async function write(store: Store, key: string, value: unknown) {
  const db = await openDB();
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(store, "readwrite");
    tx.objectStore(store).put(value, key);
    tx.oncomplete = () => resolve();
    tx.onabort = tx.onerror = () =>
      reject(
        new Error(
          "Unable to save locally. Check device storage and retry; keep this screen open.",
        ),
      );
  });
}
const CROSS_TAB_SYNC_CHANNEL = "fleetpilot-driver-sync";
export function changed() {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new Event("fleetpilot-sync"));
  if (typeof BroadcastChannel !== "undefined") {
    const channel = new BroadcastChannel(CROSS_TAB_SYNC_CHANNEL);
    channel.postMessage({ type: "fleetpilot-sync" });
    channel.close();
  }
}
export const ownerKey = (o: Owner) =>
  `${o.organization_id}:${o.user_id}:${o.driver_id ?? "unlinked"}`;
export const rawOwner = () => read<Owner | undefined>("meta", "owner");
export async function owner() {
  const o = await rawOwner();
  if (
    !o ||
    o.locked ||
    Date.now() - Date.parse(o.verified_at) > o.offline_seconds * 1000 ||
    Date.now() < Date.parse(o.verified_at) - 60000
  )
    throw new Error(
      "Reconnect and sign in to unlock saved work. Pending work is retained for the same account.",
    );
  return o;
}
export async function clearOffline() {
  const db = await openDB();
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction([...STORES], "readwrite");
    for (const store of STORES) tx.objectStore(store).clear();
    tx.oncomplete = () => resolve();
    tx.onabort = () =>
      reject(new Error("Cannot clear local driver data. Retry sign out."));
  });
  changed();
}
async function lock() {
  const o = await rawOwner();
  if (o) await write("meta", "owner", { ...o, locked: true });
  changed();
}
export async function establish(identity?: Identity) {
  const r = await fetch("/api/v1/driver/offline-identity", {
    credentials: "same-origin",
    cache: "no-store",
  });
  if (!r.ok) {
    await lock();
    throw new Error("Sign in to sync saved work.");
  }
  const fresh = (await r.json()) as Owner;
  const old = await rawOwner();
  if (old && ownerKey(old) !== ownerKey(fresh)) await clearOffline();
  const id =
    identity ??
    (old && ownerKey(old) === ownerKey(fresh) ? old.identity : undefined);
  if (!id)
    throw new Error("Open the Driver App online to prepare offline access.");
  if (
    id.user.id !== fresh.user_id ||
    id.organization.id !== fresh.organization_id
  )
    throw new Error("Account changed. Reload the Driver App online.");
  // Keep only the identity needed by existing driver display and capability checks.
  fresh.identity = { ...id, organizations: [] };
  await write("meta", "owner", fresh);
  changed();
  return fresh;
}
export async function actions() {
  const o = await owner();
  return (await read<Action[]>("actions"))
    .filter((a) => a.owner === ownerKey(o))
    .sort((a, b) => a.sequence - b.sequence);
}
export async function pendingCount() {
  const rows = await read<Action[]>("actions");
  return rows.filter((a) => a.status !== "SYNCED").length;
}
export async function beforeAccountExit() {
  const n = await pendingCount();
  const drafts = await read<Draft[]>("drafts");
  if (
    (n || drafts.length) &&
    !window.confirm(
      `${n} actions and ${drafts.length} drafts are waiting to sync. Discard this unsynced work and sign out/change account? Cancel to keep it.`,
    )
  )
    return false;
  return true;
}
function cacheable(path: string) {
  return (
    path === "/driver/maintenance-vehicles" ||
    (/^\/driver\/trips(?:\?|\/|$)/.test(path) &&
      !path.includes("history=true")) ||
    /^\/trips\/[a-f0-9-]+\/(delivery-attempts|expenses)(?:\?|$)/.test(path)
  );
}
export async function cachedRead<T>(path: string): Promise<T> {
  const o = await owner();
  const key = `${ownerKey(o)}:${path}`;
  let data: T;
  try {
    const response = await fetch(`/api/v1${path}`, {
      credentials: "same-origin",
      cache: "no-store",
    });
    if (response.status === 401 || response.status === 403) {
      await lock();
      throw new Error("Sign in to continue. Saved work is retained.");
    }
    if (!response.ok)
      throw new Error(
        `Server request failed (${response.status}). Reconnect or contact your operator.`,
      );
    data = (await response.json()) as T;
    if (cacheable(path))
      await write("snapshots", key, { data, synced: new Date().toISOString() });
    if (path.startsWith("/driver/trips?") && !path.includes("history=true")) {
      for (const trip of (data as { items: TripRecord[] }).items) {
        await write("snapshots", `${ownerKey(o)}:/driver/trips/${trip.id}`, {
          data: trip,
          synced: new Date().toISOString(),
        });
      }
    }
  } catch (error) {
    // Only a network failure permits cached data, never authorization/server rejection.
    if (!(error instanceof TypeError) && navigator.onLine) throw error;
    await owner();
    const saved = await read<{ data: T; synced: string } | undefined>(
      "snapshots",
      key,
    );
    if (!saved || Date.now() - Date.parse(saved.synced) > 43200000)
      throw new Error(
        "This information is not saved for offline use. Reconnect to load it.",
      );
    data = saved.data;
  }
  if (/^\/driver\/trips\/[a-f0-9-]+$/.test(path))
    return project(data as TripRecord, await actions()) as T;
  return data;
}
const progression: Record<string, [string, string, string]> = {
  start_pickup: ["EN_ROUTE_TO_PICKUP", "arrive_pickup", "Arrived at pickup"],
  arrive_pickup: ["ARRIVED_PICKUP", "start_loading", "Start loading"],
  start_loading: ["LOADING_STARTED", "finish_loading", "Loading complete"],
  finish_loading: ["LOADING_COMPLETED", "depart_pickup", "Depart pickup"],
  depart_pickup: [
    "EN_ROUTE_TO_DELIVERY",
    "arrive_delivery",
    "Arrived at delivery",
  ],
  arrive_delivery: ["ARRIVED_DELIVERY", "start_unloading", "Start unloading"],
  start_unloading: [
    "UNLOADING_STARTED",
    "finish_unloading",
    "Unloading complete",
  ],
  finish_unloading: ["UNLOADING_COMPLETED", "", ""],
};
export function project(trip: TripRecord, rows: Action[]): TripRecord {
  const result = { ...trip };
  for (const row of rows.filter(
    (a) => a.trip === trip.id && a.status !== "SYNCED",
  )) {
    if (row.status === "CONFLICTED" || row.status === "FAILED") {
      result.next_action = null;
      break;
    }
    if (row.command.startsWith("defect")) continue;
    if (row.command === "transition") {
      const next = progression[String(row.payload.action)];
      if (next) {
        result.current_milestone = next[0];
        result.next_action = next[1] || null;
        result.next_action_label = next[2] || null;
      }
    }
    result.version = row.expected_version + 1;
    result.offline_pending = true;
  }
  // current_status stays server-confirmed, especially DELIVERED.
  return result;
}
async function enqueue(rows: Action[]) {
  const o = await owner();
  const db = await openDB();
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(["actions", "drafts"], "readwrite");
    const request = tx.objectStore("actions").getAll();
    request.onsuccess = () => {
      const all = request.result as Action[];
      const pending = all.filter((a) => a.status !== "SYNCED");
      const bytes = [...pending, ...rows].reduce(
        (n, a) => n + (a.file?.size ?? 0),
        0,
      );
      if (
        pending.length + rows.length > 100 ||
        bytes > 40 * 1024 * 1024 ||
        pending.some(
          (a) =>
            !a.command.startsWith("defect") &&
            !rows[0].command.startsWith("defect") &&
            a.trip === rows[0].trip &&
            a.expected_version >= rows[0].expected_version,
        )
      ) {
        tx.abort();
        return;
      }
      let sequence = Math.max(0, ...all.map((a) => a.sequence));
      for (const row of rows)
        tx.objectStore("actions").put(
          { ...row, owner: ownerKey(o), sequence: ++sequence },
          row.id,
        );
    };
    tx.oncomplete = () => resolve();
    tx.onabort = tx.onerror = () =>
      reject(
        new Error(
          "Not saved. Refresh conflicting tabs, or free device storage and retry (100 actions / 40 MiB limit).",
        ),
      );
  });
  changed();
  if ("serviceWorker" in navigator)
    void navigator.serviceWorker.ready
      .then((r) => {
        const sync = (
          r as ServiceWorkerRegistration & {
            sync?: { register(tag: string): Promise<void> };
          }
        ).sync;
        return sync?.register("fleetpilot-driver-sync");
      })
      .catch(() => {});
}
function action(
  trip: string,
  version: number,
  command: string,
  payload: Record<string, unknown>,
): Action {
  return {
    id: crypto.randomUUID(),
    owner: "",
    trip,
    command,
    payload,
    expected_version: version,
    captured: new Date().toISOString(),
    sequence: 0,
    status: "PENDING",
    retries: 0,
  };
}
export async function queueTransition(trip: TripRecord, verb: string) {
  if (trip.next_action !== verb || !progression[verb])
    throw new Error("This action is not available.");
  await enqueue([
    action(trip.id, trip.version, "transition", { action: verb }),
  ]);
}
export async function queueDefect(
  vehicle: string,
  payload: Record<string, unknown>,
  files: File[],
  trip?: string,
) {
  if (files.length > 10) throw new Error("Select no more than 10 photos.");
  for (const file of files) await validateFile(file, file.name);
  const parent = action(trip ?? vehicle, 1, "defect", {
    ...payload,
    vehicle_id: vehicle,
    trip_id: trip ?? null,
    reported_at_client: new Date().toISOString(),
  });
  await enqueue([
    parent,
    ...files.map((file) => ({
      ...action(trip ?? vehicle, 1, "defect_evidence", {}),
      depends: parent.id,
      file,
      filename: file.name,
    })),
  ]);
}
export async function queueExpense(
  trip: TripRecord,
  payload: Record<string, unknown>,
  files: File[],
) {
  if (["SCHEDULED", "COMPLETED", "CANCELLED"].includes(trip.current_status))
    throw new Error("Expenses require an open dispatched trip.");
  if (files.length > 10) throw new Error("Select no more than 10 receipts.");
  for (const file of files) await validateFile(file, file.name);
  // A second expense can be submitted before React receives the previous
  // expense/receipt projection. Read durable local versions, not stale props.
  // enqueue still rejects concurrent writers and unresolved conflicts atomically.
  let version = project(trip, await actions()).version;
  const parent = action(trip.id, version++, "expense", payload);
  const rows = [
    parent,
    ...files.map((file) => ({
      ...action(trip.id, version++, "expense_evidence", {}),
      depends: parent.id,
      file,
      filename: file.name,
    })),
  ];
  await enqueue(rows);
}
export async function validateFile(file: Blob, name: string) {
  const ext = name.split(".").pop()?.toLowerCase();
  if (
    !file.size ||
    file.size > 5 * 1024 * 1024 ||
    !(
      {
        "image/png": ["png"],
        "image/jpeg": ["jpg", "jpeg"],
        "image/webp": ["webp"],
      } as Record<string, string[]>
    )[file.type]?.includes(ext ?? "")
  )
    throw new Error(
      "Choose a nonempty JPEG, PNG or WebP image up to 5 MiB with a matching filename.",
    );
  const magic = new Uint8Array(await file.slice(0, 12).arrayBuffer());
  const validMagic =
    file.type === "image/png"
      ? magic[0] === 137 &&
        magic[1] === 80 &&
        magic[2] === 78 &&
        magic[3] === 71
      : file.type === "image/jpeg"
        ? magic[0] === 255 && magic[1] === 216 && magic[2] === 255
        : String.fromCharCode(...magic.slice(0, 4)) === "RIFF" &&
          String.fromCharCode(...magic.slice(8, 12)) === "WEBP";
  if (!validMagic)
    throw new Error("Image content does not match its file type.");
  const bitmap = await createImageBitmap(file).catch(() => {
    throw new Error("This image could not be decoded. Choose another photo.");
  });
  const pixels = bitmap.width * bitmap.height;
  bitmap.close();
  if (pixels > 16000000)
    throw new Error("Image must not exceed 16 million pixels.");
}
export async function saveDraft(trip: string, draft: Draft) {
  const o = await owner();
  for (const file of [
    ...draft.files,
    ...(draft.signature ? [draft.signature] : []),
  ])
    await validateFile(file, file.name);
  if (draft.files.length > 10)
    throw new Error("Select no more than 10 photos.");
  await write("drafts", `${ownerKey(o)}:${trip}`, draft);
}
export async function loadDraft(trip: string) {
  const o = await owner();
  return read<Draft | undefined>("drafts", `${ownerKey(o)}:${trip}`);
}
export async function queueDelivery(
  trip: TripRecord,
  draft: Draft,
  attemptId?: string,
) {
  if (
    draft.mode === "pod" &&
    (!draft.recipient.trim() ||
      !draft.confirmed ||
      !draft.files.length ||
      trip.current_milestone !== "UNLOADING_COMPLETED")
  )
    throw new Error(
      "Complete unloading, enter recipient, add a photo and confirm delivery.",
    );
  if (
    draft.mode === "issue" &&
    draft.kind === "OTHER" &&
    draft.notes.trim().length < 3
  )
    throw new Error("Other requires notes.");
  await saveDraft(trip.id, draft);
  let version = trip.version;
  const rows: Action[] = [];
  const attempt = attemptId
    ? undefined
    : action(trip.id, version++, "attempt", {});
  if (attempt) rows.push(attempt);
  const resource = attemptId;
  const depends = attempt?.id;
  for (const file of [
    ...draft.files,
    ...(draft.mode === "pod" && draft.signature ? [draft.signature] : []),
  ]) {
    const type =
      file === draft.signature
        ? "SIGNATURE"
        : draft.mode === "pod"
          ? "DELIVERY_PHOTO"
          : "EXCEPTION_PHOTO";
    rows.push({
      ...action(trip.id, version++, "evidence", {}),
      resource,
      depends,
      file,
      filename: file.name,
      evidence_type: type,
    });
  }
  rows.push({
    ...action(
      trip.id,
      version,
      draft.mode === "pod" ? "pod" : "exception",
      draft.mode === "pod"
        ? {
            recipient_name: draft.recipient,
            recipient_role: draft.role || null,
            notes: draft.notes || null,
            driver_confirmed: true,
            signature_confirmed: !!draft.signature,
          }
        : { exception_type: draft.kind, notes: draft.notes || null },
    ),
    resource,
    depends,
  });
  await enqueue(rows);
}
export async function retryTrip(trip: string) {
  const rows = await actions();
  // Conflicts are deliberately not rebased. Operator review/discard is required.
  for (const a of rows.filter((a) => a.trip === trip && a.status === "FAILED"))
    await write("actions", a.id, {
      ...a,
      status: "PENDING",
      error: undefined,
      retries: 0,
      next_attempt_at: undefined,
    });
  await sync();
  changed();
}
export async function discardTrip(trip: string) {
  const rows = await actions();
  const o = await owner();
  const db = await openDB();
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(["actions", "drafts"], "readwrite");
    tx.objectStore("drafts").delete(`${ownerKey(o)}:${trip}`);
    for (const a of rows.filter(
      (a) => a.trip === trip && a.status !== "SYNCED",
    ))
      tx.objectStore("actions").delete(a.id);
    tx.oncomplete = () => resolve();
    tx.onabort = () => reject(new Error("Unable to discard saved work."));
  });
  changed();
}
export async function sync() {
  if (!navigator.onLine || !navigator.locks) return;
  return navigator.locks.request("fleetpilot-driver-sync", async (lease) => {
    if (!lease) return;
    const o = await establish();
    const key = ownerKey(o);
    const rows = await actions();
    const blocked = new Set<string>();
    for (const a of rows) {
      if (a.status === "SYNCED" || blocked.has(a.trip)) continue;
      if (a.next_attempt_at && a.next_attempt_at > Date.now()) {
        blocked.add(a.trip);
        continue;
      }
      if (a.status === "CONFLICTED" || a.status === "FAILED") {
        blocked.add(a.trip);
        continue;
      }
      if (ownerKey(await owner()) !== key) return;
      try {
        // Refresh authorization and authoritative state before sending ANY saved command.
        const defect = a.command.startsWith("defect");
        const current = await fetch(
          defect
            ? "/api/v1/driver/maintenance-vehicles"
            : `/api/v1/driver/trips/${a.trip}`,
          {
            credentials: "same-origin",
            cache: "no-store",
          },
        );
        if (current.status === 401 || current.status === 403) {
          await lock();
          return;
        }
        if (!current.ok)
          throw new Error(
            current.status === 404 ? "PERMISSION_DENIED" : "SERVER_ERROR",
          );
        const snapshot = await current.json();
        if (!defect)
          await write("snapshots", `${key}:/driver/trips/${a.trip}`, {
            data: snapshot,
            synced: new Date().toISOString(),
          });
        let resource = a.resource;
        if (a.depends) {
          const prior = await read<Action>("actions", a.depends);
          resource = (
            (a.command === "defect_evidence"
              ? prior.result?.defect
              : a.command === "expense_evidence"
                ? prior.result?.expense
                : prior.result?.attempt) as { id?: string }
          )?.id;
          if (!resource || prior.status !== "SYNCED")
            throw new Error("CONFLICT");
        }
        await write("actions", a.id, {
          ...a,
          status: "SYNCING",
          last_attempt_at: new Date().toISOString(),
          retries: a.retries + 1,
        });
        changed();
        const headers: Record<string, string> = { "Idempotency-Key": a.id };
        let url = `/api/v1/driver/sync/${a.trip}/${a.command}`;
        let body: BodyInit;
        if (a.command === "defect") {
          url = "/api/v1/driver/defects";
          headers["Content-Type"] = "application/json";
          body = JSON.stringify(a.payload);
        } else if (a.command === "defect_evidence") {
          url = `/api/v1/defects/${resource}/evidence?${new URLSearchParams({ filename: a.filename!, evidence_type: "DEFECT_PHOTO" })}`;
          headers["Content-Type"] = a.file!.type;
          body = a.file!;
        } else if (a.command === "expense_evidence") {
          url = `/api/v1/expenses/${resource}/evidence?${new URLSearchParams({ expected_version: String(a.expected_version), filename: a.filename! })}`;
          headers["Content-Type"] = a.file!.type;
          body = a.file!;
        } else if (a.command === "evidence") {
          url += `?${new URLSearchParams({ resource_id: resource!, expected_version: String(a.expected_version), occurred_at_client: a.captured, filename: a.filename!, evidence_type: a.evidence_type! })}`;
          headers["Content-Type"] = a.file!.type;
          body = a.file!;
        } else {
          headers["Content-Type"] = "application/json";
          body = JSON.stringify({
            expected_version: a.expected_version,
            occurred_at_client: a.captured,
            resource_id: resource ?? null,
            payload: a.payload,
          });
        }
        const response = await fetch(url, {
          method: "POST",
          headers,
          body,
          credentials: "same-origin",
        });
        if (response.status === 401) {
          await lock();
          return;
        }
        if (!response.ok)
          throw new Error(
            response.status === 409
              ? "CONFLICT"
              : response.status === 403 || response.status === 404
                ? "PERMISSION_DENIED"
                : response.status === 422 || response.status === 413
                  ? "VALIDATION_ERROR"
                  : "SERVER_ERROR",
          );
        const answer = await response.json();
        await write("actions", a.id, {
          ...a,
          status: "SYNCED",
          file: undefined,
          result: answer.result,
          retries: a.retries + 1,
          error: undefined,
        });
        if (["pod", "exception"].includes(a.command)) {
          const db = await openDB();
          await new Promise<void>((resolve, reject) => {
            const tx = db.transaction("drafts", "readwrite");
            tx.objectStore("drafts").delete(`${key}:${a.trip}`);
            tx.oncomplete = () => resolve();
            tx.onabort = () => reject(new Error("STORAGE_ERROR"));
          });
        }
        await write("meta", "lastSynced", new Date().toISOString());
        changed();
      } catch (error) {
        const code =
          error instanceof TypeError
            ? "NETWORK_ERROR"
            : error instanceof Error
              ? error.message
              : "STORAGE_ERROR";
        const retryable =
          ["NETWORK_ERROR", "SERVER_ERROR"].includes(code) && a.retries < 7;
        await write("actions", a.id, {
          ...a,
          status: retryable
            ? "PENDING"
            : code === "CONFLICT"
              ? "CONFLICTED"
              : "FAILED",
          retries: a.retries + 1,
          next_attempt_at: retryable
            ? Date.now() + Math.min(300000, 5000 * 2 ** a.retries)
            : undefined,
          last_attempt_at: new Date().toISOString(),
          error: code,
        });
        blocked.add(a.trip);
        changed();
        if (retryable) break;
      }
    }
    for (const trip of new Set(
      rows
        .filter((a) => !a.command.startsWith("defect") && !blocked.has(a.trip))
        .map((a) => a.trip),
    ))
      await cachedRead(`/driver/trips/${trip}`).catch(() => {});
    changed();
  });
}
export const lastSynced = () => read<string | undefined>("meta", "lastSynced");
