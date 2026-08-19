"""Read-only JSON source inventory for data-layer migration scripts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .schema import SENSITIVE_LOCAL_SOURCES


ROOT_METADATA_FILES = (
    "auth.json",
    "config.json",
    "ai_detection_tasks.json",
    "data_analysis_records.json",
    "pipeline_state.json",
    "pipeline_tasks.json",
)

DIRECTORY_METADATA_GLOBS = (
    ("accessory_candidates", "*.json"),
    ("training_tasks", "*.json"),
    ("auto_optimize", "*.json"),
)


@dataclass(frozen=True)
class JsonSource:
    rel_path: str
    path: Path
    size_bytes: int
    sha256: str
    data: Any | None
    error: str
    parse_warning: str = ""


@dataclass(frozen=True)
class SensitiveSource:
    rel_path: str
    path: Path
    exists: bool
    size_bytes: int


@dataclass(frozen=True)
class SourceInventory:
    source_root: Path
    service_root: Path
    data_dir: Path
    json_sources: tuple[JsonSource, ...]
    sensitive_sources: tuple[SensitiveSource, ...]


def resolve_data_dir(source: Path) -> Path:
    source = source.resolve()
    if (source / "config.json").exists() or source.name == "data":
        return source
    repo_data_dir = source / "local_inspection_service" / "data"
    if repo_data_dir.exists():
        return repo_data_dir.resolve()
    service_data_dir = source / "data"
    if service_data_dir.exists():
        return service_data_dir.resolve()
    raise FileNotFoundError(f"Cannot resolve VantaLine data dir from {source}")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json_source(data_dir: Path, path: Path) -> JsonSource:
    rel_path = path.relative_to(data_dir).as_posix()
    size_bytes = path.stat().st_size
    checksum = sha256_file(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:  # report exact source, but never include file body
        recovered, warning = _recover_accessory_candidate_extra_data(rel_path, path)
        if warning:
            return JsonSource(rel_path, path, size_bytes, checksum, recovered, "", warning)
        return JsonSource(rel_path, path, size_bytes, checksum, None, f"{type(exc).__name__}: {exc}")
    except Exception as exc:  # report exact source, but never include file body
        return JsonSource(rel_path, path, size_bytes, checksum, None, f"{type(exc).__name__}: {exc}")
    return JsonSource(rel_path, path, size_bytes, checksum, data, "")


def _recover_accessory_candidate_extra_data(rel_path: str, path: Path) -> tuple[Any | None, str]:
    if not rel_path.startswith("accessory_candidates/"):
        return None, ""
    text = path.read_text(encoding="utf-8")
    decoder = json.JSONDecoder()
    try:
        data, end = decoder.raw_decode(text)
    except json.JSONDecodeError:
        return None, ""
    trailing = text[end:].strip()
    if not trailing:
        return None, ""
    if not isinstance(data, dict):
        return None, ""
    expected_id = path.stem
    if str(data.get("id") or "").strip() != expected_id:
        return None, ""
    return data, "recovered_accessory_candidate_extra_data"


def load_inventory(source: Path) -> SourceInventory:
    data_dir = resolve_data_dir(source)
    service_root = data_dir.parent
    json_sources: list[JsonSource] = []
    for name in ROOT_METADATA_FILES:
        path = data_dir / name
        if path.exists() and path.is_file():
            json_sources.append(_read_json_source(data_dir, path))
    for directory_name, pattern in DIRECTORY_METADATA_GLOBS:
        directory = data_dir / directory_name
        if not directory.exists():
            continue
        for path in sorted(directory.glob(pattern)):
            if path.is_file():
                json_sources.append(_read_json_source(data_dir, path))

    sensitive_sources: list[SensitiveSource] = []
    for name in SENSITIVE_LOCAL_SOURCES:
        path = data_dir / name
        sensitive_sources.append(
            SensitiveSource(
                rel_path=name,
                path=path,
                exists=path.exists(),
                size_bytes=path.stat().st_size if path.exists() else 0,
            )
        )

    return SourceInventory(
        source_root=source.resolve(),
        service_root=service_root,
        data_dir=data_dir,
        json_sources=tuple(json_sources),
        sensitive_sources=tuple(sensitive_sources),
    )
