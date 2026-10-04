#!/usr/bin/env python3
"""Import reviewed evacuation manifests without reading or changing the source disk."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cos_migrate import load_manifest
from local_inspection_service.storage.artifacts.runtime import get_runtime
from local_inspection_service.storage.artifacts.types import Artifact, ArtifactConflict


def load_pair(manifest, receipt, bucket):
    _, files = load_manifest(manifest)
    entries = [json.loads(line) for line in receipt.read_text().splitlines()]
    expected_header = {"type": "header", "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
                       "bucket": bucket, "prefix": "objects"}
    if not entries or entries[0] != expected_header:
        raise ValueError("receipt does not identify this manifest and bucket")
    expected = {row["path"]: Artifact(row["path"], 1, row["sha256"], row["size"],
                                      mtime_ns=row.get("mtime_ns", 0)) for row in files}
    seen = set()
    for row in entries[1:-1]:
        artifact = expected.get(row.get("path"))
        if artifact is None or artifact.path in seen or row != {
            "type": "verified", "path": artifact.path, "key": artifact.key,
            "sha256": artifact.sha256, "size": artifact.size,
        }:
            raise ValueError("receipt contains missing, duplicate or mismatched file entries")
        seen.add(artifact.path)
    if seen != set(expected) or entries[-1] != {
        "type": "complete", "verified_files": len(expected), "verified_bytes": sum(r.size for r in expected.values()),
    }:
        raise ValueError("receipt is not complete")
    return list(expected.values())


def import_rows(store, rows, *, apply):
    verified, published, existing = set(), 0, 0
    for row in sorted(rows, key=lambda r: r.path):
        current = store.locations.get(row.path)
        if current is not None and (current.sha256, current.size, current.state) != (row.sha256, row.size, "ready"):
            raise ArtifactConflict("existing logical path differs; reconcile final delta explicitly")
        if row.key not in verified:
            store.objects.verify(row)
            verified.add(row.key)
        if current is not None:
            existing += 1
        elif apply:
            store.locations.publish(row, expected_generation=0)
            published += 1
    return {"files": len(rows), "bytes": sum(r.size for r in rows), "verified_objects": len(verified),
            "published": published, "already_indexed": existing, "apply": apply}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pair", nargs=2, action="append", required=True, metavar=("MANIFEST", "RECEIPT"))
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--apply", action="store_true", help="publish missing paths only after remote readback")
    args = parser.parse_args()
    runtime = get_runtime()
    if runtime is None:
        raise ValueError("configure the restricted COS operational runtime first")
    rows, seen = [], set()
    for manifest, receipt in args.pair:
        for row in load_pair(Path(manifest), Path(receipt), runtime.store.objects.bucket):
            if row.path in seen:
                raise ValueError("overlapping manifests")
            seen.add(row.path)
            rows.append(row)
    # Reserve the report path before any mutation; incomplete reports lack ok.
    fd = os.open(args.report, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as report:
        result = import_rows(runtime.store, rows, apply=args.apply)
        json.dump({"ok": True, **result}, report, indent=2)
    print(json.dumps(result))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"location import failed ({type(error).__name__}); retain source and inspect restricted evidence", file=sys.stderr)
        sys.exit(1)
