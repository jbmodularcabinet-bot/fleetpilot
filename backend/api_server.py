from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse

from creativeos_db import CreativeOSStore
from creativeos_db.higgsfield_provider import (
    HiggsfieldProvider,
    HiggsfieldProviderError,
    HiggsfieldSubmission,
)
from creativeos_db.saas_bridge import SaaSBridgeService


HOST = os.environ.get("CREATIVEOS_HOST", "127.0.0.1")
PORT = int(os.environ.get("CREATIVEOS_PORT", "8765"))
DB_PATH = Path(
    os.environ.get(
        "CREATIVEOS_DB_PATH",
        str(Path(os.environ.get("LOCALAPPDATA", ".")) / "CreativeOS" / "Runtime" / "creativeos.sqlite3"),
    )
)
PREFLIGHT_REQUEST_ID = os.environ.get("CREATIVEOS_PROVIDER_PREFLIGHT_REQUEST_ID", "").strip()
FRONTEND_ORIGIN = os.environ.get("CREATIVEOS_FRONTEND_ORIGIN", "http://127.0.0.1:4173")


def bootstrap_provider() -> dict[str, object]:
    credential_present = bool(
        os.environ.get("HF_CREDENTIALS") or os.environ.get("HF_KEY")
    )
    provider = None
    auth = "UNCONFIGURED"
    if credential_present:
        provider = HiggsfieldProvider.from_env()
    for name in ("HF_KEY", "HF_CREDENTIALS", "HF_API_KEY", "HF_API_SECRET"):
        os.environ.pop(name, None)
    if provider is not None and PREFLIGHT_REQUEST_ID:
        try:
            result = provider.poll(
                HiggsfieldSubmission(
                    request_id=PREFLIGHT_REQUEST_ID,
                    status="completed",
                    status_url=(
                        "https://api.higgsfield.ai/requests/"
                        + PREFLIGHT_REQUEST_ID
                        + "/status"
                    ),
                    cancel_url=None,
                    raw={},
                ),
                timeout_seconds=30,
                max_polls=1,
            )
            auth = "PASS" if result.status == "completed" else "FAIL"
        except HiggsfieldProviderError:
            auth = "FAIL"
    elif provider is not None:
        auth = "CONFIGURED"
    return {
        "configured": provider is not None,
        "authentication": auth,
        "secret_env_present_after_bootstrap": any(
            os.environ.get(name)
            for name in ("HF_KEY", "HF_CREDENTIALS", "HF_API_KEY", "HF_API_SECRET")
        ),
    }
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
store = CreativeOSStore(DB_PATH)
schema = store.migrate_to_latest()
bridge = SaaSBridgeService(store)
provider_state = bootstrap_provider()


def _jsonable(value):
    return value


class Handler(BaseHTTPRequestHandler):
    server_version = "CreativeOSLocal/1.0"

    def _send(self, code: int, payload: object) -> None:
        body = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", FRONTEND_ORIGIN)
        self.send_header("Access-Control-Allow-Methods", "GET,POST,PATCH,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or "0")
        if not length:
            return {}
        raw = self.rfile.read(length)
        value = json.loads(raw.decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("request body must be a JSON object")
        return value

    def _parts(self) -> list[str]:
        return [part for part in urlparse(self.path).path.split("/") if part]

    def _campaign_id(self, parts: list[str]) -> str:
        if len(parts) < 3 or parts[0:2] != ["api", "campaigns"]:
            raise ValueError("campaign route is invalid")
        return parts[2]

    def do_OPTIONS(self):
        self._send(204, {})
    def do_GET(self):
        try:
            parts = self._parts()
            if parts == ["health"]:
                self._send(
                    200,
                    {
                        "status": "ok",
                        "schema_version": schema,
                        "database_path": str(DB_PATH),
                        "provider_auth": provider_state["authentication"],
                        "secret_env_present_after_bootstrap": provider_state[
                            "secret_env_present_after_bootstrap"
                        ],
                    },
                )
                return
            if parts == ["provider-status"]:
                self._send(
                    200,
                    {
                        "provider": "HIGGSFIELD",
                        "configured": provider_state["configured"],
                        "authentication": provider_state["authentication"],
                        "selected_model": "marketing-studio/image",
                        "secret_env_present_after_bootstrap": provider_state[
                            "secret_env_present_after_bootstrap"
                        ],
                    },
                )
                return
            if parts == ["api", "campaigns"]:
                self._send(200, {"campaigns": bridge.list_campaigns()})
                return
            campaign_id = self._campaign_id(parts)
            if len(parts) == 3:
                self._send(200, {"campaign": bridge.get_campaign(campaign_id)})
            elif parts[3:] == ["brand"]:
                self._send(200, {"brand": bridge.brand(campaign_id)})
            elif parts[3:] == ["director"]:
                self._send(200, {"plan": bridge.latest_director_plan(campaign_id)})
            elif parts[3:] == ["storyboard"]:
                self._send(200, bridge.storyboard(campaign_id) or {})
            elif parts[3:] == ["generation-request"]:
                self._send(
                    200,
                    {"generation_request": bridge.generation_request(campaign_id)},
                )
            elif parts[3:] == ["governance"]:
                self._send(200, {"governance": bridge.governance(campaign_id)})
            else:
                self._send(404, {"error": "not_found"})
        except KeyError:
            self._send(404, {"error": "not_found"})
        except (ValueError, PermissionError) as exc:
            self._send(400, {"error": str(exc)})
    def do_POST(self):
        try:
            parts = self._parts()
            body = self._body()
            if parts == ["api", "campaigns"]:
                campaign = bridge.create_campaign(
                    body.get("title", ""), body.get("objective", "")
                )
                self._send(200, {"campaign": campaign})
                return
            campaign_id = self._campaign_id(parts)
            action = parts[3:]
            if action == ["advance"]:
                self._send(
                    200,
                    {
                        "campaign": bridge.advance_stage(
                            campaign_id, body.get("stage", "")
                        )
                    },
                )
            elif action == ["director"]:
                self._send(
                    200, {"plan": bridge.generate_director(campaign_id)}
                )
            elif action == ["director", "approve"]:
                self._send(200, bridge.approve_director(campaign_id))
            elif action == ["asset-plan"]:
                self._send(200, bridge.asset_plan(campaign_id))
            elif action == ["generation-request"]:
                self._send(
                    200,
                    {
                        "generation_request": bridge.ensure_generation_request(
                            campaign_id
                        )
                    },
                )
            else:
                self._send(404, {"error": "not_found"})
        except KeyError:
            self._send(404, {"error": "not_found"})
        except (ValueError, PermissionError) as exc:
            self._send(400, {"error": str(exc)})

    def do_PATCH(self):
        try:
            parts = self._parts()
            campaign_id = self._campaign_id(parts)
            if len(parts) != 3:
                self._send(404, {"error": "not_found"})
                return
            campaign = bridge.update_campaign(campaign_id, self._body())
            self._send(200, {"campaign": campaign})
        except KeyError:
            self._send(404, {"error": "not_found"})
        except (ValueError, PermissionError) as exc:
            self._send(400, {"error": str(exc)})

    def log_message(self, format, *args):
        return


def main() -> None:
    server = HTTPServer((HOST, PORT), Handler)
    try:
        server.serve_forever()
    finally:
        store.close()
        server.server_close()


if __name__ == "__main__":
    main()
