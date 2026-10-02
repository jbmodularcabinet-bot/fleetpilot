"""Authenticated orchestration of the existing pipeline; MOCK is explicit and local."""
from __future__ import annotations

import hashlib
import struct
import zlib
from pathlib import Path

from .auth import AccessError
from .brand_service import BrandBrainService
from .composition import CompositionService
from .director import CampaignBrief, DeterministicMockCreativeDirectorProvider
from .director_service import CreativeDirectorService
from .generation_engine import BudgetGuard, GenerationOrchestrator, GenerationReleaseGate, ProviderGenerationWorker, RouteDecision
from .provider_contract import ProviderSubmission, ProviderResult
from .qa import QAService
from .voice import VoiceService


class LocalPreviewRouter:
    def route(self, intent, **kwargs):
        return RouteDecision("MOCK", "local-preview", "image", intent, {}, 0, cost_source="LOCAL_MOCK_ZERO_COST")

    def provider_input(self, route, prompt, references):
        return {"prompt": prompt}


class LocalPreviewProvider:
    """A deterministic placeholder image, never represented as live AI generation."""
    def submit(self, model_id, input_payload, *, correlation_id, **kwargs):
        self.seed = hashlib.sha256(input_payload["prompt"].encode()).digest()
        return ProviderSubmission(correlation_id, "queued", "mock://status", None, {"mode": "MOCK"})

    def poll(self, submission, **kwargs):
        return ProviderResult(submission.request_id, "completed", "mock://local-preview",
                              {"actual_cost_minor": 0, "mode": "MOCK"})

    def download(self, url):
        def chunk(kind, data):
            return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
        width, height = 640, 360
        pixels = b"".join(b"\x00" + bytes(self.seed[:3]) * width for _ in range(height))
        return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(pixels)) + chunk(b"IEND", b""))


def storage_component(identifier):
    # Imported legacy identifiers are data, never filesystem path components.
    return hashlib.sha256(str(identifier).encode()).hexdigest()


