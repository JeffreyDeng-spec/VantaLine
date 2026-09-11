"""Bounded, local-only OCR for VLM-located missing regions. No model text.

Proposals never become erasure masks: only measured OCR boxes enter cleaning.
Original observations are immutable; new IDs are deterministic per region/row.
"""
import copy
import math
import time

from PIL import Image
from . import standard_preparation as engine


def recover(image, elements, classification, observe, *, progress=None, timeout=60):
    regions = engine.missing_regions(classification)
    merged = copy.deepcopy(elements)
    evidence = dict(regions=[], reasons=[], timeout_seconds=timeout)
    deadline = time.monotonic()+timeout
    width, height = image.size
    if classification["kind"] != "label_design":
        evidence["reasons"].append("not_single_label_design")
        return merged, evidence
    for index, region in enumerate(regions):
        rid = f"r{index+1}"
        bounds = engine.pixels(region["box"], image.size)
        x1, y1, x2, y2 = bounds
        row = dict(id=rid, proposal=copy.deepcopy(region), source_pixels=list(bounds), state="recognizing", observations=[], added_ids=[], deduplicated_ids=[])
        evidence["regions"].append(row)
        # Save a durable checkpoint BEFORE each local job, not only final output.
        if progress:
            progress(copy.deepcopy(evidence), image.crop(bounds), None)
        try:
            remaining = deadline-time.monotonic()
            if remaining <= 0:
                raise TimeoutError("local_recovery_timeout")
            # At most 3x; cap inference pixels and keep source transform exact.
            scale = min(3.0, 2048/max(x2-x1, y2-y1), math.sqrt(4_000_000/((x2-x1)*(y2-y1))))
            size = (max(1, round((x2-x1)*scale)), max(1, round((y2-y1)*scale)))
            preview = image.crop(bounds).resize(size, Image.Resampling.LANCZOS)
            row["ocr_size"] = list(size)
            started = time.monotonic()
            local = observe(preview, timeout=remaining)
            row["elapsed_ms"] = round((time.monotonic()-started)*1000)
            row["observations"] = copy.deepcopy(local)
            if not local:
                raise ValueError("recovery_no_elements")
            for n, value in enumerate(local):
                x, y, w, h = engine.box(value["box"])
                mapped = [(x1+x*(x2-x1))/width, (y1+y*(y2-y1))/height, w*(x2-x1)/width, h*(y2-y1)/height]
                engine.box(mapped)
                candidate = {**value, "id": f"{rid}e{n+1}", "box": mapped,
                    "state": region["state"], "reason": region["reason"],
                    "provenance": {"kind": "local_recovery", "region_id": rid, "local_box": value["box"], "source_pixels": list(bounds), "ocr_size": list(size)}}
                # Touching the OCR input edge can mean a partial line.
                if min(x*size[0], y*size[1], (1-x-w)*size[0], (1-y-h)*size[1]) < 2:
                    candidate.update(state="uncertain", reason="recovery_touches_region_edge")
                    evidence["reasons"].append(rid+":truncated_region")
                p = engine.pixels(mapped, image.size)
                conflicts = [e for e in merged if engine.overlaps(p, engine.pixels(e["box"], image.size))]
                identical = []
                for prior in conflicts:
                    q = engine.pixels(prior["box"], image.size)
                    intersection = max(0, min(p[2], q[2])-max(p[0], q[0]))*max(0, min(p[3], q[3])-max(p[1], q[1]))
                    overlap = intersection/max(1, (p[2]-p[0])*(p[3]-p[1])+(q[2]-q[0])*(q[3]-q[1])-intersection)
                    if prior["type"] == candidate["type"] and prior["text"] == candidate["text"] and overlap >= .8 and prior["state"] == candidate["state"]:
                        identical.append(prior)
                if len(identical) == 1 and len(conflicts) == 1:
                    row["deduplicated_ids"].append(identical[0]["id"])
                    continue
                if conflicts:
                    candidate.update(state="uncertain", reason="recovery_overlaps_existing_element")
                    evidence["reasons"].append(rid+":overlap_or_conflicting_reading")
                if len(merged) >= 500:
                    raise ValueError("recovery_element_limit")
                merged.append(candidate)
                row["added_ids"].append(candidate["id"])
            row["state"] = "completed"
            if progress:
                progress(copy.deepcopy(evidence), preview, engine.overlay(preview, local))
        except (ValueError, RuntimeError, TimeoutError) as exc:
            row.update(state="review", reason_code=str(exc)[:160])
            evidence["reasons"].append(rid+":local_recovery_failed")
            if progress:
                progress(copy.deepcopy(evidence), None, None)
    return merged, evidence
