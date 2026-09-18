"""Profile-cache hit/create flow with explicit persistence and provider capabilities."""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol
from .presence_payload import BoundedText

Record = dict[str, Any]


class CachedContentProvider(Protocol):
    def create_cached_content(self, system_prompt: str, user_content: list[Record], *,
                              display_name: str, ttl_seconds: int) -> Record: ...


@dataclass(frozen=True)
class CacheRecords:
    load: Callable[[], Record]
    save: Callable[[Record], None]


@dataclass(frozen=True)
class CacheEvidence:
    key: Callable[[list[Record], Record], tuple[str, list[Record]]]
    references: Callable[[list[Record]], list[Record]]
    context: Callable[[list[Record], list[Record]], list[Record]]


@dataclass(frozen=True)
class CacheProviders:
    factory: Callable[[Record], CachedContentProvider]
    kind: Callable[[], type]
    error: Callable[[], type[Exception]]


@dataclass(frozen=True)
class CacheTiming:
    now: Callable[[], float]
    ttl: Callable[[], int]


class ProfileCacheFlow:
    def __init__(self, records: CacheRecords, evidence: CacheEvidence, providers: CacheProviders,
                 timing: CacheTiming, prompt: Callable[[], str], text: Callable[[], BoundedText]):
        self.records, self.evidence, self.providers = records, evidence, providers
        self.timing, self.prompt, self.text = timing, prompt, text

    def ensure_required_profile_cache(self, required_accessories: list[dict[str, Any]], settings: dict[str, Any]) -> dict[str, Any]:
        if settings.get("provider") != "gemini" or not settings.get("configured"):
            return {"enabled": False, "status": "unsupported_provider", "name": "", "reference_images": 0, "provider_call_count": 0}
        cache_key, _ = self.evidence.key(required_accessories, settings)
        cache = self.records.load()
        entries = cache.setdefault("entries", {})
        now = int(self.timing.now())
        existing = entries.get(cache_key) if isinstance(entries.get(cache_key), dict) else None
        if existing and existing.get("name") and int(existing.get("expires_at") or 0) > now + 60:
            return {
                "enabled": True,
                "status": "hit",
                "name": existing["name"],
                "reference_images": int(existing.get("reference_images") or 0),
                "cache_key": cache_key[:12],
                "provider_call_count": 0,
            }
        references = self.evidence.references(required_accessories)
        if not references:
            return {"enabled": False, "status": "no_reference_images", "name": "", "reference_images": 0, "provider_call_count": 0}
        try:
            provider = self.providers.factory(settings)
            if not isinstance(provider, self.providers.kind()):
                raise self.providers.error()("Provider does not support Gemini cachedContent")
            created = provider.create_cached_content(
                self.prompt(),
                self.evidence.context(required_accessories, references),
                display_name=f"inspection-profile-{cache_key[:12]}",
                ttl_seconds=self.timing.ttl(),
            )
            entries[cache_key] = {
                "name": created["name"],
                "provider": settings.get("provider"),
                "model": settings.get("model"),
                "created_at": now,
                "expires_at": now + self.timing.ttl(),
                "reference_images": len(references),
                "latency_ms": created.get("latency_ms", 0),
                "usage_metadata": created.get("usage_metadata") or {},
            }
            self.records.save(cache)
            return {
                "enabled": True,
                "status": "created",
                "name": created["name"],
                "reference_images": len(references),
                "latency_ms": created.get("latency_ms", 0),
                "usage_metadata": created.get("usage_metadata") or {},
                "cache_key": cache_key[:12],
                "provider_call_count": 1,
            }
        except Exception as exc:
            return {
                "enabled": False,
                "status": "create_failed",
                "name": "",
                "reference_images": len(references),
                "error": self.text()(str(exc), 220),
                "cache_key": cache_key[:12],
                "provider_call_count": 1,
            }
