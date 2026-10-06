"""Background task submission retains save, thread creation, registration and start order."""
from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import UUID
from .submission import TrainingSubmissionRecords, TrainingSubmissionThreads
from ..runtime.training_tasks import TrainingTaskRuntime, ThreadLaunch

Record = dict[str, Any]


class BackgroundTaskSubmission:
    def __init__(self, records: TrainingSubmissionRecords, threads: TrainingSubmissionThreads,
                 owner: Callable[[], Record], clock: Callable[[], float], uuid: Callable[[], UUID], *,
                 runtime: TrainingTaskRuntime | None = None):
        self.records, self.threads, self.owner = records, threads, owner
        self.clock, self.uuid = clock, uuid
        self.runtime = runtime if runtime is not None else TrainingTaskRuntime()

    def enqueue_background_set_task(self, set_id: str, name: str, source_path: Path) -> dict[str, Any]:
        return self.runtime.submit(lambda launch: self._enqueue_background_set_task(set_id, name, source_path, launch))

    def _enqueue_background_set_task(self, set_id: str, name: str, source_path: Path, launch: ThreadLaunch) -> Record:
        job_id = f"background_{int(self.clock())}_{self.uuid().hex[:6]}"
        task = {
            "job_id": job_id,
            "task_id": job_id,
            "candidate_id": job_id,
            "candidate_name": name or set_id.replace("_", " "),
            "label": f"添加背景：{name or set_id.replace('_', ' ')}",
            "queue_kind": "training",
            "action": "generate_background_set",
            "status": "queued",
            "progress": 0,
            "created_at": int(self.clock()),
            "background_set_id": set_id,
            "source_path": str(source_path),
            "sample_count": 0,
            "estimated_minutes": 10,
            "note": "背景生成任务已加入队列；完成前该背景集不会进入可选列表。",
            **self.owner(),
        }
        self.records.save(task)
        def register(thread):
            self.threads.records()[job_id] = thread
        launch(lambda wrap: self.threads.create(target=wrap(self.threads.target()), args=(job_id,), daemon=True, name=f"background-set-task-{job_id}"), register)
        return self.records.public(task)
