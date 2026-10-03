#!/usr/bin/env python3
"""Copy explicitly selected files to COS and verify full object contents.

This operational tool never deletes source files or changes application records.
Inventory must be taken while writers are paused; online scans are preliminary.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import shutil
import uuid
from typing import Any

CHUNK = 1024 * 1024
SCHEMA = "vantaline-cos-manifest-v1"


def digest(stream) -> tuple[str, int]:
    checksum = hashlib.sha256()
    size = 0
    while block := stream.read(CHUNK):
        checksum.update(block)
        size += len(block)
    return checksum.hexdigest(), size


def safe_relative(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if not value or path.is_absolute() or any(p in ("", ".", "..") for p in value.split("/")):
        raise ValueError("path must be a normalized relative path")
    return path


def local_path(root: Path, relative: str) -> Path:
    path = root
    for part in safe_relative(relative).parts:
        path = path / part
        if path.is_symlink():
            raise ValueError("symlinks require separate operator review")
    if not path.resolve().is_relative_to(root):
        raise ValueError("path escaped source root")
    return path


def local_only(relative: str) -> bool:
    # This is a secondary guard, not a substitute for reviewing selected roots.
    return any(
        p.startswith(".") or "secret" in p.lower() or "credential" in p.lower()
        or p.lower().endswith((".env", ".pem", ".key", ".p12", ".pfx"))
        or p.lower() in {"auth.json", "config.json", "config.last_good.json", "ai_config.local.json"}
        for p in PurePosixPath(relative).parts
    )


def fingerprint(path: Path) -> dict[str, Any]:
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode):
        raise ValueError("only regular files may be migrated")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as handle:
        opened = os.fstat(handle.fileno())
        sha, size = digest(handle)
        after = os.fstat(handle.fileno())
    current = path.lstat()
    identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    if not (identity(before) == identity(opened) == identity(after) == identity(current)):
        raise ValueError("source changed during hashing; pause writers and rescan")
    return {"sha256": sha, "size": size, "mtime_ns": before.st_mtime_ns,
            "mode": stat.S_IMODE(before.st_mode)}


def inventory(root: Path, includes: list[str], destination: Path) -> dict[str, Any]:
    root = root.resolve(strict=True)
    destination = destination.absolute()
    if destination.resolve().is_relative_to(root):
        raise ValueError("manifest must be outside source root")
    selected = [safe_relative(item).as_posix() for item in includes]
    if len(set(selected)) != len(selected) or any(
        a != b and PurePosixPath(a) in PurePosixPath(b).parents for a in selected for b in selected
    ):
        raise ValueError("selected roots must not overlap")
    for item in selected:
        local_path(root, item).stat()
    summary = {"type": "complete", "files": 0, "bytes": 0, "excluded": 0}
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as out:
        def emit(record):
            out.write(json.dumps(record, ensure_ascii=True, sort_keys=True) + "\n")

        emit({"type": "header", "schema": SCHEMA, "root": str(root), "includes": selected})
        def visit(path: Path):
            relative = path.relative_to(root).as_posix()
            if path.is_symlink() or local_only(relative):
                summary["excluded"] += 1
                emit({"type": "excluded", "path": relative, "reason": "local-only-or-symlink"})
            elif path.is_dir():
                for child in sorted(path.iterdir()):
                    visit(child)
            else:
                record = {"type": "file", "path": relative, **fingerprint(path)}
                emit(record)
                summary["files"] += 1
                summary["bytes"] += record["size"]
        for item in selected:
            visit(local_path(root, item))
        emit(summary)
        out.flush()
        os.fsync(out.fileno())
    return summary


def load_manifest(path: Path) -> tuple[dict, list[dict]]:
    with path.open(encoding="utf-8") as handle:
        records = [json.loads(line) for line in handle]
    if len(records) < 2 or records[0].get("schema") != SCHEMA or records[0].get("type") != "header":
        raise ValueError("invalid manifest header")
    if records[-1].get("type") != "complete":
        raise ValueError("incomplete inventory cannot be uploaded")
    selected = [safe_relative(item) for item in records[0].get("includes", [])]
    if not selected or len(set(selected)) != len(selected) or any(
        a != b and a in b.parents for a in selected for b in selected
    ):
        raise ValueError("invalid selected roots")
    files, paths, excluded = [], set(), 0
    for row in records[1:-1]:
        relative = safe_relative(row["path"]).as_posix()
        relative_path = PurePosixPath(relative)
        if not any(root == relative_path or root in relative_path.parents for root in selected):
            raise ValueError("manifest path outside selected roots")
        if relative in paths:
            raise ValueError("duplicate manifest path")
        paths.add(relative)
        if row["type"] == "excluded":
            excluded += 1
            continue
        if row["type"] != "file" or local_only(relative):
            raise ValueError("invalid or local-only manifest row")
        if not re.fullmatch(r"[a-f0-9]{64}", row.get("sha256", "")) or type(row.get("size")) is not int or row["size"] < 0:
            raise ValueError("invalid file checksum or length")
        files.append(row)
    footer = records[-1]
    if (footer.get("files"), footer.get("bytes"), footer.get("excluded")) != (len(files), sum(x["size"] for x in files), excluded):
        raise ValueError("manifest totals do not match")
    return records[0], files


def restore(client, bucket: str, prefix: str, manifest: Path, destination: Path,
            includes: list[str] | None = None) -> dict:
    """Restore into a NEW private directory, publishing files only after hashing.

    This intentionally does not restore source owners or replace existing data.
    Operators must validate the directory and apply deployment ownership separately.
    """
    _, files = load_manifest(manifest)
    if includes:
        selected = [safe_relative(item) for item in includes]
        matched = set()
        chosen = []
        for row in files:
            path = PurePosixPath(row["path"])
            for root in selected:
                if root == path or root in path.parents:
                    matched.add(root)
                    break
            else:
                continue
            chosen.append(row)
        if set(selected) != matched:
            raise ValueError("restore selection contains no files")
        files = chosen
    needed = sum(row["size"] for row in files)
    parent = destination.absolute().parent.resolve(strict=True)
    destination = parent / destination.name
    if shutil.disk_usage(parent).free < needed + 256 * CHUNK:
        raise ValueError("insufficient restore space with safety reserve")
    destination.mkdir(mode=0o700, exist_ok=False)
    summary = {"restored_files": 0, "restored_bytes": 0}
    for row in files:
        path = local_path(destination, row["path"])
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = path.parent / (".cos-restore-" + uuid.uuid4().hex)
        stream = None
        try:
            response = client.get_object(Bucket=bucket, Key=object_key(prefix, row))
            stream = response["Body"].get_raw_stream()
            checksum, size = hashlib.sha256(), 0
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as out:
                while block := stream.read(CHUNK):
                    size += len(block)
                    if size > row["size"]:
                        raise ValueError("restore object exceeds expected size")
                    checksum.update(block)
                    out.write(block)
                if (checksum.hexdigest(), size) != (row["sha256"], row["size"]):
                    raise ValueError("restore content verification failed")
                out.flush()
                os.fsync(out.fileno())
            # link is exclusive: never replace an existing target, even on races.
            os.link(temporary, path)
            summary["restored_files"] += 1
            summary["restored_bytes"] += size
        finally:
            if stream is not None:
                stream.close()
            temporary.unlink(missing_ok=True)
    return summary


def object_key(prefix: str, row: dict) -> str:
    return f"{safe_relative(prefix).as_posix()}/sha256/{row['sha256'][:2]}/{row['sha256']}"


def verify_object(client, bucket: str, key: str, row: dict) -> None:
    response = client.get_object(Bucket=bucket, Key=key)
    stream = response["Body"].get_raw_stream()
    try:
        actual = digest(stream)
    finally:
        stream.close()
    if actual != (row["sha256"], row["size"]):
        raise ValueError("remote object content verification failed")


def transfer(client, bucket: str, prefix: str, manifest: Path, receipt: Path, *, upload: bool) -> dict:
    header, files = load_manifest(manifest)
    root = Path(header["root"]).resolve(strict=upload)
    fd = os.open(receipt, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    summary = {"verified_files": 0, "verified_bytes": 0}
    checked = set()
    with os.fdopen(fd, "w", encoding="utf-8") as out:
        with manifest.open("rb") as handle:
            manifest_sha, _ = digest(handle)
        out.write(json.dumps({"type": "header", "manifest_sha256": manifest_sha, "bucket": bucket, "prefix": prefix}) + "\n")
        for row in files:
            key = object_key(prefix, row)
            if upload:
                source = local_path(root, row["path"])
                actual = fingerprint(source)
                if (actual["sha256"], actual["size"]) != (row["sha256"], row["size"]):
                    raise ValueError("source differs from inventory; new scan required")
            if key not in checked:
                if upload:
                    try:
                        client.head_object(Bucket=bucket, Key=key)
                    except Exception as error:
                        if not hasattr(error, "get_status_code") or str(error.get_status_code()) != "404":
                            raise
                        # Content-addressed keys allow retries without replacing another file.
                        client.upload_file(Bucket=bucket, Key=key, LocalFilePath=str(source),
                                           PartSize=8, MAXThread=2, EnableMD5=True,
                                           StorageClass="STANDARD", Metadata={"x-cos-meta-sha256": row["sha256"]})
                        after = fingerprint(source)
                        if (after["sha256"], after["size"]) != (row["sha256"], row["size"]):
                            raise ValueError("source changed during upload")
                verify_object(client, bucket, key, row)
                checked.add(key)
            out.write(json.dumps({"type": "verified", "path": row["path"], "key": key,
                                  "sha256": row["sha256"], "size": row["size"]}) + "\n")
            out.flush()
            summary["verified_files"] += 1
            summary["verified_bytes"] += row["size"]
        out.write(json.dumps({"type": "complete", **summary}) + "\n")
        out.flush()
        os.fsync(out.fileno())
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    scan = commands.add_parser("inventory")
    scan.add_argument("--root", type=Path, required=True)
    scan.add_argument("--include", action="append", required=True, help="reviewed relative subtree; repeatable")
    scan.add_argument("--manifest", type=Path, required=True)
    for name in ("upload", "verify", "restore"):
        command = commands.add_parser(name)
        command.add_argument("--manifest", type=Path, required=True)
        if name == "restore":
            command.add_argument("--destination", type=Path, required=True, help="new private directory")
            command.add_argument("--include", action="append", help="relative file/subtree to restore; defaults to all")
        else:
            command.add_argument("--receipt", type=Path, required=True)
        command.add_argument("--bucket", required=True)
        command.add_argument("--region", required=True)
        command.add_argument("--prefix", default="objects")
    args = parser.parse_args()
    if args.command == "inventory":
        result = inventory(args.root, args.include, args.manifest)
    else:
        from qcloud_cos import CosConfig, CosS3Client
        client = CosS3Client(CosConfig(Region=args.region, Scheme="https",
            SecretId=os.environ["COS_SECRET_ID"], SecretKey=os.environ["COS_SECRET_KEY"],
            Token=os.environ.get("COS_SESSION_TOKEN")))
        if args.command == "restore":
            result = restore(client, args.bucket, args.prefix, args.manifest, args.destination, args.include)
        else:
            result = transfer(client, args.bucket, args.prefix, args.manifest, args.receipt,
                              upload=args.command == "upload")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # SDK exceptions may contain signed request details; never print their text.
        print(f"migration failed ({type(error).__name__}); retain source and inspect locally", file=sys.stderr)
        raise SystemExit(1)
