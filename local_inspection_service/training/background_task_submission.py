"""Background task submission retains save, thread creation, registration and start order."""
from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import UUID
from .submission import TrainingSubmissionRecords, TrainingSubmissionThreads

Record = dict[str, Any]


class BackgroundTaskSubmission:
    def __init__(self, records: TrainingSubmissionRecords, threads: TrainingSubmissionThreads,
                 owner: Callable[[], Record], clock: Callable[[], float], uuid: Callable[[], UUID]):
        self.records, self.threads, self.owner = records, threads, owner
        self.clock, self.uuid = clock, uuid

    def enqueue_background_set_task(self, set_id: str, name: str, source_path: Path) -> dict[str, Any]:
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
        thread = self.threads.create(target=self.threads.target(), args=(job_id,), daemon=True, name=f"background-set-task-{job_id}")
        self.threads.records()[job_id] = thread
        thread.start()
        return self.records.public(task)
