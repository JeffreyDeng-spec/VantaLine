#!/usr/bin/env python3
"""Run the pinned real OCR profile against commissioning images.

This is intentionally separate from mock-backed API smoke tests. It provides
model startup, warm inference timing, original text (including case), confidence
and polygons as golden-evidence input for a customer acceptance set.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import cv2


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from local_inspection_service import server  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("images", nargs="+", type=Path)
    parser.add_argument("--warm-runs", type=int, default=1)
    args = parser.parse_args()

    started = time.perf_counter()
    server.incoming_text_ocr_engine()
    startup_seconds = time.perf_counter() - started
    results = []
    for path in args.images:
        image = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if image is None:
            raise SystemExit(f"cannot decode image: {path}")
        runs = []
        observations = []
        for _ in range(max(1, args.warm_runs)):
            run_started = time.perf_counter()
            observations = server.incoming_text_ocr_observations(image)
            runs.append(round(time.perf_counter() - run_started, 4))
        results.append(
            {
                "image": str(path),
                "width": int(image.shape[1]),
                "height": int(image.shape[0]),
                "inference_seconds": runs,
                "observations": [
                    {
                        "text": item.text,
                        "confidence": round(float(item.confidence), 6),
                        "polygon": [[round(x, 2), round(y, 2)] for x, y in item.polygon],
                    }
                    for item in observations
                ],
            }
        )
    print(json.dumps({"engine_startup_seconds": round(startup_seconds, 4), "results": results}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
