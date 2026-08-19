#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


parser = argparse.ArgumentParser()
parser.add_argument("--release", required=True)
parser.add_argument("--git-commit", required=True)
parser.add_argument("--built-at", required=True)
parser.add_argument("--output", required=True, type=Path)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
dist = root / "local_inspection_service/frontend/dist-production"
index = (dist / "index.html").read_text(encoding="utf-8")
matches = re.findall(r'<script[^>]+src="[^"]*/assets/([^"?]+\.js)', index)
if len(matches) != 1:
    raise SystemExit(f"expected one production entry bundle, found {matches}")
bundle = dist / "assets" / matches[0]
payload = bundle.read_text(encoding="utf-8")
if "plc-web-serial-v4" not in payload or "plc-web-serial-v3" in payload:
    raise SystemExit("refusing to package a non-v4 browser bundle")
version = {
    "release": args.release,
    "git_commit": args.git_commit,
    "built_at": args.built_at,
    "backend_protocol": "plc-web-serial-v4",
    "frontend_protocol": "plc-web-serial-v4",
    "frontend_bundle": bundle.name,
    "frontend_bundle_sha256": sha256(bundle),
}
args.output.parent.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(prefix="vantaline-release-") as temp:
    stage = Path(temp) / "release"
    stage.mkdir()
    archive = subprocess.run(["git", "archive", "--format=tar", "HEAD"], cwd=root, check=True, stdout=subprocess.PIPE).stdout
    source_tar = Path(temp) / "source.tar"
    source_tar.write_bytes(archive)
    with tarfile.open(source_tar) as handle:
        handle.extractall(stage, filter="data")
    shutil.copytree(dist, stage / "local_inspection_service/frontend/dist-production")
    (stage / "VERSION.json").write_text(json.dumps(version, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    files = sorted(path for path in stage.rglob("*") if path.is_file())
    sums = "".join(f"{sha256(path)}  {path.relative_to(stage).as_posix()}\n" for path in files)
    (stage / "SHA256SUMS").write_text(sums, encoding="utf-8")
    with tarfile.open(args.output, "w:gz") as handle:
        handle.add(stage, arcname=f"vantaline-{args.release}")
print(args.output)
