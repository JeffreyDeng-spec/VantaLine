"""Direct legacy DOC picture extraction. No office conversion or page rendering."""
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import tempfile
import threading
import warnings
import zipfile

from PIL import Image

MAX_INPUT = 30 * 1024 * 1024
MAX_OUTPUT = 100 * 1024 * 1024
_slot = threading.BoundedSemaphore(1)


class DocImageError(ValueError): pass
class DocImageUnavailable(DocImageError): pass


def _runtime():
    root = os.environ.get("VANTALINE_DOC_IMAGE_BUNDLE", "")
    java = shutil.which("java")
    if not root or not java:
        raise DocImageUnavailable("DOC 图片提取组件未就绪，请联系管理员或暂时使用 DOCX")
    try:
        bundle = Path(root).resolve()
        manifest = json.loads((bundle / "manifest.json").read_text())
        source = Path(__file__).with_name("workers") / "doc_image_extractor/DocImages.java"
        locked = json.loads(source.with_name("dependencies.json").read_text())
        if manifest["version"] != "doc-images-v1" or manifest["poi"] != "5.5.1" or manifest["source_sha256"] != hashlib.sha256(source.read_bytes()).hexdigest():
            raise ValueError("version mismatch")
        jars = []
        if {name: digest for name, digest in manifest["files"].items() if name != "doc-images.jar"} != locked:
            raise ValueError("dependency lock mismatch")
        for name, digest in manifest["files"].items():
            if not re.fullmatch(r"(?:lib/)?[A-Za-z0-9_.-]+\.jar", name): raise ValueError("invalid path")
            path = (bundle / name).resolve()
            if not path.is_relative_to(bundle) or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise ValueError("checksum mismatch")
            jars.append(str(path))
        if "doc-images.jar" not in manifest["files"] or len(jars) != 9: raise ValueError("incomplete bundle")
        return java, os.pathsep.join(jars)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise DocImageUnavailable("DOC 图片提取组件版本或校验失败，请联系管理员") from exc


def _metadata(blob, ordinal, seen):
    digest = hashlib.sha256(blob).hexdigest()
    width = height = 0
    mime = "application/octet-stream"
    reason = "direct_doc_embedded_image_manual_review"
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            image = Image.open(io.BytesIO(blob))
        with image:
            width, height = image.size
            mime = Image.MIME.get(image.format, mime)
            if image.format in {"WMF", "EMF"}:
                reason = "vector_image_requires_review"
            elif width * height > 24_000_000:
                reason, mime = "embedded_image_preview_too_large", "application/octet-stream"
    except Exception: reason = "embedded_image_preview_unavailable"
    asset_id = f"asset_{ordinal:04d}_{digest[:12]}"
    result = {"asset_id": asset_id, "ordinal": ordinal, "sha256": digest, "width": width, "height": height,
              "mime_type": mime, "source_part": f"doc-picture-{ordinal}", "context": "",
              "status": "needs_confirmation", "category": "possible_label", "classification_confidence": 0,
              "classification_source": "unclassified", "classification_reason": reason,
              "extraction_method": "poi-hwpf-5.5.1", "duplicate_of": seen.get(digest, "")}
    seen.setdefault(digest, asset_id)
    return result


def _read_output(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_OUTPUT:
        raise DocImageError("DOC 图片提取输出无效或超过限制")
    metadata, blobs, seen = [], [], {}
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            if len(infos) > 501 or sum(x.file_size for x in infos) > MAX_OUTPUT:
                raise DocImageError("DOC 图片数量或大小超过限制")
            if len({x.filename for x in infos}) != len(infos): raise DocImageError("重复图片条目")
            if archive.getinfo("manifest.tsv").file_size > 100_000: raise DocImageError("图片清单过大")
            lines = archive.read("manifest.tsv").decode().splitlines()
            if not lines or lines[0] != "doc-images-v1\tpoi-5.5.1": raise DocImageError("图片清单版本错误")
            names = []
            for ordinal, line in enumerate(lines[1:], 1):
                name, offset = line.split("\t")
                if name != f"image{ordinal:04d}.bin" or not re.fullmatch(r"-?\d+", offset): raise DocImageError("图片清单无效")
                if archive.getinfo(name).file_size > MAX_INPUT: raise DocImageError("单张图片过大")
                blob = archive.read(name)
                if not blob: raise DocImageError("提取到空图片")
                item = _metadata(blob, ordinal, seen)
                item["source_offset"] = int(offset)
                metadata.append(item); blobs.append(blob); names.append(name)
            if not names or set(names + ["manifest.tsv"]) != {x.filename for x in infos}:
                raise DocImageError("图片清单不完整或没有内嵌图片")
    except (zipfile.BadZipFile, KeyError, UnicodeError, ValueError) as exc:
        if isinstance(exc, DocImageError): raise
        raise DocImageError("DOC 图片提取输出损坏") from exc
    return metadata, blobs


def extract_doc_images(data):
    if not data.startswith(bytes.fromhex("d0cf11e0a1b11ae1")) or len(data) > MAX_INPUT:
        raise DocImageError("不是有效的二进制 Word DOC 文件，或超过 30MB")
    java, classpath = _runtime()
    if not _slot.acquire(blocking=False):
        raise DocImageUnavailable("正在提取其他 DOC 的图片，请稍后重试")
    try:
        with tempfile.TemporaryDirectory(prefix="vantaline-doc-images-") as temporary:
            work = Path(temporary)
            source, output = work / "source.doc", work / "images.zip"
            source.write_bytes(data)
            # No shell, no inherited provider credentials/JAVA_TOOL_OPTIONS,
            # no application callbacks, macros, external links or rendering.
            env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": temporary, "TMPDIR": temporary, "LANG": "C.UTF-8"}
            command = [java, "-Xmx256m", "-Djava.awt.headless=true", "-Djava.io.tmpdir="+temporary,
                       "-cp", classpath, "DocImages", str(source), str(output)]
            try:
                process = subprocess.Popen(command, cwd=work, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            except OSError as exc: raise DocImageUnavailable("无法启动 DOC 图片提取组件") from exc
            try: code = process.wait(timeout=30)
            except subprocess.TimeoutExpired as exc:
                os.killpg(process.pid, signal.SIGKILL); process.wait()
                raise DocImageError("DOC 图片提取超过 30 秒，请检查文件") from exc
            if code: raise DocImageError("无法提取 DOC 图片，文档可能已加密、损坏或版本不支持")
            return _read_output(output)
    finally: _slot.release()
