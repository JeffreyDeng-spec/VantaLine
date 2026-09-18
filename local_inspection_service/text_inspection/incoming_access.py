"""Owner-only task access and legacy public evidence projection."""
import copy
from collections.abc import Callable
from typing import Any
from urllib.parse import quote
from fastapi import HTTPException

Record = dict[str, Any]


def public_record(record: Record, sanitize: Callable[[Record], Record]) -> Record:
    value = copy.deepcopy(record)
    record_id = str(value.get("id") or "")
    for key in ("source_path", "canonical_path", "corrected_path", "annotated_path"):
        raw_path = str(value.pop(key, "") or "")
        if raw_path:
            asset_kind = key.removesuffix("_path")
            if record_id.startswith("itinsp_"):
                value[f"{asset_kind}_url"] = f"/api/incoming-text/inspections/{quote(record_id)}/evidence/{asset_kind}"
            elif record_id.startswith("itref_"):
                value[f"{asset_kind}_url"] = f"/api/incoming-text/references/{quote(record_id)}/asset/{asset_kind}"
    return sanitize(value)


def task_access_allowed(task: Record, user: Record, is_admin: Callable[[Record], bool], owner: Callable[[Record], str]) -> bool:
    return is_admin(user) or owner(task) == str(user.get("id") or "")


class IncomingTaskAccess:
    def __init__(self, load: Callable[[str], Record | None], user: Callable[[], Record],
                 allowed: Callable[[], Callable[[Record, Record], bool]]):
        self.load, self.user, self.allowed = load, user, allowed

    def require(self, task_id: str, *, write: bool = False) -> Record:
        task = self.load(task_id)
        if not task or str(task.get("task_kind") or "") != "incoming_material_text":
            raise HTTPException(status_code=404, detail="包材文字检验任务不存在")
        if not self.allowed()(task, self.user()):
            raise HTTPException(status_code=404, detail="包材文字检验任务不存在")
        return task
