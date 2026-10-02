from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from .composition import DURATION_TOLERANCE_SECONDS, discover_media_tools
from .store import CreativeOSStore, now_iso

MANIFEST_ID = "CREATIVEOS_RENDER_QA"
MANIFEST_VERSION = "1"
RULE_VERSION = "1"

REQUIRED_CHECKS = (
    "RENDER_STATUS_SUCCEEDED",
    "OUTPUT_EXISTS",
    "OUTPUT_CHECKSUM_MATCH",
    "FFPROBE_READABLE",
    "VIDEO_STREAM_PRESENT",
    "REQUIRED_AUDIO_PRESENT",
    "WIDTH_MATCH",
    "HEIGHT_MATCH",
    "DURATION_WITHIN_TOLERANCE",
    "SOURCE_CHECKSUM_EVIDENCE_PRESENT",
    "SOURCE_CHECKSUM_MATCH",
)
CHECK_VERSION = "1"


class QAEngineError(RuntimeError):
    pass


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _decode_json(value: str | None, default: Any) -> Any:
    if value is None or value == "":
        return default
    return json.loads(value)


def derive_overall(checks: list[dict[str, Any]], required_ids: tuple[str, ...] = REQUIRED_CHECKS) -> str:
    ids = [str(c["check_id"]) for c in checks]
    if len(ids) != len(set(ids)):
        return "FAIL"
    if set(ids) != set(required_ids) or len(ids) != len(required_ids):
        return "FAIL"
    results = [str(c["result"]) for c in checks]
    if any(result == "FAIL" for result in results):
        return "FAIL"
    if any(result == "WARN" for result in results):
        return "WARN"
    if all(result == "PASS" for result in results):
        return "PASS"
    return "FAIL"


