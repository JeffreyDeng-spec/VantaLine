"""Detection task HTTP workflows with existing persistence and authorization order."""
from dataclasses import dataclass
from typing import Any
from fastapi import HTTPException
from ..schemas.detection import AiDetectionTaskRequest
from .task_request_ports import TaskRequestAccess, TaskRequestPolicy, TaskRequestStore, TaskPipelineSync, TaskRequestClock

@dataclass(frozen=True)
class DetectionTaskRequests:
    access: TaskRequestAccess
    policy: TaskRequestPolicy
    store: TaskRequestStore
    pipeline: TaskPipelineSync
    clock: TaskRequestClock

    def get_ai_detection_tasks(self, user_id: str | None = None) -> dict[str, Any]:
        user = self.access.current_auth_user()()
        target_user_id = user_id if self.access.user_is_admin()(user) else None
        config = self.access.scope_config_for_user()(self.store.load_config()(), user, target_user_id)
        with self.pipeline._pipeline_tasks_lock():
            tasks = self.pipeline.load_pipeline_tasks()()
            if self.pipeline.sync_ready_pipeline_ai_detection_tasks()(tasks, config, user, target_user_id):
                self.pipeline.save_pipeline_tasks()(tasks)
        return self.policy.ai_detection_tasks_response()(config, user=user, target_user_id=target_user_id)


    def create_ai_detection_task(self, request: AiDetectionTaskRequest) -> dict[str, Any]:
        user = self.access.current_auth_user()()
        config = self.access.scope_config_for_user()(self.store.load_config()(), user)
        payload = self.policy.ai_detection_task_payload_from_request()(request, config)
        self.policy.assert_unique_task_name()(payload["name"], self.access.resource_owner_id_for_new_record()(user))
        now = self.clock.time().time()
        task = {
            "id": f"aitask_{self.clock.uuid().uuid4().hex[:10]}",
            "created_at": now,
            "updated_at": now,
            **self.access.current_owner_fields()(),
            **payload,
        }
        self.store.save_ai_detection_task()(task, prepend=True)
        response = self.policy.ai_detection_tasks_response()(self.access.scope_config_for_user()(config, user), task["id"], user=user)
        response["status"] = "saved"
        response["task"] = self.policy.serialize_ai_detection_task()(task, config)
        return response


    def update_ai_detection_task(self, task_id: str, request: AiDetectionTaskRequest) -> dict[str, Any]:
        user = self.access.current_auth_user()()
        clean_task_id = self.policy.sanitize_ai_detection_task_id()(task_id)
        config = self.access.scope_config_for_user()(self.store.load_config()(), user)
        payload = self.policy.ai_detection_task_payload_from_request()(request, config)
        existing = self.store.find_ai_detection_task()(clean_task_id)
        if existing:
            self.access.require_record_access()(existing, user, write=True)
            self.policy.assert_unique_task_name()(payload["name"], self.access.record_owner_id()(existing), exclude_ai_task_id=clean_task_id)
            task = {
                **existing,
                **payload,
                "id": clean_task_id,
                "created_at": float(existing.get("created_at") or self.clock.time().time()),
                "updated_at": self.clock.time().time(),
            }
            self.store.save_ai_detection_task()(task)
            response = self.policy.ai_detection_tasks_response()(self.access.scope_config_for_user()(config, user), clean_task_id, user=user)
            response["status"] = "saved"
            response["task"] = self.policy.serialize_ai_detection_task()(task, config)
            return response
        raise HTTPException(status_code=404, detail="AI detection task not found")


    def delete_ai_detection_task_record(self, task_id: str, user: dict[str, Any], *, missing_ok: bool = False) -> str | None:
        clean_task_id = self.policy.sanitize_ai_detection_task_id()(task_id)
        existing = self.store.find_ai_detection_task()(clean_task_id)
        if not existing:
            if missing_ok:
                return None
            raise HTTPException(status_code=404, detail="AI detection task not found")
        self.access.require_record_access()(existing, user, write=True)
        repository = self.store.runtime_postgres_repository_or_none()()
        if repository is not None:
            self.store.store_read_cache_invalidate()("ai_detection_tasks")
            repository.delete_by_primary_key("ai_detection_tasks", {"id": clean_task_id})
        else:
            tasks = self.store.load_ai_detection_tasks()()
            remaining = [task for task in tasks if task.get("id") != clean_task_id]
            self.store.save_ai_detection_tasks()(remaining)
        return clean_task_id


    def delete_ai_detection_task(self, task_id: str) -> dict[str, Any]:
        user = self.access.current_auth_user()()
        config = self.store.load_config()()
        clean_task_id = self.store.delete_ai_detection_task_record()(task_id, user) or self.policy.sanitize_ai_detection_task_id()(task_id)
        self.pipeline.mark_pipeline_ai_task_deleted()(clean_task_id, user)
        response = self.policy.ai_detection_tasks_response()(self.access.scope_config_for_user()(config, user), user=user)
        response["status"] = "deleted"
        response["deleted_task_id"] = clean_task_id
        return response
