"""Text revision publication preserving caller-owned transaction boundaries."""
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol
from fastapi import HTTPException

Record = dict[str, Any]


class SaveRevision(Protocol):
    def __call__(self, kind: str, value: Record, *, insert_only: bool = False) -> bool: ...


@dataclass(frozen=True)
class RevisionRecords:
    load: Callable[[str], list[Record]]
    save: SaveRevision


def confirmed_snapshot(assets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from .preparation_policy import snapshot
    return snapshot(assets)


def expected_revision(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool) or (not isinstance(value, int) and not re.fullmatch(r"[0-9]+", str(value))):
        raise HTTPException(status_code=400, detail="expected_revision 必须为非负整数")
    try:
        revision = int(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="expected_revision 必须为非负整数") from exc
    if revision < 0:
        raise HTTPException(status_code=400, detail="expected_revision 必须为非负整数")
    return revision


class TextRevisions:
    def __init__(self, records: RevisionRecords, snapshot: Callable[[list[Record]], list[Record]]):
        self.records = records
        self.snapshot = snapshot

    def apply(
        self, standard: dict[str, Any], assets: list[dict[str, Any]], *, action: str, asset_id: str, now: int,
    ) -> dict[str, Any]:
        snapshot = self.snapshot(assets)
        current_revision = int(standard.get("revision_number") or 0)
        if standard.get("status") == "confirmed" and action != "confirm" and current_revision == 0:
            legacy_snapshot = [
                dict(item) for item in standard.get("confirmed_assets", [])
                if isinstance(item, dict) and item.get("id")
            ]
            baseline = {
                "id": f"rev_baseline_{standard['id']}", "standard_id": standard["id"],
                "owner_user_id": standard["owner_user_id"], "revision_number": 1,
                "action": "baseline", "asset_id": "", "confirmed_assets": legacy_snapshot,
                "confirmed_asset_ids": [str(item["id"]) for item in legacy_snapshot], "created_at": now,
            }
            existing_baseline = next((
                item for item in self.records.load("revisions")
                if item.get("id") == baseline["id"] and item.get("standard_id") == standard["id"]
            ), None)
            if existing_baseline:
                if existing_baseline.get("confirmed_assets") != legacy_snapshot:
                    raise HTTPException(status_code=409, detail="标准基线修订冲突，请刷新后重试")
            elif not self.records.save("revisions", baseline, insert_only=True):
                raise HTTPException(status_code=409, detail="标准基线修订已存在，请刷新后重试")
            current_revision = 1
        revision_number = current_revision + 1
        revision = {
            "id": "rev_" + uuid.uuid4().hex, "standard_id": standard["id"],
            "owner_user_id": standard["owner_user_id"], "revision_number": revision_number,
            "action": action, "asset_id": asset_id, "confirmed_assets": snapshot,
            "confirmed_asset_ids": [item["id"] for item in snapshot], "created_at": now,
        }
        standard.update({
            "revision_number": revision_number, "current_revision_id": revision["id"],
            "confirmed_assets": snapshot, "confirmed_asset_ids": revision["confirmed_asset_ids"],
            "asset_count": len(snapshot), "updated_at": now,
        })
        self.records.save("revisions", revision, insert_only=True)
        return revision
