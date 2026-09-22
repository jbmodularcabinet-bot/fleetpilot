from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .store import CreativeOSStore, now_iso

DURATION_TOLERANCE_SECONDS = 0.20
MAX_PREVIEW_SECONDS = 60.0
MAX_WIDTH = 1920
MAX_HEIGHT = 1080
MAX_FPS = 60


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _version_line(path: Path) -> str:
    result = subprocess.run([str(path), "-version"], capture_output=True, text=True, timeout=10, shell=False)
    if result.returncode != 0:
        raise RuntimeError(f"cannot execute {path}")
    return (result.stdout or result.stderr).splitlines()[0].strip()

def discover_media_tools() -> tuple[Path, Path]:
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if ffmpeg and ffprobe:
        return Path(ffmpeg).resolve(), Path(ffprobe).resolve()
    local = os.environ.get("LOCALAPPDATA")
    if local:
        root = Path(local) / "Microsoft" / "WinGet" / "Packages"
        ffmpeg_hits = sorted(root.glob("Gyan.FFmpeg*/**/bin/ffmpeg.exe"))
        ffprobe_hits = sorted(root.glob("Gyan.FFmpeg*/**/bin/ffprobe.exe"))
        if ffmpeg_hits and ffprobe_hits:
            return ffmpeg_hits[-1].resolve(), ffprobe_hits[-1].resolve()
    raise RuntimeError("ffmpeg and ffprobe are required")


