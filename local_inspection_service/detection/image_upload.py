import hashlib
"""Ordinary uploaded-image decoding, persistence and analysis."""
from ..storage.artifacts.files import BusinessFiles
_business_files = BusinessFiles()
from collections.abc import Callable
from typing import Any
from pathlib import Path
from fastapi import UploadFile, HTTPException
from .analysis_ports import AnalysisCall
from .upload_ports import UploadAccess, UploadPaths, ImageArrays, ImageDecoder
from ..training.real_photo_provenance import group
import uuid
import re

class ImageUpload:
    def __init__(self, access: UploadAccess, paths: UploadPaths,
                 arrays: Callable[[], ImageArrays], images: Callable[[], ImageDecoder], analyze: AnalysisCall):
        self.access, self.paths, self.arrays, self.images, self.analyze = access, paths, arrays, images, analyze

    async def analyze_image(self, file: UploadFile, model_id: str | None, capture_session_id: str | None = None) -> dict[str, Any]:
        capture_session_id=capture_session_id if isinstance(capture_session_id,str) else None
        self.access.ensure()
        self.access.permit(model_id)
        payload = await file.read()
        arr = self.arrays().frombuffer(payload, self.arrays().uint8)
        image = self.images().imdecode(arr, self.images().IMREAD_COLOR)
        if image is None:
            raise HTTPException(status_code=400, detail='Could not decode image')
        request_id = self.paths.name()(file.filename).rsplit('.', 1)[0]
        upload_path = self.paths.directory() / f"{request_id}{Path(file.filename).suffix.lower() or '.png'}"
        _business_files.write_bytes(upload_path, payload)
        if capture_session_id and not re.fullmatch(r'[a-zA-Z0-9_-]{1,128}',capture_session_id):
            raise HTTPException(422,'Invalid camera capture session')
        source_group='camera_session:'+capture_session_id if capture_session_id else 'upload_batch:'+uuid.uuid4().hex
        with group(source_group,original_hash=hashlib.sha256(payload).hexdigest()):
            return self.analyze(image, request_id, model_id, image_path=upload_path)
