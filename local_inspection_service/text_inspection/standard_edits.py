"""Human standard edits; repository transactions and JSON locks stay caller-visible."""
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any
from fastapi import HTTPException
from .standard_ports import (Record, Upload, StandardAccess, StandardRecords,
                             StandardWrites, StandardMedia, StandardRevisions, StandardPreparation)


class StandardEdits:
    def __init__(self, access: StandardAccess, records: StandardRecords,
                 writes: StandardWrites, media: StandardMedia, revisions: StandardRevisions,
                 preparation: StandardPreparation, prepare_image: Callable[[bytes], tuple[bytes, str, str, str]],
                 bounded_text: Callable[[str, int], str]):
        self.access, self.records, self.writes, self.media = access, records, writes, media
        self.revisions, self.preparation = revisions, preparation
        self.prepare_image, self.bounded_text = prepare_image, bounded_text

    async def add_text_inspection_standard_asset(self, standard_id: str, file: Upload, expected_revision: str) -> Record:
        self.access.require_permission("inspection", detail="没有文字检验权限")
        owner_user_id, _ = self.access.owner()
        standard = self.records.owned("standards", standard_id, owner_user_id)
        if standard and standard.get("standard_type") == "manual":
            raise HTTPException(410, "旧说明书标准仅供查阅，请新建任务导入 PDF")
        if not standard:
            raise HTTPException(status_code=404, detail="标准不存在")
        if standard.get("standard_type") != "label":
            raise HTTPException(status_code=409, detail="说明书标准不支持追加标签图片")
        if standard.get('status') == 'deleted':
            raise HTTPException(status_code=409, detail='订单已删除')
        expected = self.revisions.expected(expected_revision)
        contents = await file.read()
        contents, mime, suffix, source_format = self.prepare_image(contents)
        now = int(time.time())
        asset_id = "ast_" + uuid.uuid4().hex
        media_path = self.media.path(owner_user_id, standard_id, f"{asset_id}{suffix}")
        asset = {
            "id": asset_id, "standard_id": standard_id, "owner_user_id": owner_user_id,
            "asset_kind": "label_candidate", "ordinal": 0, "status": "candidate",
            "sha256": self.media.digest(contents), "mime_type": mime, "category": "label",
            "context": self.bounded_text(file.filename or "新增标签图片", 160),
            "source_format": source_format,
            "classification_source": "human", "media_path": str(media_path),
            "created_at": now, "updated_at": now,
        }
        self.media.write(media_path, contents)
        if standard.get("preparation_required"):
            asset["preparation_required"] = True
        repository = self.writes.repository()
        try:
            if repository is not None:
                asset, standard = repository.add_text_inspection_standard_asset(
                    standard_id, owner_user_id, asset,
                    revision_id="rev_" + uuid.uuid4().hex, updated_at=now, expected_revision=expected,
                )
            else:
                with self.writes.guard():
                    standard = self.records.owned("standards", standard_id, owner_user_id) or {}
                    if not standard or standard.get("standard_type") != "label" or standard.get('status') == 'deleted':
                        raise HTTPException(status_code=409, detail="标准状态已变化，请刷新后重试")
                    current_revision = int(standard.get("revision_number") or 0)
                    if expected is not None and expected != current_revision:
                        raise HTTPException(status_code=409, detail="标准已被其他操作更新，请刷新后重试")
                    assets = [
                        item for item in self.records.load("assets")
                        if item.get("standard_id") == standard_id and item.get("owner_user_id") == owner_user_id
                    ]
                    asset["ordinal"] = max((int(item.get("ordinal") or 0) for item in assets), default=0) + 1
                    if not self.records.save("assets", asset, insert_only=True):
                        raise HTTPException(status_code=409, detail="标签图片序号冲突，请刷新后重试")
                    assets.append(asset)
                    if standard.get("status") == "confirmed":
                        self.revisions.apply(standard, assets, action="add", asset_id=asset_id, now=now)
                    else:
                        standard["asset_count"] = len(self.revisions.snapshot(assets))
                        standard["updated_at"] = now
                    self.records.save("standards", standard)
        except HTTPException:
            media_path.unlink(missing_ok=True)
            raise
        except Exception as exc:
            media_path.unlink(missing_ok=True)
            raise HTTPException(status_code=409, detail="标准已被其他操作更新，请刷新后重试") from exc
        return {"asset": self.records.public(asset), "standard": self.records.public(standard)}

    async def patch_text_inspection_asset(self, standard_id: str, asset_id: str, read_body: Callable[[], Awaitable[Any]]) -> Record:
        self.access.require_permission("inspection", detail="没有文字检验权限")
        owner_user_id, _ = self.access.owner()
        standard = self.records.owned("standards", standard_id, owner_user_id)
        if standard and standard.get("standard_type") == "manual":
            raise HTTPException(410, "旧说明书标准仅供查阅，请新建任务导入 PDF")
        asset = self.records.owned("assets", asset_id, owner_user_id)
        if not standard or not asset or asset.get("standard_id") != standard_id:
            raise HTTPException(status_code=404, detail="标准资源不存在")
        body = await read_body()
        action = str(body.get("action") or "") if isinstance(body, dict) else ""
        status_by_action = {"restore": "candidate", "remove": "excluded", "exclude": "excluded", "confirm": "candidate", "review": "needs_confirmation"}
        if action not in status_by_action:
            raise HTTPException(status_code=400, detail="action 必须为 restore、remove、exclude、confirm 或 review")
        expected = self.revisions.expected(body.get("expected_revision") if isinstance(body, dict) else None)
        updated_at = int(time.time())
        revision_id = "rev_" + uuid.uuid4().hex
        repository = self.writes.repository()
        if repository is not None:
            try:
                asset, standard = repository.patch_text_inspection_asset(
                    standard_id, asset_id, owner_user_id, action, updated_at,
                    revision_id=revision_id, expected_revision=expected,
                )
            except Exception as exc:
                raise HTTPException(status_code=409, detail="标准或资源状态已变化，请刷新后重试") from exc
        else:
            with self.writes.guard():
                authoritative_standard = self.records.owned("standards", standard_id, owner_user_id)
                authoritative_asset = self.records.owned("assets", asset_id, owner_user_id)
                if not authoritative_standard or not authoritative_asset or authoritative_standard.get('status') == 'deleted':
                    raise HTTPException(status_code=409, detail="标准或资源状态已变化，请刷新后重试")
                current_revision = int(authoritative_standard.get("revision_number") or 0)
                if expected is not None and expected != current_revision:
                    raise HTTPException(status_code=409, detail="标准已被其他操作更新，请刷新后重试")
                asset = authoritative_asset
                target_status = status_by_action[action]
                if asset.get("status") != target_status or asset.get("classification_source") != "human":
                    asset.setdefault("original_classification", {key: asset.get(key) for key in ("status", "category", "classification_source", "classification_reason")})
                    asset["status"] = target_status
                    asset["updated_at"] = updated_at
                    asset["classification_source"] = "human"
                    self.records.save("assets", asset)
                    assets = [
                        item for item in self.records.load("assets")
                        if item.get("standard_id") == standard_id and item.get("owner_user_id") == owner_user_id
                    ]
                    if authoritative_standard.get("status") == "confirmed":
                        self.revisions.apply(
                            authoritative_standard, assets,
                            action="review" if action == "review" else "restore" if action in {"restore", "confirm"} else "remove",
                            asset_id=asset_id, now=updated_at,
                        )
                    else:
                        authoritative_standard["asset_count"] = len(self.revisions.snapshot(assets))
                        authoritative_standard["updated_at"] = updated_at
                    self.records.save("standards", authoritative_standard)
                standard = authoritative_standard
        feedback = {"id": "fb_" + uuid.uuid4().hex, "owner_user_id": owner_user_id, "standard_id": standard_id, "asset_id": asset_id, "action": action, "created_at": int(time.time())}
        self.records.save("feedback", feedback, insert_only=True)
        return {**self.records.public(asset), "standard": self.records.public(standard)}

    def confirm_text_inspection_standard(self, standard_id: str) -> Record:
        self.access.require_permission("inspection", detail="没有文字检验权限")
        owner_user_id, _ = self.access.owner()
        standard = self.records.owned("standards", standard_id, owner_user_id)
        if standard and standard.get("standard_type") == "manual":
            raise HTTPException(410, "旧说明书标准仅供查阅，请新建任务导入 PDF")
        if not standard:
            raise HTTPException(status_code=404, detail="标准不存在")
        if standard.get("standard_type") == "label" and (self.preparation.enabled(owner_user_id) or standard.get("preparation_required")):
            self.preparation.start(standard_id, owner_user_id)
            return self.records.public(self.records.owned("standards", standard_id, owner_user_id) or standard)
        repository = self.writes.repository()
        if repository is not None:
            try:
                return self.records.public(repository.confirm_text_inspection_standard(
                    standard_id, owner_user_id, int(time.time()), revision_id="rev_" + uuid.uuid4().hex,
                ))
            except Exception as exc:
                raise HTTPException(status_code=409, detail="标准无法确认，请刷新候选状态后重试") from exc
        if standard.get("status") == "confirmed":
            return self.records.public(standard)
        with self.writes.guard():
            standard = self.records.owned("standards", standard_id, owner_user_id) or {}
            if standard.get('status') == 'deleted' or standard.get('classification', {}).get('state') == 'processing':
                raise HTTPException(status_code=409, detail='订单已删除或仍在识别中')
            if standard.get("status") == "confirmed":
                return self.records.public(standard)
            all_assets = [item for item in self.records.load("assets") if item.get("standard_id") == standard_id and item.get("owner_user_id") == owner_user_id]
            if any(item.get("status") == "needs_confirmation" for item in all_assets):
                raise HTTPException(status_code=409, detail="还有待确认图片，请逐张选择保留或排除后再启用")
            selected = [item for item in all_assets if item.get("status") in {"candidate", "page"}]
            if not selected:
                raise HTTPException(status_code=409, detail="至少确认一个标签或标准页面")
            standard["status"] = "confirmed"
            standard["confirmed_at"] = standard["updated_at"] = int(time.time())
            selected.sort(key=lambda item: int(item.get("ordinal") or 0))
            self.revisions.apply(standard, selected, action="confirm", asset_id="", now=standard["confirmed_at"])
            self.records.save("standards", standard)
        return self.records.public(standard)
