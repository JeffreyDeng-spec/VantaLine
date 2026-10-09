import hashlib
"""Dedicated camera analysis and durable browser dispatch evidence workflow."""
from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Any
import cv2
import numpy as np
from fastapi import File, Form, HTTPException, Request, UploadFile
from ..plc_fx_ascii import PlcConfigError
from .camera_request_ports import CameraRequestAccess, CameraDispatchEvidence, CameraImageExecution
from ..training.real_photo_provenance import group

@dataclass(frozen=True)
class CameraDetectionRequest:
    access: CameraRequestAccess
    evidence: CameraDispatchEvidence
    images: CameraImageExecution

    async def analyze_camera_image(
        self,
        request: Request,
        file: UploadFile = File(...),
        model_id: str | None = Form(None),
        plc_session_id: str = Form(...),
        camera_request_id: str = Form(...),
    ) -> dict[str, Any]:
        self.access.ensure_dirs()()
        self.access.require_analyze_model_permission()(model_id)
        station = self.access.require_plc_web_serial_station()(request)
        payload = await file.read()
        fingerprint = hashlib.sha256(payload).hexdigest()
        try:
            dispatch, created = self.evidence.plc_web_serial_begin_camera_detection()(
                str(station["id"]),
                plc_session_id,
                camera_request_id,
                str(model_id or "").strip(),
                fingerprint,
            )
        except PlcConfigError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if not created:
            stored_result = dispatch.get("result")
            if isinstance(stored_result, dict):
                return {**stored_result, "plc_sync": self.evidence.plc_web_serial_dispatch_public()(dispatch)}
            raise HTTPException(status_code=409, detail="plc_camera_request_in_progress")

        arr = np.frombuffer(payload, np.uint8)
        image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        dispatch_id = str(dispatch["dispatch_id"])
        if image is None:
            self.evidence.plc_web_serial_finish_camera_detection()(
                str(station["id"]), dispatch_id, plc_session_id, None, "image_decode_failed"
            )
            raise HTTPException(status_code=400, detail="Could not decode image")

        request_id = f"camera_{self.images.safe_name()(camera_request_id)}"
        upload_path = self.images.UPLOAD_DIR() / f"{request_id}{Path(file.filename).suffix.lower() or '.png'}"
        try:
            self.images._business_files().write_bytes(upload_path, payload)
            with group('camera_session:'+str(station['id'])+':'+plc_session_id,original_hash=hashlib.sha256(payload).hexdigest()):
                result = self.images.analyze_bgr()(image, request_id, model_id, image_path=upload_path)
            completed_dispatch = self.evidence.plc_web_serial_finish_camera_detection()(
                str(station["id"]), dispatch_id, plc_session_id, result
            )
            return {**result, "plc_sync": self.evidence.plc_web_serial_dispatch_public()(completed_dispatch)}
        except Exception as exc:
            try:
                self.evidence.plc_web_serial_finish_camera_detection()(
                    str(station["id"]), dispatch_id, plc_session_id, None, type(exc).__name__
                )
            except Exception:
                pass
            raise
