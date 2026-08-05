#!/usr/bin/env python3
"""Focused regression smoke for object overlap, material alpha, and pose scale."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import server  # noqa: E402


def polygon_overlap_area(a: list[list[int]], b: list[list[int]]) -> float:
    rect_a = cv2.minAreaRect(np.array(a, dtype=np.float32))
    rect_b = cv2.minAreaRect(np.array(b, dtype=np.float32))
    return server.rotated_rect_overlap_area(rect_a, rect_b)


def material_alpha_smoke() -> dict:
    asset = np.full((80, 80, 3), 42, dtype=np.uint8)
    mask = np.zeros((80, 80), dtype=np.uint8)
    cv2.circle(mask, (40, 40), 28, 210, -1)
    solid, solid_stats = server.material_aware_object_alpha(asset, mask, {"material_alpha_policy": "solid"})
    glass, glass_stats = server.material_aware_object_alpha(asset, mask, {"material_alpha_policy": "transparent"})
    return {
        "solid_policy": solid_stats.get("object_alpha_material_policy"),
        "solid_mean_alpha": round(float(solid[mask > 20].mean()), 3),
        "solid_opaque_fraction": round(float((solid[mask > 20] >= 240).mean()), 3),
        "glass_policy": glass_stats.get("object_alpha_material_policy"),
        "glass_transparent_alpha_applied": bool(glass_stats.get("transparent_alpha_applied")),
        "glass_center_alpha": int(glass[40, 40]),
    }


def object_collision_smoke() -> dict:
    rng = np.random.default_rng(20260527)
    placed: list[dict] = []
    max_overlap = 0.0
    placements = []
    for idx in range(5):
        center, meta = server.choose_object_center_inside_background(rng, (240, 140), 0.0, placed)
        rect = server.rotated_rect_tuple(center, (240, 140), 0.0)
        for prior in placed:
            max_overlap = max(max_overlap, server.rotated_rect_overlap_area(rect, prior["rect"]))
        placed.append({"rect": rect})
        placements.append({"index": idx, "center": center, **meta})
    return {"max_object_pair_overlap_px": round(max_overlap, 3), "placements": placements}


def document_overlap_smoke() -> dict:
    cfg = server.load_config()
    docs = [dict(item) for item in cfg.get("accessories", []) if server.accessory_material_type(item) == "text"][:2]
    if len(docs) < 2:
        raise SystemExit("Need at least two document accessories for document overlap smoke.")
    for idx, item in enumerate(docs):
        item.setdefault("id", f"smoke_doc_{idx}")
        item.setdefault("name", f"Smoke Document {idx + 1}")
    original_random_center = server.random_center_inside_background

    def fixed_center(*args, **kwargs):
        return (640, 450)

    try:
        server.random_center_inside_background = fixed_center
        output = server.OUTPUT_DIR / "training_previews" / "smoke_document_overlap.png"
        output.parent.mkdir(parents=True, exist_ok=True)
        rendered = server.draw_training_preview(docs, output, seed=17)
    finally:
        server.random_center_inside_background = original_random_center

    labels = rendered.get("labels", [])
    overlap = polygon_overlap_area(labels[0]["placement_polygon_xy"], labels[1]["placement_polygon_xy"])
    occlusion_fractions = [float(label.get("occlusion_fraction") or 0.0) for label in labels]
    return {
        "document_count": len(labels),
        "document_centers": [label.get("center_xy") for label in labels],
        "document_overlap_area_px": round(float(overlap), 3),
        "document_max_occlusion_fraction": round(max(occlusion_fractions or [0.0]), 4),
        "documents_bypass_object_exclusion": all(label.get("material_type") == "text" for label in labels),
    }


def headphone_scale_smoke() -> dict:
    cfg = server.load_config()
    synthetic_tmp: tempfile.TemporaryDirectory[str] | None = None
    headphone = next(
        (
            item
            for item in cfg.get("accessories", [])
            if item.get("id") == "acc_62f963cd27" or "耳机" in str(item.get("name", "")) or "headphone" in str(item.get("name", "")).lower()
        ),
        None,
    )
    if headphone is None:
        synthetic_tmp = tempfile.TemporaryDirectory(prefix="vantaline_headphone_scale_")
        sprite_root = Path(synthetic_tmp.name)
        upright_path = sprite_root / "upright.png"
        lying_path = sprite_root / "lying.png"
        cv2.imwrite(str(upright_path), np.full((181, 72, 4), 255, dtype=np.uint8))
        cv2.imwrite(str(lying_path), np.full((72, 181, 4), 255, dtype=np.uint8))
        headphone = {
            "id": "synthetic_headphone_scale_fixture",
            "name": "Synthetic headphone scale fixture",
            "material_type": "object",
            "physical_size": {"kind": "object", "length_mm": 100.0, "width_mm": 42.0, "height_mm": 32.0},
            "normalized_assets": [
                {
                    "kind": "clean_object_sprite",
                    "path": str(upright_path),
                    "pose_family": "upright",
                    "source_pose_family": "upright",
                    "source_object_size_px": [72, 181],
                },
                {
                    "kind": "clean_object_sprite",
                    "path": str(lying_path),
                    "pose_family": "lying",
                    "source_pose_family": "lying",
                    "source_object_size_px": [181, 72],
                },
            ],
        }
    by_family: dict[str, list[list[int]]] = {"upright": [], "lying": []}
    bases: dict[str, set[str]] = {"upright": set(), "lying": set()}
    for asset in server.clean_sprite_assets(headphone):
        family = server.canonical_pose_family_name(asset.get("source_pose_family") or asset.get("pose_family"))
        if family in by_family:
            footprint = asset.get("render_footprint_px")
            if isinstance(footprint, list) and len(footprint) >= 2:
                by_family[family].append([int(footprint[0]), int(footprint[1])])
            bases[family].add(str(asset.get("render_scale_basis")))
    major = {
        family: sorted({max(size) for size in sizes})
        for family, sizes in by_family.items()
    }
    result = {
        "headphone_id": headphone.get("id"),
        "fixture_source": "synthetic" if synthetic_tmp is not None else "runtime_config",
        "upright_footprints": sorted({tuple(size) for size in by_family["upright"]}),
        "lying_footprints": sorted({tuple(size) for size in by_family["lying"]}),
        "upright_major_axes": major["upright"],
        "lying_major_axes": major["lying"],
        "major_axis_match": major["upright"] == major["lying"],
        "upright_basis": sorted(bases["upright"]),
        "lying_basis": sorted(bases["lying"]),
    }
    if synthetic_tmp is not None:
        synthetic_tmp.cleanup()
    return result


def main() -> int:
    result = {
        "alpha": material_alpha_smoke(),
        "object_collision": object_collision_smoke(),
        "document_overlap": document_overlap_smoke(),
        "headphone_scale": headphone_scale_smoke(),
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if result["object_collision"]["max_object_pair_overlap_px"] != 0:
        return 1
    if result["document_overlap"]["document_count"] < 2 or not result["document_overlap"]["documents_bypass_object_exclusion"]:
        return 1
    if (
        result["document_overlap"]["document_overlap_area_px"] <= 0
        and result["document_overlap"]["document_max_occlusion_fraction"] <= 0
    ):
        return 1
    if not result["headphone_scale"]["major_axis_match"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
