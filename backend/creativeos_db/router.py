from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .generation import DeterministicMockGenerationProvider, GenerationProvider

CAPABILITIES = {"image", "video", "presenter", "voice"}

@dataclass(frozen=True)
class ProviderRegistration:
    name: str
    capabilities: frozenset[str]
    provider: GenerationProvider | None
    enabled: bool
    generative: bool = True


class ProviderRouter:
    def __init__(self) -> None:
        self._providers: dict[str, ProviderRegistration] = {}
    def register(self, registration: ProviderRegistration) -> None:
        if not registration.capabilities or not registration.capabilities <= CAPABILITIES:
            raise ValueError("invalid provider capabilities")
        self._providers[registration.name.upper()] = registration

    def resolve(self, capability: str, preferred: str | None = None,
                immutable_ui: bool = False) -> GenerationProvider:
        capability = capability.lower().strip()
        if capability not in CAPABILITIES:
            raise ValueError("unsupported generation capability")
        if immutable_ui and capability in {"image", "video"}:
            raise ValueError("immutable UI cannot enter generative image/video routing")
        key = (preferred or "AUTO").upper()
        candidates = list(self._providers.values()) if key in {"", "AUTO"} else [self._get(key)]
        for item in candidates:
            if capability in item.capabilities and item.enabled and item.provider is not None:
                return item.provider
        if key not in {"", "AUTO"}:
            item = self._get(key)
            if not item.enabled:
                raise RuntimeError(f"provider {item.name} is not configured/enabled")
        raise RuntimeError(f"no enabled provider for capability {capability}")
    def _get(self, key: str) -> ProviderRegistration:
        try:
            return self._providers[key]
        except KeyError as exc:
            raise RuntimeError(f"provider {key} is not registered") from exc


def default_router() -> ProviderRouter:
    router = ProviderRouter()
    router.register(ProviderRegistration(
        "MOCK", frozenset(CAPABILITIES), DeterministicMockGenerationProvider(), True, True
    ))
    for name, caps in {
        "LIVE_IMAGE": {"image"},
        "LIVE_VIDEO": {"video"},
        "LIVE_PRESENTER": {"presenter"},
        "LIVE_VOICE": {"voice"},
    }.items():
        router.register(ProviderRegistration(name, frozenset(caps), None, False, True))
    return router
