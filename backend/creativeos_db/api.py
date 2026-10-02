"""One authenticated boundary for all network-accessible campaign operations."""
from urllib.parse import urlsplit, parse_qs

from .auth import AuthService
from .adoption import AdoptionService
from .workflow import CampaignWorkflow

READABLE = frozenset({
    "campaigns", "director_plans", "storyboards", "scenes", "assets", "asset_requirements",
    "generation_requests", "generation_queue", "generation_approvals", "generation_spend_ledger",
    "generation_provenance", "generation_attempts", "qa_runs", "qa_reviews", "export_jobs", "render_jobs",
})


class API:
    def __init__(self, db_path, output_root):
        self.auth = AuthService(db_path)
        self.output_root = output_root

    def dispatch(self, method, target, body, token, version, csrf):
        url = urlsplit(target)
        path = url.path.rstrip("/")
        parts = path.split("/")[2:]
        if method == "GET" and path == "/api/session":
            return self.auth.session(token)
        if method == "GET" and path == "/api/brands":
            return self.auth.brands(token, parse_qs(url.query).get("organization_id", [""])[0])
        if method == "POST" and path == "/api/context":
            return self.auth.select_scope(token, csrf, version, body.get("organization_id"), body.get("brand_profile_id"))
        if method == "POST" and path == "/api/logout":
            self.auth.logout(token, csrf)
            return {"signed_out": True}
        if method not in {"GET", "POST"}:
            raise KeyError("Unknown endpoint")
        adoption = parts and parts[0] == "adoption"
        with self.auth.request(token, expected_version=version, csrf=csrf,
                               write=method == "POST", require_brand=not adoption) as ctx:
            if adoption:
                service = AdoptionService(ctx)
                if path == "/api/adoption" and method == "GET":
                    return service.inventory()
                if path == "/api/adoption/preview" and method == "POST":
                    return service.preview(body.get("legacy_brand_id"))
                if path == "/api/adoption/confirm" and method == "POST":
                    return service.confirm(body.get("preview_id"), body.get("digest"), body.get("confirmation"))
                raise KeyError("Unknown endpoint")
            workflow = CampaignWorkflow(ctx, self.output_root)
            if method == "GET" and path == "/api/workspace":
                return {"brand": ctx.store.get("brand_profiles", ctx.brand_profile_id),
                        "campaigns": ctx.store.list("campaigns")}
            if method == "POST" and path == "/api/campaigns":
                return workflow.create_campaign(body)
            if len(parts) == 3 and parts[0] == "records" and parts[1] in READABLE and method == "GET":
                return ctx.store.get(parts[1], parts[2])
            if len(parts) >= 2 and parts[0] == "campaigns":
                campaign_id = parts[1]
                if len(parts) == 2 and method == "GET":
                    return workflow.detail(campaign_id)
                if len(parts) == 3 and method == "POST":
                    action = parts[2]
                    if action == "plan":
                        return workflow.plan(campaign_id)
                    if action == "approve-plan":
                        return workflow.approve_plan(campaign_id, body.get("plan_id"))
                    if action == "generate":
                        return workflow.generate(campaign_id)
            if len(parts) == 3 and parts[0] == "requests" and parts[2] == "preview" and method == "GET":
                return workflow.preview_media(parts[1])
            if len(parts) == 3 and parts[0] == "requests" and method == "POST":
                request_id, action = parts[1:]
                if action == "qa":
                    return workflow.qa(request_id)
                if action == "review":
                    return workflow.review(request_id, body.get("decision"), body.get("note"))
                if action == "export":
                    return workflow.export(request_id)
            if len(parts) == 3 and parts[0] == "exports" and parts[2] == "download" and method == "GET":
                return workflow.download(parts[1])
            raise KeyError("Unknown endpoint")
