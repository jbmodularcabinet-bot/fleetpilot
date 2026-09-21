from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .store import CreativeOSStore

REVIEW_STATES = {"PENDING", "APPROVED", "REJECTED", "REGENERATE"}
JOB_STATES = {"DRAFT", "QUEUED", "RUNNING", "SUCCEEDED", "FAILED"}

@dataclass(frozen=True)
class MockGenerationResult:
    output_path: str
    output_type: str
    metadata: dict[str, Any]
    payload: bytes

class GenerationProvider(Protocol):
    name: str
    def generate(self, job: dict[str, Any]) -> MockGenerationResult: ...
class DeterministicMockGenerationProvider:
    name = "MOCK"
    def generate(self, job: dict[str, Any]) -> MockGenerationResult:
        seed = "|".join([
            str(job.get("id", "")), str(job.get("model", "")),
            str(job.get("prompt", "")), str(job.get("aspect_ratio", "")),
            str(job.get("duration_seconds") or ""),
        ])
        digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
        payload = f"creativeos-mock:{digest}".encode("utf-8")
        return MockGenerationResult(
            output_path=f"mock://generated/{job['id']}/{digest[:16]}",
            output_type="mock",
            metadata={"deterministic": True, "digest": digest},
            payload=payload,
        )

class GenerationService:
    def __init__(self, store: CreativeOSStore, provider: GenerationProvider):
        self.store = store
        self.provider = provider
    def create_requirement(self, scene_id: str, values: dict[str, Any]) -> dict[str, Any]:
        self.store.get("scenes", scene_id)
        asset_type = str(values.get("asset_type", "")).strip()
        if not asset_type:
            raise ValueError("asset_type is required")
        duration = values.get("duration_seconds")
        if duration is not None and int(duration) <= 0:
            raise ValueError("duration_seconds must be positive")
        data = {"scene_id": scene_id, **values}
        return self.store.create("asset_requirements", data)

    def create_job(self, requirement_id: str, provider: str, model: str, prompt: str,
                   negative_prompt: str = "", reference_assets: list[str] | None = None,
                   aspect_ratio: str = "", duration_seconds: int | None = None,
                   cost_credit: dict[str, Any] | None = None) -> dict[str, Any]:
        requirement = self.store.get("asset_requirements", requirement_id)
        if not prompt.strip():
            raise ValueError("prompt is required")
        return self.store.create("generation_jobs", {
            "scene_id": requirement["scene_id"], "asset_requirement_id": requirement_id,
            "provider": provider, "model": model, "state": "QUEUED",
            "prompt": prompt, "negative_prompt": negative_prompt,
            "reference_assets_json": reference_assets or [], "aspect_ratio": aspect_ratio,
            "duration_seconds": duration_seconds, "cost_credit_json": cost_credit or {},
            "provider_snapshot": provider, "model_snapshot": model,
            "request_json": {"prompt": prompt, "negative_prompt": negative_prompt},
        })

    def _successful_asset(self, job_id: str) -> dict[str, Any] | None:
        rows = self.store.list("generated_assets", {"generation_job_id": job_id})
        return rows[0] if rows else None

    def run_job(self, job_id: str) -> dict[str, Any]:
        job = self.store.get("generation_jobs", job_id)
        existing = self._successful_asset(job_id)
        if job["state"] == "SUCCEEDED" and existing:
            return existing
        if job["state"] == "SUCCEEDED" and not existing:
            raise ValueError("succeeded job missing immutable output record")
        self.store.update("generation_jobs", job_id, {"state": "RUNNING", "error": None})
        try:
            result = self.provider.generate({**job, "state": "RUNNING"})
            checksum = hashlib.sha256(result.payload).hexdigest()
            asset = self.store.create("generated_assets", {
                "generation_job_id": job_id,
                "asset_requirement_id": job["asset_requirement_id"],
                "output_path": result.output_path, "output_type": result.output_type,
                "output_metadata_json": result.metadata,
                "prompt_snapshot": job["prompt"], "provider_snapshot": job["provider_snapshot"],
                "model_snapshot": job["model_snapshot"], "checksum_sha256": checksum,
                "review_state": "PENDING",
            })
            self.store.update("generation_jobs", job_id, {
                "state": "SUCCEEDED", "output_path": result.output_path,
                "response_json": result.metadata, "error": None,
            })
            return asset
        except Exception as exc:
            self.store.update("generation_jobs", job_id, {"state": "FAILED", "error": str(exc)})
            raise

    def retry_failed(self, job_id: str) -> dict[str, Any]:
        job = self.store.get("generation_jobs", job_id)
        if job["state"] != "FAILED":
            raise ValueError("only FAILED jobs may retry")
        return self.store.create("generation_jobs", {
            "scene_id": job["scene_id"], "asset_requirement_id": job["asset_requirement_id"],
            "provider": job["provider"], "model": job["model"], "state": "QUEUED",
            "request_json": json.loads(job["request_json"] or "{}"), "response_json": None,
            "prompt": job["prompt"], "negative_prompt": job["negative_prompt"],
            "reference_assets_json": json.loads(job["reference_assets_json"] or "[]"),
            "aspect_ratio": job["aspect_ratio"], "duration_seconds": job["duration_seconds"],
            "cost_credit_json": json.loads(job["cost_credit_json"] or "{}"),
            "retry_count": int(job["retry_count"] or 0) + 1,
            "retry_of_id": job_id, "provider_snapshot": job["provider_snapshot"],
            "model_snapshot": job["model_snapshot"],
        })

    def review_asset(self, asset_id: str, state: str) -> dict[str, Any]:
        normalized = state.upper()
        if normalized not in REVIEW_STATES:
            raise ValueError("invalid review state")
        current = self.store.get("generated_assets", asset_id)
        if current["review_state"] == "APPROVED" and normalized != "APPROVED":
            raise ValueError("approved generated asset is immutable")
        self.store.conn.execute("UPDATE generated_assets SET review_state=? WHERE id=?", (normalized, asset_id))
        self.store.conn.commit()
        return self.store.get("generated_assets", asset_id)
