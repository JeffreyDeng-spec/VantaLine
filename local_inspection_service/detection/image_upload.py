"""Ordinary uploaded-image decoding, persistence and analysis."""
from collections.abc import Callable
from typing import Any
from pathlib import Path
from fastapi import UploadFile, HTTPException
from .analysis_ports import AnalysisCall
from .upload_ports import UploadAccess, UploadPaths, ImageArrays, ImageDecoder

class ImageUpload:
    def __init__(self, access: UploadAccess, paths: UploadPaths,
                 arrays: Callable[[], ImageArrays], images: Callable[[], ImageDecoder], analyze: AnalysisCall):
        self.access, self.paths, self.arrays, self.images, self.analyze = access, paths, arrays, images, analyze

    async def analyze_image(self, file: UploadFile, model_id: str | None) -> dict[str, Any]:
        self.access.ensure()
        self.access.permit(model_id)
        payload = await file.read()
        arr = self.arrays().frombuffer(payload, self.arrays().uint8)
        image = self.images().imdecode(arr, self.images().IMREAD_COLOR)
        if image is None:
            raise HTTPException(status_code=400, detail='Could not decode image')
        request_id = self.paths.name()(file.filename).rsplit('.', 1)[0]
        upload_path = self.paths.directory() / f"{request_id}{Path(file.filename).suffix.lower() or '.png'}"
        upload_path.write_bytes(payload)
        return self.analyze(image, request_id, model_id, image_path=upload_path)
