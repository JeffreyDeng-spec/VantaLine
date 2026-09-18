"""Standard import orchestration with the original partial persistence boundaries."""
import asyncio
import time
import uuid
from collections.abc import Callable
from fastapi import HTTPException
from ..document_images import DocImageError, DocImageUnavailable
from ..text_inspection_v2 import UnsafeDocument
from .standard_ports import (Record, Upload, StandardAccess, StandardRecords,
                             StandardMedia, StandardParsers, StandardClassification)


class StandardImports:
    def __init__(self, access: StandardAccess, records: StandardRecords,
                 media: StandardMedia, parsers: StandardParsers,
                 classification: StandardClassification, bounded_text: Callable[[], Callable[[str, int], str]]):
        self.access, self.records, self.media = access, records, media
        self.parsers, self.classification = parsers, classification
        self.bounded_text = bounded_text

    async def import_text_inspection_standard(self, file: Upload, name: str, material_code: str, version_label: str) -> Record:
        self.access.require_permission("inspection", detail="没有文字检验权限")
        owner_user_id, owner_username = self.access.owner()
        clean_name = self.bounded_text()(name.strip(), 120)
        clean_material = self.bounded_text()(material_code.strip(), 120)
        clean_version = self.bounded_text()(version_label.strip(), 80)
        if not clean_name or not clean_material or not clean_version:
            raise HTTPException(status_code=400, detail="标准名称、物料编码和版本不能为空")
        contents = await file.read(100 * 1024 * 1024 + 1)
        if not contents or len(contents) > 100 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="标准文档不能为空且不能超过 100MB")
        filename = (file.filename or "").lower()
        if filename.endswith(".pdf") or contents.startswith(b"%PDF-"):
            raise HTTPException(410, "旧说明书流程已只读，请在文字检验新建任务中导入 PDF")
        digest = self.media.digest(contents)
        duplicate = next((
            item for item in self.records.load("standards")
            if str(item.get("owner_user_id")) == owner_user_id
            and item.get("source_sha256") == digest
            and item.get("material_code") == clean_material
            and item.get("version_label") == clean_version
        ), None)
        if duplicate:
            if duplicate.get('status') == 'deleted':
                raise HTTPException(status_code=409, detail='该物料版本已删除并保留历史，请使用新的版本号导入')
            return {**self.records.public()(duplicate), "duplicate": True}
        standard_id = "std_" + uuid.uuid4().hex
        now = int(time.time())
        try:
            if filename.endswith(".doc") and not filename.endswith(".docx"):
                metadata, blobs = await asyncio.to_thread(self.parsers.doc(), contents)
                standard_type, extension = "label", ".doc"
            elif filename.endswith(".docx"):
                metadata, blobs = self.parsers.docx(contents)
                standard_type, extension = "label", ".docx"
            elif filename.endswith(".pdf"):
                info = self.parsers.pdf(contents)
                metadata = [{"asset_id": f"asset_{index:04d}_{digest[:12]}", "ordinal": index, "status": "page", "category": "manual_page", "classification_confidence": 1.0} for index in range(1, int(info["page_count"]) + 1)]
                blobs, standard_type, extension = [], "manual", ".pdf"
            else:
                raise HTTPException(status_code=400, detail="仅支持 DOC、DOCX 或 PDF 标准文档")
        except DocImageUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except DocImageError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except UnsafeDocument as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        source_path = self.media.path(owner_user_id, standard_id, "source" + extension)
        self.media.write()(source_path, contents)
        standard = {"id": standard_id, "owner_user_id": owner_user_id, "owner_username": owner_username, "name": clean_name, "material_code": clean_material, "version_label": clean_version, "standard_type": standard_type, "status": "draft", "source_sha256": digest, "source_path": str(source_path), "created_at": now, "updated_at": now, "asset_count": len(metadata)}
        if not self.records.save("standards", standard, insert_only=True):
            raise HTTPException(status_code=409, detail="相同物料、版本和类型的标准已存在")
        for index, item in enumerate(metadata):
            asset_id = "ast_" + uuid.uuid4().hex
            asset_path = ""
            if standard_type == "label":
                suffix = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp", "image/bmp": ".bmp", "image/gif": ".gif", "image/tiff": ".tiff", "image/emf": ".emf", "image/wmf": ".wmf"}.get(str(item.get("mime_type")), ".bin")
                path = self.media.path(owner_user_id, standard_id, f"{asset_id}{suffix}")
                self.media.write()(path, blobs[index])
                asset_path = str(path)
            asset = {**item, "id": asset_id, "standard_id": standard_id, "owner_user_id": owner_user_id, "asset_kind": "label_candidate" if standard_type == "label" else "manual_page", "media_path": asset_path, "created_at": now, "updated_at": now}
            if standard_type == 'label':
                asset.update(status='needs_confirmation', classification_source='unclassified', classification_reason='等待视觉模型识别')
            self.records.save("assets", asset, insert_only=True)
        if standard_type == 'label':
            try:
                self.classification.start(standard_id, owner_user_id)
            except HTTPException as exc:
                self.classification.mark_unavailable()(standard_id, owner_user_id, str(exc.detail))
            standard = self.records.owned('standards', standard_id, owner_user_id) or standard
        return {**self.records.public()(standard), "assets": [self.records.public()(item) for item in self.records.load("assets") if item.get("standard_id") == standard_id]}
