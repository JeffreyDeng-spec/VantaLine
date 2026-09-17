"""Legacy standard uploads, version activation and task configuration."""
import copy
import hashlib
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any
import cv2
from fastapi import HTTPException
from ..schemas.text_inspection import IncomingTextRulesRequest
from ..incoming_text_inspection import IncomingTextValidationError, normalize_field_rules
from .incoming_ports import IncomingAccess, IncomingReferences, IncomingTasks, IncomingMedia, IncomingWrites, IncomingJSON, Upload


class IncomingCatalog:
    def __init__(self, access: IncomingAccess, references: IncomingReferences, tasks: IncomingTasks,
                 media: IncomingMedia, writes: IncomingWrites, json: IncomingJSON,
                 public: Callable[[dict[str, Any]], dict[str, Any]], verified: Callable[[], bool]):
        self.access, self.references, self.tasks = access, references, tasks
        self.media, self.writes, self.json = media, writes, json
        self.public, self.verified = public, verified

    def get_incoming_text_task(self, task_id: str) -> dict[str, Any]:
        task = self.access.task(task_id)
        references = [
            self.public(item)
            for item in self.references.all()
            if str(item.get("task_id")) == task_id
        ]
        references.sort(key=lambda item: int(item.get("created_at") or 0), reverse=True)
        active_items = [item for item in references if item.get("status") == "active"]
        active = active_items[0] if len(active_items) == 1 else None
        public_task = self.tasks.public(task, self.tasks.config())
        public_task["status"] = "ready" if active else "configuration_error" if active_items else "setup_required"
        public_task["active_reference_id"] = str(active.get("id") or "") if active else ""
        public_task["reference_version_label"] = str(active.get("version_label") or "") if active else ""
        return {
            "task": public_task,
            "references": references,
            "active_reference": active,
            "configuration_valid": len(active_items) <= 1,
            "automatic_decisions_verified": self.verified(),
        }

    def get_incoming_text_reference_asset(self, reference_id: str, asset_kind: str) -> Path:
        reference = self.references.load(reference_id)
        if not reference:
            raise HTTPException(status_code=404, detail="标准版本不存在")
        self.access.record(reference, self.access.user())
        self.access.task(str(reference.get("task_id")))
        key = {"source": "source_path", "canonical": "canonical_path"}.get(asset_kind)
        path = Path(str(reference.get(key or "") or ""))
        if not key or not path.exists() or not self.media.under(path, self.media.root()):
            raise HTTPException(status_code=404, detail="标准稿文件不存在")
        return path

    async def create_incoming_text_reference(self, task_id: str, file: Upload, version_label: str) -> dict[str, Any]:
        self.access.permission("incoming_material_config", detail="没有包材文字标准配置权限")
        task = self.access.task(task_id, write=True)
        clean_version = version_label.strip()
        if not clean_version or len(clean_version) > 40:
            raise HTTPException(status_code=400, detail="标准版本号必须为 1–40 个字符")
        contents = await file.read()
        image, suffix = self.media.decode(contents, file.filename or "reference")
        owner_user_id = str(task.get("owner_user_id") or self.access.owner(task))
        reference_id = f"itref_{uuid.uuid4().hex[:12]}"
        output_dir = self.media.output(f"incoming_text/references/{task_id}", owner_user_id)
        source_path = output_dir / f"{reference_id}{suffix}"
        canonical_path = output_dir / f"{reference_id}_canonical.png"
        source_path.write_bytes(contents)
        if not cv2.imwrite(str(canonical_path), image):
            source_path.unlink(missing_ok=True)
            raise HTTPException(status_code=500, detail="标准稿规范化图片保存失败")
        now = int(time.time())
        reference = {
            "id": reference_id,
            "task_id": task_id,
            "version_label": clean_version,
            "material_code": str(task.get("material_code") or ""),
            "material_name": str(task.get("material_name") or ""),
            "status": "draft",
            "source_filename": Path(file.filename or "reference").name,
            "source_path": str(source_path),
            "canonical_path": str(canonical_path),
            "source_sha256": hashlib.sha256(contents).hexdigest(),
            "canonical_sha256": hashlib.sha256(canonical_path.read_bytes()).hexdigest(),
            "width": int(image.shape[1]),
            "height": int(image.shape[0]),
            "rules": [],
            "created_at": now,
            "activated_at": 0,
            "created_by_user_id": str(self.access.user().get("id") or ""),
            "owner_user_id": owner_user_id,
            "owner_username": str(task.get("owner_username") or ""),
            "shared_with_user_ids": list(task.get("shared_with_user_ids") or []),
        }
        if not self.references.save(reference, insert_only=True):
            source_path.unlink(missing_ok=True)
            canonical_path.unlink(missing_ok=True)
            raise HTTPException(status_code=409, detail="该标准版本号已存在")
        return self.public(reference)

    def update_incoming_text_reference_rules(self, reference_id: str, request: IncomingTextRulesRequest) -> dict[str, Any]:
        self.access.permission("incoming_material_config", detail="没有包材文字标准配置权限")
        reference = self.references.load(reference_id)
        if not reference:
            raise HTTPException(status_code=404, detail="标准版本不存在")
        self.access.record(reference, self.access.user(), write=True)
        self.access.task(str(reference.get("task_id")), write=True)
        if reference.get("status") != "draft":
            raise HTTPException(status_code=409, detail="已启用的标准不可修改，请新建版本")
        try:
            rules = normalize_field_rules(request.rules)
        except IncomingTextValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None
        reference["rules"] = rules
        reference["updated_at"] = int(time.time())
        if request.activate:
            reference["status"] = "active"
            reference["activated_at"] = int(time.time())
            reference["activated_by_user_id"] = str(self.access.user().get("id") or "")
            repository = self.writes.repository()
            if repository is not None:
                draft = dict(reference)
                draft["status"] = "draft"
                self.references.save(draft)
                repository.activate_incoming_text_reference(
                    reference_id,
                    str(reference.get("owner_user_id")),
                    str(reference.get("task_id")),
                    reference,
                )
            else:
                with self.writes.guard():
                    values = self.json.read(self.json.paths.references())
                    for item in values:
                        if (
                            str(item.get("owner_user_id")) == str(reference.get("owner_user_id"))
                            and str(item.get("task_id")) == str(reference.get("task_id"))
                            and item.get("status") == "active"
                        ):
                            item["status"] = "archived"
                    values = [reference if str(item.get("id")) == reference_id else item for item in values]
                    self.json.write(self.json.paths.references(), values)
            task = self.access.task(str(reference.get("task_id")), write=True)
            task.update(
                {
                    "status": "ready",
                    "active_reference_id": reference_id,
                    "reference_version_label": reference["version_label"],
                    "updated_at": int(time.time()),
                }
            )
            self.tasks.save(task)
        else:
            self.references.save(reference)
        return self.public(reference)

    def clone_incoming_text_reference(self, reference_id: str, version_label: str) -> dict[str, Any]:
        self.access.permission("incoming_material_config", detail="没有包材文字标准配置权限")
        source = self.references.load(reference_id)
        if not source:
            raise HTTPException(status_code=404, detail="标准版本不存在")
        self.access.record(source, self.access.user(), write=True)
        self.access.task(str(source.get("task_id") or ""), write=True)
        clean_version = version_label.strip()
        if not clean_version or len(clean_version) > 40:
            raise HTTPException(status_code=400, detail="标准版本号必须为 1–40 个字符")
        clone = copy.deepcopy(source)
        clone.update(
            {
                "id": f"itref_{uuid.uuid4().hex[:12]}",
                "version_label": clean_version,
                "status": "draft",
                "created_at": int(time.time()),
                "activated_at": 0,
                "created_by_user_id": str(self.access.user().get("id") or ""),
            }
        )
        if not self.references.save(clone, insert_only=True):
            raise HTTPException(status_code=409, detail="该标准版本号已存在")
        return self.public(clone)
