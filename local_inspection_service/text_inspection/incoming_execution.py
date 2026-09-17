"""Capture admission, durable evidence and unchanged fail-closed OCR orchestration."""
import hashlib
import re
import time
import uuid
from collections.abc import Callable
from typing import Any
import cv2
import numpy as np
from fastapi import HTTPException
from ..incoming_text_inspection import FAIL as INCOMING_TEXT_FAIL, PASS as INCOMING_TEXT_PASS, REVIEW_REQUIRED as INCOMING_TEXT_REVIEW_REQUIRED, normalize_field_rules, decide_inspection, apply_commissioning_gate
from .incoming_ports import IncomingAccess, IncomingReferences, IncomingInspections, IncomingMedia, IncomingOCR, IncomingImaging, Upload


class IncomingExecution:
    def __init__(self, access: IncomingAccess, references: IncomingReferences, inspections: IncomingInspections,
                 media: IncomingMedia, ocr: IncomingOCR, imaging: IncomingImaging,
                 capacity: Callable[[int], None], verified: Callable[[], bool],
                 public: Callable[[dict[str, Any]], dict[str, Any]]):
        self.access, self.references, self.inspections = access, references, inspections
        self.media, self.ocr, self.imaging = media, ocr, imaging
        self.capacity, self.verified, self.public = capacity, verified, public

    async def inspect_incoming_text(self, task_id: str, file: Upload, capture_id: str) -> dict[str, Any]:
        self.access.permission("inspection", detail="没有来料检验权限")
        task = self.access.task(task_id)
        capture_id = capture_id.strip()
        if not re.fullmatch(r"[A-Za-z0-9_.-]{8,128}", capture_id):
            raise HTTPException(status_code=400, detail="capture_id 格式错误")
        owner_user_id = str(task.get("owner_user_id") or self.access.owner(task))
        contents = await file.read()
        if not contents or len(contents) > 20 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="拍照图片必须在 20MB 以内")
        source_hash = hashlib.sha256(contents).hexdigest()
        duplicate = self.inspections.duplicate(owner_user_id, task_id, capture_id)
        if duplicate:
            if duplicate.get("source_sha256") != source_hash:
                raise HTTPException(status_code=409, detail="同一 capture_id 对应了不同图片")
            return self.public(duplicate)
        self.capacity(len(contents))
        active_references = [
            item
            for item in self.references.all()
            if str(item.get("task_id")) == task_id and item.get("status") == "active" and str(item.get("owner_user_id")) == owner_user_id
        ]
        if not active_references:
            raise HTTPException(status_code=409, detail="任务还没有已启用的标准版本")
        if len(active_references) != 1:
            raise HTTPException(status_code=409, detail="任务标准状态异常，请管理员处理后再检验")
        reference = active_references[0]
        image = cv2.imdecode(np.frombuffer(contents, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise HTTPException(status_code=400, detail="拍照图片解码失败")
        image_height, image_width = image.shape[:2]
        if image_width * image_height > 40_000_000 or min(image_width, image_height) < 300:
            raise HTTPException(status_code=400, detail="拍照图片尺寸不符合要求")
        inspection_id = f"itinsp_{uuid.uuid4().hex[:14]}"
        output_dir = self.media.output(f"incoming_text/inspections/{task_id}", owner_user_id)
        source_suffix = ".png" if contents[:8] == b"\x89PNG\r\n\x1a\n" else ".jpg"
        source_path = output_dir / f"{inspection_id}_source{source_suffix}"
        source_path.write_bytes(contents)
        now = int(time.time())
        inspection = {
            "id": inspection_id,
            "capture_id": capture_id,
            "task_id": task_id,
            "reference_id": str(reference["id"]),
            "reference_version_label": str(reference.get("version_label") or ""),
            "reference_sha256": str(reference.get("source_sha256") or ""),
            "material_code": str(task.get("material_code") or ""),
            "material_name": str(task.get("material_name") or ""),
            "status": "processing",
            "auto_decision": "",
            "final_decision": "",
            "source_path": str(source_path),
            "source_sha256": source_hash,
            "created_at": now,
            "updated_at": now,
            "operator_user_id": str(self.access.user().get("id") or ""),
            "owner_user_id": owner_user_id,
            "owner_username": str(task.get("owner_username") or ""),
            "shared_with_user_ids": list(task.get("shared_with_user_ids") or []),
        }
        if not self.inspections.save(inspection, insert_only=True):
            source_path.unlink(missing_ok=True)
            duplicate = self.inspections.duplicate(owner_user_id, task_id, capture_id)
            if duplicate and duplicate.get("source_sha256") == source_hash:
                return self.public(duplicate)
            raise HTTPException(status_code=409, detail="capture_id 已被其他请求占用")
        quality = self.imaging.quality(image)
        try:
            reference_image = cv2.imread(str(reference.get("canonical_path") or ""), cv2.IMREAD_COLOR)
            if reference_image is None:
                raise RuntimeError("reference_image_missing")
            corrected, alignment = self.imaging.rectify(image, (reference_image.shape[1], reference_image.shape[0]))
            can_run_ocr = bool(quality.get("accepted") and alignment.get("accepted"))
            rules = normalize_field_rules(reference.get("rules"))
            first = self.ocr.observe(corrected) if can_run_ocr else []
            gray = cv2.cvtColor(corrected, cv2.COLOR_BGR2GRAY)
            enhanced = cv2.cvtColor(cv2.createCLAHE(clipLimit=1.8, tileGridSize=(8, 8)).apply(gray), cv2.COLOR_GRAY2BGR)
            second_by_field = self.ocr.corroborate(enhanced, rules) if can_run_ocr else {}
            observations = {
                rule["field_id"]: self.ocr.field(
                    rule, first, second_by_field.get(str(rule["field_id"]), []), corrected, reference_image
                )
                for rule in rules
            }
            similarities = {
                rule["field_id"]: score
                for rule in rules
                for score in [self.imaging.similarity(reference_image, corrected, rule["region_normalized"])]
                if score is not None
            }
            result = decide_inspection(rules, observations, quality=quality, alignment=alignment, visual_similarities=similarities)
            result = apply_commissioning_gate(
                result, automatic_decisions_verified=self.verified()
            )
            annotated = self.imaging.annotate(corrected, result["fields"])
            corrected_path = output_dir / f"{inspection_id}_corrected.jpg"
            annotated_path = output_dir / f"{inspection_id}_annotated.jpg"
            if not cv2.imwrite(str(corrected_path), corrected) or not cv2.imwrite(str(annotated_path), annotated):
                raise RuntimeError("evidence_save_failed")
            inspection.update(
                {
                    "status": "completed",
                    "auto_decision": result["decision"],
                    "final_decision": result["decision"] if result["decision"] in {INCOMING_TEXT_PASS, INCOMING_TEXT_FAIL} else "",
                    "quality": quality,
                    "alignment": alignment,
                    "fields": result["fields"],
                    "reasons": result["reasons"],
                    "candidate_decision": result.get("candidate_decision", ""),
                    "corrected_path": str(corrected_path),
                    "annotated_path": str(annotated_path),
                    "ocr_engine": "PaddleOCR-3.7.0/PP-OCRv6-medium/two-pass",
                    "updated_at": int(time.time()),
                }
            )
        except Exception as exc:  # fail closed: engine/files/rules can never yield PASS
            inspection.update(
                {
                    "status": "completed_with_error",
                    "auto_decision": INCOMING_TEXT_REVIEW_REQUIRED,
                    "final_decision": "",
                    "quality": quality,
                    "reasons": ["inspection_engine_error"],
                    "error_code": type(exc).__name__,
                    "updated_at": int(time.time()),
                }
            )
        self.inspections.save(inspection)
        return self.public(inspection)
