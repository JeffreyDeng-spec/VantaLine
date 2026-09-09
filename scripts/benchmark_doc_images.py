#!/usr/bin/env python3
"""Local real-DOC image extraction evidence. Never writes production standards."""
import argparse
import hashlib
import html
import io
import json
from pathlib import Path
import sys
import time

from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local_inspection_service.document_images import extract_doc_images


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    report, sections = [], []
    for doc_no, source in enumerate(sorted(args.input_dir.glob("*.doc")), 1):
        data = source.read_bytes(); start = time.monotonic()
        metadata, blobs = extract_doc_images(data)
        elapsed = round(time.monotonic()-start, 3)
        folder = args.output / f"doc{doc_no}"; folder.mkdir()
        cards = []
        for item, blob in zip(metadata, blobs):
            name = f"image{item['ordinal']:04d}"
            (folder / (name+".bin")).write_bytes(blob)
            preview = "不可预览；原始图片文件已保留"
            try:
                if item["classification_reason"] != "direct_doc_embedded_image_manual_review": raise ValueError("preview disabled")
                with Image.open(io.BytesIO(blob)) as image:
                    image = image.convert("RGB"); image.thumbnail((800, 800))
                    image.save(folder / (name+".jpg"))
                preview = f'<img src="doc{doc_no}/{name}.jpg" loading="lazy">'
            except Exception: pass
            cards.append(f'<article><h3>{name}</h3>{preview}<p>{html.escape(item["mime_type"])} · {item["width"]}×{item["height"]}</p><a href="doc{doc_no}/{name}.bin">原始图片</a></article>')
        (folder / "manifest.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2))
        row = {"document": source.name, "source_sha256": hashlib.sha256(data).hexdigest(), "images": len(metadata),
               "unique_images": len({x["sha256"] for x in metadata}), "elapsed_seconds": elapsed,
               "preview_unavailable": sum(x["classification_reason"] != "direct_doc_embedded_image_manual_review" for x in metadata)}
        report.append(row); print(json.dumps(row, ensure_ascii=False), flush=True)
        sections.append(f'<h2>{html.escape(source.name)}：{len(metadata)} 张 / {elapsed}s</h2><div class="grid">'+"".join(cards)+"</div>")
    (args.output / "summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    (args.output / "index.html").write_text('<!doctype html><meta charset="utf-8"><title>DOC 内嵌图片提取</title><style>body{font:16px sans-serif;margin:30px;background:#f5f5f5}.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:16px}article{background:white;padding:14px}img{width:100%;height:220px;object-fit:contain}</style><h1>DOC 原始图片提取测试</h1><p>预览按比例缩小；下载为提取的原始图片。没有叠加 Word 文字、没有模型分类、没有写入生产。</p>'+"".join(sections))


if __name__ == "__main__": main()
