"""Detection task/model catalogs with explicit record, request identity and registry ports."""
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

Record = dict[str, Any]


class TrainedSpecs(Protocol):
    def __call__(self, config: Record | None = None) -> list[Record]: ...


@dataclass(frozen=True)
class TaskCatalogSources:
    config: Callable[[], Record]
    tasks: Callable[[], list[Record]]
    trained: TrainedSpecs
    accessory_uid: Callable[[Record], str]
    serialize_accessory: Callable[[Record], Record]


@dataclass(frozen=True)
class TaskCatalogAccess:
    user: Callable[[], Record | None]
    visible: Callable[[Record, Record, str | None], bool]
    owner_username: Callable[[Record], str]


@dataclass(frozen=True)
class TaskModelRegistry:
    base_spec: Callable[[], Record]
    label: Callable[[], str]
    tasks_path: Callable[[], Path]
    legacy_owner: Callable[[], str]
    model_id: Callable[[str], str]


class TaskCatalog:
    def __init__(self, sources: TaskCatalogSources, access: TaskCatalogAccess,
                 registry: TaskModelRegistry, project: Callable[[Record, Record], Record]):
        self.sources, self.access, self.registry, self.project = sources, access, registry, project

    def list_ai_detection_task_model_specs(self, config: dict[str, Any] | None = None, target_user_id: str | None = None) -> list[dict[str, Any]]:
        config = config or self.sources.config()
        specs: list[dict[str, Any]] = []
        user = self.access.user()
        for task in self.sources.tasks():
            if user and not self.access.visible(task, user, target_user_id):
                continue
            payload = self.project(task, config)
            task_id = payload["id"]
            if not task_id or not payload["selected_accessory_ids"]:
                continue
            specs.append(
                {
                    **self.registry.base_spec(),
                    "id": payload["model_id"],
                    "run_id": task_id,
                    "task_id": task_id,
                    "task_label": payload["name"],
                    "task_source": "ai_detection_task_config",
                    "is_specialized": True,
                    "is_ai_detection": True,
                    "variant": "ai_detection",
                    "label": self.registry.label(),
                    "description": "AI检测工具台创建的无训练任务，按配件画像调用无状态 AI 检测。",
                    "selected_accessory_ids": payload["selected_accessory_ids"],
                    "required_accessory_counts": payload["required_accessory_counts"],
                    "accessory_names": payload["accessory_names"],
                    "accessory_labels": payload["accessory_labels"],
                    "artifact_path": "",
                    "metadata_path": str(self.registry.tasks_path()),
                    "missing_accessory_ids": payload["missing_accessory_ids"],
                    "created_at": payload["created_at"],
                    "updated_at": payload["updated_at"],
                    "owner_user_id": payload["owner_user_id"],
                    "owner_username": payload["owner_username"],
                }
            )
        return specs

    def list_ai_detection_specialized_model_specs(self,
        config: dict[str, Any] | None = None,
        trained_specs: list[dict[str, Any]] | None = None,
        target_user_id: str | None = None,
    ) -> list[dict[str, Any]]:
        config = config or self.sources.config()
        trained_specs = trained_specs if trained_specs is not None else self.sources.trained()
        accessories_by_id = {
            str(item.get("id") or self.sources.accessory_uid(item)): self.sources.serialize_accessory(item)
            for item in config.get("accessories", [])
        }
        grouped: dict[str, dict[str, Any]] = {
            str(spec["task_id"]): spec
            for spec in self.list_ai_detection_task_model_specs(config, target_user_id)
        }
        for spec in trained_specs:
            task_id = str(spec.get("task_id") or spec.get("run_id") or "")
            if not task_id:
                continue
            selected_accessory_ids = [str(item_id) for item_id in spec.get("selected_accessory_ids") or []]
            if not selected_accessory_ids:
                continue
            required_counts = {
                str(k): max(1, int(v))
                for k, v in (spec.get("required_accessory_counts") or {}).items()
            } or {item_id: 1 for item_id in selected_accessory_ids}
            accessory_names = [
                str((accessories_by_id.get(item_id) or {}).get("name") or (spec.get("accessory_labels") or {}).get(item_id) or item_id)
                for item_id in selected_accessory_ids
            ]
            current = grouped.setdefault(
                task_id,
                {
                    **self.registry.base_spec(),
                    "id": self.registry.model_id(task_id),
                    "run_id": str(spec.get("run_id") or task_id),
                    "task_id": task_id,
                    "is_specialized": True,
                    "is_ai_detection": True,
                    "variant": "ai_detection",
                    "label": self.registry.label(),
                    "description": "按当前任务配件画像调用无状态 AI 检测。",
                    "selected_accessory_ids": selected_accessory_ids,
                    "required_accessory_counts": required_counts,
                    "accessory_names": accessory_names,
                    "accessory_labels": {item_id: accessory_names[idx] for idx, item_id in enumerate(selected_accessory_ids)},
                    "artifact_path": "",
                    "metadata_path": "",
                    "created_at": spec.get("created_at") or 0,
                    "updated_at": spec.get("updated_at") or spec.get("created_at") or 0,
                    "owner_user_id": spec.get("owner_user_id") or self.registry.legacy_owner(),
                    "owner_username": spec.get("owner_username") or self.access.owner_username(spec),
                },
            )
            for item_id in selected_accessory_ids:
                if item_id not in current["selected_accessory_ids"]:
                    current["selected_accessory_ids"].append(item_id)
                    current["accessory_names"].append(str((accessories_by_id.get(item_id) or {}).get("name") or item_id))
            current["required_accessory_counts"].update(required_counts)
        return list(grouped.values())

    def ai_detection_tasks_response(self,
        config: dict[str, Any],
        selected_id: str | None = None,
        *,
        user: dict[str, Any] | None = None,
        target_user_id: str | None = None,
    ) -> dict[str, Any]:
        user = user or self.access.user()
        raw_tasks = self.sources.tasks()
        if user:
            raw_tasks = [task for task in raw_tasks if self.access.visible(task, user, target_user_id)]
        tasks = [self.project(task, config) for task in raw_tasks]
        seen_ids = {str(task.get("id") or "") for task in tasks}
        trained_specs = [
            spec
            for spec in self.sources.trained(config)
            if not user or self.access.visible(spec, user, target_user_id)
        ]
        for spec in self.list_ai_detection_specialized_model_specs(config, trained_specs, target_user_id):
            task_id = str(spec.get("task_id") or spec.get("run_id") or "").strip()
            if not task_id or task_id in seen_ids:
                continue
            names = [str(name) for name in spec.get("accessory_names") or [] if str(name).strip()]
            tasks.append(
                {
                    "id": task_id,
                    "name": str(spec.get("task_label") or (" + ".join(names) if names else task_id)),
                    "model_id": str(spec.get("id") or self.registry.model_id(task_id)),
                    "source": str(spec.get("task_source") or "trained_model_ai_sync"),
                    "task_type": "trained_model_ai",
                    "accessory_count": len(spec.get("selected_accessory_ids") or []),
                    "selected_accessory_ids": spec.get("selected_accessory_ids") or [],
                    "accessory_names": names,
                    "accessory_labels": spec.get("accessory_labels") or {},
                    "required_accessory_counts": spec.get("required_accessory_counts") or {},
                    "missing_accessory_ids": spec.get("missing_accessory_ids") or [],
                    "created_at": spec.get("created_at") or 0,
                    "updated_at": spec.get("updated_at") or spec.get("created_at") or 0,
                    "owner_user_id": spec.get("owner_user_id") or self.registry.legacy_owner(),
                    "owner_username": spec.get("owner_username") or self.access.owner_username(spec),
                }
            )
            seen_ids.add(task_id)
        return {
            "tasks": tasks,
            "selected_task_id": selected_id or (tasks[0]["id"] if tasks else ""),
        }
