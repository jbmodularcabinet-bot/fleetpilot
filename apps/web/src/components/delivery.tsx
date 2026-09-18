"use client";
import { useEffect, useRef, useState, type PointerEvent } from "react";
import { Card, ErrorState, LoadingState, StatusBadge } from "@fleetpilot/ui";
import { can } from "@fleetpilot/auth";
import type { Identity } from "@fleetpilot/types";
import {
  loadDraft,
  saveDraft,
  queueDelivery,
  sync,
  actions,
} from "@/lib/offline";
import { request } from "@/lib/client";
import { dateLabel, human, type TripRecord } from "@/lib/trips";

interface Evidence {
  id: string;
  evidence_type: string;
  original_filename: string;
  status: string;
  uploaded_at: string;
  uploaded_by: string;
  file_size: number;
  supersedes_id: string | null;
}

function LocalPreview({ file }: { file: File }) {
  const [url, setUrl] = useState("");
  useEffect(() => {
    const value = URL.createObjectURL(file);
    queueMicrotask(() => setUrl(value));
    return () => URL.revokeObjectURL(value);
  }, [file]);
  return url ? (
    // eslint-disable-next-line @next/next/no-img-element -- device-local evidence must not go to an optimizer
    <img
      src={url}
      alt={`Saved locally: ${file.name}`}
      style={{ maxWidth: "100%", maxHeight: 160 }}
    />
  ) : null;
}

export function EvidencePreview({ evidence }: { evidence: Evidence }) {
  const [failed, setFailed] = useState(false);
  const [retry, setRetry] = useState(0);
  const url = `/api/v1/evidence/${evidence.id}`;
  if (failed)
    return (
      <>
        <ErrorState message="Evidence image is unavailable. Retry or contact your operator." />
        <button
          type="button"
          className="button secondary"
          onClick={() => {
            setRetry((value) => value + 1);
            setFailed(false);
          }}
        >
          Retry image
        </button>
      </>
    );
  return (
    <a
      href={url}
      target="_blank"
      rel="noreferrer"
      aria-label={`Open ${human(evidence.evidence_type)} ${evidence.original_filename}`}
    >
      {/* eslint-disable-next-line @next/next/no-img-element -- private cookie-authorized API, never a public image optimizer */}
      <img
        src={retry ? `${url}?retry=${retry}` : url}
        alt={human(evidence.evidence_type)}
        loading="lazy"
        onError={() => setFailed(true)}
      />
    </a>
  );
}
interface POD {
  id: string;
  recipient_name: string;
  recipient_role: string | null;
  notes: string | null;
  confirmed_at: string;
  confirmed_by_user_id: string;
  status: string;
  reviewed_at: string | null;
  reviewed_by: string | null;
}
interface Issue {
  id: string;
  exception_type: string;
  notes: string | null;
  status: string;
  created_at: string;
  resolved_at: string | null;
  resolution_notes: string | null;
}
interface Attempt {
  id: string;
  attempt_number: number;
  status: string;
  arrived_at: string;
  completed_at: string | null;
  created_by: string;
  evidence: Evidence[];
  pod: POD | null;
  exception: Issue | null;
}
interface History {
  items: Attempt[];
  total: number;
  offset: number;
  limit: number;
  trip_version: number;
  legacy_delivery: boolean;
  policy: {
    signature_required: boolean;
    minimum_delivery_photos: number;
    max_file_bytes: number;
    max_attempt_files: number;
  };
}
const exceptionTypes = [
  "RECIPIENT_UNAVAILABLE",
  "WRONG_ADDRESS",
  "INCOMPLETE_ADDRESS",
  "DELIVERY_REJECTED",
  "DAMAGED_CARGO",
  "PARTIAL_DELIVERY",
  "SITE_ACCESS_ISSUE",
  "VEHICLE_ISSUE",
  "DRIVER_ISSUE",
  "OTHER",
];

