"""Pipeline task creation and its existing partial side effects."""
from typing import Any
from ..schemas.pipeline import PipelineTaskCreateRequest
from .task_create_ports import TaskCreateAccess, TaskCreatePolicy, TaskCreateRuntime


class PipelineTaskCreator:
    def __init__(self, access: TaskCreateAccess, policy: TaskCreatePolicy, runtime: TaskCreateRuntime):
        self.access = access
        self.policy = policy
        self.runtime = runtime

    def create(self, request: PipelineTaskCreateRequest, user_id: str | None = None) -> dict[str, Any]:
        user = self.access.current_user()()
        task_kind = str(request.task_kind or "product_inspection").strip().lower()
        if task_kind == "incoming_material_text":
            self.access.require_permission()("incoming_material_config", detail="没有包材文字标准配置权限")
            self.access.require_permission()("inspection", detail="当前账号没有日常检验权限，不能创建仅供本人使用的包材文字任务")
            if request.inspection_user_ids:
                raise self.access.http_error()(status_code=400, detail="包材文字任务自动归当前账号使用，不支持分配给其他账号")
        else:
            self.access.require_permission()("training_pipeline", detail="没有任务流水线权限")
        if task_kind not in {"product_inspection", "incoming_material_text"}:
            raise self.access.http_error()(status_code=400, detail="不支持的任务类型")
        target_user_id = None if task_kind == "incoming_material_text" else (user_id if self.access.is_admin()(user) else None)
        owner_fields = self.access.owner_fields()(user, target_user_id)
        owner_user_id = str(owner_fields.get("owner_user_id") or self.access.fallback_owner()(user))
        config = self.access.scope_config()(self.access.load_config()(), user, target_user_id)
        accessories_by_id = self.access.accessory_lookup()(config)
        accessory_ids = self.policy.canonical_accessory_ids()(config, request.accessory_ids)
        names = [str(accessories_by_id[item_id].get("name") or item_id) for item_id in accessory_ids]
        labels = {item_id: names[index] for index, item_id in enumerate(accessory_ids)}
        agent_config = self.access.load_agent_config()()
        if task_kind == "incoming_material_text":
            if request.detection_method not in {None, "", "label_text_compare"}:
                raise self.access.http_error()(status_code=400, detail="包材文字任务只能使用 label_text_compare")
            if request.accessory_ids or request.accessory_counts or request.expected_production_count not in {None, 0} or request.auto_advance:
                raise self.access.http_error()(status_code=400, detail="包材文字任务不接受配件、预计产量或自动训练参数")
            detection_method = "label_text_compare"
        else:
            detection_method = self.policy.normalize_detection_method()(request.detection_method)
        expected_production_count = self.policy.normalize_expected_count()(request.expected_production_count)
        if detection_method == "ai" and expected_production_count <= 0:
            raise self.access.http_error()(status_code=400, detail="创建 AI 任务需要填写预计产量")
        material_code = str(request.material_code or "").strip()
        material_name = str(request.material_name or "").strip()
        if task_kind == "incoming_material_text" and not material_code:
            raise self.access.http_error()(status_code=400, detail="创建包材文字任务需要填写物料编码")
        task_name = (request.name or "").strip() or (material_name if task_kind == "incoming_material_text" else (" + ".join(names) if names else "新流水线任务"))
        inspection_user_ids: list[str] = []
        params = {"train_mode": detection_method} if self.policy.method_uses_training()(detection_method) else {"route": detection_method}
        if expected_production_count:
            params["expected_production_count"] = expected_production_count
        task = {
            "id": f"pipe_{self.runtime.uuid4()().hex[:10]}",
            "name": task_name,
            "accessory_ids": accessory_ids,
            "accessory_counts": self.policy.normalize_accessory_counts()(config, accessory_ids, request.accessory_counts),
            "accessory_names": names,
            "accessory_labels": labels,
            "detection_method": detection_method,
            "task_kind": task_kind,
            "material_code": material_code,
            "material_name": material_name,
            "stage": "library" if task_kind == "incoming_material_text" else "draft",
            "status": "setup_required" if task_kind == "incoming_material_text" else "ready",
            "progress": 0,
            "params": params,
            "expected_production_count": expected_production_count,
            "auto_advance": False if task_kind == "incoming_material_text" else bool(request.auto_advance if request.auto_advance is not None else agent_config.get("auto_advance_default", True)),
            "created_at": int(self.runtime.now()()),
            "updated_at": int(self.runtime.now()()),
            **owner_fields,
            "shared_with_user_ids": inspection_user_ids,
        }
        with self.runtime.lock():
            self.policy.assert_unique_name()(task_name, owner_user_id)
            if detection_method == "ai" and accessory_ids:
                self.runtime.activate_ai_task()(task, config)
            self.runtime.save_task()(task)
        if detection_method == "ai" and task.get("ai_task_id"):
            self.runtime.initialize_auto_optimize()(task, config)
            with self.runtime.lock():
                existing = self.runtime.load_task()(str(task.get("id") or ""))
                if existing:
                    task = {**existing, **task, "updated_at": int(self.runtime.now()())}
                    self.runtime.save_task()(task)
        pregen_stage = self.policy.next_recommendation_stage()(task)
        if pregen_stage:
            self.runtime.schedule_pregen()([(str(task.get("id")), pregen_stage)], self.runtime.request_user().get())
        return self.runtime.public_task()(task, config)
