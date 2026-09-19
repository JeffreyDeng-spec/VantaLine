"""Reference-sheet rendering and process-local descriptor cache."""
from collections.abc import Callable
from pathlib import Path
from typing import Any
import hashlib
import json
import math
from .media_ports import ReferenceSheetPolicy, ReferenceSheetCache, ReferenceSheetImages, BoundedText

class ReferenceSheet:
    def __init__(self, text: Callable[[], BoundedText], output: Callable[[str], Path],
                 policy: ReferenceSheetPolicy, cache: ReferenceSheetCache, media: ReferenceSheetImages):
        self.text, self.output, self.policy, self.cache, self.media = text, output, policy, cache, media

    def build_reference_sheet_descriptor(self, required_accessories: list[dict[str, Any]]) -> dict[str, Any] | None:
        items: list[dict[str, Any]] = []
        for required in required_accessories:
            item_id = str(required.get("accessory_id") or "")
            profile = required.get("profile") if isinstance(required.get("profile"), dict) else {}
            refs = [ref for ref in profile.get("reference_images", []) if isinstance(ref, dict) and ref.get("source_path")]
            if not refs:
                continue
            ref = refs[0]
            path = Path(str(ref.get("source_path") or ""))
            if not path.exists() or path.suffix.lower() not in self.policy.suffixes():
                continue
            items.append(
                {
                    "accessory_id": item_id,
                    "name": self.text()(required.get("name") or profile.get("name") or item_id, 80),
                    "expected_count": int(required.get("expected_count") or 1),
                    "source_path": str(path),
                    "sha256": str(ref.get("sha256") or hashlib.sha256(path.read_bytes()).hexdigest()),
                }
            )
        if not items:
            return None
        items = sorted(items, key=lambda item: item["accessory_id"])
        digest_payload = {
            "mode": self.policy.mode(),
            "items": [{"accessory_id": item["accessory_id"], "sha256": item["sha256"]} for item in items],
        }
        digest = hashlib.sha256(json.dumps(digest_payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
        sheet_dir = self.output("ai_reference_sheets")
        sheet_dir.mkdir(parents=True, exist_ok=True)
        sheet_path = sheet_dir / f"reference_sheet_{digest[:16]}.jpg"
        with self.cache.lock():
            cached = self.cache.records().get(digest)
            if cached and cached.get("data_url") and cached.get("source_path") == str(sheet_path):
                return dict(cached)
        if not sheet_path.exists():
            cols = 3 if len(items) > 2 else len(items)
            rows = int(math.ceil(len(items) / max(1, cols)))
            cell_w, cell_h, label_h, margin = 560, 620, 86, 24
            sheet_w = cols * cell_w + (cols + 1) * margin
            sheet_h = rows * (cell_h + label_h) + (rows + 1) * margin
            sheet = self.media.arrays().full((sheet_h, sheet_w, 3), 250, dtype=self.media.arrays().uint8)
            for idx, item in enumerate(items):
                row = idx // cols
                col = idx % cols
                x = margin + col * (cell_w + margin)
                y = margin + row * (cell_h + label_h + margin)
                image = self.media.images().imread(item["source_path"], self.media.images().IMREAD_UNCHANGED)
                tile = self.media.fit(image, cell_w, cell_h)
                sheet[y : y + cell_h, x : x + cell_w] = tile
                self.media.images().rectangle(sheet, (x, y), (x + cell_w, y + cell_h), (30, 30, 30), 2)
                label_y = y + cell_h + 30
                self.media.images().putText(sheet, item["accessory_id"], (x + 12, label_y), self.media.images().FONT_HERSHEY_SIMPLEX, 0.78, (0, 0, 0), 2, self.media.images().LINE_AA)
                self.media.images().putText(sheet, item["name"][:42], (x + 12, label_y + 34), self.media.images().FONT_HERSHEY_SIMPLEX, 0.62, (70, 70, 70), 1, self.media.images().LINE_AA)
            self.media.images().imwrite(str(sheet_path), sheet, [int(self.media.images().IMWRITE_JPEG_QUALITY), self.policy.quality()])
        data_url = self.media.encode()(
            sheet_path,
            max_side=self.policy.max_side(),
            quality=self.policy.quality(),
        )
        if not data_url:
            return None
        descriptor = {
            "accessory_id": "__reference_sheet__",
            "data_url": data_url,
            "detail": "low",
            "source_path": str(sheet_path),
            "mode": self.policy.mode(),
            "sheet_items": items,
        }
        with self.cache.lock():
            self.cache.records()[digest] = dict(descriptor)
        return descriptor
