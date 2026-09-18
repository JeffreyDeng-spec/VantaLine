"""Task environment background replacement using request-local arguments and narrow storage ports."""
from collections.abc import Callable, Collection
from dataclasses import dataclass
from pathlib import Path
import shutil
from typing import Any
from .background_variants import CreateBackgroundVariants
from .background_writes import UpdateBackgroundManifest

Record = dict[str, Any]


@dataclass(frozen=True)
class TaskBackgroundIdentity:
    sanitize: Callable[[str], str]
    fallback: Callable[[str], str]
    safe: Callable[[], Callable[[str], str]]
    legacy_owner: Callable[[], str]


@dataclass(frozen=True)
class TaskBackgroundPaths:
    sets: Callable[[], Path]
    suffixes: Callable[[], Collection[str]]


@dataclass(frozen=True)
class TaskBackgroundRecords:
    update_provider: Callable[[], UpdateBackgroundManifest]
    payload: Callable[[str, Record], Record]


class TaskBackgroundStore:
    def __init__(self, identity: TaskBackgroundIdentity, paths: TaskBackgroundPaths,
                 records: TaskBackgroundRecords, create: CreateBackgroundVariants,
                 images: Callable[[Path], list[Path]], clock: Callable[[], float]):
        self.identity, self.paths, self.records = identity, paths, records
        self.create, self.images, self.clock = create, images, clock

    def save_task_environment_background_set(self, task_id: str, source_path: Path, user: dict[str, Any], display_name: str = "") -> dict[str, Any]:
        clean_task_id = self.identity.sanitize(task_id) or self.identity.fallback(task_id)
        set_id = self.identity.safe()(f"task_env_{clean_task_id}")
        set_dir = self.paths.sets() / set_id
        if set_dir.exists():
            shutil.rmtree(set_dir, ignore_errors=True)
        set_dir.mkdir(parents=True, exist_ok=True)
        suffix = source_path.suffix.lower() if source_path.suffix.lower() in self.paths.suffixes() else ".jpg"
        target_path = set_dir / f"source{suffix}"
        shutil.copy2(source_path, target_path)
        self.create(target_path, set_dir, count=5)
        image_count = len(self.images(set_dir))
        meta = self.records.update_provider()(
            set_id,
            id=set_id,
            name=display_name or f"任务空场景背景 · {clean_task_id}",
            description="用户首次检测前通过摄像头采集的空白生产环境背景",
            source=str(target_path),
            created_at=int(self.clock()),
            updated_at=int(self.clock()),
            status="ready" if image_count else "empty",
            image_count=image_count,
            generation_method="camera_empty_environment_local_variants",
            owner_user_id=str(user.get("id") or self.identity.legacy_owner()),
            owner_username=str(user.get("username") or user.get("name") or ""),
            shared_with_user_ids=[],
        )
        return self.records.payload(set_id, meta)
