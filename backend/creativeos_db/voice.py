from __future__ import annotations

import hashlib
import math
import struct
import wave
from pathlib import Path
from typing import Any

from .store import CreativeOSStore

VOICE_STATUSES = {"PENDING", "RUNNING", "SUCCEEDED", "FAILED"}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class DeterministicMockVoiceAdapter:
    provider = "MOCK"
    model = "deterministic-sine-v1"

    def synthesize(self, text: str, language: str, voice_id: str, output_path: Path) -> dict[str, Any]:
        key = f"{language}|{voice_id}|{text}".encode("utf-8")
        seed = hashlib.sha256(key).digest()
        duration_ms = max(600, min(4000, 500 + len(text.encode("utf-8")) * 35))
        sample_rate = 48000
        frequency = 220 + (int.from_bytes(seed[:2], "big") % 440)
        frames = int(sample_rate * duration_ms / 1000)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(output_path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            payload = bytearray()
            for i in range(frames):
                envelope = min(1.0, i / 400.0, (frames - i) / 400.0)
                sample = int(5000 * envelope * math.sin(2 * math.pi * frequency * i / sample_rate))
                payload.extend(struct.pack("<h", sample))
            wav.writeframes(bytes(payload))
        return {
            "duration_ms": duration_ms,
            "checksum_sha256": _sha256_file(output_path),
            "sample_rate": sample_rate,
        }


class VoiceService:
    def __init__(self, store: CreativeOSStore, output_root: str | Path,
                 adapter: DeterministicMockVoiceAdapter | None = None):
        self.store = store
        self.output_root = Path(output_root).resolve()
        self.output_root.mkdir(parents=True, exist_ok=True)
        self.adapter = adapter or DeterministicMockVoiceAdapter()
    def create_job(self, scene_id: str, text: str, language: str = "en",
                   voice_id: str = "mock-default", generation_job_id: str | None = None) -> dict[str, Any]:
        self.store.get("scenes", scene_id)
        if generation_job_id:
            self.store.get("generation_jobs", generation_job_id)
        text = str(text)
        if not text.strip():
            raise ValueError("voice text is required")
        if not language.strip() or not voice_id.strip():
            raise ValueError("language and voice_id are required")
        return self.store.create("voice_jobs", {
            "scene_id": scene_id,
            "generation_job_id": generation_job_id,
            "provider": self.adapter.provider,
            "model": self.adapter.model,
            "voice_id": voice_id,
            "text_snapshot": text,
            "language": language,
            "status": "PENDING",
        })

    def run_job(self, voice_job_id: str) -> dict[str, Any]:
        job = self.store.get("voice_jobs", voice_job_id)
        if job["status"] == "SUCCEEDED" and job.get("output_path"):
            path = Path(job["output_path"])
            if path.exists() and _sha256_file(path) == job.get("checksum_sha256"):
                return job
        output_path = (self.output_root / f"{job['id']}.wav").resolve()
        if self.output_root not in output_path.parents:
            raise ValueError("voice output escaped approved directory")
        self.store.update("voice_jobs", voice_job_id, {"status": "RUNNING", "error": None})
        try:
            result = self.adapter.synthesize(
                job["text_snapshot"], job["language"], job["voice_id"], output_path
            )
            return self.store.update("voice_jobs", voice_job_id, {
                "status": "SUCCEEDED",
                "output_path": str(output_path),
                "duration_ms": int(result["duration_ms"]),
                "checksum_sha256": result["checksum_sha256"],
                "error": None,
            })
        except Exception as exc:
            self.store.update("voice_jobs", voice_job_id, {"status": "FAILED", "error": str(exc)})
            raise