class CompositionService:
    def __init__(self, store: CreativeOSStore, project_root: str | Path,
                 output_root: str | Path, ffmpeg_path: str | Path | None = None,
                 ffprobe_path: str | Path | None = None):
        self.store = store
        self.project_root = Path(project_root).resolve()
        self.output_root = Path(output_root).resolve()
        self.output_root.mkdir(parents=True, exist_ok=True)
        if self.project_root not in self.output_root.parents and self.output_root != self.project_root:
            raise ValueError("output root must be inside project root")
        if ffmpeg_path is None or ffprobe_path is None:
            ffmpeg_path, ffprobe_path = discover_media_tools()
        self.ffmpeg_path = Path(ffmpeg_path).resolve()
        self.ffprobe_path = Path(ffprobe_path).resolve()
        self.ffmpeg_version = _version_line(self.ffmpeg_path)
        self.ffprobe_version = _version_line(self.ffprobe_path)

    def _source_path(self, value: str) -> Path:
        path = Path(value).resolve()
        if self.project_root not in path.parents and path != self.project_root:
            raise ValueError("source path must be inside project root")
        if not path.is_file():
            raise ValueError(f"source file does not exist: {path}")
        return path

    def _validate_dimensions(self, width: int, height: int, fps: int) -> None:
        if width <= 0 or height <= 0 or width > MAX_WIDTH or height > MAX_HEIGHT:
            raise ValueError("invalid preview dimensions")
        if fps <= 0 or fps > MAX_FPS:
            raise ValueError("invalid preview frame rate")

    def create_timeline(self, campaign_id: str, storyboard_id: str, entries: list[dict[str, Any]],
                        target_width: int = 640, target_height: int = 360,
                        aspect_ratio: str = "16:9", fps: int = 24) -> dict[str, Any]:
        campaign = self.store.get("campaigns", campaign_id)
        board = self.store.get("storyboards", storyboard_id)
        if board["campaign_id"] != campaign["id"]:
            raise ValueError("storyboard does not belong to campaign")
        self._validate_dimensions(int(target_width), int(target_height), int(fps))
        if not entries:
            raise ValueError("timeline requires at least one entry")
        total_ms = 0
        prepared: list[dict[str, Any]] = []
        for sequence, raw in enumerate(entries, 1):
            scene = self.store.get("scenes", raw["scene_id"])
            if scene["storyboard_id"] != storyboard_id:
                raise ValueError("timeline scene does not belong to storyboard")
            duration_ms = int(raw.get("duration_ms", 0))
            if duration_ms <= 0:
                raise ValueError("timeline duration must be positive")
            total_ms += duration_ms
            if total_ms > int(MAX_PREVIEW_SECONDS * 1000):
                raise ValueError("preview exceeds bounded duration")
            visual = self._source_path(str(raw["visual_path"]))
            audio = None
            if raw.get("audio_path"):
                audio = self._source_path(str(raw["audio_path"]))
            transition = raw.get("transition") or {"type": "cut"}
            if not isinstance(transition, dict) or transition.get("type", "cut") != "cut":
                raise ValueError("Batch 9 supports approved cut transitions only")
            prepared.append({
                "sequence": sequence,
                "scene_id": scene["id"],
                "scene_version_id": raw.get("scene_version_id"),
                "generated_asset_id": raw.get("generated_asset_id"),
                "start_ms": total_ms - duration_ms,
                "duration_ms": duration_ms,
                "visual_path": str(visual),
                "audio_path": str(audio) if audio else None,
                "transition_json": transition,
            })
        timeline = self.store.create("composition_timelines", {
            "campaign_id": campaign_id, "storyboard_id": storyboard_id,
            "target_width": int(target_width), "target_height": int(target_height),
            "aspect_ratio": aspect_ratio, "fps": int(fps),
        })
        created_entries = []
        for item in prepared:
            created_entries.append(self.store.create("composition_timeline_entries", {
                "timeline_id": timeline["id"], **item,
            }))
        return {"timeline": timeline, "entries": created_entries}

    def load_timeline(self, timeline_id: str) -> dict[str, Any]:
        timeline = self.store.get("composition_timelines", timeline_id)
        rows = self.store.conn.execute(
            "SELECT * FROM composition_timeline_entries WHERE timeline_id=? ORDER BY sequence ASC",
            (timeline_id,),
        ).fetchall()
        return {"timeline": timeline, "entries": [dict(row) for row in rows]}

    def _render_identity(self, loaded: dict[str, Any]) -> tuple[str, dict[str, str]]:
        timeline = loaded["timeline"]
        source_hashes: dict[str, str] = {}
        identity_entries = []
        for row in loaded["entries"]:
            visual = self._source_path(row["visual_path"])
            source_hashes[str(visual)] = _sha256_file(visual)
            audio_hash = None
            if row.get("audio_path"):
                audio = self._source_path(row["audio_path"])
                source_hashes[str(audio)] = _sha256_file(audio)
                audio_hash = source_hashes[str(audio)]
            identity_entries.append({
                "sequence": row["sequence"], "scene_id": row["scene_id"],
                "scene_version_id": row.get("scene_version_id"),
                "generated_asset_id": row.get("generated_asset_id"),
                "start_ms": row["start_ms"], "duration_ms": row["duration_ms"],
                "visual_path": str(visual), "visual_sha256": source_hashes[str(visual)],
                "audio_path": row.get("audio_path"), "audio_sha256": audio_hash,
                "transition_json": json.loads(row["transition_json"] or "{}"),
            })
        payload = {
            "timeline_id": timeline["id"],
            "target_width": timeline["target_width"], "target_height": timeline["target_height"],
            "aspect_ratio": timeline["aspect_ratio"], "fps": timeline["fps"],
            "entries": identity_entries,
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest(), source_hashes

    def build_ffmpeg_args(self, timeline_id: str, output_path: str | Path) -> list[str]:
        loaded = self.load_timeline(timeline_id)
        timeline = loaded["timeline"]
        entries = loaded["entries"]
        self._validate_dimensions(int(timeline["target_width"]), int(timeline["target_height"]), int(timeline["fps"]))
        output = Path(output_path).resolve()
        if self.output_root not in output.parents:
            raise ValueError("render output must stay inside approved output directory")
        output.parent.mkdir(parents=True, exist_ok=True)
        inputs: list[str] = []
        filters: list[str] = []
        pairs: list[str] = []
        input_index = 0
        for i, row in enumerate(entries):
            visual = self._source_path(row["visual_path"])
            seconds = int(row["duration_ms"]) / 1000.0
            if seconds <= 0 or seconds > MAX_PREVIEW_SECONDS:
                raise ValueError("invalid entry duration")
            sec = f"{seconds:.3f}"
            inputs += ["-loop", "1", "-framerate", str(timeline["fps"]), "-t", sec, "-i", str(visual)]
            video_index = input_index
            input_index += 1
            filters.append(
                f"[{video_index}:v]scale={timeline['target_width']}:{timeline['target_height']}:force_original_aspect_ratio=decrease,"
                f"pad={timeline['target_width']}:{timeline['target_height']}:(ow-iw)/2:(oh-ih)/2,setsar=1,"
                f"trim=duration={sec},setpts=PTS-STARTPTS[v{i}]"
            )
            if row.get("audio_path"):
                audio = self._source_path(row["audio_path"])
                inputs += ["-i", str(audio)]
                audio_index = input_index
                input_index += 1
                filters.append(
                    f"[{audio_index}:a]aresample=48000,apad=pad_dur={sec},atrim=duration={sec},asetpts=PTS-STARTPTS[a{i}]"
                )
            else:
                filters.append(
                    f"anullsrc=r=48000:cl=mono,atrim=duration={sec},asetpts=PTS-STARTPTS[a{i}]"
                )
            pairs.append(f"[v{i}][a{i}]")
        filters.append("".join(pairs) + f"concat=n={len(entries)}:v=1:a=1[vout][aout]")
        return [
            "-hide_banner", "-loglevel", "warning", *inputs,
            "-filter_complex", ";".join(filters),
            "-map", "[vout]", "-map", "[aout]", "-r", str(timeline["fps"]),
            "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-movflags", "+faststart", "-y", str(output),
        ]

    def _probe(self, path: Path) -> dict[str, Any]:
        result = subprocess.run([
            str(self.ffprobe_path), "-v", "error", "-show_entries",
            "stream=index,codec_type,width,height:format=duration", "-of", "json", str(path)
        ], capture_output=True, text=True, timeout=20, shell=False)
        if result.returncode != 0:
            raise RuntimeError((result.stderr or "ffprobe failed")[-4000:])
        return json.loads(result.stdout)

    def render_preview(self, timeline_id: str) -> dict[str, Any]:
        loaded = self.load_timeline(timeline_id)
        identity, source_before = self._render_identity(loaded)
        existing = self.store.list("render_jobs", {"render_identity": identity})
        if existing:
            job = existing[0]
            path = Path(job["output_path"])
            if job["status"] == "SUCCEEDED" and path.exists() and _sha256_file(path) == job.get("output_checksum_sha256"):
                return job
        else:
            output = (self.output_root / "previews" / f"{identity}.mp4").resolve()
            args = self.build_ffmpeg_args(timeline_id, output)
            job = self.store.create("render_jobs", {
                "timeline_id": timeline_id, "render_identity": identity,
                "status": "PENDING", "output_path": str(output),
                "command_args_json": args, "ffmpeg_path": str(self.ffmpeg_path),
                "ffmpeg_version": self.ffmpeg_version,
            })
        output = Path(job["output_path"]).resolve()
        args = json.loads(job["command_args_json"] or "[]")
        started = now_iso()
        attempt = self.store.create("render_attempts", {"render_job_id": job["id"], "started_at": started})
        self.store.update("render_jobs", job["id"], {"status": "RUNNING", "started_at": started, "error": None})
        try:
            result = subprocess.run(
                [str(self.ffmpeg_path), *args], capture_output=True, text=True,
                timeout=90, shell=False,
            )
            finished = now_iso()
            stdout_summary = (result.stdout or "")[-4000:]
            stderr_summary = (result.stderr or "")[-4000:]
            self.store.update("render_attempts", attempt["id"], {
                "finished_at": finished, "exit_code": result.returncode,
                "stdout_summary": stdout_summary, "stderr_summary": stderr_summary,
                "error": None if result.returncode == 0 else "ffmpeg returned non-zero",
            })
            if result.returncode != 0 or not output.is_file():
                raise RuntimeError(f"ffmpeg render failed with exit code {result.returncode}")
            source_after = {path: _sha256_file(Path(path)) for path in source_before}
            if source_before != source_after:
                raise RuntimeError("source asset checksum changed during render")
            probe = self._probe(output)
            streams = probe.get("streams", [])
            video = next((s for s in streams if s.get("codec_type") == "video"), None)
            audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
            timeline = loaded["timeline"]
            expected_seconds = sum(int(e["duration_ms"]) for e in loaded["entries"]) / 1000.0
            actual_seconds = float(probe.get("format", {}).get("duration", 0.0))
            audio_required = any(bool(e.get("audio_path")) for e in loaded["entries"])
            if video is None:
                raise RuntimeError("ffprobe found no video stream")
            if int(video.get("width", 0)) != int(timeline["target_width"]) or int(video.get("height", 0)) != int(timeline["target_height"]):
                raise RuntimeError("render dimensions do not match timeline")
            if abs(actual_seconds - expected_seconds) > DURATION_TOLERANCE_SECONDS:
                raise RuntimeError("render duration outside tolerance")
            if audio_required and audio is None:
                raise RuntimeError("required audio stream is missing")
            checksum = _sha256_file(output)
            evidence = {
                "ffprobe": probe,
                "ffprobe_path": str(self.ffprobe_path),
                "ffprobe_version": self.ffprobe_version,
                "expected_duration_seconds": expected_seconds,
                "actual_duration_seconds": actual_seconds,
                "duration_tolerance_seconds": DURATION_TOLERANCE_SECONDS,
                "audio_required": audio_required,
                "source_checksums_before": source_before,
                "source_checksums_after": source_after,
            }
            return self.store.update("render_jobs", job["id"], {
                "status": "SUCCEEDED", "finished_at": finished,
                "exit_code": 0, "stdout_summary": stdout_summary,
                "stderr_summary": stderr_summary, "output_checksum_sha256": checksum,
                "probe_json": evidence, "error": None,
            })
        except Exception as exc:
            finished = now_iso()
            try:
                current_attempt = self.store.get("render_attempts", attempt["id"])
                if current_attempt.get("finished_at") is None:
                    self.store.update("render_attempts", attempt["id"], {
                        "finished_at": finished, "error": str(exc)
                    })
            finally:
                self.store.update("render_jobs", job["id"], {
                    "status": "FAILED", "finished_at": finished, "error": str(exc)
                })
            raise
