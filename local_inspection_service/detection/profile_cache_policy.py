"""Deterministic profile-cache identity and cached appearance context."""
from collections.abc import Callable
from typing import Any
import hashlib
import json
from .presence_payload import StringList

Record = dict[str, Any]


class ProfileCachePolicy:
    def __init__(self, strings: Callable[[], StringList], version: Callable[[], int],
                 reference_mode: Callable[[], str], prompt: Callable[[], str],
                 task: Callable[[list[Record]], Record], sheet: Callable[[list[Record]], Record | None]):
        self.strings, self.version, self.reference_mode, self.prompt = strings, version, reference_mode, prompt
        self.task, self.sheet = task, sheet

    def required_accessory_cache_key(self, required_accessories: list[dict[str, Any]], settings: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
        cache_items: list[dict[str, Any]] = []
        for required in required_accessories:
            profile = required.get("profile") if isinstance(required.get("profile"), dict) else {}
            references = [
                {
                    "source_path": str(ref.get("source_path") or ""),
                    "sha256": str(ref.get("sha256") or ""),
                }
                for ref in profile.get("reference_images", [])
                if isinstance(ref, dict) and ref.get("source_path")
            ]
            cache_items.append(
                {
                    "accessory_id": str(required.get("accessory_id") or ""),
                    "expected_count": int(required.get("expected_count") or 1),
                    "visual_signature": profile.get("visual_signature") or "",
                    "distinguishing_text": self.strings()(profile.get("distinguishing_text"), max_items=12),
                    "references": references,
                }
            )
        payload = {
            "version": self.version(),
            "reference_mode": self.reference_mode(),
            "provider": settings.get("provider"),
            "model": settings.get("model"),
            "system": hashlib.sha256(self.prompt().encode("utf-8")).hexdigest()[:16],
            "required": sorted(cache_items, key=lambda item: item["accessory_id"]),
        }
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
        return digest, cache_items

    def cached_profile_context_content(self, required_accessories: list[dict[str, Any]], references: list[dict[str, Any]]) -> list[dict[str, Any]]:
        content: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": (
                    "REQUIRED_ACCESSORY_PROFILE_CONTEXT: reuse this context for later inspection images. "
                    "Reference images are examples of required accessories only; never count them as present in an inspection image.\n"
                    + json.dumps(self.task(required_accessories), ensure_ascii=False)
                ),
            }
        ]
        for ref in references:
            item_id = str(ref.get("accessory_id") or "")
            if not item_id or not ref.get("data_url"):
                continue
            if ref.get("mode") == self.reference_mode():
                content.append(
                    {
                        "type": "text",
                        "text": (
                            "CACHED_REFERENCE_SHEET: one image containing all required accessory reference tiles. "
                            "Use it only as appearance evidence and ID mapping. Never count objects in this sheet as present "
                            "in the inspection image. Sheet item mapping:\n"
                            + json.dumps(ref.get("sheet_items") or [], ensure_ascii=False)
                        ),
                    }
                )
            else:
                content.append(
                    {
                        "type": "text",
                        "text": f"CACHED_REFERENCE_IMAGE for accessory_id={item_id}. Use as profile appearance evidence only.",
                    }
                )
            content.append({"type": "image_url", "image_url": {"url": ref["data_url"], "detail": ref.get("detail", "low")}})
        return content

    def profile_reference_descriptors(self, required_accessories: list[dict[str, Any]]) -> list[dict[str, Any]]:
        sheet = self.sheet(required_accessories)
        return [sheet] if sheet else []
