"""Accessory profile construction and normalization."""
from typing import Any
from pathlib import Path
from .profile_projection_ports import ProfileIdentity, ProfileText, ProfileDimensions, ProfileReferences

class AccessoryProfileProjection:
    def __init__(self, identity: ProfileIdentity, text: ProfileText, dimensions: ProfileDimensions, references: ProfileReferences) -> None:
        self._identity = identity
        self._text = text
        self._dimensions = dimensions
        self._references = references

    def fallback_accessory_ai_profile(self, item: dict[str, Any], reference_images: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        accessory_id = self._identity.uid()(item)
        name = self._text.bounded()(item.get("name") or item.get("label") or accessory_id, 120)
        english_name = self._text.preferred()(item)
        material_type = self._identity.material()(item)
        source_names = sorted(
            {
                self._text.bounded()(Path(str(path)).stem.replace("_", " "), 60)
                for path in [*(item.get("source_files") or []), *(item.get("original_source_files") or [])]
                if str(path).strip()
            }
        )
        tags = [material_type, str(item.get("training_role") or "detect_and_classify")]
        physical_size = item.get("physical_size") if isinstance(item.get("physical_size"), dict) else {}
        if physical_size.get("kind"):
            tags.append(str(physical_size["kind"]))
        if material_type == "object":
            tags.append(self._identity.alpha()(item))
        tags.extend(source_names[:4])
        tags = self._text.strings()(tags, max_items=12)
        if reference_images is None:
            reference_images = self._references.contexts()(item)
        image_count = len(reference_images)
        signature_parts = [
            f"name={name}",
            f"material={material_type}",
            self._text.size()(physical_size),
            f"visual_evidence_images={image_count}",
        ]
        if material_type == "object":
            signature_parts.append(f"alpha_policy={self._identity.alpha()(item)}")
        distinguishing_text = self._text.strings()([name, *source_names], max_items=8)
        negative_cues = [
            "Do not count a different accessory with only similar size.",
            "Do not infer presence from previous images or configured task state.",
        ]
        if material_type == "text":
            negative_cues.append("If visible printed text does not match this profile, mark missing.")
        else:
            negative_cues.append("If the object shape/material does not match this profile, mark missing.")
        dimensions_mm = self._dimensions.physical()(physical_size)
        top_view_aspect_ratio = self._dimensions.ratio()(dimensions_mm)
        return {
            "accessory_id": accessory_id,
            "name": name,
            "english_name": english_name,
            "material_type": material_type,
            "description": self._text.bounded()(item.get("description") or f"{name} required accessory.", 240),
            "tags": tags,
            "visual_signature": "; ".join(signature_parts),
            "distinguishing_text": distinguishing_text,
            "negative_cues": negative_cues,
            "dimensions_mm": dimensions_mm,
            "top_view_aspect_ratio": top_view_aspect_ratio,
            "reference_images": reference_images,
            "provider_cache": {},
            "expected_count": max(1, int(item.get("expected_count") or 1)),
        }

    def normalize_accessory_ai_profile(self, raw: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
        raw_dict = raw if isinstance(raw, dict) else {}
        raw_reference_images = raw_dict.get("reference_images") if isinstance(raw_dict.get("reference_images"), list) else None
        fallback = self._references.fallback()(item, reference_images=raw_reference_images)
        expected_count = raw.get("expected_count", fallback["expected_count"]) if isinstance(raw, dict) else fallback["expected_count"]
        try:
            expected_count_int = max(1, int(expected_count))
        except (TypeError, ValueError):
            expected_count_int = fallback["expected_count"]
        reference_images = raw.get("reference_images") if isinstance(raw, dict) else None
        if not isinstance(reference_images, list):
            reference_images = fallback.get("reference_images", [])
        safe_reference_images = [
            {
                "accessory_id": self._text.bounded()(ref.get("accessory_id") or self._identity.uid()(item), 120),
                "source_path": str(ref.get("source_path") or ""),
                "sha256": self._text.bounded()(ref.get("sha256") or "", 80),
                "mime_type": self._text.bounded()(ref.get("mime_type") or "image/jpeg", 40),
                "width": int(ref.get("width") or 0) if isinstance(ref, dict) else 0,
                "height": int(ref.get("height") or 0) if isinstance(ref, dict) else 0,
                "ordinal": int(ref.get("ordinal") or idx + 1) if isinstance(ref, dict) else idx + 1,
            }
            for idx, ref in enumerate(reference_images)
            if isinstance(ref, dict) and str(ref.get("source_path") or "").strip()
        ][:self._references.limit()]
        provider_cache = raw.get("provider_cache") if isinstance(raw, dict) and isinstance(raw.get("provider_cache"), dict) else {}
        dimensions_mm = self._dimensions.normalize()(
            raw.get("dimensions_mm") if isinstance(raw, dict) else None,
            fallback.get("dimensions_mm") if isinstance(fallback.get("dimensions_mm"), dict) else {},
        )
        top_view_aspect_ratio = (
            self._dimensions.number()(raw.get("top_view_aspect_ratio")) if isinstance(raw, dict) else None
        ) or self._dimensions.ratio()(dimensions_mm)
        return {
            "accessory_id": self._identity.uid()(item),
            "name": self._text.bounded()(raw.get("name") if isinstance(raw, dict) else fallback["name"], 120) or fallback["name"],
            "english_name": self._text.compact()(raw.get("english_name") if isinstance(raw, dict) else "") or fallback["english_name"],
            "material_type": self._identity.material()(item),
            "description": self._text.bounded()(raw.get("description") if isinstance(raw, dict) else fallback["description"], 240) or fallback["description"],
            "tags": self._text.strings()(raw.get("tags") if isinstance(raw, dict) else None, fallback["tags"], max_items=12),
            "visual_signature": self._text.bounded()(raw.get("visual_signature") if isinstance(raw, dict) else fallback["visual_signature"], 420) or fallback["visual_signature"],
            "distinguishing_text": self._text.strings()(
                raw.get("distinguishing_text") if isinstance(raw, dict) else None,
                fallback["distinguishing_text"],
                max_items=12,
            ),
            "negative_cues": self._text.strings()(raw.get("negative_cues") if isinstance(raw, dict) else None, fallback["negative_cues"], max_items=12),
            "dimensions_mm": dimensions_mm,
            "top_view_aspect_ratio": round(float(top_view_aspect_ratio), 3),
            "reference_images": safe_reference_images,
            "provider_cache": provider_cache,
            "expected_count": expected_count_int,
        }
