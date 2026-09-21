"""Accessory profile payloads and required-reference projections."""
from typing import Any
from pathlib import Path
from .profile_payload_ports import PayloadIdentity, PayloadProfiles, PayloadCatalog

class AccessoryProfilePayloads:
    def __init__(self, identity: PayloadIdentity, profiles: PayloadProfiles, catalog: PayloadCatalog) -> None:
        self._identity = identity
        self._profiles = profiles
        self._catalog = catalog

    def accessory_profile_prompt_payload(self, item: dict[str, Any]) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "instruction": "Return only deterministic JSON for an accessory profile with the required keys.",
            "required_keys": list(self._profiles.fallback()(item).keys()),
            "accessory": {
                "accessory_id": self._identity.uid()(item),
                "name": item.get("name"),
                "material_type": self._identity.material()(item),
                "training_role": item.get("training_role"),
                "physical_size": item.get("physical_size"),
                "source_file_names": [Path(str(path)).name for path in item.get("source_files", [])],
                "normalized_asset_kinds": [asset.get("kind") for asset in item.get("normalized_assets", []) if isinstance(asset, dict)],
                "expected_count": int(item.get("expected_count") or 1),
            },
        }
        reference = self._profiles.reference()(item.get("size_reference")) if self._identity.material()(item) == "object" else None
        if reference:
            payload["size_reference"] = {
                "id": reference.get("id"),
                "label": reference.get("label"),
                "kind": reference.get("kind"),
                "long_mm": reference.get("long_mm"),
                "short_mm": reference.get("short_mm"),
                "note": reference.get("note"),
                "usage": (
                    "至少有一张参考图里把该配件和这个参照物放在一起拍摄。"
                    "请用参照物的已知真实尺寸作为比例尺，测量并推断配件的真实 length_mm/width_mm/height_mm。"
                ),
            }
        return payload

    def required_accessory_profile_payload(self, item: dict[str, Any], expected_count: int, profile: dict[str, Any] | None = None) -> dict[str, Any]:
        profile = self._profiles.normalize()(profile or item.get("ai_profile") or {}, item)
        try:
            expected_count = max(1, int(expected_count or profile.get("expected_count") or 1))
        except (TypeError, ValueError):
            try:
                expected_count = max(1, int(profile.get("expected_count") or 1))
            except (TypeError, ValueError):
                expected_count = 1
        profile = {**profile, "expected_count": expected_count}
        return {
            "accessory_id": profile["accessory_id"],
            "name": profile["name"],
            "label": profile["name"],
            "material_type": profile["material_type"],
            "expected_count": expected_count,
            "profile": {
                "description": profile["description"],
                "tags": profile["tags"],
                "visual_signature": profile["visual_signature"],
                "distinguishing_text": profile["distinguishing_text"],
                "negative_cues": profile["negative_cues"],
                "reference_images": profile.get("reference_images") or [],
                "provider_cache": profile.get("provider_cache") or {},
            },
        }

    def resolve_required_accessory_refs(self, required_refs: list[Any]) -> list[dict[str, Any]]:
        config = self._catalog.config()()
        by_id = {self._identity.uid()(item): item for item in config.get("accessories", []) if isinstance(item, dict)}
        resolved: list[dict[str, Any]] = []
        for raw in required_refs:
            if not isinstance(raw, dict):
                continue
            item_id = str(raw.get("accessory_id") or raw.get("id") or "").strip()
            if not item_id:
                continue
            try:
                expected_count = max(1, int(raw.get("expected_count") or 1))
            except (TypeError, ValueError):
                expected_count = 1
            item = by_id.get(item_id)
            if not item:
                item = {
                    "id": item_id,
                    "name": self._catalog.text()(raw.get("name") or item_id, 120),
                    "material_type": raw.get("material_type") or "object",
                    "source_files": [],
                    "normalized_assets": [],
                }
            profile = item.get("ai_profile") if isinstance(item.get("ai_profile"), dict) else self._profiles.fallback()(item)
            resolved.append(self._profiles.required()(item, expected_count, profile))
        return resolved
