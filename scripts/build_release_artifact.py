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
parser.add_argument("--doc-image-bundle", required=True, type=Path)
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
    doc_bundle = args.doc_image_bundle.resolve()
    manifest = json.loads((doc_bundle / "manifest.json").read_text())
    source = stage / "local_inspection_service/workers/doc_image_extractor/DocImages.java"
    lock = json.loads(source.with_name("dependencies.json").read_text())
    if manifest["source_sha256"] != sha256(source) or manifest["version"] != "doc-images-v1" or manifest["poi"] != "5.5.1":
        raise SystemExit("DOC bundle/source mismatch")
    if {k: v for k, v in manifest["files"].items() if k != "doc-images.jar"} != lock or "doc-images.jar" not in manifest["files"]:
        raise SystemExit("DOC bundle dependency mismatch")
    destination = source.parent / "bundle"
    destination.mkdir()
    for name, digest in manifest["files"].items():
        if not re.fullmatch(r"(?:lib/)?[A-Za-z0-9_.-]+\.jar", name) or sha256(doc_bundle / name) != digest:
            raise SystemExit("DOC bundle checksum mismatch")
        target = destination / name
        target.parent.mkdir(exist_ok=True)
        shutil.copy2(doc_bundle / name, target)
    shutil.copy2(doc_bundle / "manifest.json", destination / "manifest.json")
    (stage / "VERSION.json").write_text(json.dumps(version, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    files = sorted(path for path in stage.rglob("*") if path.is_file())
    sums = "".join(f"{sha256(path)}  {path.relative_to(stage).as_posix()}\n" for path in files)
    (stage / "SHA256SUMS").write_text(sums, encoding="utf-8")
    with tarfile.open(args.output, "w:gz") as handle:
        handle.add(stage, arcname=f"vantaline-{args.release}")
print(args.output)
