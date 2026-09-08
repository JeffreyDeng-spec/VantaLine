"""Bounded native-media extraction. Context never determines acceptance."""
from __future__ import annotations

import io
import posixpath
import xml.etree.ElementTree as ET
import zipfile

from .document_label_crop import decode, digest
from .text_inspection_v2 import DOCUMENT_MAX_BYTES, UnsafeDocument, _safe_zip_members

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
REL = "http://schemas.openxmlformats.org/package/2006/relationships"


def extract(contents: bytes) -> list[dict]:
    if len(contents) > DOCUMENT_MAX_BYTES:
        raise UnsafeDocument("文档过大")
    try:
        archive = zipfile.ZipFile(io.BytesIO(contents))
    except zipfile.BadZipFile as exc:
        raise UnsafeDocument("DOCX 损坏") from exc
    with archive:
        members = _safe_zip_members(archive)
        if "word/document.xml" not in members or "[Content_Types].xml" not in members:
            raise UnsafeDocument("DOCX 结构不完整")
        for name in members:
            if name.endswith(".rels"):
                for rel in ET.fromstring(archive.read(name)):
                    if rel.get("TargetMode", "").lower() == "external":
                        raise UnsafeDocument("文档包含外部资源")
        assets = {}
        for part in sorted(members):
            if not part.startswith("word/") or "/" in part[5:] or not part.endswith(".xml"):
                continue
            if not (part == "word/document.xml" or part.startswith(("word/header", "word/footer"))):
                continue
            root = ET.fromstring(archive.read(part))
            relpart = "word/_rels/" + part.split("/")[-1] + ".rels"
            rels = {}
            if relpart in members:
                for rel in ET.fromstring(archive.read(relpart)):
                    target = rel.get("Target", "").replace("\\", "/")
                    if ".." in target.split("/") or target.startswith("/"):
                        raise UnsafeDocument("资源路径越界")
                    rels[rel.get("Id")] = posixpath.normpath("word/" + target)
            parents = {child: parent for parent in root.iter() for child in parent}
            # Floating text can be visually overlaid across paragraph boundaries.
            # Without a renderer proving composition, quarantine those parts.
            overlay = any(node.tag.rsplit("}", 1)[-1] in {"txbxContent", "wgp", "grpSp", "group"} for node in root.iter())
            recent = []
            for index, paragraph in enumerate(root.iter(f"{{{W}}}p")):
                text = "".join(node.text or "" for node in paragraph.iter(f"{{{W}}}t"))[:1000]
                if text:
                    recent = (recent + [text])[-4:]
                for node in paragraph.iter():
                    if node.tag.rsplit("}", 1)[-1] not in {"blip", "imagedata"}:
                        continue
                    relid = node.get(f"{{{R}}}embed") or node.get(f"{{{R}}}id")
                    target = rels.get(relid, "")
                    if target not in members or not target.startswith("word/media/"):
                        raise UnsafeDocument("图片关系无效")
                    blob = archive.read(target)
                    sha = digest(blob)
                    if sha not in assets:
                        reason = ""
                        try:
                            image = decode(blob)
                            size = list(image.size)
                        except Exception:
                            size, reason = [], "图片无法安全解码、像素超限或为矢量/多帧对象"
                        assets[sha] = {"sha256": sha, "blob": blob, "size": size, "references": [], "review_reason": reason}
                    ancestors, current = [], node
                    while current in parents:
                        current = parents[current]
                        ancestors.append(current)
                    table = next((a for a in ancestors if a.tag == f"{{{W}}}tc"), None)
                    cell_text = "".join(t.text or "" for t in table.iter(f"{{{W}}}t"))[:1500] if table is not None else ""
                    # Negative srcRect values add outside padding; the complete
                    # native image remains visible. Positive values hide source
                    # content and need rendered review. Keep the exact transform
                    # with the occurrence rather than applying it to source pixels.
                    transforms = [c for a in ancestors if a.tag.rsplit("}", 1)[-1] in {"drawing", "pict"}
                                  for c in a.iter() if c.tag.rsplit("}", 1)[-1] in {"srcRect", "xfrm"}]
                    def hidden_source(c):
                        try:
                            return any(int(v) > 0 for v in c.attrib.values())
                        except ValueError:
                            return True
                    transformed = any((c.tag.rsplit("}", 1)[-1] == "srcRect" and hidden_source(c)) or
                                      (c.tag.rsplit("}", 1)[-1] == "effectLst" and len(c) > 0) or
                                      (c.tag.rsplit("}", 1)[-1] == "xfrm" and any(c.get(k, "0").lower() not in {"0", "false"} for k in ("rot", "flipH", "flipV")))
                                      for a in ancestors if a.tag.rsplit("}", 1)[-1] in {"drawing", "pict"} for c in a.iter())
                    if overlay or transformed:
                        assets[sha]["review_reason"] = "Word 叠加文字、组合或变换未获完整渲染验证"
                    assets[sha]["references"].append({"part": part, "source_part": target, "paragraph_index": index,
                        "context": " / ".join(recent)[-1500:], "table_cell_context": cell_text,
                        "word_transforms": [{"type": c.tag.rsplit("}", 1)[-1], "attributes": c.attrib} for c in transforms]})
            # Objects without native raster media must remain visible as review
            # items instead of disappearing from the import summary.
            for index, node in enumerate(root.iter()):
                if node.tag.rsplit("}", 1)[-1] not in {"object", "wgp", "grpSp", "group", "txbxContent"}:
                    continue
                sha = digest((part + str(index)).encode())
                assets.setdefault(sha, {"sha256": sha, "blob": b"", "size": [],
                    "references": [{"part": part, "object_index": index}],
                    "review_reason": "嵌入对象或组合文字需完整渲染后人工确认；不能只采用底图"})
        if not assets:
            raise UnsafeDocument("文档中没有图片或可复核对象")
        if len(assets) > 250:
            raise UnsafeDocument("文档图片/对象超过 250 项限制")
        return list(assets.values())
