"""Bound bodies before parsers and emit only allowlisted operational telemetry."""

import json
import logging
from collections.abc import Callable
from datetime import datetime, timezone

from starlette.responses import JSONResponse

logger = logging.getLogger("fleetpilot")
logger.setLevel(logging.INFO)
if not logger.handlers:
    logger.addHandler(logging.StreamHandler())
logger.propagate = False

# Optional exporter registered by deployment bootstrap. It receives no exception text,
# request payload, URL query, headers, token, filename or evidence content.
monitor: Callable[[dict], None] | None = None


def emit(event: str, **fields):
    safe = {
        key: value
        for key, value in fields.items()
        if key in {"request_id", "route", "method", "status_code", "duration_ms", "error_type"}
    }
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "level": "ERROR" if "failed" in event else "INFO",
        "event": event,
        **safe,
    }
    logger.info(json.dumps(record))
    if monitor and "failed" in event:
        try:
            monitor(record.copy())
        except Exception:
            logger.error('{"event":"monitor.failed"}')


class BodyLimitMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] in {"GET", "HEAD", "OPTIONS"}:
            return await self.app(scope, receive, send)
        upload = scope["path"].startswith(
            (
                "/api/v1/delivery-attempts/",
                "/api/v1/driver/sync/",
                "/api/v1/expenses/",
                "/api/v1/maintenance/work-orders/",
                "/api/v1/defects/",
            )
        ) and scope["path"].endswith("/evidence")
        limit = 5 * 1024 * 1024 if upload else 64 * 1024
        headers = dict(scope["headers"])
        try:
            length = int(headers.get(b"content-length", b"0"))
        except ValueError:
            length = -1
        if length < 0 or length > limit:
            return await self.reject(scope, receive, send)
        if upload:
            # Preserve Batch 5's authorization-before-streaming boundary. Its route
            # enforces MAX_FILE_BYTES while reading, including chunked requests.
            return await self.app(scope, receive, send)
        # Bounded buffering also enforces chunked bodies before expensive form/JSON parsing.
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > limit:
                return await self.reject(scope, receive, send)
            if not message.get("more_body", False):
                break
        sent = False

        async def replay():
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, replay, send)

    @staticmethod
    async def reject(scope, receive, send):
        response = JSONResponse(
            {
                "error": {
                    "code": "body_too_large",
                    "message": "Request body exceeds the permitted size.",
                    "request_id": scope.get("state", {}).get("request_id", ""),
                }
            },
            status_code=413,
        )
        await response(scope, receive, send)
