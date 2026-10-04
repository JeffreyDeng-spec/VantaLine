"""Storage identities and validation, independent of application and cloud SDKs."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
from pathlib import Path, PurePosixPath
import re
from typing import BinaryIO

BUSINESS_ROOTS = frozenset({
    "outputs", "uploads", "backgrounds", "normalized_assets", "auto_optimize",
    "codex_comparisons", "accessory_candidates", "incoming_anchor_guides",
    "training_tasks", "label_inspection", "text_inspection_v2", "training_jobs",
    "image_worker_logs", "anchor_pose_guides",
})


class ArtifactUnavailable(RuntimeError):
    """Storage failed without disclosing SDK requests, credentials or source paths."""


class ArtifactIntegrityError(ArtifactUnavailable):
    pass


class DiskCapacityError(ArtifactUnavailable):
    pass


class ArtifactConflict(RuntimeError):
    """The expected logical-path generation is no longer current."""


def logical_path(value: str) -> str:
    parts = value.split("/")
    if (not value or "\\" in value or "\x00" in value or
            any(p in {"", ".", ".."} for p in parts) or parts[0] not in BUSINESS_ROOTS):
        raise ValueError("invalid business file path")
    for part in parts:
        lower = part.lower()
        if (part.startswith(".") or "secret" in lower or "credential" in lower or
                lower.endswith((".pem", ".key", ".env", ".p12", ".pfx")) or
                lower in {"auth.json", "config.json", "config.last_good.json", "ai_config.local.json"}):
            raise ValueError("local-only file cannot enter object storage")
    return PurePosixPath(value).as_posix()


def checksum(stream: BinaryIO, *, limit: int | None = None) -> tuple[str, int]:
    sha, size = hashlib.sha256(), 0
    while block := stream.read(1024 * 1024):
        size += len(block)
        if limit is not None and size > limit:
            raise ArtifactIntegrityError("object exceeds its recorded length")
        sha.update(block)
    return sha.hexdigest(), size


def checksum_file(path: Path) -> tuple[str, int]:
    with path.open("rb") as stream:
        return checksum(stream)


@dataclass(frozen=True)
class Artifact:
    path: str
    generation: int
    sha256: str
    size: int
    state: str = "ready"

    def __post_init__(self):
        logical_path(self.path)
        if (type(self.generation) is not int or self.generation < 1 or
                type(self.size) is not int or self.size < 0 or
                not re.fullmatch("[a-f0-9]{64}", self.sha256) or
                self.state not in {"ready", "deleted"}):
            raise ValueError("invalid artifact identity")

    @property
    def key(self) -> str:
        return f"objects/sha256/{self.sha256[:2]}/{self.sha256}"
