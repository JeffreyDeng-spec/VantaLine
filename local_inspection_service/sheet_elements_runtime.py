"""Lazy, local-only Paddle runtime. No model download is a request side effect."""
from __future__ import annotations
import os
import hashlib
import multiprocessing
import time
import threading
from pathlib import Path

_model = None
_metadata = {}
_lock = threading.Lock()
_process_lock = threading.Lock()
_process = None
_connection = None
_task_id = ""
_deadline = 0.
_worker_metadata = {}


def _local_observations(image):
    global _model, _metadata
    with _lock:
        if _model is not None and _metadata["profile"] != os.environ.get("VANTALINE_SHEET_OCR_PROFILE","medium"):
            raise RuntimeError("restart_required_after_profile_change")
        if _model is None:
            configured = os.environ.get("VANTALINE_SHEET_OCR_MODEL_DIR", "")
            if not configured:
                raise RuntimeError("sheet_ocr_models_not_provisioned")
            base = Path(configured)
            profile=os.environ.get("VANTALINE_SHEET_OCR_PROFILE","medium")
            if profile not in {"small","medium"}:raise RuntimeError("invalid_sheet_ocr_profile")
            names = (f"PP-OCRv6_{profile}_det", f"PP-OCRv6_{profile}_rec", "PP-LCNet_x1_0_textline_ori")
            if not all((base/name/"inference.yml").is_file() and (base/name/"inference.pdiparams").is_file() for name in names):
                raise RuntimeError("sheet_ocr_models_missing")
            hashes={}
            for name in names:
                for filename in ("inference.yml","inference.json","inference.pdiparams"):
                    path=base/name/filename
                    if path.is_file():
                        sha=hashlib.sha256()
                        with path.open("rb") as stream:
                            for chunk in iter(lambda:stream.read(1024*1024),b""):sha.update(chunk)
                        hashes[name+"/"+filename]=sha.hexdigest()
            from paddleocr import PaddleOCR
            _model = PaddleOCR(text_detection_model_name=names[0], text_recognition_model_name=names[1],
                               text_detection_model_dir=str(base/names[0]), text_recognition_model_dir=str(base/names[1]),
                               textline_orientation_model_name=names[2], textline_orientation_model_dir=str(base/names[2]),
                               use_doc_orientation_classify=False, use_doc_unwarping=False,
                               use_textline_orientation=True, device="cpu", cpu_threads=2)
            _metadata={"profile":profile,"paddleocr":"3.7.0","paddle":"3.2.2","artifacts":hashes,"device":"cpu","threads":2}
        import cv2
        result = _model.predict(cv2.cvtColor(image,cv2.COLOR_BGR2RGB))[0]
        raw = result if isinstance(result,dict) else result.json
        if callable(raw): raw = raw()
        if isinstance(raw,str):
            import json
            raw = json.loads(raw)
        raw = raw.get("res",raw)
        return [{"text": text,"confidence": float(score),"polygon": polygon.tolist() if hasattr(polygon,"tolist") else polygon}
                for text,score,polygon in zip(raw.get("rec_texts",[]),raw.get("rec_scores",[]),raw.get("rec_polys",[]))]


def metadata():
    return dict(_worker_metadata)


def begin_task(identifier, deadline):
    global _task_id, _deadline
    _task_id, _deadline = identifier, deadline


def cancel_task(identifier):
    """Terminate only the active task's native process, never a different job."""
    global _process, _connection, _worker_metadata
    with _process_lock:
        if identifier != _task_id:return
        if _process is not None:
            _process.terminate()
            _process.join(timeout=1)
            if _process.is_alive():_process.kill();_process.join(timeout=1)
        if _connection is not None:_connection.close()
        _process=None;_connection=None;_worker_metadata={}


def _child(connection):
    try:
        while True:
            image=connection.recv()
            try:
                values=_local_observations(image)
                connection.send({"observations":values,"metadata":_metadata})
            except Exception as exc:
                connection.send({"error":type(exc).__name__})
    except (EOFError,BrokenPipeError):
        pass
    finally:
        connection.close()


def observations(image):
    """Warm subprocess protects API latency/GIL and permits hard cancellation."""
    global _process, _connection, _worker_metadata
    if time.time() >= _deadline:
        raise TimeoutError("sheet_ocr_deadline")
    with _process_lock:
        if _process is None or not _process.is_alive():
            context=multiprocessing.get_context("spawn")
            parent,child=context.Pipe()
            _process=context.Process(target=_child,args=(child,),daemon=True,name="sheet-local-ocr")
            _process.start();child.close();_connection=parent
        connection=_connection
    try:
        connection.send(image)
        if not connection.poll(max(0,_deadline-time.time())):
            cancel_task(_task_id)
            raise TimeoutError("sheet_ocr_deadline")
        result=connection.recv()
    except (EOFError,BrokenPipeError,OSError):
        raise TimeoutError("sheet_ocr_worker_unavailable") from None
    if "error" in result:
        raise RuntimeError("sheet_ocr_"+result["error"])
    _worker_metadata=result["metadata"]
    return result["observations"]