export function SignatureCapture({
  onChange,
}: {
  onChange: (file: File | null) => void;
}) {
  const canvas = useRef<HTMLCanvasElement>(null),
    drawing = useRef(false);
  const [hasInk, setHasInk] = useState(false),
    [confirmed, setConfirmed] = useState(false);
  function point(event: PointerEvent<HTMLCanvasElement>) {
    const box = event.currentTarget.getBoundingClientRect();
    return [
      ((event.clientX - box.left) * 600) / box.width,
      ((event.clientY - box.top) * 200) / box.height,
    ];
  }
  return (
    <fieldset className="signature-field">
      <legend>Recipient signature (optional)</legend>
      <p className="field-help">
        Ask the recipient to draw here, then confirm the signature. This is
        operational evidence.
      </p>
      <canvas
        ref={canvas}
        width={600}
        height={200}
        aria-label="Recipient signature drawing area"
        className="signature-canvas"
        onPointerDown={(event) => {
          drawing.current = true;
          event.currentTarget.setPointerCapture(event.pointerId);
          const ctx = event.currentTarget.getContext("2d")!;
          const [x, y] = point(event);
          ctx.beginPath();
          ctx.moveTo(x, y);
          ctx.lineWidth = 3;
          ctx.lineCap = "round";
          ctx.strokeStyle = "#162235";
          setConfirmed(false);
          onChange(null);
        }}
        onPointerMove={(event) => {
          if (!drawing.current) return;
          const ctx = event.currentTarget.getContext("2d")!;
          const [x, y] = point(event);
          ctx.lineTo(x, y);
          ctx.stroke();
          setHasInk(true);
        }}
        onPointerUp={() => {
          drawing.current = false;
        }}
        onPointerCancel={() => {
          drawing.current = false;
        }}
      />
      <button
        type="button"
        className="button secondary"
        onClick={() => {
          canvas.current?.getContext("2d")?.clearRect(0, 0, 600, 200);
          setHasInk(false);
          setConfirmed(false);
          onChange(null);
        }}
      >
        Clear signature
      </button>
      <label className="checkbox-label">
        <input
          type="checkbox"
          disabled={!hasInk}
          checked={confirmed}
          onChange={(event) => {
            const checked = event.target.checked;
            setConfirmed(checked);
            if (!checked) onChange(null);
            else
              canvas.current?.toBlob((blob) => {
                if (blob)
                  onChange(
                    new File([blob], "signature.png", { type: "image/png" }),
                  );
              }, "image/png");
          }}
        />
        Recipient confirms this signature
      </label>
    </fieldset>
  );
}

async function upload(
  attempt: string,
  version: number,
  file: File,
  evidenceType: string,
  supersedes?: string,
) {
  const params = new URLSearchParams({
    expected_version: String(version),
    filename: file.name,
    evidence_type: evidenceType,
    ...(supersedes ? { supersedes_id: supersedes } : {}),
  });
  const response = await fetch(
    `/api/v1/delivery-attempts/${attempt}/evidence?${params}`,
    {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": file.type },
      body: file,
    },
  );
  const data = await response.json();
  if (!response.ok)
    throw new Error(
      data?.error?.message ?? "Evidence upload failed. Try again.",
    );
  return data as { evidence: Evidence; trip_version: number };
}

