"""Uploaded training backgrounds and task environment captures, preserving file/state write boundaries."""
from collections.abc import Callable, Collection
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
import shutil
from typing import Any, BinaryIO, Protocol
from uuid import UUID
from fastapi import HTTPException
from .background_writes import UpdateBackgroundManifest

Record = dict[str, Any]


class BackgroundUploadFile(Protocol):
    filename: str | None
    file: BinaryIO


@dataclass(frozen=True)
class BackgroundUploadPaths:
    sets: Callable[[], Path]
    suffixes: Callable[[], Collection[str]]


@dataclass(frozen=True)
class BackgroundUploadRecords:
    unique: Callable[[str], str]
    update_provider: Callable[[], UpdateBackgroundManifest]
    enqueue: Callable[[str, str, Path], Record]
    payload: Callable[[str, Record], Record]


class BackgroundUpload:
    def __init__(self, paths: BackgroundUploadPaths, records: BackgroundUploadRecords,
                 owner: Callable[[], Record], clock: Callable[[], float], catalog: Callable[[], Record]):
        self.paths, self.records, self.owner = paths, records, owner
        self.clock, self.catalog = clock, catalog

    async def upload_training_background_set(self,
        name: str,
        file: BackgroundUploadFile,
    ) -> dict[str, Any]:
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in self.paths.suffixes():
            raise HTTPException(status_code=400, detail="Only image background files are supported")
        display_name = name.strip() or Path(file.filename or "background").stem
        set_id = self.records.unique(display_name)
        set_dir = self.paths.sets() / set_id
        set_dir.mkdir(parents=True, exist_ok=True)
        source_path = set_dir / f"source{suffix or '.png'}"
        with source_path.open("wb") as out:
            shutil.copyfileobj(file.file, out)
        meta = self.records.update_provider()(
            set_id,
            id=set_id,
            name=display_name,
            description="用户上传背景生成的同环境背景集",
            source=str(source_path),
            created_at=int(self.clock()),
            generation_method="queued_codexcli_imgworker",
            status="queued",
            **self.owner(),
        )
        task = self.records.enqueue(set_id, display_name, source_path)
        return {
            "status": "queued",
            "task": task,
            "task_id": task["job_id"],
            "background_set": self.records.payload(set_id, meta),
            **self.catalog(),
        }



class BackgroundTaskAccess(Protocol):
    def __call__(self, record: Record, user: Record, *, write: bool = False) -> None: ...


class SaveTaskBackground(Protocol):
    def __call__(self, task_id: str, source_path: Path, user: Record, display_name: str = "") -> Record: ...


class PublicBackgroundState(Protocol):
    def __call__(self, task_id: str, *, user: Record) -> Record: ...


@dataclass(frozen=True)
class BackgroundCaptureIdentity:
    sanitize: Callable[[str], str]
    current: Callable[[], Record]
    public: Callable[[Any], Any]


@dataclass(frozen=True)
class BackgroundCapturePaths:
    suffixes: Callable[[], Collection[str]]
    output: Callable[[], Callable[[str, str], Path]]
    url: Callable[[Path], str]


@dataclass(frozen=True)
class BackgroundCaptureTasks:
    load: Callable[[], list[Record]]
    access: BackgroundTaskAccess
    save: Callable[[Record], Any]


@dataclass(frozen=True)
class BackgroundCaptureSets:
    validate: Callable[[str, Record, Path], Record]
    save: Callable[[], SaveTaskBackground]


@dataclass(frozen=True)
class BackgroundCaptureState:
    lock: Callable[[], AbstractContextManager]
    load: Callable[[str], Record]
    save: Callable[[Record], Any]
    public: PublicBackgroundState


class BackgroundCapture:
    def __init__(self, identity: BackgroundCaptureIdentity, paths: BackgroundCapturePaths,
                 tasks: BackgroundCaptureTasks, background: BackgroundCaptureSets, state: BackgroundCaptureState,
                 clock: Callable[[], float], uuid: Callable[[], UUID]):
        self.identity, self.paths, self.tasks = identity, paths, tasks
        self.background, self.state, self.clock, self.uuid = background, state, clock, uuid

    async def upload_ai_task_environment_background(self,
        task_id: str,
        file: BackgroundUploadFile,
    ) -> dict[str, Any]:
        clean_task_id = self.identity.sanitize(task_id)
        if not clean_task_id:
            raise HTTPException(status_code=404, detail="AI detection task not found")
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in self.paths.suffixes():
            raise HTTPException(status_code=400, detail="Only image background files are supported")
        user = self.identity.current()
        tasks = self.tasks.load()
        task = next((item for item in tasks if item.get("id") == clean_task_id), None)
        if not task:
            raise HTTPException(status_code=404, detail="AI detection task not found")
        self.tasks.access(task, user, write=True)
        capture_dir = self.paths.output()("task_environment_backgrounds", str(user.get("id") or "")) / clean_task_id
        capture_dir.mkdir(parents=True, exist_ok=True)
        source_path = capture_dir / f"environment_{int(self.clock())}_{self.uuid().hex[:6]}{suffix or '.jpg'}"
        with source_path.open("wb") as out:
            shutil.copyfileobj(file.file, out)
        validation = self.background.validate(clean_task_id, task, source_path)
        background_set = self.background.save()(
            clean_task_id,
            source_path,
            user,
            display_name=f"{task.get('name') or clean_task_id} · 空场景背景",
        )
        environment_background = {
            "background_set_id": background_set["id"],
            "captured_at": int(self.clock()),
            "source_path": str(source_path),
            "source_url": self.paths.url(source_path),
            "background_source": background_set.get("source") or "",
            "image_count": background_set.get("image_count") or 0,
            "generation_method": background_set.get("generation_method") or "",
            "validation": validation,
        }
        task["background_set_id"] = background_set["id"]
        task["environment_background"] = environment_background
        self.tasks.save(task)
        with self.state.lock():
            state = self.state.load(clean_task_id)
            state["background_set_id"] = background_set["id"]
            state["environment_background"] = environment_background
            state["task_name"] = task.get("name") or state.get("task_name") or ""
            state["owner_user_id"] = task.get("owner_user_id") or state.get("owner_user_id") or str(user.get("id") or "")
            state["owner_username"] = task.get("owner_username") or state.get("owner_username") or str(user.get("username") or "")
            self.state.save(state)
        response = self.state.public(clean_task_id, user=user)
        response["status"] = "saved"
        response["background_set"] = self.identity.public(background_set)
        return response
