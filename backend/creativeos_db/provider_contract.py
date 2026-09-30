from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class ProviderError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: str,
        retryable: bool = False,
        submit_uncertain: bool = False,
        status_code: int | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.retryable = bool(retryable)
        self.submit_uncertain = bool(submit_uncertain)
        self.status_code = status_code


@dataclass(frozen=True)
class ProviderSubmission:
    request_id: str
    status: str
    status_url: str
    cancel_url: str | None
    raw: dict[str, Any]


@dataclass(frozen=True)
class ProviderResult:
    request_id: str
    status: str
    output_url: str
    raw: dict[str, Any]



class AsyncGenerationProvider(Protocol):
    """Submit/poll/download contract; provider SDKs belong only in adapters."""

    def submit(self, model_id: str, input_payload: dict[str, Any], *,
               correlation_id: str, **kwargs: Any) -> ProviderSubmission: ...

    def poll(self, submission: ProviderSubmission, **kwargs: Any) -> ProviderResult: ...

    def download(self, url: str, **kwargs: Any) -> bytes: ...
