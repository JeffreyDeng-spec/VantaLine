"""Owned resource-name validation across existing catalogs."""
from dataclasses import dataclass
import re
from typing import Any
from fastapi import HTTPException
from .resource_name_ports import NamePolicy, NameCatalogs

@dataclass(frozen=True)
class ResourceNames:
    policy: NamePolicy
    catalogs: NameCatalogs

    def resource_name_key(self, value: Any) -> str:
        return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


    def resource_owner_id_for_new_record(self, user: dict[str, Any]) -> str:
        return str(user.get("id") or self.policy.LEGACY_OWNER_ID())


    def duplicate_name_error(self, resource_label: str) -> None:
        raise HTTPException(status_code=409, detail=f"{resource_label}名称已存在，请换一个名称")


    def assert_unique_accessory_name(self, config: dict[str, Any], name: Any, owner_user_id: str, *, exclude_id: str = "") -> None:
        key = self.policy.resource_name_key()(name)
        if not key:
            return
        for item in config.get("accessories", []):
            if exclude_id and self.policy.accessory_uid()(item) == exclude_id:
                continue
            if self.policy.record_owner_id()(item) == owner_user_id and self.policy.resource_name_key()(item.get("name") or item.get("label")) == key:
                self.policy.duplicate_name_error()("配件")


    def task_record_name(self, record: dict[str, Any]) -> str:
        return str(record.get("name") or record.get("label") or record.get("candidate_name") or record.get("id") or "")


    def task_matches_excluded_identity(self,
        task: dict[str, Any],
        *,
        excluded_pipeline_task_ids: set[str],
        excluded_ai_task_ids: set[str],
    ) -> bool:
        task_id = str(task.get("id") or "")
        if task_id in excluded_pipeline_task_ids:
            return True
        ai_task_id = str(task.get("ai_task_id") or "")
        if ai_task_id and ai_task_id in excluded_ai_task_ids:
            return True
        return False


    def assert_unique_task_name(self,
        name: Any,
        owner_user_id: str,
        *,
        exclude_pipeline_task_id: str = "",
        exclude_ai_task_id: str = "",
    ) -> None:
        key = self.policy.resource_name_key()(name)
        if not key:
            return
        pipeline_tasks = self.catalogs.load_pipeline_tasks()()
        excluded_pipeline_task_ids = {exclude_pipeline_task_id} if exclude_pipeline_task_id else set()
        excluded_ai_task_ids = {exclude_ai_task_id} if exclude_ai_task_id else set()
        for task in pipeline_tasks:
            if exclude_pipeline_task_id and str(task.get("id") or "") == exclude_pipeline_task_id:
                linked_ai_task_id = str(task.get("ai_task_id") or "")
                if linked_ai_task_id:
                    excluded_ai_task_ids.add(linked_ai_task_id)
                break
        for task in pipeline_tasks:
            if self.policy.task_matches_excluded_identity()(
                task,
                excluded_pipeline_task_ids=excluded_pipeline_task_ids,
                excluded_ai_task_ids=excluded_ai_task_ids,
            ):
                continue
            if self.policy.record_owner_id()(task) == owner_user_id and self.policy.resource_name_key()(self.policy.task_record_name()(task)) == key:
                self.policy.duplicate_name_error()("任务")
        for task in self.catalogs.load_ai_detection_tasks()():
            if str(task.get("id") or "") in excluded_ai_task_ids:
                continue
            if self.policy.record_owner_id()(task) == owner_user_id and self.policy.resource_name_key()(self.policy.task_record_name()(task)) == key:
                self.policy.duplicate_name_error()("任务")


    def assert_unique_dataset_name(self, name: Any, owner_user_id: str, user: dict[str, Any], *, exclude_dataset_id: str = "") -> None:
        key = self.policy.resource_name_key()(name)
        if not key:
            return
        for dataset in self.catalogs.training_resources_payload()(user=user).get("datasets", []):
            if exclude_dataset_id and str(dataset.get("id") or "") == exclude_dataset_id:
                continue
            if self.policy.record_owner_id()(dataset) == owner_user_id and self.policy.resource_name_key()(dataset.get("display_name") or dataset.get("id")) == key:
                self.policy.duplicate_name_error()("样本集")


    def assert_unique_model_name(self, name: Any, owner_user_id: str, *, exclude_run_id: str = "") -> None:
        key = self.policy.resource_name_key()(name)
        if not key:
            return
        seen_run_ids: set[str] = set()
        for spec in self.catalogs.list_trained_model_specs()():
            run_id = str(spec.get("run_id") or "")
            if not run_id or run_id in seen_run_ids:
                continue
            seen_run_ids.add(run_id)
            if exclude_run_id and run_id == exclude_run_id:
                continue
            if self.policy.record_owner_id()(spec) == owner_user_id and self.policy.resource_name_key()(spec.get("label") or run_id) == key:
                self.policy.duplicate_name_error()("模型")
