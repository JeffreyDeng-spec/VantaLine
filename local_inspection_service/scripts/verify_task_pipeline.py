#!/usr/bin/env python3
"""Focused verification for the task-centric training/inference pipeline."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import cv2  # noqa: E402
import numpy as np  # noqa: E402
from fastapi import HTTPException  # noqa: E402

import server  # noqa: E402


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def fake_accessories(count: int = 4) -> list[dict]:
    items = []
    for idx in range(count):
        items.append(
            {
                "id": f"acc_{idx}",
                "class_id": idx,
                "name": f"part_{idx}",
                "material_type": "text" if idx == count - 1 else "object",
                "physical_size": server.physical_size_payload("text" if idx == count - 1 else "object"),
            }
        )
    return items


def verify_sample_plan_distribution() -> None:
    selected = fake_accessories(4)
    plan = server.build_training_sample_plan(selected, 200, 12345, "auto")
    split_counts = Counter(item["split"] for item in plan)
    true_count = sum(1 for item in plan if item["is_true"])
    false_count = len(plan) - true_count
    extra_samples = [item for item in plan if item.get("extra_accessory_ids")]
    assert_true(len(plan) == 200, "sample plan should keep requested sample count")
    assert_true(split_counts == {"train": 160, "val": 20, "test": 20}, f"unexpected split counts: {split_counts}")
    assert_true(true_count == 100 and false_count == 100, f"unexpected true/false counts: {true_count}/{false_count}")
    assert_true(extra_samples, "false sample plan should include extra-object negatives")
    for item in extra_samples:
        assert_true(item["false_reason"] == "extra_one_accessory", "extra negatives must be marked as exact-count failures")
        for extra_id in item["extra_accessory_ids"]:
            assert_true(item["present_accessory_ids"].count(extra_id) == 2, "extra object must be present and therefore labeled")


def verify_exact_count_rule() -> None:
    config = {
        "confidence_threshold": 0.5,
        "required_classes": [0],
        "min_counts": {"0": 1},
        "ocr": {"enabled": False},
    }
    spec = {"model_class_names": {0: "part"}, "model_to_business_class": {0: 0}}
    one = [{"class_id": 0, "confidence": 0.9, "polygon": [[0, 0], [1, 0], [1, 1]]}]
    two = one + [{"class_id": 0, "confidence": 0.91, "polygon": [[2, 2], [3, 2], [3, 3]]}]
    assert_true(server.apply_rule(one, config, spec)["passed"], "exact required count should pass")
    result = server.apply_rule(two, config, spec)
    assert_true(not result["passed"], "extra detected object must fail exact-count rule")
    assert_true(result["extra"] and result["extra"][0]["found"] == 2, "extra object should be reported explicitly")


def verify_manual_type_exact_count() -> None:
    config = {
        "confidence_threshold": 0.5,
        "required_classes": [1],
        "min_counts": {"1": 2},
        "ocr": {"enabled": True, "require_manual_types": True, "manual_types": ["warranty_service"]},
    }
    spec = {"model_class_names": {1: "manual"}, "model_to_business_class": {1: 1}}
    detections = [
        {"class_id": 1, "confidence": 0.9, "manual_type": "warranty_service", "polygon": [[0, 0], [1, 0], [1, 1]]},
        {"class_id": 1, "confidence": 0.9, "manual_type": "warranty_service", "polygon": [[2, 2], [3, 2], [3, 3]]},
    ]
    result = server.apply_rule(detections, config, spec)
    assert_true(not result["passed"], "duplicate OCR manual type must fail exact-count rule")
    assert_true(result["manual_type_missing"][0]["issue"] == "extra", "duplicate OCR manual type should be marked extra")


def verify_one_task_model_selection() -> None:
    original = server.list_trained_model_specs
    specs = [
        {"id": "trained_task_a__yolo", "task_id": "task_a", "path": "/tmp/a.pt", "uses_ocr": False},
        {"id": "trained_task_b__yolo_ocr", "task_id": "task_b", "path": "/tmp/b.pt", "uses_ocr": True},
    ]
    try:
        server.list_trained_model_specs = lambda: specs
        selected = server.selected_model_spec("trained_task_b__yolo_ocr", {})
        assert_true(selected["id"] == "trained_task_b__yolo_ocr", "inference must select exactly the requested task model")
        try:
            server.selected_model_spec("trained_task_a__yolo+trained_task_b__yolo_ocr", {})
        except HTTPException:
            pass
        else:
            raise AssertionError("combined multi-model id must not be accepted")
    finally:
        server.list_trained_model_specs = original


def verify_yolo_vs_yolo_ocr_behavior() -> None:
    image = np.zeros((40, 40, 3), dtype=np.uint8)
    detections = [
        {"class_id": 0, "model_class_id": 0, "confidence": 0.9, "polygon": [[1, 1], [10, 1], [10, 10], [1, 10]]},
        {"class_id": 1, "model_class_id": 1, "confidence": 0.9, "polygon": [[12, 12], [22, 12], [22, 22], [12, 22]]},
    ]
    calls: list[int] = []
    original = server.score_ocr_variants
    try:
        server.score_ocr_variants = lambda crops, rotations: calls.extend(range(len(crops))) or [
            {
                "rotation": 0,
                "texts": ["warranty service"],
                "mean_text_score": 0.9,
                "classification": {"manual_type": "warranty_service", "manual_label": "Warranty Service Manual", "confidence": 1.0},
            }
            for _ in crops
        ]
        server.attach_ocr_results(image, [dict(item) for item in detections], {"ocr": {"enabled": True}}, {"is_specialized": True, "ocr_model_class_ids": []})
        assert_true(not calls, "YOLO-only task should not invoke OCR")
        server.attach_ocr_results(image, [dict(item) for item in detections], {"ocr": {"enabled": True}}, {"is_specialized": True, "ocr_model_class_ids": [1]})
        assert_true(len(calls) == 1, "YOLO+OCR task should invoke OCR only for configured text classes")
    finally:
        server.score_ocr_variants = original


def verify_background_metadata() -> None:
    rng = np.random.default_rng(42)
    _, meta = server.render_training_background(rng, "train")
    assert_true(meta.get("background_split") == "train", "background metadata should include split")
    assert_true(meta.get("background_policy"), "background metadata should include policy")
    assert_true("background_augmentation" in meta, "background metadata should include augmentation parameters")


def verify_text_document_asset_multi_image_selection() -> None:
    with tempfile.TemporaryDirectory(prefix="vantaline_doc_assets_") as tmp:
        tmp_dir = Path(tmp)
        first_path = tmp_dir / "manual_front_canonical.png"
        second_path = tmp_dir / "manual_back_canonical.png"
        first_image = np.full((48, 72, 3), (245, 245, 245), dtype=np.uint8)
        second_image = np.full((48, 72, 3), (215, 215, 215), dtype=np.uint8)
        server.cv2.putText(first_image, "FRONT", (4, 28), server.cv2.FONT_HERSHEY_SIMPLEX, 0.45, (20, 20, 20), 1)
        server.cv2.putText(second_image, "BACK", (6, 28), server.cv2.FONT_HERSHEY_SIMPLEX, 0.45, (20, 20, 20), 1)
        assert_true(server.cv2.imwrite(str(first_path), first_image), "front document fixture should be written")
        assert_true(server.cv2.imwrite(str(second_path), second_image), "back document fixture should be written")
        item = {
            "id": "acc_doc_two_sides",
            "name": "two side manual",
            "material_type": "text",
            "physical_size": server.physical_size_payload("text"),
            "normalized_assets": [
                {
                    "kind": "canonical_text_image",
                    "path": str(first_path),
                    "method": "fixture",
                    "width": 72,
                    "height": 48,
                },
                {
                    "kind": "canonical_text_image",
                    "path": str(second_path),
                    "method": "fixture",
                    "width": 72,
                    "height": 48,
                },
            ],
        }

        selected_indexes = set()
        selected_paths = set()
        for seed in range(64):
            loaded = server.load_rectified_document_asset_with_metadata(item, np.random.default_rng(seed))
            assert_true(loaded is not None, "document asset loader should return a fixture image")
            _, meta = loaded
            selected_indexes.add(meta.get("document_asset_index"))
            selected_paths.add(meta.get("asset_path"))
            assert_true(meta.get("document_asset_count") == 2, f"document candidate count should be recorded: {meta}")
            assert_true(
                meta.get("document_asset_selection_policy") == "seeded_uniform_canonical_text_image",
                f"multi-image canonical documents should use seeded uniform policy: {meta}",
            )
        assert_true(selected_indexes == {0, 1}, f"seeded selection should be able to choose both document sides: {selected_indexes}")
        assert_true(selected_paths == {str(first_path), str(second_path)}, f"both document paths should be selected: {selected_paths}")

        rendered_indexes = set()
        rendered_paths = set()
        for seed in range(64):
            output_path = tmp_dir / f"preview_{seed}.png"
            rendered = server.draw_training_preview([item], output_path, seed=seed)
            rendered_image = cv2.imread(str(output_path), cv2.IMREAD_UNCHANGED)
            assert_true(output_path.is_file() and rendered_image is not None and rendered_image.size > 0, "real preview renderer should write a readable image artifact")
            label = next((entry for entry in rendered.get("labels", []) if entry.get("material_type") == "text"), None)
            assert_true(label is not None, "training preview should include the text accessory label")
            rendered_indexes.add(label.get("document_asset_index"))
            rendered_paths.add(label.get("document_asset_path"))
            assert_true(label.get("document_asset_count") == 2, f"preview label should record document candidate count: {label}")
            assert_true(
                label.get("document_asset_selection_policy") == "seeded_uniform_canonical_text_image",
                f"preview label should record seeded uniform document policy: {label}",
            )
        assert_true(rendered_indexes == {0, 1}, f"training preview should render both document sides by seed: {rendered_indexes}")
        assert_true(rendered_paths == {str(first_path), str(second_path)}, f"training preview should expose both document paths: {rendered_paths}")


def verify_accessory_long_short_aspect_rule() -> None:
    # Production-baseline preview scale: a 1280px frame represents 600mm.
    # Keep this oracle independent from server.MM_TO_PREVIEW_PX so a runtime
    # calibration change cannot silently rewrite the expected fixture values.
    calibrated_px_per_mm = 1280.0 / 600.0
    assert_true(server.MM_TO_PREVIEW_PX == calibrated_px_per_mm, "inspection preview scale changed from the production 1280px / 600mm baseline")
    physical_size = {"kind": "object", "length_mm": 100.0, "width_mm": 42.0, "height_mm": 32.0}
    metadata = server.pose_render_footprint_metadata("upright", [72, 181], physical_size)
    expected_watch_footprint = [
        round((physical_size["length_mm"] / (181 / 72)) * calibrated_px_per_mm),
        round(physical_size["length_mm"] * calibrated_px_per_mm),
    ]
    assert_true(metadata["source_long_side_px"] == 181, "source long side should come from the visible long side")
    assert_true(metadata["source_short_side_px"] == 72, "source short side should come from the visible short side")
    assert_true(metadata["source_long_edge_axis"] == "height", "source long edge axis should stay observable")
    assert_true(metadata["source_length_width_rule"] == "source_visible_long_side_is_length_short_side_is_width", "dimension rule should be explicit")
    assert_true(metadata["render_scale_basis"] == "source_visible_long_short_aspect", "elongated objects should use source long:short aspect")
    assert_true(metadata["render_footprint_px"] == expected_watch_footprint, f"watch-like source should follow calibrated physical scale: {metadata['render_footprint_px']}")
    assert_true(metadata["render_source_aspect_preserved"], "metadata should mark source aspect preservation")

    asset = np.zeros((300, 120, 3), dtype=np.uint8)
    mask = np.full((300, 120), 255, dtype=np.uint8)
    _, _, resize_meta = server.resize_masked_asset_to_visible_footprint(asset, mask, (86, 86), preserve_aspect_ratio=True)
    assert_true(resize_meta["render_resize_policy"] == "alpha_visible_bbox_fit_physical_footprint_preserve_aspect", "object paste should support aspect-preserving fit")
    assert_true(not resize_meta["non_uniform_scaling_applied"], "aspect-preserving fit must not use non-uniform scaling")
    assert_true(resize_meta["render_visible_footprint_px"][1] > resize_meta["render_visible_footprint_px"][0], "long source must remain long after fitting")

    physical_bottle = {"kind": "object", "length_mm": 180.0, "width_mm": 45.0, "height_mm": 45.0}
    expected_cap_footprint = [round(45.0 * calibrated_px_per_mm)] * 2
    for source_size in ([80, 87], [80, 90], [90, 100]):
        top_view = server.pose_render_footprint_metadata("upright", source_size, physical_bottle)
        assert_true(top_view["render_scale_basis"] == "cap_outer_edge_diameter_mm", f"square-ish upright top view should stay on cap path: {source_size} -> {top_view}")
        assert_true(top_view["render_footprint_px"] == expected_cap_footprint, f"square-ish upright top view should keep calibrated cap footprint: {source_size} -> {top_view['render_footprint_px']}")

    upright_asset = {
        "source_pose_family": "upright",
        "visible_width_px": 120,
        "visible_height_px": 300,
        **server.pose_render_footprint_metadata("upright", [72, 181], physical_size),
    }
    lying_asset = {
        "source_pose_family": "lying",
        "visible_width_px": 286,
        "visible_height_px": 43,
        **server.pose_render_footprint_metadata("lying", [286, 43], physical_size),
    }
    server.apply_laying_standard_render_size_hints([upright_asset, lying_asset])
    assert_true(upright_asset["render_scale_basis"] == "source_visible_long_short_aspect", "source-aspect basis should remain intact after laying-standard pass")
    assert_true(upright_asset["source_long_edge_axis"] == "height", "upright watch source long edge should remain height")
    assert_true(upright_asset["render_long_edge_axis"] == "height", "laying-standard pass must preserve source long-edge axis for source-aspect assets")
    assert_true(upright_asset["render_footprint_px"] == expected_watch_footprint, f"upright watch footprint must not flip to lying median axis: {upright_asset['render_footprint_px']}")
    assert_true(
        upright_asset["render_long_short_orientation_basis"] == "source_visible_long_short_aspect_preserve_source_axis",
        "source-aspect orientation basis should document why the global lying axis was skipped",
    )

    source_asset = np.zeros((420, 140, 3), dtype=np.uint8)
    source_mask = np.zeros((420, 140), dtype=np.uint8)
    source_asset[40:395, 40:97] = (180, 180, 180)
    source_mask[40:395, 40:97] = 255
    pipe_length_mm = 700.0
    pipe_source_ratio = 355 / 58
    physical_render_target = (
        round(pipe_length_mm * calibrated_px_per_mm),
        round((pipe_length_mm / pipe_source_ratio) * calibrated_px_per_mm),
    )
    _, _, collapsed_meta = server.resize_masked_asset_to_visible_footprint(
        source_asset,
        source_mask,
        physical_render_target,
        preserve_aspect_ratio=True,
    )
    assert_true(
        collapsed_meta["render_visible_footprint_px"][0] <= 40 and collapsed_meta["render_visible_footprint_px"][1] >= 140,
        f"regression fixture should reproduce the upright-normalized lying collapse: {collapsed_meta}",
    )

    source_meta = {"source_restore_rotation_degrees": 90.0}
    restored_asset, restored_mask, applied_rotation, ignored_rotation = server.restore_object_sprite_source_orientation_for_render(
        source_asset,
        source_mask,
        source_meta,
        top_view_pose=False,
    )
    assert_true(abs(applied_rotation - 90.0) < 0.05, f"lying sprite should apply source restore rotation: {applied_rotation}")
    assert_true(abs(ignored_rotation) < 0.05, f"lying sprite should not ignore source restore rotation: {ignored_rotation}")
    assert_true(source_meta["source_orientation_restored_for_render"], "lying sprite should record source orientation restoration")
    restored_visible = server.visible_mask_size_px(restored_mask)
    assert_true(restored_visible[0] > restored_visible[1], f"restored source should expose the long axis horizontally: {restored_visible}")

    _, _, restored_resize_meta = server.resize_masked_asset_to_visible_footprint(
        restored_asset,
        restored_mask,
        physical_render_target,
        preserve_aspect_ratio=True,
    )
    restored_render_visible = restored_resize_meta["render_visible_footprint_px"]
    assert_true(
        restored_render_visible[0] >= 900 and restored_render_visible[1] >= 140,
        f"restored lying sprite should keep the physical long side instead of collapsing: {restored_resize_meta}",
    )
    canvas = np.zeros((900, 1500, 3), dtype=np.uint8)
    paste_meta = server.paste_physical_object_asset(
        canvas,
        restored_asset,
        restored_mask,
        (750, 450),
        physical_render_target[0],
        physical_render_target[1],
        0.0,
        preserve_aspect_ratio=True,
    )
    pasted_mask = paste_meta["_visible_mask_canvas"]
    pasted_polygon = server.visible_polygon_from_mask(pasted_mask)
    pipe_long_px = server.polygon_max_pair_distance_px(pasted_polygon)
    a4_long_px = max(
        server.physical_render_size_px(
            {"physical_size": {"kind": "paper", "width_mm": 210.0, "height_mm": 297.0}},
            "text",
        )
    )
    pipe_to_a4_ratio = pipe_long_px / a4_long_px
    expected_pipe_to_a4_ratio = pipe_length_mm / 297.0
    assert_true(
        abs(pipe_to_a4_ratio - expected_pipe_to_a4_ratio) < 0.25,
        f"final pasted pipe pixels should preserve 700mm:A4-long ratio, got {pipe_to_a4_ratio:.3f} from {paste_meta}",
    )
    assert_true(not paste_meta["render_paste_rescaled"], "physical object paste must not rescale the already-sized sprite")
    assert_true(
        paste_meta["render_visible_footprint_px"] == server.visible_mask_size_px(pasted_mask),
        f"physical object metadata should reflect final pasted pixels: {paste_meta}",
    )
    constrained_center = server.random_center_inside_background(
        np.random.default_rng(1),
        (1001, 162),
        57.73,
    )
    assert_true(
        constrained_center[1] == server.PREVIEW_CANVAS_SIZE_PX[1] // 2,
        f"oversized steep pipe should be centered on the axis that cannot fit instead of clipped near an edge: {constrained_center}",
    )

    top_view_meta = {"source_restore_rotation_degrees": 90.0}
    _, _, top_view_applied, top_view_ignored = server.restore_object_sprite_source_orientation_for_render(
        source_asset,
        source_mask,
        top_view_meta,
        top_view_pose=True,
    )
    assert_true(abs(top_view_applied) < 0.05, f"upright top-view sprite should not apply source restore rotation: {top_view_applied}")
    assert_true(abs(top_view_ignored - 90.0) < 0.05, f"upright top-view sprite should record ignored source restore rotation: {top_view_ignored}")
    assert_true(not top_view_meta["source_orientation_restored_for_render"], "upright top-view sprite should not restore source orientation")


def verify_pipeline_accessory_working_set_state() -> None:
    original_state_path = server.PIPELINE_STATE_PATH
    try:
        with tempfile.TemporaryDirectory(prefix="vantaline_pipeline_state_") as tmp:
            server.PIPELINE_STATE_PATH = Path(tmp) / "pipeline_state.json"
            server.save_pipeline_state(
                {
                    "accessory_ids": ["acc_keep", "acc_keep", "", "acc_missing", "1_warranty_service_manual", "2_stored_manual"],
                    "pending_candidate_ids": [],
                }
            )
            state = server.load_pipeline_state()
            assert_true(
                state["accessory_ids"] == ["acc_keep", "acc_missing", "1_warranty_service_manual", "2_stored_manual"],
                "pipeline state should dedupe current-flow accessories without dropping legacy aliases",
            )

            server.add_pipeline_accessory_id("acc_new")
            server.remove_pipeline_accessory_id("acc_missing")
            config = {
                "accessories": [
                    {"id": "acc_keep", "class_id": 100, "name": "keep", "material_type": "object"},
                    {"id": "acc_new", "class_id": 101, "name": "new", "material_type": "text"},
                    {"id": "acc_global_only", "class_id": 102, "name": "global", "material_type": "object"},
                    {"class_id": 1, "name": "warranty service manual", "material_type": "text"},
                    {"id": "acc_stored", "class_id": 2, "name": "stored manual", "material_type": "text"},
                ]
            }
            lookup = server.accessory_lookup_by_id(config)
            assert_true("1_warranty_service_manual" in lookup, "lookup should accept serialized legacy ids from /api/accessories")
            assert_true(
                lookup["2_stored_manual"]["id"] == "acc_stored",
                "lookup should accept class/name aliases for stored-id accessories",
            )
            payload = server.pipeline_accessories_payload(config)
            assert_true(
                [item["id"] for item in payload["accessories"]] == ["acc_new", "acc_keep", "1_warranty_service_manual", "acc_stored"],
                "pipeline payload must include current-flow accessories with canonical ids, not the whole global library",
            )
            state = server.load_pipeline_state()
            assert_true(
                state["accessory_ids"] == ["acc_new", "acc_keep", "1_warranty_service_manual", "acc_stored"],
                "pipeline state should canonicalize accepted legacy aliases after payload refresh",
            )
    finally:
        server.PIPELINE_STATE_PATH = original_state_path


def verify_pipeline_candidate_confirmation_filter() -> None:
    original_state_path = server.PIPELINE_STATE_PATH
    original_candidates_dir = server.ACCESSORY_CANDIDATES_DIR
    try:
        with tempfile.TemporaryDirectory(prefix="vantaline_pipeline_candidates_") as tmp:
            root = Path(tmp)
            server.PIPELINE_STATE_PATH = root / "pipeline_state.json"
            server.ACCESSORY_CANDIDATES_DIR = root / "candidates"
            server.ACCESSORY_CANDIDATES_DIR.mkdir(parents=True, exist_ok=True)
            candidate = {
                "id": "cand_ready",
                "name": "ready candidate",
                "material_type": "object",
                "pipeline_context": "pipeline",
                "codex_image_jobs": [{"job_id": "job_ready", "status": "completed", "progress": 100}],
            }
            confirmed = {
                **candidate,
                "id": "cand_confirmed",
                "confirmed_accessory_id": "acc_saved",
                "status": "confirmed",
            }
            (server.ACCESSORY_CANDIDATES_DIR / "cand_ready.json").write_text(json.dumps(candidate), encoding="utf-8")
            (server.ACCESSORY_CANDIDATES_DIR / "cand_confirmed.json").write_text(json.dumps(confirmed), encoding="utf-8")
            server.save_pipeline_state({"accessory_ids": [], "pending_candidate_ids": ["cand_ready", "cand_confirmed"]})

            config = {
                "accessories": [
                    {
                        "id": "acc_saved",
                        "class_id": 200,
                        "name": "saved accessory",
                        "material_type": "object",
                        "status": "reference_uploaded",
                    }
                ]
            }
            payload = server.pipeline_accessories_payload(config)
            assert_true(len(payload["pending_candidates"]) == 1, "confirmed candidates must not render as pending pipeline cards")
            assert_true(payload["pending_candidates"][0]["id"] == "cand_ready", "unconfirmed pipeline candidate should remain visible")
            assert_true(payload["pending_candidates"][0]["status"] == "ready", "completed unconfirmed candidates should render as green-ready")
            assert_true(
                payload["pending_candidates"][0]["status_text"] == "已生成，待确认",
                "completed unconfirmed candidates should say已生成，待确认, not建档中",
            )
            assert_true(
                [item["id"] for item in payload["accessories"]] == ["acc_saved"],
                "confirmed pipeline candidates should migrate into the current-flow accessory list",
            )
            state = server.load_pipeline_state()
            assert_true(state["pending_candidate_ids"] == ["cand_ready"], "confirmed candidate id should be pruned from pipeline state")
            assert_true(state["accessory_ids"] == ["acc_saved"], "confirmed candidate migration should persist canonical accessory id")
    finally:
        server.PIPELINE_STATE_PATH = original_state_path
        server.ACCESSORY_CANDIDATES_DIR = original_candidates_dir


def verify_pipeline_detection_methods_and_ai_handoff() -> None:
    original_ai_path = server.AI_DETECTION_TASKS_PATH
    original_load_config = server.load_config
    try:
        with tempfile.TemporaryDirectory(prefix="vantaline_pipeline_methods_") as tmp:
            server.AI_DETECTION_TASKS_PATH = Path(tmp) / "ai_detection_tasks.json"
            config = {
                "accessories": [
                    {"id": "acc_ready", "class_id": 301, "name": "ready accessory", "material_type": "object"}
                ]
            }
            server.load_config = lambda: config

            assert_true(server.normalize_pipeline_detection_method("yolo") == "yolo", "YOLO method should persist")
            assert_true(server.normalize_pipeline_detection_method("yolo_ocr") == "yolo_ocr", "YOLO+OCR method should persist")
            assert_true(server.normalize_pipeline_detection_method("ai_detection") == "ai", "AI aliases should normalize to ai")
            assert_true(server.normalize_pipeline_detection_method("locate_anything") == "yolo_ocr", "removed Locate aliases should fall back to the YOLO+OCR default")
            public_yolo = server.pipeline_task_public(
                {"id": "pipe_yolo", "name": "yolo", "stage": "draft", "status": "ready", "detection_method": "yolo", "accessory_ids": ["acc_ready"]},
                config,
            )
            assert_true(public_yolo["uses_training_flow"] is True, "YOLO should still use training flow")

            ai_task = {
                "id": "pipe_ai",
                "name": "AI direct",
                "stage": "draft",
                "status": "ready",
                "detection_method": "ai",
                "accessory_ids": ["acc_ready"],
                "params": {"route": "ai"},
            }
            server.advance_pipeline_task(ai_task)
            assert_true(ai_task["stage"] == "library" and ai_task["status"] == "completed", "AI pipeline task should complete into library")
            assert_true(ai_task["params"].get("route") == "ai" and "train_mode" not in ai_task["params"], "AI pipeline task must not carry YOLO train_mode")
            saved_ai_tasks = json.loads(server.AI_DETECTION_TASKS_PATH.read_text(encoding="utf-8"))["tasks"]
            assert_true(saved_ai_tasks[0]["source"] == "pipeline", "pipeline-created AI task should be tagged as pipeline source")
            assert_true(saved_ai_tasks[0]["selected_accessory_ids"] == ["acc_ready"], "pipeline AI task should preserve selected accessory ids")

    finally:
        server.AI_DETECTION_TASKS_PATH = original_ai_path
        server.load_config = original_load_config


def verify_frontend_pipeline_method_coverage() -> None:
    pipeline_page = (ROOT / "frontend" / "src" / "features" / "pipeline" / "TrainingPipelinePage.tsx").read_text(encoding="utf-8")
    app_shell = (ROOT / "frontend" / "src" / "components" / "AppShell.tsx").read_text(encoding="utf-8")
    global_css = (ROOT / "frontend" / "src" / "styles" / "global.css").read_text(encoding="utf-8")
    assert_true("PIPELINE_METHODS" in pipeline_page and "AI 检测" in pipeline_page, "frontend should render supported pipeline methods")
    assert_true("Locate Anything" not in pipeline_page and '"locate"' not in pipeline_page, "frontend should not render removed LocateAnything method")
    assert_true("LabelSheetPage" not in app_shell and "LocateAnythingPage" not in app_shell, "removed pages should not be routed")
    assert_true("training-library-pane" in global_css, "training library tab styles should remain present")


def main() -> int:
    checks = [
        verify_sample_plan_distribution,
        verify_exact_count_rule,
        verify_manual_type_exact_count,
        verify_one_task_model_selection,
        verify_yolo_vs_yolo_ocr_behavior,
        verify_background_metadata,
        verify_text_document_asset_multi_image_selection,
        verify_accessory_long_short_aspect_rule,
        verify_pipeline_accessory_working_set_state,
        verify_pipeline_candidate_confirmation_filter,
        verify_pipeline_detection_methods_and_ai_handoff,
        verify_frontend_pipeline_method_coverage,
    ]
    for check in checks:
        check()
        print(f"PASS {check.__name__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
