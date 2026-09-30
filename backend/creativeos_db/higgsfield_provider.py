from __future__ import annotations

import json
import os
import socket
import time
import urllib.error

import httpx
from typing import Any, Callable


TERMINAL_STATUSES = {"completed", "failed", "nsfw", "canceled"}
NON_TERMINAL_STATUSES = {"queued", "in_progress"}
RETRYABLE_SUBMIT_HTTP = {423, 500, 503}
RETRYABLE_POLL_HTTP = {500, 502, 503, 504}


# Compatibility names for existing adapter clients.
from .provider_contract import (
    ProviderError as HiggsfieldProviderError,
    ProviderSubmission as HiggsfieldSubmission,
    ProviderResult as HiggsfieldTerminalResult,
)


Transport = Callable[
    [str, str, dict[str, str], bytes | None, float],
    tuple[int, dict[str, str], bytes],
]


class HiggsfieldProvider:
    name = "HIGGSFIELD"

    def __init__(
        self,
        credentials: str,
        *,
        base_url: str = "https://api.higgsfield.ai",
        transport: Transport | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
        monotonic_fn: Callable[[], float] = time.monotonic,
    ):
        if not str(credentials or "").strip():
            raise ValueError("Higgsfield server credentials are required")
        self._credentials = str(credentials).strip()
        self.base_url = base_url.rstrip("/")
        self._transport = transport
        self._sleep = sleep_fn
        self._monotonic = monotonic_fn

    def __repr__(self) -> str:
        return f"HiggsfieldProvider(configured={bool(self._credentials)!r})"

    @classmethod
    def from_env(cls, **kwargs: Any) -> "HiggsfieldProvider":
        credentials = os.environ.get("HF_CREDENTIALS") or os.environ.get("HF_KEY")
        if not credentials:
            raise RuntimeError(
                "Higgsfield credentials are not configured in server environment "
                "(HF_CREDENTIALS or HF_KEY)"
            )
        return cls(credentials, **kwargs)

    @staticmethod
    def credentials_configured() -> bool:
        return bool(os.environ.get("HF_CREDENTIALS") or os.environ.get("HF_KEY"))

    def _headers(self, correlation_id: str | None = None) -> dict[str, str]:
        headers = {
            "Authorization": f"Key {self._credentials}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "CreativeOS/1.0",
        }
        if correlation_id:
            headers["X-Correlation-ID"] = correlation_id
        return headers

    def _default_transport(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
        timeout: float,
    ) -> tuple[int, dict[str, str], bytes]:
        try:
            with httpx.Client(timeout=timeout, follow_redirects=True) as client:
                response = client.request(
                    method,
                    url,
                    headers=headers,
                    content=body,
                    timeout=timeout,
                )
            return int(response.status_code), dict(response.headers), response.content
        except httpx.TimeoutException as exc:
            raise TimeoutError(str(exc)) from exc
        except httpx.RequestError as exc:
            raise OSError(str(exc)) from exc

    def _call(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
        timeout: float,
    ) -> tuple[int, dict[str, str], bytes]:
        transport = self._transport or self._default_transport
        return transport(method, url, headers, body, timeout)

    @staticmethod
    def _json(raw: bytes) -> dict[str, Any]:
        if not raw:
            return {}
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise HiggsfieldProviderError(
                "Higgsfield returned invalid JSON",
                code="INVALID_PROVIDER_RESPONSE",
            ) from exc
        if not isinstance(value, dict):
            raise HiggsfieldProviderError(
                "Higgsfield response must be a JSON object",
                code="INVALID_PROVIDER_RESPONSE",
            )
        return value

    @staticmethod
    def _error_message(payload: dict[str, Any], fallback: str) -> str:
        for key in ("message", "detail", "error"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
            if isinstance(value, dict):
                nested = value.get("message") or value.get("detail")
                if isinstance(nested, str) and nested.strip():
                    return nested.strip()
        return fallback

    def submit(
        self,
        model_id: str,
        input_payload: dict[str, Any],
        *,
        correlation_id: str,
        timeout_seconds: float = 30.0,
        max_http_attempts: int = 2,
    ) -> HiggsfieldSubmission:
        if not model_id or model_id.startswith("/") or ".." in model_id:
            raise ValueError("invalid Higgsfield model id")
        if max_http_attempts < 1 or max_http_attempts > 3:
            raise ValueError("max_http_attempts must be between 1 and 3")
        body = json.dumps(input_payload, sort_keys=True).encode("utf-8")
        url = f"{self.base_url}/{model_id}"
        for attempt in range(1, max_http_attempts + 1):
            try:
                status, _, raw = self._call(
                    "POST", url, self._headers(correlation_id), body, timeout_seconds
                )
            except (TimeoutError, socket.timeout, urllib.error.URLError, OSError) as exc:
                raise HiggsfieldProviderError(
                    "generation submit outcome is uncertain; do not auto-resubmit",
                    code="SUBMIT_UNCERTAIN",
                    retryable=False,
                    submit_uncertain=True,
                ) from exc
            payload = self._json(raw)
            if 200 <= status < 300:
                request_id = str(payload.get("request_id") or "").strip()
                status_url = str(payload.get("status_url") or "").strip()
                if not request_id or not status_url:
                    raise HiggsfieldProviderError(
                        "accepted submit is missing request_id or status_url",
                        code="INVALID_PROVIDER_RESPONSE",
                    )
                return HiggsfieldSubmission(
                    request_id=request_id,
                    status=str(payload.get("status") or "queued"),
                    status_url=status_url,
                    cancel_url=(
                        str(payload.get("cancel_url")).strip()
                        if payload.get("cancel_url")
                        else None
                    ),
                    raw=payload,
                )
            if status in RETRYABLE_SUBMIT_HTTP and attempt < max_http_attempts:
                self._sleep(min(2.0 ** (attempt - 1), 4.0))
                continue
            retryable = status in RETRYABLE_SUBMIT_HTTP
            raise HiggsfieldProviderError(
                self._error_message(payload, f"Higgsfield submit failed with HTTP {status}"),
                code=f"HTTP_{status}",
                retryable=retryable,
                status_code=status,
            )
        raise AssertionError("unreachable submit loop")

    def poll(
        self,
        submission: HiggsfieldSubmission,
        *,
        timeout_seconds: float = 600.0,
        max_polls: int = 120,
        on_status: Callable[[dict[str, Any]], None] | None = None,
    ) -> HiggsfieldTerminalResult:
        if timeout_seconds <= 0 or max_polls <= 0:
            raise ValueError("poll timeout and max_polls must be positive")
        started = self._monotonic()
        delay = 2.0
        polls = 0
        while polls < max_polls and self._monotonic() - started <= timeout_seconds:
            polls += 1
            try:
                status_code, _, raw = self._call(
                    "GET",
                    submission.status_url,
                    self._headers(),
                    None,
                    min(30.0, timeout_seconds),
                )
            except (TimeoutError, socket.timeout, urllib.error.URLError, OSError):
                self._sleep(delay)
                delay = min(10.0, delay * 1.5)
                continue
            if status_code in RETRYABLE_POLL_HTTP:
                self._sleep(delay)
                delay = min(10.0, delay * 1.5)
                continue
            payload = self._json(raw)
            if status_code == 401:
                raise HiggsfieldProviderError(
                    "Higgsfield status authentication failed",
                    code="HTTP_401",
                    status_code=401,
                )
            if status_code == 404:
                raise HiggsfieldProviderError(
                    "Higgsfield request no longer exists",
                    code="HTTP_404",
                    status_code=404,
                )
            if not 200 <= status_code < 300:
                raise HiggsfieldProviderError(
                    self._error_message(
                        payload, f"Higgsfield status failed with HTTP {status_code}"
                    ),
                    code=f"HTTP_{status_code}",
                    retryable=False,
                    status_code=status_code,
                )
            status = str(payload.get("status") or "").lower().strip()
            if on_status is not None:
                on_status(payload)
            if status == "completed":
                output_url = self._output_url(payload)
                return HiggsfieldTerminalResult(
                    request_id=submission.request_id,
                    status=status,
                    output_url=output_url,
                    raw=payload,
                )
            if status in {"failed", "nsfw", "canceled"}:
                raise HiggsfieldProviderError(
                    self._error_message(payload, f"Higgsfield request ended as {status}"),
                    code=f"TERMINAL_{status.upper()}",
                    retryable=False,
                )
            if status not in NON_TERMINAL_STATUSES:
                raise HiggsfieldProviderError(
                    f"unknown Higgsfield lifecycle status: {status or '<empty>'}",
                    code="UNKNOWN_PROVIDER_STATUS",
                )
            self._sleep(delay)
            delay = min(10.0, delay * 1.5)
        raise HiggsfieldProviderError(
            "Higgsfield polling deadline reached; resume the existing provider request",
            code="POLL_TIMEOUT",
            retryable=True,
        )

    @staticmethod
    def _output_url(payload: dict[str, Any]) -> str:
        video = payload.get("video")
        if isinstance(video, dict) and video.get("url"):
            return str(video["url"])
        images = payload.get("images")
        if isinstance(images, list) and images:
            first = images[0]
            if isinstance(first, dict) and first.get("url"):
                return str(first["url"])
        output = payload.get("output")
        if isinstance(output, dict) and output.get("url"):
            return str(output["url"])
        raise HiggsfieldProviderError(
            "completed Higgsfield request is missing an output URL",
            code="MISSING_PROVIDER_OUTPUT",
        )

    def download(self, url: str, *, timeout_seconds: float = 120.0) -> bytes:
        if not str(url).lower().startswith("https://"):
            raise HiggsfieldProviderError(
                "provider output URL must be HTTPS",
                code="UNSAFE_OUTPUT_URL",
            )
        try:
            status, _, raw = self._call(
                "GET", url, {"Accept": "*/*"}, None, timeout_seconds
            )
        except (TimeoutError, socket.timeout, urllib.error.URLError, OSError) as exc:
            raise HiggsfieldProviderError(
                "could not copy Higgsfield output into CreativeOS storage",
                code="OUTPUT_DOWNLOAD_FAILED",
                retryable=True,
            ) from exc
        if not 200 <= status < 300 or not raw:
            raise HiggsfieldProviderError(
                f"provider output download failed with HTTP {status}",
                code="OUTPUT_DOWNLOAD_FAILED",
                retryable=status in RETRYABLE_POLL_HTTP,
                status_code=status,
            )
        return raw
