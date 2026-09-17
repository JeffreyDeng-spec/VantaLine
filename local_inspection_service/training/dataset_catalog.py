"""Dataset manifest projection and ordered, permission-aware filesystem lookup."""
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any, Protocol

Record = dict[str, Any]


class DatasetItem(Protocol):
    def __call__(self, directory: Path, *, include_samples: bool = True) -> Record | None: ...


class FindDataset(Protocol):
    def __call__(self, dataset_id: str, user: Record | None = None, *,
                 include_samples: bool = False, write: bool = False) -> tuple[Path | None, Record | None]: ...


@dataclass(frozen=True)
class DatasetPaths:
    output: Callable[[], Path]
    resolve: Callable[[], Callable[[Any], Path]]
    roots: Callable[[], list[Path]]
    clean: Callable[[str], str]


@dataclass(frozen=True)
class DatasetAudit:
    fields: Callable[[Record, Path], Record]
    created: Callable[[], Callable[[Record, Path], Any]]
    updated: Callable[[], Callable[[Record, Path], Any]]


@dataclass(frozen=True)
class DatasetAccess:
    visible: Callable[[Record, Record], bool]
    mutable: Callable[[Record, Record], bool]


def clean_training_resource_id(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "_", str(value or "")).strip("._")


class DatasetCatalog:
    def __init__(self, paths: DatasetPaths, read: Callable[[Path], Any], audit: DatasetAudit,
                 access: DatasetAccess, item: DatasetItem):
        self.paths, self.read, self.audit = paths, read, audit
        self.access, self.item = access, item

    def dataset_resource_item(self, dataset_dir: Path, *, include_samples: bool = True) -> dict[str, Any] | None:
        manifest_path = dataset_dir / "manifest.json"
        if not manifest_path.exists():
            return None
        manifest = self.read(manifest_path)
        if not isinstance(manifest, dict):
            return None
        raw_samples = manifest.get("samples") if isinstance(manifest.get("samples"), list) else []
        audit = self.audit.fields(manifest, dataset_dir)
        samples = []
        if include_samples:
            # Per-sample hydration touches the filesystem (resolve + exists + stat fallbacks),
            # so it only runs when the caller actually needs sample payloads.
            for sample in raw_samples:
                if not isinstance(sample, dict):
                    continue
                sample_path = self.paths.resolve()(sample.get("image")) if sample.get("image") else dataset_dir
                sample_copy = dict(sample)
                sample_copy.update(
                    {
                        "created_at": self.audit.created()(sample_copy, sample_path if sample_path.exists() else dataset_dir),
                        "updated_at": self.audit.updated()(sample_copy, sample_path if sample_path.exists() else dataset_dir),
                        "owner_user_id": str(sample_copy.get("owner_user_id") or audit["owner_user_id"]),
                        "owner_username": str(sample_copy.get("owner_username") or audit["owner_username"]),
                    }
                )
                samples.append(sample_copy)
        sample_count = len(samples) if include_samples else len([s for s in raw_samples if isinstance(s, dict)])
        item = {
            "id": dataset_dir.name,
            "kind": "dataset",
            "display_name": manifest.get("display_name") or dataset_dir.name,
            "note": manifest.get("note") or "",
            "path": str(dataset_dir),
            "manifest_path": str(manifest_path),
            "sample_count": sample_count or manifest.get("sample_count") or 0,
            "created_at": audit["created_at"],
            "updated_at": audit["updated_at"],
            "selected_accessory_ids": manifest.get("selected_accessory_ids") or [],
            "background_set_id": manifest.get("background_set_id") or "",
            "owner_user_id": audit["owner_user_id"],
            "owner_username": audit["owner_username"],
            "samples_loaded": bool(include_samples),
        }
        if include_samples:
            item["samples"] = samples
        return item

    def training_task_dataset_resource_id(self, task: dict[str, Any]) -> str:
        dataset_dir_value = str(task.get("dataset_dir") or "").strip()
        if not dataset_dir_value:
            return ""
        return self.paths.clean(Path(dataset_dir_value).name)

    def find_dataset_resource(self,
        dataset_id: str,
        user: dict[str, Any] | None = None,
        *,
        include_samples: bool = False,
        write: bool = False,
    ) -> tuple[Path | None, dict[str, Any] | None]:
        clean_id = self.paths.clean(dataset_id)
        if not clean_id:
            return None, None
        for root in self.paths.roots():
            candidate_dir = root / clean_id
            if not candidate_dir.exists() or not candidate_dir.is_dir():
                continue
            item = self.item(candidate_dir, include_samples=include_samples)
            if not item:
                continue
            if user:
                allowed = self.access.mutable(item, user) if write else self.access.visible(item, user)
                if not allowed:
                    continue
            return candidate_dir, item
        return None, None

    def training_dataset_roots(self) -> list[Path]:
        roots = [self.paths.output() / "training_datasets"]
        users_root = self.paths.output() / "users"
        if users_root.exists():
            roots.extend(path / "training_datasets" for path in users_root.iterdir() if path.is_dir())
        return roots

    def training_run_roots(self) -> list[Path]:
        roots = [self.paths.output() / "training_runs"]
        users_root = self.paths.output() / "users"
        if users_root.exists():
            roots.extend(path / "training_runs" for path in users_root.iterdir() if path.is_dir())
        return roots
