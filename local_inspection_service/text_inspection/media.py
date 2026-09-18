"""Owned text evidence and lazy PDF page media; no application imports."""
import os
import re
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from fastapi import HTTPException

Record = dict[str, Any]


@dataclass(frozen=True)
class TextMediaRecords:
    owned: Callable[[], Callable[[str, str, str], Record | None]]
    save: Callable[[str, Record], bool]


class TextMedia:
    def __init__(self, directory: Callable[[], Path], digest: Callable[[bytes], str], records: TextMediaRecords):
        self.directory = directory
        self.digest = digest
        self.records = records


    def media_path(self, owner_user_id: str, standard_id: str, filename: str) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", owner_user_id + standard_id + filename):
            raise HTTPException(status_code=400, detail="资源标识无效")
        base = (self.directory() / owner_user_id / standard_id).resolve()
        target = (base / filename).resolve()
        if base not in target.parents:
            raise HTTPException(status_code=400, detail="资源路径无效")
        return target

    def write(self, path: Path, contents: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.parent / f".{uuid.uuid4().hex[:12]}.tmp"
        temp.write_bytes(contents)
        os.replace(temp, path)

    def read_verified(self, path_value: str, owner_user_id: str, standard_id: str, *, expected_sha256: str = "", max_bytes: int = 120 * 1024 * 1024) -> bytes:
        path = Path(path_value).resolve()
        allowed = (self.directory() / owner_user_id / standard_id).resolve()
        if allowed not in path.parents or not path.is_file() or path.is_symlink():
            raise HTTPException(status_code=404, detail="标准资源不存在")
        stat = path.stat()
        if stat.st_size <= 0 or stat.st_size > max_bytes:
            raise HTTPException(status_code=409, detail="标准资源大小异常")
        contents = path.read_bytes()
        if expected_sha256 and self.digest(contents) != expected_sha256:
            raise HTTPException(status_code=409, detail="标准资源完整性校验失败")
        return contents

    def asset_bytes(self, asset: dict[str, Any], owner_user_id: str) -> bytes:
        media_path = str(asset.get("media_path") or "")
        if media_path:
            return self.read_verified(media_path, owner_user_id, str(asset.get("standard_id") or ""), expected_sha256=str(asset.get("sha256") or ""))
        if asset.get("asset_kind") != "manual_page":
            raise HTTPException(status_code=404, detail="标准资源不存在")
        standard = self.records.owned()("standards", str(asset.get("standard_id") or ""), owner_user_id)
        if not standard:
            raise HTTPException(status_code=404, detail="说明书标准源文件不存在")
        source_bytes = self.read_verified(str(standard.get("source_path") or ""), owner_user_id, str(standard.get("id") or ""), expected_sha256=str(standard.get("source_sha256") or ""))
        import fitz

        document = fitz.open(stream=source_bytes, filetype="pdf")
        try:
            page_index = int(asset.get("ordinal") or 0) - 1
            if page_index < 0 or page_index >= document.page_count:
                raise HTTPException(status_code=404, detail="标准页不存在")
            page = document.load_page(page_index)
            matrix = fitz.Matrix(1.5, 1.5)
            projected = page.rect * matrix
            if projected.width * projected.height > 20_000_000:
                raise HTTPException(status_code=400, detail="标准页渲染像素过大")
            pixmap = page.get_pixmap(matrix=matrix, alpha=False)
            contents = pixmap.tobytes("png")
        finally:
            document.close()
        path = self.media_path(owner_user_id, str(asset["standard_id"]), f"{asset['id']}.png")
        self.write(path, contents)
        asset["media_path"] = str(path)
        asset["sha256"] = self.digest(contents)
        asset["updated_at"] = int(time.time())
        self.records.save("assets", asset)
        return contents