export function DeliveryPanel({
  trip,
  identity,
  own,
  onChanged,
}: {
  trip: TripRecord;
  identity: Identity;
  own: boolean;
  onChanged: () => void;
}) {
  const [history, setHistory] = useState<History>(),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [reload, setReload] = useState(0),
    [offset, setOffset] = useState(0);
  const [mode, setMode] = useState<"pod" | "issue">("pod"),
    [recipient, setRecipient] = useState(""),
    [role, setRole] = useState(""),
    [notes, setNotes] = useState(""),
    [confirmed, setConfirmed] = useState(false),
    [kind, setKind] = useState("RECIPIENT_UNAVAILABLE"),
    [files, setFiles] = useState<File[]>([]),
    [signature, setSignature] = useState<File | null>(null),
    [resolution, setResolution] = useState("");
  const [draftReady, setDraftReady] = useState(false),
    [localMessage, setLocalMessage] = useState("");
  useEffect(() => {
    if (!own) return;
    const refresh = () => setReload((value) => value + 1);
    window.addEventListener("fleetpilot-sync", refresh);
    return () => window.removeEventListener("fleetpilot-sync", refresh);
  }, [own]);
  useEffect(() => {
    if (!own) return;
    let alive = true;
    loadDraft(trip.id)
      .then((d) => {
        if (alive && d) {
          setMode(d.mode);
          setRecipient(d.recipient);
          setRole(d.role);
          setNotes(d.notes);
          setConfirmed(d.confirmed);
          setKind(d.kind);
          setFiles(d.files);
          setSignature(d.signature);
          setLocalMessage(
            "Saved local draft restored, including selected evidence.",
          );
        }
      })
      .catch(() => {})
      .finally(() => {
        if (alive) setDraftReady(true);
      });
    return () => {
      alive = false;
    };
  }, [own, trip.id]);
  useEffect(() => {
    if (
      !own ||
      !draftReady ||
      !(recipient || notes || files.length || signature)
    )
      return;
    const timer = setTimeout(() => {
      setLocalMessage("");
      void saveDraft(trip.id, {
        mode,
        recipient,
        role,
        notes,
        confirmed,
        kind,
        files,
        signature,
      })
        .then(() => setLocalMessage("Draft saved locally."))
        .catch((e) => setError(e.message));
    }, 300);
    return () => clearTimeout(timer);
  }, [
    own,
    draftReady,
    trip.id,
    mode,
    recipient,
    role,
    notes,
    confirmed,
    kind,
    files,
    signature,
  ]);
  useEffect(() => {
    let alive = true;
    request<History>(`/trips/${trip.id}/delivery-attempts?offset=${offset}`)
      .then((data) => {
        if (alive) setHistory(data);
      })
      .catch((err) => {
        if (alive) setError(err.message);
      });
    return () => {
      alive = false;
    };
  }, [trip.id, trip.version, reload, offset]);
  const submitAllowed = can(
    identity,
    own ? "driver_pod.submit_own" : "pod.submit",
  );
  const uploadAllowed = can(
    identity,
    own ? "driver_evidence.upload_own" : "delivery_evidence.upload",
  );
  const issueAllowed = can(
    identity,
    own ? "driver_exception.create_own" : "delivery_exception.create",
  );
  const stage = [
    "ARRIVED_DELIVERY",
    "UNLOADING_STARTED",
    "UNLOADING_COMPLETED",
  ].includes(trip.current_milestone);
  const newest = offset === 0 ? history?.items[0] : undefined;
  const unresolved = newest?.exception?.status === "OPEN";
  async function submit() {
    if (!history) return;
    setBusy(true);
    setError("");
    try {
      if (own) {
        const retained =
          newest?.status === "IN_PROGRESS"
            ? newest.evidence.filter(
                (e) =>
                  e.status === "ACTIVE" && e.evidence_type === "DELIVERY_PHOTO",
              ).length
            : 0;
        if (
          mode === "pod" &&
          files.length + (retained ?? 0) <
            history.policy.minimum_delivery_photos
        )
          throw new Error("At least one delivery photo is required.");
        if (
          (await actions()).some(
            (a) =>
              a.trip === trip.id &&
              a.status !== "SYNCED" &&
              ["pod", "exception"].includes(a.command),
          )
        )
          throw new Error(
            "Delivery is already saved locally. Use Retry sync or review the pending work.",
          );
        await queueDelivery(
          trip,
          { mode, recipient, role, notes, confirmed, kind, files, signature },
          newest?.status === "IN_PROGRESS" ? newest.id : undefined,
        );
        setDraftReady(false);
        setLocalMessage("Saved locally. Waiting for server confirmation.");
        await sync();
        onChanged();
        return;
      }
      let attempt = newest?.status === "IN_PROGRESS" ? newest : undefined,
        version = history.trip_version;
      const retainedPhotos =
        attempt?.evidence.filter(
          (e) => e.status === "ACTIVE" && e.evidence_type === "DELIVERY_PHOTO",
        ).length ?? 0;
      if (
        mode === "pod" &&
        retainedPhotos + files.length < history.policy.minimum_delivery_photos
      )
        throw new Error("At least one delivery photo is required.");
      if (
        files.some(
          (file) =>
            file.size > history.policy.max_file_bytes || file.size === 0,
        )
      )
        throw new Error(
          "Each image must be nonempty and no larger than 5 MiB.",
        );
      if (!attempt) {
        const created = await request<{
          attempt: Attempt;
          trip_version: number;
        }>(`/trips/${trip.id}/delivery-attempts`, "POST", {
          expected_version: version,
        });
        attempt = created.attempt;
        version = created.trip_version;
      }
      for (const file of files) {
        const saved = await upload(
          attempt.id,
          version,
          file,
          mode === "pod" ? "DELIVERY_PHOTO" : "EXCEPTION_PHOTO",
        );
        version = saved.trip_version;
      }
      if (mode === "pod" && signature) {
        const previous = attempt.evidence.find(
          (e) => e.evidence_type === "SIGNATURE" && e.status === "ACTIVE",
        );
        const saved = await upload(
          attempt.id,
          version,
          signature,
          "SIGNATURE",
          previous?.id,
        );
        version = saved.trip_version;
      }
      await request(
        `/delivery-attempts/${attempt.id}/${mode === "pod" ? "pod" : "exception"}`,
        "POST",
        mode === "pod"
          ? {
              expected_version: version,
              recipient_name: recipient,
              recipient_role: role || null,
              notes: notes || null,
              driver_confirmed: confirmed,
              signature_confirmed:
                !!signature ||
                attempt.evidence.some(
                  (e) =>
                    e.evidence_type === "SIGNATURE" && e.status === "ACTIVE",
                ),
            }
          : {
              expected_version: version,
              exception_type: kind,
              notes: notes || null,
            },
      );
      onChanged();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to submit delivery.",
      );
      if (!own) setFiles([]);
      setReload((value) => value + 1);
    } finally {
      setBusy(false);
    }
  }
  async function review(pod: POD) {
    setBusy(true);
    setError("");
    try {
      await request(`/pod/${pod.id}/review`, "POST", {
        expected_version: history?.trip_version,
      });
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Review failed.");
    } finally {
      setBusy(false);
    }
  }
  async function resolve(issue: Issue) {
    setBusy(true);
    setError("");
    try {
      await request(`/delivery-exceptions/${issue.id}/resolve`, "POST", {
        expected_version: history?.trip_version,
        resolution_notes: resolution,
      });
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Resolution failed.");
    } finally {
      setBusy(false);
    }
  }
  if (!history && !error) return <LoadingState />;
  return (
    <Card title="Delivery evidence" className="master-card delivery-panel">
      {own && localMessage && (
        <p role="status" className="trip-notice">
          {localMessage}
        </p>
      )}
      {own && files.length > 0 && (
        <p className="small muted">
          Saved/selected photos: {files.map((f) => f.name).join(", ")}
          {signature ? " Signature retained" : ""}
        </p>
      )}
      {own && localMessage && (
        <div className="evidence-grid">
          {files.map((file, i) => (
            <LocalPreview key={`${file.name}-${i}`} file={file} />
          ))}
          {signature && <LocalPreview file={signature} />}
        </div>
      )}
      {error && (
        <>
          <ErrorState message={error} />
          <button
            type="button"
            className="button secondary"
            onClick={() => {
              setError("");
              setReload((v) => v + 1);
            }}
          >
            Refresh delivery history
          </button>
        </>
      )}
      {history?.legacy_delivery && !history.total && (
        <p className="trip-notice">
          Legacy trip closed before proof-of-delivery capture was introduced. No
          evidence has been fabricated.
        </p>
      )}
      {unresolved && (
        <p role="status" className="trip-notice">
          Delivery issue reported. Awaiting operator retry authorization. This
          trip is not delivered.
        </p>
      )}
      {newest?.exception?.status === "RETRY_AUTHORIZED" && stage && (
        <p className="trip-notice">
          Retry authorized at this delivery stop. Confirm a new attempt below;
          previous evidence stays in history.
        </p>
      )}
      {history && stage && !unresolved && offset === 0 && submitAllowed && (
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void submit();
          }}
          className="delivery-form"
        >
          <h3>
            {mode === "pod" ? "Confirm delivery" : "Report delivery issue"}
          </h3>
          <div className="master-actions">
            <button
              type="button"
              className="button secondary"
              disabled={
                busy || trip.current_milestone !== "UNLOADING_COMPLETED"
              }
              onClick={() => setMode("pod")}
            >
              Confirm delivery
            </button>
            {issueAllowed && (
              <button
                type="button"
                className="button secondary"
                disabled={busy}
                onClick={() => setMode("issue")}
              >
                Report delivery issue
              </button>
            )}
          </div>
          {mode === "pod" &&
          trip.current_milestone !== "UNLOADING_COMPLETED" ? (
            <p className="field-help">
              Complete unloading using the next action before confirming
              delivery. You can report an issue now.
            </p>
          ) : (
            <>
              {mode === "pod" ? (
                <>
                  <label>
                    Recipient name
                    <input
                      required
                      maxLength={160}
                      value={recipient}
                      onChange={(event) => setRecipient(event.target.value)}
                    />
                  </label>
                  <label>
                    Recipient role
                    <input
                      maxLength={120}
                      value={role}
                      onChange={(event) => setRole(event.target.value)}
                    />
                  </label>
                </>
              ) : (
                <label>
                  Delivery issue
                  <select
                    aria-label="Delivery issue"
                    value={kind}
                    onChange={(event) => setKind(event.target.value)}
                  >
                    {exceptionTypes.map((value) => (
                      <option key={value} value={value}>
                        {human(value)}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              {uploadAllowed && (
                <label>
                  {mode === "pod"
                    ? "Delivery photos (at least one required)"
                    : "Exception photos (optional)"}
                  <input
                    type="file"
                    accept="image/jpeg,image/png,image/webp"
                    multiple
                    onChange={(event) =>
                      setFiles(Array.from(event.target.files ?? []))
                    }
                  />
                  <span className="field-help">
                    JPEG, PNG or WebP. Up to 5 MiB and 16 megapixels per image;
                    12 retained files per attempt. Uploads are private.
                  </span>
                </label>
              )}
              {mode === "pod" && uploadAllowed && (
                <SignatureCapture onChange={setSignature} />
              )}
              <label>
                {mode === "pod" ? "Delivery notes" : "Exception notes"}
                <textarea
                  required={mode === "issue" && kind === "OTHER"}
                  minLength={
                    mode === "issue" && kind === "OTHER" ? 3 : undefined
                  }
                  maxLength={4000}
                  value={notes}
                  onChange={(event) => setNotes(event.target.value)}
                  rows={3}
                />
              </label>
              {mode === "pod" && (
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    required
                    checked={confirmed}
                    onChange={(event) => setConfirmed(event.target.checked)}
                  />
                  {own
                    ? "I confirm the cargo was delivered to this recipient."
                    : "The assigned driver confirmed delivery to this recipient; I am recording that confirmation."}
                </label>
              )}
              <button
                className="button primary"
                disabled={busy || (mode === "issue" && !issueAllowed)}
              >
                {busy
                  ? "Saving evidence…"
                  : mode === "pod"
                    ? "Submit proof of delivery"
                    : "Submit delivery issue"}
              </button>
              <p className="field-help">
                Submitting preserves this attempt and its evidence. Delivery
                issues do not mark the trip delivered.{" "}
                {own
                  ? "Saved offline work remains pending until the server confirms synchronization."
                  : "Stay online until confirmation."}
              </p>
            </>
          )}
        </form>
      )}
      <h3>Delivery attempt history</h3>
      {history?.total === 0 && (
        <p className="muted">No delivery attempts recorded yet.</p>
      )}
      {history?.items.map((attempt) => (
        <section key={attempt.id} className="delivery-attempt">
          <div className="trip-card-title">
            <h4>Attempt {attempt.attempt_number}</h4>
            <StatusBadge>{human(attempt.status)}</StatusBadge>
          </div>
          <p className="small muted">
            Arrival confirmed {dateLabel(attempt.arrived_at)}
            {attempt.completed_at
              ? ` · Finished ${dateLabel(attempt.completed_at)}`
              : ""}
          </p>
          {!own && (
            <p className="field-help">Recorded by {attempt.created_by}</p>
          )}
          {attempt.pod && (
            <>
              <p>
                <strong>Received by {attempt.pod.recipient_name}</strong>
                {attempt.pod.recipient_role
                  ? ` · ${attempt.pod.recipient_role}`
                  : ""}
              </p>
              <p>{attempt.pod.notes}</p>
              <p className="small">
                Delivery confirmed {dateLabel(attempt.pod.confirmed_at)} · POD{" "}
                {human(attempt.pod.status)}
              </p>
              {!own && (
                <p className="field-help">
                  Submitted by {attempt.pod.confirmed_by_user_id}
                </p>
              )}
              {attempt.pod.reviewed_at && (
                <p className="small">
                  Reviewed {dateLabel(attempt.pod.reviewed_at)}
                  {!own ? ` · ${attempt.pod.reviewed_by}` : ""}
                </p>
              )}
              {!own &&
                attempt.pod.status === "SUBMITTED" &&
                can(identity, "pod.review") &&
                trip.current_status === "DELIVERED" && (
                  <button
                    className="button primary"
                    disabled={busy}
                    onClick={() => {
                      if (
                        window.confirm(
                          "Confirm you reviewed the recipient details and evidence?",
                        )
                      )
                        void review(attempt.pod!);
                    }}
                  >
                    Review POD
                  </button>
                )}
            </>
          )}
          {attempt.exception && (
            <>
              <p>
                <strong>{human(attempt.exception.exception_type)}</strong> ·{" "}
                {human(attempt.exception.status)}
              </p>
              <p>{attempt.exception.notes}</p>
              {attempt.exception.resolved_at && (
                <p className="small">
                  Retry authorized {dateLabel(attempt.exception.resolved_at)} ·{" "}
                  {attempt.exception.resolution_notes}
                </p>
              )}
              {!own &&
                attempt.exception.status === "OPEN" &&
                stage &&
                can(identity, "delivery_exception.resolve") && (
                  <form
                    onSubmit={(event) => {
                      event.preventDefault();
                      if (
                        window.confirm(
                          "Authorize another delivery attempt at this stop? Previous history will remain unchanged.",
                        )
                      )
                        void resolve(attempt.exception!);
                    }}
                  >
                    <label>
                      Retry authorization notes
                      <textarea
                        required
                        minLength={3}
                        maxLength={4000}
                        value={resolution}
                        onChange={(event) => setResolution(event.target.value)}
                      />
                    </label>
                    <button className="button secondary" disabled={busy}>
                      Authorize delivery retry
                    </button>
                    <p className="field-help">
                      This authorizes an on-site retry. It does not reset travel
                      milestones or change the address.
                    </p>
                  </form>
                )}
            </>
          )}
          <div className="evidence-gallery">
            {attempt.evidence.map((evidence) => (
              <figure key={evidence.id}>
                <EvidencePreview evidence={evidence} />
                <figcaption>
                  {human(evidence.evidence_type)} · {human(evidence.status)}
                  <small>
                    {dateLabel(evidence.uploaded_at)} ·{" "}
                    {Math.ceil(evidence.file_size / 1024)} KiB
                  </small>
                  {!own && <small>Uploaded by {evidence.uploaded_by}</small>}
                  {evidence.supersedes_id && (
                    <small>Replaces earlier evidence; original retained.</small>
                  )}
                </figcaption>
              </figure>
            ))}
          </div>
        </section>
      ))}
      {history && history.total > history.limit && (
        <div className="master-pager">
          <button
            className="button secondary"
            disabled={offset === 0}
            onClick={() => setOffset(Math.max(0, offset - history.limit))}
          >
            Newer attempts
          </button>
          <span>
            {offset + 1}–{Math.min(offset + history.limit, history.total)} of{" "}
            {history.total}
          </span>
          <button
            className="button secondary"
            disabled={offset + history.limit >= history.total}
            onClick={() => setOffset(offset + history.limit)}
          >
            Older attempts
          </button>
        </div>
      )}
    </Card>
  );
}
