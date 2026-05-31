#!/usr/bin/env python3
"""Focused verification for the task-centric training/inference pipeline."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

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


def main() -> int:
    checks = [
        verify_sample_plan_distribution,
        verify_exact_count_rule,
        verify_manual_type_exact_count,
        verify_one_task_model_selection,
        verify_yolo_vs_yolo_ocr_behavior,
        verify_background_metadata,
    ]
    for check in checks:
        check()
        print(f"PASS {check.__name__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
