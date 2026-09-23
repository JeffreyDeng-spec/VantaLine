"""Pipeline task update behavior; caller owns the task and process lock."""
from typing import Any
from ..schemas.pipeline import PipelineTaskUpdateRequest
from .task_update_ports import TaskUpdateAccess, TaskUpdatePolicy, TaskUpdateRuntime


class PipelineTaskUpdater:
    def __init__(self, access: TaskUpdateAccess, policy: TaskUpdatePolicy, runtime: TaskUpdateRuntime):
        self.access = access
        self.policy = policy
        self.runtime = runtime

    def update(self, task_id: str, request: PipelineTaskUpdateRequest) -> dict[str, Any]:
        user = self.access.current_user()()
        config = self.access.scope_config()(self.access.load_config()(), user)
        with self.runtime.lock():
            task = self.access.load_task()(task_id)
            if not task:
                raise self.access.http_error()(status_code=404, detail="流水线任务不存在")
            self.access.require_record_access()(task, user, write=True)
            if str(task.get("task_kind") or "") == "incoming_material_text":
                self.access.require_permission()("incoming_material_config", detail="没有包材文字标准配置权限")
                if (
                    request.accessory_ids is not None
                    or request.accessory_counts is not None
                    or request.detection_method not in {None, "label_text_compare"}
                    or request.params is not None
                    or request.auto_advance is not None
                    or request.expected_production_count is not None
                ):
                    raise self.access.http_error()(status_code=409, detail="包材文字任务不进入配件或训练配置")
                if request.material_code is not None:
                    material_code = request.material_code.strip()
                    if not material_code:
                        raise self.access.http_error()(status_code=400, detail="物料编码不能为空")
                    task["material_code"] = material_code
                if request.material_name is not None:
                    task["material_name"] = request.material_name.strip()
                if request.inspection_user_ids is not None:
                    raise self.access.http_error()(status_code=409, detail="包材文字任务固定归创建账号使用，不支持重新分配")
                if request.name is not None and request.name.strip():
                    next_name = request.name.strip()
                    self.access.assert_unique_name()(next_name, self.access.record_owner_id()(task), exclude_pipeline_task_id=task_id)
                    task["name"] = next_name
                task["updated_at"] = int(self.runtime.now()())
                self.runtime.save_task()(task)
                return self.runtime.public_task()(task, config)
            if request.name is not None and request.name.strip():
                next_name = request.name.strip()
                self.access.assert_unique_name()(next_name, self.access.record_owner_id()(task), exclude_pipeline_task_id=task_id)
                task["name"] = next_name
            if request.accessory_ids is not None:
                if task.get("stage") != "draft":
                    raise self.access.http_error()(status_code=409, detail="任务已经开始执行,不能再修改配件")
                accessory_ids = self.policy.canonical_accessory_ids()(config, request.accessory_ids)
                task["accessory_ids"] = accessory_ids
                task["accessory_counts"] = self.policy.normalize_accessory_counts()(config, accessory_ids, task.get("accessory_counts"))
                labels, names = self.policy.accessory_snapshot()(config, task, accessory_ids)
                task["accessory_names"] = names
                task["accessory_labels"] = {item_id: labels.get(item_id, names[index]) for index, item_id in enumerate(accessory_ids)}
                task.pop("agent_mcp", None)
            if request.accessory_counts is not None:
                if task.get("stage") != "draft":
                    raise self.access.http_error()(status_code=409, detail="任务已经开始执行,不能再修改配件数量")
                accessory_ids = self.policy.canonical_accessory_ids()(config, [str(item_id) for item_id in task.get("accessory_ids") or []])
                task["accessory_counts"] = self.policy.normalize_accessory_counts()(config, accessory_ids, request.accessory_counts)
                task.pop("agent_mcp", None)
            if request.detection_method is not None:
                if task.get("stage") != "draft":
                    raise self.access.http_error()(status_code=409, detail="任务已经开始执行,不能再修改检测方法")
                detection_method = self.policy.normalize_detection_method()(request.detection_method)
                task["detection_method"] = detection_method
                params = dict(task.get("params") or {})
                if self.policy.method_uses_training()(detection_method):
                    params["train_mode"] = detection_method
                    params.pop("route", None)
                else:
                    params["route"] = detection_method
                    params.pop("train_mode", None)
                task["params"] = params
                task.pop("agent_mcp", None)
            if request.params is not None:
                params = dict(task.get("params") or {})
                for key in ("sample_count", "epochs", "image_size", "expected_production_count"):
                    if key in request.params:
                        try:
                            params[key] = int(request.params[key])
                        except (TypeError, ValueError):
                            pass
                requested_method = self.policy.normalize_detection_method()(str(request.params.get("train_mode") or request.params.get("route") or ""))
                if requested_method in self.policy.detection_methods():
                    task["detection_method"] = requested_method
                    if self.policy.method_uses_training()(requested_method):
                        params["train_mode"] = requested_method
                        params.pop("route", None)
                    else:
                        params["route"] = requested_method
                        params.pop("train_mode", None)
                if "background_set_id" in request.params:
                    params["background_set_id"] = request.params["background_set_id"] or None
                if "sample_count" in params:
                    params["sample_count"] = max(50, min(20000, int(params["sample_count"])))
                if "epochs" in params:
                    params["epochs"] = max(1, min(500, int(params["epochs"])))
                if "image_size" in params:
                    params["image_size"] = max(320, min(1280, int(params["image_size"])))
                if "expected_production_count" in params:
                    params["expected_production_count"] = self.policy.normalize_expected_count()(params["expected_production_count"])
                    task["expected_production_count"] = params["expected_production_count"]
                task["params"] = params
            if request.expected_production_count is not None:
                expected_production_count = self.policy.normalize_expected_count()(request.expected_production_count)
                task["expected_production_count"] = expected_production_count
                params = dict(task.get("params") or {})
                params["expected_production_count"] = expected_production_count
                task["params"] = params
            if request.auto_advance is not None:
                task["auto_advance"] = bool(request.auto_advance)
            task["updated_at"] = int(self.runtime.now()())
            self.runtime.save_task()(task)
        return self.runtime.public_task()(task, config)
