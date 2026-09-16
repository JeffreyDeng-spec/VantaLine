"""Private real-photo calibration. Manifest: [{path, expected_pass, name}].
Never commit manifest, media, or generated output. No provider calls or DB writes.
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
from local_inspection_service.label_inspection import model, quality


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    entries = json.loads(Path(args.manifest).read_text())
    rows = []
    timings = []
    for entry in entries:
        data = Path(entry["path"]).read_bytes()
        image, _ = model.decode(data)
        prepared = model.jpeg(image)
        result = quality.inspect(prepared, image.size)
        for _ in range(10):
            start = time.monotonic()
            quality.inspect(prepared, image.size)
            timings.append((time.monotonic() - start) * 1000)
        rows.append(
            {
                "name": entry["name"],
                "sha256": quality.digest(data),
                "expected_pass": entry["expected_pass"],
                **result,
            }
        )
    feasible = []
    for pixels in [200, 225, 250, 275, 300]:
        for focus in range(200, 1800, 200):
            decisions = [
                any(
                    c["metrics"]["active_blocks"] >= quality.CONFIG["min_active_blocks"]
                    and min(
                        c["metrics"]["input_short_side"],
                        c["metrics"]["native_short_side"],
                    )
                    >= pixels
                    and max(c["metrics"]["focus"], c["metrics"]["block_median"])
                    >= focus
                    for c in r["candidates"]
                )
                for r in rows
            ]
            if decisions == [r["expected_pass"] for r in rows]:
                feasible.append([pixels, focus])
    selected = min(feasible) if feasible else None
    report = {
        "policy": quality.POLICY,
        "config": quality.CONFIG,
        "rows": rows,
        "grid_selected": selected,
        "all_expected": all(r["passed"] == r["expected_pass"] for r in rows),
        "p95_ms": round(float(np.percentile(timings, 95)), 2),
        "scope": "Calibration only; six files are not six independent capture scenes. Not a production accuracy estimate.",
    }
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(
        json.dumps(
            {k: v for k, v in report.items() if k not in ("rows", "config")},
            ensure_ascii=False,
        )
    )
    assert report["all_expected"] and selected == [
        quality.CONFIG["min_short_side"],
        quality.CONFIG["min_focus"],
    ], "Calibration does not support frozen policy"
    assert report["p95_ms"] < 500, "Quality gate latency budget exceeded"


if __name__ == "__main__":
    main()