class QAService:
    def __init__(
        self,
        store: CreativeOSStore,
        ffprobe_path: str | Path | None = None,
        probe_runner: Callable[[Path], dict[str, Any]] | None = None,
    ):
        self.store = store
        self.manifest_id = MANIFEST_ID
        self.manifest_version = MANIFEST_VERSION
        self.rule_version = RULE_VERSION
        if ffprobe_path is None and probe_runner is None:
            _ffmpeg, ffprobe_path = discover_media_tools()
        self.ffprobe_path = Path(ffprobe_path).resolve() if ffprobe_path is not None else None
        self.probe_runner = probe_runner
    def _render_snapshot(self, render_job_id: str) -> tuple[dict[str, Any], str]:
        render = self.store.get("render_jobs", render_job_id)
        base_payload = {
            "render_job_id": render["id"],
            "render_identity_snapshot": render["render_identity"],
            "render_checksum_snapshot": render.get("output_checksum_sha256"),
            "manifest_id": self.manifest_id,
            "manifest_version": self.manifest_version,
            "rule_version": self.rule_version,
        }
        return render, _hash(base_payload)

    def _attempt_identity(self, base_identity_key: str, attempt_version: int) -> str:
        return _hash({"base_identity_key": base_identity_key, "attempt_version": int(attempt_version)})

    def create_qa_run(self, render_job_id: str) -> dict[str, Any]:
        render, base_key = self._render_snapshot(render_job_id)
        conn = self.store.conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            row = conn.execute(
                "SELECT * FROM qa_runs WHERE base_identity_key=? AND attempt_version=1",
                (base_key,),
            ).fetchone()
            if row is not None:
                conn.commit()
                return dict(row)
            stamp = now_iso()
            qa_id = str(uuid4())
            attempt_key = self._attempt_identity(base_key, 1)
            conn.execute(
                """INSERT INTO qa_runs(
                    id,render_job_id,render_identity_snapshot,render_checksum_snapshot,
                    manifest_id,manifest_version,rule_version,base_identity_key,
                    attempt_version,attempt_identity_key,retry_of_qa_run_id,
                    lifecycle_state,overall_result,required_checks_json,
                    required_check_count,actual_check_count,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    qa_id, render["id"], render["render_identity"], render.get("output_checksum_sha256"),
                    self.manifest_id, self.manifest_version, self.rule_version, base_key,
                    1, attempt_key, None, "PENDING", None, _canonical(list(REQUIRED_CHECKS)),
                    len(REQUIRED_CHECKS), 0, stamp, stamp,
                ),
            )
            conn.execute(
                "INSERT INTO qa_reviews(id,qa_run_id,review_state,reviewer_note,reviewed_at,created_at) VALUES(?,?,?,?,?,?)",
                (str(uuid4()), qa_id, "PENDING", "", None, stamp),
            )
            conn.commit()
            return self.store.get("qa_runs", qa_id)
        except sqlite3.IntegrityError:
            conn.rollback()
            row = conn.execute(
                "SELECT * FROM qa_runs WHERE base_identity_key=? AND attempt_version=1",
                (base_key,),
            ).fetchone()
            if row is None:
                raise
            return dict(row)
        except Exception:
            conn.rollback()
            raise

    def retry_error_qa_run(self, qa_run_id: str) -> dict[str, Any]:
        self.store.get("qa_runs", qa_run_id)
        conn = self.store.conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            source = conn.execute("SELECT * FROM qa_runs WHERE id=?", (qa_run_id,)).fetchone()
            if source is None:
                raise KeyError(f"qa_runs:{qa_run_id}")
            source = dict(source)
            if source["lifecycle_state"] != "ERROR":
                raise ValueError("only ERROR QA runs may be retried")
            child = conn.execute(
                "SELECT * FROM qa_runs WHERE retry_of_qa_run_id=?", (qa_run_id,)
            ).fetchone()
            if child is not None:
                conn.commit()
                return dict(child)
            max_attempt = conn.execute(
                "SELECT COALESCE(MAX(attempt_version),0) FROM qa_runs WHERE base_identity_key=?",
                (source["base_identity_key"],),
            ).fetchone()[0]
            attempt_version = int(max_attempt) + 1
            qa_id = str(uuid4())
            stamp = now_iso()
            attempt_key = self._attempt_identity(source["base_identity_key"], attempt_version)
            conn.execute(
                """INSERT INTO qa_runs(
                    id,render_job_id,render_identity_snapshot,render_checksum_snapshot,
                    manifest_id,manifest_version,rule_version,base_identity_key,
                    attempt_version,attempt_identity_key,retry_of_qa_run_id,
                    lifecycle_state,overall_result,required_checks_json,
                    required_check_count,actual_check_count,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    qa_id, source["render_job_id"], source["render_identity_snapshot"],
                    source["render_checksum_snapshot"], source["manifest_id"],
                    source["manifest_version"], source["rule_version"],
                    source["base_identity_key"], attempt_version, attempt_key, source["id"],
                    "PENDING", None, source["required_checks_json"],
                    source["required_check_count"], 0, stamp, stamp,
                ),
            )
            conn.execute(
                "INSERT INTO qa_reviews(id,qa_run_id,review_state,reviewer_note,reviewed_at,created_at) VALUES(?,?,?,?,?,?)",
                (str(uuid4()), qa_id, "PENDING", "", None, stamp),
            )
            conn.commit()
            return self.store.get("qa_runs", qa_id)
        except sqlite3.IntegrityError:
            conn.rollback()
            child = conn.execute(
                "SELECT * FROM qa_runs WHERE retry_of_qa_run_id=?", (qa_run_id,)
            ).fetchone()
            if child is None:
                raise
            return dict(child)
        except Exception:
            conn.rollback()
            raise
    def _probe(self, path: Path) -> tuple[bool, dict[str, Any], str]:
        if self.probe_runner is not None:
            try:
                return True, self.probe_runner(path), ""
            except QAEngineError:
                raise
            except OSError as exc:
                raise QAEngineError(str(exc)) from exc
            except Exception as exc:
                return False, {}, str(exc)
        if self.ffprobe_path is None:
            raise QAEngineError("ffprobe path unavailable")
        try:
            result = subprocess.run(
                [
                    str(self.ffprobe_path), "-v", "error", "-show_entries",
                    "stream=index,codec_type,width,height:format=duration",
                    "-of", "json", str(path),
                ],
                capture_output=True, text=True, timeout=20, shell=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise QAEngineError(str(exc)) from exc
        if result.returncode != 0:
            return False, {}, (result.stderr or "ffprobe failed")[-2000:]
        try:
            return True, json.loads(result.stdout), ""
        except json.JSONDecodeError as exc:
            return False, {}, str(exc)

    def _check(self, check_id: str, passed: bool, expected: Any, observed: Any,
               evidence: Any, message_pass: str, message_fail: str,
               severity: str = "CRITICAL") -> dict[str, Any]:
        return {
            "check_id": check_id,
            "check_version": CHECK_VERSION,
            "result": "PASS" if passed else "FAIL",
            "severity": severity,
            "expected_json": expected,
            "observed_json": observed,
            "evidence_json": evidence,
            "message": message_pass if passed else message_fail,
        }

    def _evaluate(self, run: dict[str, Any]) -> list[dict[str, Any]]:
        render = self.store.get("render_jobs", run["render_job_id"])
        timeline = self.store.get("composition_timelines", render["timeline_id"])
        entries = self.store.list("composition_timeline_entries", {"timeline_id": timeline["id"]})
        entries = sorted(entries, key=lambda row: int(row["sequence"]))

        output = Path(render["output_path"])
        output_exists = output.is_file()
        actual_output_hash = _file_sha(output) if output_exists else None

        probe_ok = False
        probe: dict[str, Any] = {}
        probe_error = ""
        if output_exists:
            probe_ok, probe, probe_error = self._probe(output)

        streams = probe.get("streams", []) if probe_ok else []
        video = next((s for s in streams if s.get("codec_type") == "video"), None)
        audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
        expected_duration = sum(int(row["duration_ms"]) for row in entries) / 1000.0
        actual_duration = None
        if probe_ok:
            try:
                actual_duration = float(probe.get("format", {}).get("duration"))
            except (TypeError, ValueError):
                actual_duration = None
        audio_required = any(bool(row.get("audio_path")) for row in entries)

        prior = _decode_json(render.get("probe_json"), {})
        source_before = prior.get("source_checksums_before")
        source_after = prior.get("source_checksums_after")
        source_evidence_present = (
            isinstance(source_before, dict) and bool(source_before)
            and isinstance(source_after, dict) and bool(source_after)
        )
        current_sources: dict[str, str | None] = {}
        if source_evidence_present:
            for raw_path in sorted(source_before):
                path = Path(raw_path)
                current_sources[raw_path] = _file_sha(path) if path.is_file() else None
        source_match = bool(source_evidence_present)
        if source_match:
            source_match = source_before == source_after
            if source_match:
                source_match = all(current_sources.get(path) == checksum for path, checksum in source_before.items())

        checks = [
            self._check(
                "RENDER_STATUS_SUCCEEDED", render["status"] == "SUCCEEDED",
                {"status": "SUCCEEDED"}, {"status": render["status"]},
                {"render_job_id": render["id"]}, "render succeeded", "render status is not SUCCEEDED",
            ),
            self._check(
                "OUTPUT_EXISTS", output_exists,
                {"exists": True}, {"exists": output_exists},
                {"path": str(output)}, "output exists", "output file is missing",
            ),
            self._check(
                "OUTPUT_CHECKSUM_MATCH",
                output_exists and actual_output_hash == run["render_checksum_snapshot"],
                {"sha256": run["render_checksum_snapshot"]},
                {"sha256": actual_output_hash},
                {"path": str(output)}, "output checksum matches", "output checksum mismatch",
            ),
            self._check(
                "FFPROBE_READABLE", probe_ok,
                {"readable": True}, {"readable": probe_ok},
                {"error": probe_error}, "ffprobe readable", "ffprobe could not read output",
            ),
            self._check(
                "VIDEO_STREAM_PRESENT", video is not None,
                {"present": True}, {"present": video is not None},
                {"video": video}, "video stream present", "video stream missing",
            ),
            self._check(
                "REQUIRED_AUDIO_PRESENT", (not audio_required) or audio is not None,
                {"required": audio_required}, {"present": audio is not None},
                {"audio": audio}, "audio requirement satisfied", "required audio stream missing",
            ),
            self._check(
                "WIDTH_MATCH", video is not None and int(video.get("width", -1)) == int(timeline["target_width"]),
                {"width": int(timeline["target_width"])},
                {"width": int(video.get("width")) if video and video.get("width") is not None else None},
                {"timeline_id": timeline["id"]}, "width matches", "width mismatch",
            ),
            self._check(
                "HEIGHT_MATCH", video is not None and int(video.get("height", -1)) == int(timeline["target_height"]),
                {"height": int(timeline["target_height"])},
                {"height": int(video.get("height")) if video and video.get("height") is not None else None},
                {"timeline_id": timeline["id"]}, "height matches", "height mismatch",
            ),
            self._check(
                "DURATION_WITHIN_TOLERANCE",
                actual_duration is not None and abs(actual_duration - expected_duration) <= DURATION_TOLERANCE_SECONDS,
                {"duration_seconds": expected_duration, "tolerance_seconds": DURATION_TOLERANCE_SECONDS},
                {"duration_seconds": actual_duration},
                {"timeline_id": timeline["id"]}, "duration within tolerance", "duration outside tolerance",
            ),
            self._check(
                "SOURCE_CHECKSUM_EVIDENCE_PRESENT", source_evidence_present,
                {"present": True}, {"present": source_evidence_present},
                {"before_count": len(source_before) if isinstance(source_before, dict) else 0,
                 "after_count": len(source_after) if isinstance(source_after, dict) else 0},
                "source checksum evidence present", "source checksum evidence missing",
            ),
            self._check(
                "SOURCE_CHECKSUM_MATCH", source_match,
                {"match": True}, {"match": source_match},
                {"recorded_before": source_before, "recorded_after": source_after,
                 "current": current_sources},
                "source checksums match", "source checksum mismatch",
            ),
        ]
        return checks
    def _mark_error(self, qa_run_id: str, code: str, message: str) -> dict[str, Any]:
        self.store.get("qa_runs", qa_run_id)
        stamp = now_iso()
        conn = self.store.conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            cur = conn.execute(
                """UPDATE qa_runs
                   SET lifecycle_state='ERROR', overall_result=NULL,
                       finished_at=?, error_code=?, error_message=?, updated_at=?
                   WHERE id=? AND lifecycle_state='RUNNING'""",
                (stamp, code, str(message)[:2000], stamp, qa_run_id),
            )
            if cur.rowcount != 1:
                raise ValueError("QA run is not RUNNING")
            conn.commit()
            return self.store.get("qa_runs", qa_run_id)
        except Exception:
            conn.rollback()
            raise

    def _finalize(self, qa_run_id: str, checks: list[dict[str, Any]]) -> dict[str, Any]:
        self.store.get("qa_runs", qa_run_id)
        conn = self.store.conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            row = conn.execute("SELECT * FROM qa_runs WHERE id=?", (qa_run_id,)).fetchone()
            if row is None:
                raise KeyError(f"qa_runs:{qa_run_id}")
            run = dict(row)
            if run["lifecycle_state"] != "RUNNING":
                raise ValueError("QA run is not RUNNING")
            expected_ids = tuple(_decode_json(run["required_checks_json"], []))
            actual_ids = [check["check_id"] for check in checks]
            if tuple(expected_ids) != REQUIRED_CHECKS:
                raise ValueError("persisted QA manifest mismatch")
            if len(actual_ids) != len(set(actual_ids)) or set(actual_ids) != set(expected_ids):
                raise ValueError("required QA check set mismatch")
            if len(checks) != int(run["required_check_count"]):
                raise ValueError("QA check count mismatch")
            overall = derive_overall(checks, tuple(expected_ids))
            stamp = now_iso()
            for check in checks:
                conn.execute(
                    """INSERT INTO qa_check_results(
                        id,qa_run_id,check_id,check_version,result,severity,
                        expected_json,observed_json,evidence_json,message,created_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        str(uuid4()), qa_run_id, check["check_id"], check["check_version"],
                        check["result"], check["severity"], _canonical(check["expected_json"]),
                        _canonical(check["observed_json"]), _canonical(check["evidence_json"]),
                        check["message"], stamp,
                    ),
                )
            cur = conn.execute(
                """UPDATE qa_runs
                   SET lifecycle_state='FINALIZED', overall_result=?, actual_check_count=?,
                       finished_at=?, finalized_at=?, error_code=NULL, error_message=NULL, updated_at=?
                   WHERE id=? AND lifecycle_state='RUNNING'""",
                (overall, len(checks), stamp, stamp, stamp, qa_run_id),
            )
            if cur.rowcount != 1:
                raise ValueError("QA finalization transition failed")
            conn.commit()
            return self.store.get("qa_runs", qa_run_id)
        except Exception:
            conn.rollback()
            raise

    def execute_qa_run(self, qa_run_id: str) -> dict[str, Any]:
        run = self.store.get("qa_runs", qa_run_id)
        if run["lifecycle_state"] != "PENDING":
            raise ValueError("only PENDING QA runs may execute")
        stamp = now_iso()
        cur = self.store.conn.execute(
            """UPDATE qa_runs SET lifecycle_state='RUNNING', started_at=?, updated_at=?
               WHERE id=? AND lifecycle_state='PENDING'""",
            (stamp, stamp, qa_run_id),
        )
        if cur.rowcount != 1:
            self.store.conn.rollback()
            raise ValueError("QA lifecycle transition lost")
        self.store.conn.commit()
        try:
            checks = self._evaluate(self.store.get("qa_runs", qa_run_id))
            return self._finalize(qa_run_id, checks)
        except QAEngineError as exc:
            return self._mark_error(qa_run_id, "QA_ENGINE_ERROR", str(exc))
        except Exception as exc:
            try:
                current = self.store.get("qa_runs", qa_run_id)
                if current["lifecycle_state"] == "RUNNING":
                    return self._mark_error(qa_run_id, "QA_INTERNAL_ERROR", str(exc))
            except Exception:
                pass
            raise

    def get_qa_run(self, qa_run_id: str) -> dict[str, Any]:
        return self.store.get("qa_runs", qa_run_id)

    def list_qa_checks(self, qa_run_id: str) -> list[dict[str, Any]]:
        self.store.get("qa_runs", qa_run_id)
        rows = self.store.list("qa_check_results", {"qa_run_id": qa_run_id})
        order = {check_id: index for index, check_id in enumerate(REQUIRED_CHECKS)}
        return sorted(rows, key=lambda row: order.get(row["check_id"], 999))

    def get_qa_review(self, qa_run_id: str) -> dict[str, Any]:
        self.store.get("qa_runs", qa_run_id)
        rows = self.store.list("qa_reviews", {"qa_run_id": qa_run_id})
        if not rows:
            raise KeyError(f"qa_reviews:{qa_run_id}")
        return rows[0]

    def record_qa_review(self, qa_run_id: str, decision: str, note: str) -> dict[str, Any]:
        run = self.store.get("qa_runs", qa_run_id)
        if run["lifecycle_state"] != "FINALIZED":
            raise ValueError("only FINALIZED QA runs may be reviewed")
        state = str(decision).upper().strip()
        if state not in {"ACCEPTED", "REJECTED"}:
            raise ValueError("review state must be ACCEPTED or REJECTED")
        note = str(note).strip()
        if not note:
            raise ValueError("reviewer note is required")
        stamp = now_iso()
        cur = self.store.conn.execute(
            """UPDATE qa_reviews
               SET review_state=?, reviewer_note=?, reviewed_at=?
               WHERE qa_run_id=?""",
            (state, note, stamp, qa_run_id),
        )
        if cur.rowcount != 1:
            self.store.conn.rollback()
            raise KeyError(f"qa_reviews:{qa_run_id}")
        self.store.conn.commit()
        return self.get_qa_review(qa_run_id)
