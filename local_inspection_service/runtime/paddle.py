"""Unchanged Paddle environment preparation and process-local detection OCR cache."""
import ctypes
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any


def prepare_runtime() -> None:
    os.environ.setdefault("FLAGS_use_mkldnn", "false")
    os.environ.setdefault("FLAGS_use_onednn", "false")
    os.environ.setdefault("FLAGS_enable_pir_api", "0")
    libgomp = Path("/home/dministrator/.local/lib/python3.12/site-packages/torch/lib/libgomp.so.1")
    if libgomp.exists():
        try:
            ctypes.CDLL(str(libgomp), mode=ctypes.RTLD_GLOBAL)
        except OSError:
            pass


def create_detection_ocr() -> Any:
    from paddleocr import PaddleOCR
    return PaddleOCR(
        lang="en",
        text_detection_model_name="PP-OCRv6_small_det",
        text_recognition_model_name="PP-OCRv6_small_rec",
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=True,
    )


class DetectionOCREngine:
    def __init__(self, prepare: Callable[[], None], factory: Callable[[], Any] = create_detection_ocr):
        self.prepare, self.factory = prepare, factory
        self.instance: Any | None = None

    def get(self) -> Any:
        if self.instance is None:
            self.prepare()
            self.instance = self.factory()
        return self.instance
