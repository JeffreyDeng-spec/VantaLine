"""Bounded local OCR worker; never downloads models as a request side effect."""
import multiprocessing
import os
from pathlib import Path
import threading
import time
from types import SimpleNamespace

_lock = threading.Lock()
_process = None
_connection = None


def available():
    configured = os.getenv("VANTALINE_STANDARD_OCR_MODEL_DIR", "")
    if not configured:
        return False
    root = Path(configured)
    return all((root/name/filename).is_file() for name in
               ("PP-OCRv6_medium_det", "PP-OCRv6_medium_rec", "PP-LCNet_x1_0_textline_ori")
               for filename in ("inference.yml", "inference.json", "inference.pdiparams"))


def child(connection):
    try:
        if not available():
            raise RuntimeError("local_ocr_models_not_provisioned")
        os.environ.setdefault("FLAGS_use_mkldnn", "false")
        os.environ.setdefault("FLAGS_use_onednn", "false")
        os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
        from paddleocr import PaddleOCR
        root = Path(os.environ["VANTALINE_STANDARD_OCR_MODEL_DIR"])
        detector, recognizer, orientation = ("PP-OCRv6_medium_det", "PP-OCRv6_medium_rec", "PP-LCNet_x1_0_textline_ori")
        model = PaddleOCR(text_detection_model_name=detector, text_detection_model_dir=str(root/detector),
            text_recognition_model_name=recognizer, text_recognition_model_dir=str(root/recognizer),
            textline_orientation_model_name=orientation, textline_orientation_model_dir=str(root/orientation),
            use_doc_orientation_classify=False, use_doc_unwarping=False, use_textline_orientation=True,
            device="cpu", cpu_threads=2)
        while True:
            image = connection.recv()
            if image is None:
                break
            try:
                raw = model.predict(image)[0]
                # PaddleOCR 3.x returns a mapping-like OCRResult.
                rows = [dict(text=str(text), confidence=float(confidence), polygon=polygon.tolist())
                    for text, confidence, polygon in zip(raw["rec_texts"], raw["rec_scores"], raw["rec_polys"])]
                connection.send({"rows": rows})
            except Exception as exc:
                connection.send({"error": type(exc).__name__})
    except (EOFError, BrokenPipeError):
        pass
    except Exception as exc:
        connection.send({"error": type(exc).__name__})
    finally:
        connection.close()


def stop(graceful=False):
    global _process, _connection
    if _process is not None:
        if graceful and _process.is_alive() and _connection is not None:
            try:
                _connection.send(None)
                _process.join(2)
            except (BrokenPipeError, OSError):
                pass
        if _process.is_alive():
            _process.terminate()
            _process.join(1)
            if _process.is_alive():
                _process.kill()
                _process.join(1)
        _process = None
    if _connection is not None:
        _connection.close()
        _connection = None


def recognize(bgr, timeout=120):
    global _process, _connection
    deadline = time.monotonic()+timeout
    if not _lock.acquire(timeout=max(0, timeout)):
        raise TimeoutError("ocr_queue_timeout")
    try:
        if not available():
            raise RuntimeError("local_ocr_models_not_provisioned")
        if _process is None or not _process.is_alive():
            stop()
            context = multiprocessing.get_context("spawn")
            _connection, channel = context.Pipe()
            _process = context.Process(target=child, args=(channel,), daemon=True)
            _process.start()
            channel.close()
        _connection.send(bgr[:, :, ::-1].copy())
        if not _connection.poll(max(0, deadline-time.monotonic())):
            stop()
            raise TimeoutError("ocr_execution_timeout")
        result = _connection.recv()
        if "error" in result:
            stop()
            raise RuntimeError("local_ocr_failed_"+result["error"])
        return [SimpleNamespace(**r) for r in result["rows"]]
    except (EOFError, OSError):
        stop()
        raise RuntimeError("local_ocr_worker_interrupted") from None
    finally:
        _lock.release()
