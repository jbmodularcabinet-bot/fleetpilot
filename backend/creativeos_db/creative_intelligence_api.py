"""Authenticated Creative Intelligence endpoints layered onto the existing production API."""
from urllib.parse import urlsplit

from .api import API
from .creative_intelligence import CreativeIntelligenceService


class ApplicationAPI(API):
    def dispatch(self, method, target, body, token, version, csrf):
        path = urlsplit(target).path.rstrip("/")
        if not path.startswith("/api/intelligence"):
            return super().dispatch(method, target, body, token, version, csrf)
        if method not in {"GET", "POST"}:
            raise KeyError("Unknown endpoint")

        parts = path.split("/")[3:]
        with self.auth.request(
            token,
            expected_version=version,
            csrf=csrf,
            write=method == "POST",
            require_brand=True,
        ) as ctx:
            service = CreativeIntelligenceService(ctx.store)
            if method == "GET" and not parts:
                return service.overview()

            if parts[:1] == ["market"]:
                if method == "POST" and len(parts) == 1:
                    return service.create_market_intelligence(body)
                if method == "POST" and len(parts) == 2:
                    return service.update_market_intelligence(parts[1], body)
                if method == "POST" and len(parts) == 3 and parts[2] == "delete":
                    service.delete_market_intelligence(parts[1])
                    return {"deleted": True}

            if parts[:1] == ["hypotheses"]:
                if method == "POST" and len(parts) == 1:
                    return service.create_hypothesis(body)
                if method == "POST" and len(parts) == 2:
                    return service.update_hypothesis(parts[1], body)
                if method == "POST" and len(parts) == 3 and parts[2] == "evidence":
                    return service.add_evidence({**body, "hypothesis_id": parts[1]})
                if method == "POST" and len(parts) == 3 and parts[2] == "delete":
                    service.delete_hypothesis(parts[1])
                    return {"deleted": True}

            if parts[:1] == ["references"]:
                if method == "POST" and len(parts) == 1:
                    return service.create_reference_pattern(body)
                if method == "POST" and len(parts) == 2:
                    return service.update_reference_pattern(parts[1], body)
                if method == "POST" and len(parts) == 3 and parts[2] == "delete":
                    service.delete_reference_pattern(parts[1])
                    return {"deleted": True}

            if parts[:1] == ["experiments"]:
                if method == "POST" and len(parts) == 1:
                    return service.create_experiment(body)
                if method == "POST" and len(parts) == 2:
                    return service.update_experiment(parts[1], body)
                if method == "POST" and len(parts) == 3 and parts[2] == "delete":
                    service.delete_experiment(parts[1])
                    return {"deleted": True}
                if method == "POST" and len(parts) == 3 and parts[2] == "assets":
                    return service.link_experiment_asset(
                        parts[1], body.get("asset_id"), body.get("asset_kind", "ASSET"),
                    )
                if (
                    method == "POST"
                    and len(parts) == 5
                    and parts[2] == "assets"
                    and parts[4] == "delete"
                ):
                    service.unlink_experiment_asset(parts[3])
                    return {"deleted": True}

            if (
                parts[:1] == ["assets"]
                and method == "POST"
                and len(parts) == 3
                and parts[2] == "provenance"
            ):
                return service.set_asset_provenance(
                    parts[1],
                    truth_level=body.get("truth_level"),
                    reference_fidelity_required=body.get("reference_fidelity_required", False),
                )

            raise KeyError("Unknown endpoint")