class CampaignWorkflow:
    def __init__(self, context, output_root):
        self.ctx, self.store = context, context.store
        self.root = Path(output_root).resolve() / storage_component(context.organization_id) / storage_component(context.brand_profile_id)

    def campaign(self, campaign_id):
        return self.store.get("campaigns", campaign_id)

    def create_campaign(self, values):
        allowed = {"title", "objective", "audience", "offer", "cta"}
        if set(values) - allowed:
            raise ValueError("Campaign ownership and other fields are assigned by the server")
        if not all(isinstance(v, str) and len(v) <= 2000 for v in values.values()):
            raise ValueError("Campaign fields must be bounded text")
        if not str(values.get("title", "")).strip():
            raise ValueError("Campaign title is required")
        return self.store.create("campaigns", {
            **values, "organization_id": self.ctx.organization_id,
            "brand_profile_id": self.ctx.brand_profile_id, "format": "Product Walkthrough",
            "duration_seconds": 2, "aspect_ratio": "16:9"})

    def rows(self, table, campaign_id):
        self.campaign(campaign_id)
        return [self.store.get(table, r[0]) for r in self.store.conn.execute(
            f"SELECT id FROM v_scope_{table} WHERE campaign_id=? ORDER BY id", (campaign_id,))]

    def detail(self, campaign_id):
        campaign = self.campaign(campaign_id)
        return {"campaign": campaign, **{table: self.rows(table, campaign_id) for table in (
            "director_plans", "storyboards", "generation_requests", "generation_queue",
            "generation_approvals", "generation_spend_ledger", "qa_runs", "qa_reviews", "export_jobs",
            "generation_attempts", "render_jobs")}}

    def plan(self, campaign_id):
        campaign = self.campaign(campaign_id)
        brand = BrandBrainService(self.store).get(self.ctx.brand_profile_id)
        brief = CampaignBrief(
            brand_profile_id=brand["id"], objective=campaign["objective"] or campaign["title"],
            target_audience=campaign["audience"] or brand.get("audience") or "Campaign audience",
            awareness_level="problem-aware", pain_points=brand.get("pain_points_json") or [],
            core_offer=campaign["offer"] or brand.get("core_promise") or "Explore this product",
            cta=campaign["cta"] or "Learn more", campaign_format="Product Walkthrough",
            duration_seconds=10, aspect_ratio="16:9", language="English",
            tone=brand.get("tone_of_voice") or "Clear", presenter_mode="none",
            real_ui_percent=0, generated_percent=100, budget_preference="Local MOCK preview",
            quality_preference="Preview", production_constraints=["Local MOCK preview only"])
        return CreativeDirectorService(self.store, DeterministicMockCreativeDirectorProvider()).generate_plan_for_campaign(
            campaign_id, brief)

    def approve_plan(self, campaign_id, plan_id):
        self.campaign(campaign_id)
        plan = self.store.get("director_plans", plan_id)
        if plan["campaign_id"] != campaign_id:
            raise AccessError("Plan belongs to another campaign")
        if self.store.list("storyboards", {"campaign_id": campaign_id}):
            raise ValueError("Campaign already has an approved storyboard")
        director = CreativeDirectorService(self.store, DeterministicMockCreativeDirectorProvider())
        director.approve_plan(plan_id)
        return director.materialize_storyboard(plan_id, self.campaign(campaign_id)["title"])

    def generate(self, campaign_id):
        campaign = self.campaign(campaign_id)
        boards = self.store.list("storyboards", {"campaign_id": campaign_id})
        if not boards:
            raise ValueError("Approve a Director plan first")
        scenes = self.store.list("scenes", {"storyboard_id": boards[0]["id"]})
        scene = next((s for s in scenes if not s["immutable_ui"] and s["generation_method"] != "COMPOSITING_ONLY"), None)
        if scene is None:
            raise AccessError("Approved immutable UI cannot enter generative routing")
        prior = self.store.list("generation_requests", {"campaign_id": campaign_id})
        if prior:
            raise ValueError("Campaign already has a generation request; open its current state")
        requirement = self.store.create("asset_requirements", {"scene_id": scene["id"], "asset_type": "image"})
        orchestrator = GenerationOrchestrator(self.store, model_router=LocalPreviewRouter())
        BudgetGuard(self.store).set_policy(self.ctx.organization_id, campaign_id,
            campaign_limit_minor=100, tenant_daily_limit_minor=100, approval_required_minor=1)
        request = orchestrator.create_request(asset_requirement_id=requirement["id"],
            tenant_id=self.ctx.organization_id, user_id=self.ctx.user_id, idempotency_key=campaign_id,
            intent="STATIC_META", original_prompt=campaign["objective"] or campaign["title"])
        orchestrator.plan(request["id"], actor=self.ctx.user_id, aspect_ratio="16:9", duration_seconds=2)
        orchestrator.cost(request["id"], actor=self.ctx.user_id)
        orchestrator.approve_cost(request["id"], approved_by=self.ctx.user_id, note="User requested zero-cost MOCK preview")
        orchestrator.queue_request(request["id"], actor=self.ctx.user_id)
        root = self.root / storage_component(campaign_id)
        result = ProviderGenerationWorker(self.store, LocalPreviewProvider(), root / "generated",
                                          orchestrator=orchestrator).execute_request(request["id"])
        if not result.get("local_path"):
            return {"failure": "Generation did not complete; recorded attempt history is retained.",
                    "request": self.store.get("generation_requests", request["id"])}
        voice_service = VoiceService(self.store, root / "voice")
        voice = voice_service.run_job(voice_service.create_job(scene["id"],
            (campaign["objective"] or campaign["title"])[:500], "en", "mock-ainsley")["id"])
        composition = CompositionService(self.store, root, root / "rendered")
        timeline = composition.create_timeline(campaign_id, boards[0]["id"], [{
            "scene_id": scene["id"], "duration_ms": 2000, "visual_path": result["local_path"],
            "audio_path": voice["output_path"],
        }])["timeline"]
        render = composition.render_preview(timeline["id"])
        updated = self.store.update("generation_requests", request["id"], {"render_job_id": render["id"]})
        if render["status"] != "SUCCEEDED":
            return {"failure": "Preview rendering failed; recorded render history is retained.", "request": updated}
        return updated

    def qa(self, request_id):
        request = self.store.get("generation_requests", request_id)
        if request["lifecycle_step"] != 6 or not request["render_job_id"]:
            raise ValueError("A generated render is required")
        service = QAService(self.store)
        run = service.execute_qa_run(service.create_qa_run(request["render_job_id"])["id"])
        self.store.update("generation_requests", request_id, {"qa_run_id": run["id"]})
        orch = GenerationOrchestrator(self.store)
        orch.begin_qa(request_id, actor=self.ctx.user_id)
        gate = GenerationReleaseGate(self.store).run(request_id, render_qa_run_id=run["id"])
        if gate["result"] == "PASS":
            orch.complete_qa(request_id, actor=self.ctx.user_id)
        return {"qa": run, "gate": gate}

    def review(self, request_id, decision, note):
        request = self.store.get("generation_requests", request_id)
        if request["lifecycle_step"] != 8 or not request["qa_run_id"]:
            raise ValueError("Passing QA is required for human review")
        if decision not in {"ACCEPTED", "REJECTED"} or not isinstance(note, str) or not 1 <= len(note.strip()) <= 2000:
            raise ValueError("A review decision and note are required")
        review = QAService(self.store).record_qa_review(request["qa_run_id"], decision, note)
        if decision == "ACCEPTED":
            GenerationOrchestrator(self.store).human_approve(request_id, approved_by=self.ctx.user_id, note=note)
        return review

    def export(self, request_id):
        request = self.store.get("generation_requests", request_id)
        return GenerationOrchestrator(self.store).create_export(request_id,
            render_job_id=request["render_job_id"], qa_run_id=request["qa_run_id"],
            actor=self.ctx.user_id, preset="LOCAL_MOCK_PREVIEW_16_9")["export"]

    def preview_media(self, request_id):
        request = self.store.get("generation_requests", request_id)
        if request["lifecycle_step"] < 6 or not request["render_job_id"]:
            raise AccessError("A completed preview is required")
        render = self.store.get("render_jobs", request["render_job_id"])
        path = Path(render["output_path"] or "").resolve()
        if self.root not in path.parents or not path.is_file() or render["status"] != "SUCCEEDED":
            raise AccessError("Preview file is unavailable")
        return path.read_bytes()

    def download(self, export_id):
        export = self.store.get("export_jobs", export_id)
        path = Path(export["output_path"] or "").resolve()
        if self.root not in path.parents or not path.is_file() or export["state"] != "APPROVED":
            raise AccessError("Export file is unavailable")
        return path.read_bytes()
