"""Snapshot-bound background task execution with explicit record and generation capabilities."""
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from ..model_profiles.dependencies import ResolverProvider
from ..model_profiles.snapshots import pinned
from .background_codex import GenerateCodexBackground
from .background_variants import CreateBackgroundVariants
from .background_writes import UpdateBackgroundManifest

Record = dict[str, Any]


class UpdateBackgroundTask(Protocol):
    def __call__(self, job_id: str, **updates: Any) -> Record | None: ...


@dataclass(frozen=True)
class BackgroundTaskRecords:
    find: Callable[[str], Record | None]
    path: Callable[[str], Path]
    load: Callable[[], Callable[[Path], Record | None]]
    update_provider: Callable[[], UpdateBackgroundTask]


@dataclass(frozen=True)
class BackgroundTaskGeneration:
    sets: Callable[[], Path]
    safe: Callable[[str], str]
    update_provider: Callable[[], UpdateBackgroundManifest]
    local: CreateBackgroundVariants
    codex: GenerateCodexBackground
    images: Callable[[Path], list[Path]]


class BackgroundTaskRunner:
    def __init__(self, records: BackgroundTaskRecords, generation: BackgroundTaskGeneration,
                 clock: Callable[[], float], resolver: ResolverProvider):
        self.records, self.generation, self.clock = records, generation, clock
        # Bind the bound method once; constructing an application does not resolve models or read a task.
        self.run_background_set_task = pinned(resolver, records.find)(self.run_background_set_task)

    def run_background_set_task(self, job_id: str) -> None:
        task = self.records.load()(self.records.path(job_id))
        if not task:
            return
        set_id = str(task.get("background_set_id") or "")
        source_path = Path(str(task.get("source_path") or ""))
        set_dir = self.generation.sets() / self.generation.safe(set_id)
        try:
            if not source_path.exists():
                raise RuntimeError("上传的背景源图不存在。")
            self.records.update_provider()(job_id, status="running", progress=8, started_at=int(self.clock()), note="背景任务已启动，正在准备源图。")
            self.generation.update_provider()(set_id, status="generating", updated_at=int(self.clock()))
            local_variants = self.generation.local(source_path, set_dir, 5)
            if len(local_variants) < 5:
                raise RuntimeError(f"本地背景变体生成不足：{len(local_variants)}/5。")
            self.records.update_provider()(
                job_id,
                status="running",
                progress=42,
                generated_image_count=1 + len(local_variants),
                note=f"本地背景变体已生成 {len(local_variants)}/5，正在等待 AI 背景生成。",
            )
            codex_outputs = self.generation.codex(source_path, set_dir, set_id, 5)
            if len(codex_outputs) < 5:
                raise RuntimeError(f"AI 背景生成不足：{len(codex_outputs)}/5。")
            image_count = len(self.generation.images(set_dir))
            self.generation.update_provider()(
                set_id,
                status="ready",
                generation_method="queued_codexcli_imgworker_plus_local_same_environment_fallback",
                image_count=image_count,
                completed_at=int(self.clock()),
                updated_at=int(self.clock()),
            )
            self.records.update_provider()(
                job_id,
                status="completed",
                progress=100,
                completed_at=int(self.clock()),
                generated_image_count=image_count,
                note=f"背景集已生成完成，共 {image_count} 张。",
            )
        except Exception as exc:
            self.generation.update_provider()(set_id, status="failed", error=str(exc), updated_at=int(self.clock()))
            self.records.update_provider()(job_id, status="failed", progress=100, completed_at=int(self.clock()), error=str(exc), note=f"背景生成失败：{exc}")
