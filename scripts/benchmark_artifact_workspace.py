#!/usr/bin/env python3
"""Opt-in disk benchmark: incompressible synthetic bytes at historical dataset scale."""
import argparse
import hashlib
import json
from pathlib import Path
import random
import shutil
import sys
import tempfile
import time
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local_inspection_service.storage.artifacts.archives import package
from local_inspection_service.storage.artifacts.disk import DiskBudget
from local_inspection_service.storage.artifacts.types import Artifact


def run(size, report):
    started = time.monotonic()
    block = random.Random(7913383).randbytes(1024*1024)
    def blocks(length):
        while length:
            chunk = block[:min(length, len(block))]
            yield chunk
            length -= len(chunk)
    rows, remaining, index = [], size, 0
    while remaining:
        length = min(remaining, 64*1024*1024)
        digest = hashlib.sha256()
        for chunk in blocks(length):
            digest.update(chunk)
        rows.append(Artifact(f"outputs/fixture/images/train/{index}.bin", 1, digest.hexdigest(), length))
        remaining -= length
        index += 1
    class Objects:
        def copy_to(self, row, target):
            digest = hashlib.sha256()
            for chunk in blocks(row.size):
                target.write(chunk)
                digest.update(chunk)
            assert digest.hexdigest() == row.sha256
    with tempfile.TemporaryDirectory(prefix="cos-workspace-benchmark-") as temporary:
        root = Path(temporary)
        budget = DiskBudget(root / "control")
        before = shutil.disk_usage(root).free
        store = SimpleNamespace(list=lambda prefix: rows, objects=Objects(), budget=budget)
        handle, archive = package(store, "outputs/fixture")
        try:
            archive_size = archive.stat().st_size
            reservation = sum(json.loads(p.read_text())["bytes"] for p in (budget.root / "reservations").glob("*.json"))
            minimum_free = shutil.disk_usage(root).free
        finally:
            handle.cleanup()
        result = {"ok": True, "source": "synthetic incompressible fixture; no model or COS call",
                  "input_bytes": size, "files": len(rows), "archive_bytes": archive_size,
                  "workspace_reserved_bytes": reservation, "free_before": before, "free_after_archive": minimum_free,
                  "scratch_empty_after_cleanup": not any((budget.root / "scratch").iterdir()),
                  "duration_seconds": round(time.monotonic()-started, 3)}
    with report.open("x") as output:
        json.dump(result, output, indent=2)
    print(json.dumps(result))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bytes", type=int, default=3920294827)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.bytes <= 0:
        parser.error("bytes must be positive")
    run(args.bytes, args.report)
