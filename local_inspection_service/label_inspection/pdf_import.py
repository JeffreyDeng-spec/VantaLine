"""Deterministic bounded PDF rendering; originals and display-space clips are retained."""

import io
import math
import threading
import time
import uuid

from PIL import Image
from . import model
from ..codex_compare.contracts import digest
from ..codex_compare.media import MediaStore
from ..storage.label_inspection import LabelRepository

MAX_BYTES = 200 * 1024 * 1024
VERSION = "pdf-split-render-v1"


def inspect(data):
    import fitz

    if not data or len(data) > MAX_BYTES or not data.startswith(b"%PDF-"):
        raise ValueError("请上传有效 PDF，文件不得超过 200 MiB")
    try:
        with fitz.open(stream=data, filetype="pdf") as doc:
            if doc.is_repaired:
                raise ValueError("PDF 文件损坏，请重新导出后上传")
            if doc.needs_pass:
                raise ValueError("不支持需要密码的 PDF")
            if not 1 <= len(doc) <= 500:
                raise ValueError("PDF 拆分后必须包含 1 到 500 个标准条目")
            entries = []
            for index, page in enumerate(doc):
                w, h = page.rect.width, page.rect.height
                if not all(math.isfinite(v) and 1 <= v <= 14400 for v in (w, h)):
                    raise ValueError("PDF 页面尺寸无效或过大")
                clips = (
                    [("左", [0, 0, w / 2, h]), ("右", [w / 2, 0, w, h])]
                    if w > h
                    else [("整页", [0, 0, w, h])]
                )
                for side, clip in clips:
                    entries.append(
                        {
                            "page_index": index,
                            "side": side,
                            "clip": clip,
                            "rotation": page.rotation,
                            "page_size": [w, h],
                        }
                    )
                if len(entries) > 500:
                    raise ValueError("PDF 拆分后最多 500 个标准条目")
            return entries
    except ValueError:
        raise
    except Exception:
        raise ValueError("PDF 文件损坏或无法解析") from None


def render(doc, entry):
    import fitz

    page = doc[entry["page_index"]]
    clip = fitz.Rect(entry["clip"])
    scale = 3200 / max(clip.width, clip.height)
    pix = page.get_pixmap(
        matrix=fitz.Matrix(scale, scale), clip=clip, alpha=False, colorspace=fitz.csRGB
    )
    image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    if max(image.size) > 3200:
        image.thumbnail((3200, 3200), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    image.save(out, "PNG")
    return image, out.getvalue()


def process(repo, media, task, token):
    import fitz

    owner, identity = task["owner_user_id"], task["id"]
    try:
        if task["import"]["version"] != VERSION:
            raise ValueError("PDF 导入规则已更新，请重新上传")
        source = media.read(owner, task["source"]["document_sha256"])
        with fitz.open(stream=source, filetype="pdf") as doc:
            assets = list(task["import"].get("assets", []))
            for entry in task["import"]["entries"][len(assets) :]:
                picture, data = render(doc, entry)
                sha = media.put(owner, data)
                assets.append(
                    {
                        "id": "a_"
                        + digest({"task": identity, "ordinal": len(assets) + 1})[:24],
                        "ordinal": len(assets) + 1,
                        "name": f"PDF 第 {entry['page_index']+1} 张 · {entry['side']}",
                        "enabled": True,
                        "pdf": entry,
                        "media": {
                            "original": sha,
                            "image": sha,
                            "preview": media.put(owner, model.jpeg(picture)),
                            "orientation": 1,
                            "size": list(picture.size),
                            "original_size": list(picture.size),
                        },
                    }
                )
                if not repo.pdf_progress(owner, identity, token, assets):
                    return
            repo.pdf_progress(owner, identity, token, assets, complete=True)
    except Exception as exc:
        repo.pdf_progress(
            owner,
            identity,
            token,
            None,
            error=(
                str(exc)[:200]
                if isinstance(exc, ValueError)
                else "PDF 页面渲染失败，请重新上传"
            ),
        )


def register(ns):
    stop = threading.Event()

    def loop():
        while not stop.is_set():
            task = None
            try:
                raw = ns["runtime_postgres_repository_or_none"]()
                if raw:
                    repo = LabelRepository(raw)
                    token = uuid.uuid4().hex
                    task = repo.claim_pdf(token)
                    if task:
                        process(
                            repo,
                            MediaStore(ns["DATA_DIR"] / "label_inspection" / "media"),
                            task,
                            token,
                        )
            finally:
                ns["clear_thread_runtime_repository_selection"]()
            if not task:
                stop.wait(2)

    def safe_loop():
        while not stop.is_set():
            try:
                loop()
            except Exception:
                stop.wait(2)

    ns["app"].on_event("startup")(
        lambda: threading.Thread(
            target=safe_loop, name="pdf-import", daemon=True
        ).start()
    )
    ns["app"].on_event("shutdown")(stop.set)
