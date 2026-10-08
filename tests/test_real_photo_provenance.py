"""Unleased camera grouping remains ordinary upload metadata, bound to exact bytes."""
import asyncio
import io
from types import SimpleNamespace
from fastapi import UploadFile
import cv2
import numpy as np
from PIL import Image
from local_inspection_service.detection import image_upload
from local_inspection_service.storage.artifacts.files import BusinessFiles
from local_inspection_service.training.real_photo_contracts import digest
from local_inspection_service.training.real_photo_provenance import source_group,original_sha


def test_camera_grouping_has_no_dispatch_and_preserves_original(tmp_path,monkeypatch):
    out=io.BytesIO();Image.new('RGB',(32,24),'blue').save(out,'JPEG');raw=out.getvalue()
    monkeypatch.setattr(image_upload,'_business_files',BusinessFiles(runtime_provider=lambda:None))
    observed=[]
    def analyze(pixels,request_id,model_id,**kwargs):
        observed.append((source_group.get(),original_sha.get(),kwargs['image_path'].read_bytes()))
        return {'ok':True}
    upload=image_upload.ImageUpload(SimpleNamespace(ensure=lambda:None,permit=lambda m:None),
        SimpleNamespace(name=lambda:lambda n:'capture.jpg',directory=lambda:tmp_path),lambda:np,lambda:cv2,analyze)
    for _ in range(2):
        result=asyncio.run(upload.analyze_image(UploadFile(filename='input.jpg',file=io.BytesIO(raw)),'model','session_1'))
        assert result=={'ok':True}
    assert observed==[('camera_session:session_1',digest(raw),raw)]*2
    assert source_group.get()==original_sha.get()==''
