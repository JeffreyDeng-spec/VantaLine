import ast
import csv
import hashlib
import math
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps


ROOT = Path("/mnt/f/CodexWorkspace/assembly_line_optimize")
QUEUE = ROOT / "agent_handoffs/image2_ai_only_pipeline/image2_ai_only_task_queue.csv"
REF = ROOT / "generated_bottle_pose_collection/overhead_bottle_pose_collection_image2.png"
OUT_DIR = ROOT / "image2_ai_only_1000_atom_combinations"
QA_DIR = ROOT / "qa_reports"
CANVAS_SIZE = (1448, 1086)
TASK_START = 57
TASK_END = 106


def crop_to_alpha(rgba: Image.Image) -> Image.Image:
    bbox = rgba.getchannel("A").getbbox()
    return rgba.crop(bbox) if bbox else rgba


def green_alpha(rgb: Image.Image, min_area: int = 20) -> Image.Image:
    arr = np.array(rgb.convert("RGB"))
    hsv = cv2.cvtColor(arr, cv2.COLOR_RGB2HSV)
    h, s, v = cv2.split(hsv)
    background = (h > 35) & (h < 98) & (s > 28) & (v < 205)
    alpha = (~background).astype(np.uint8) * 255
    alpha = cv2.morphologyEx(alpha, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    alpha = cv2.morphologyEx(alpha, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    n, labels, stats, _ = cv2.connectedComponentsWithStats(alpha)
    kept = np.zeros_like(alpha)
    for idx in range(1, n):
        if stats[idx, cv2.CC_STAT_AREA] >= min_area:
            kept[labels == idx] = 255
    return Image.fromarray(kept).filter(ImageFilter.GaussianBlur(0.75))


def lying_alpha(rgb: Image.Image) -> Image.Image:
    # Shape envelope for the near-vertical side-view bottle in the collection.
    w, h = rgb.size
    shape = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(shape)
    d.rounded_rectangle((45, 84, 128, 300), radius=24, fill=42)
    d.rounded_rectangle((39, 66, 130, 118), radius=14, fill=185)
    d.polygon([(56, 12), (100, 8), (123, 67), (44, 72)], fill=230)
    detail = green_alpha(rgb, min_area=8)
    alpha = Image.composite(Image.new("L", (w, h), 255), shape, detail.point(lambda p: 255 if p > 35 else 0))
    # Keep a faint glass body, but avoid carrying a rectangular green patch.
    alpha = Image.composite(alpha, shape, shape.point(lambda p: 255 if p > 0 else 0))
    return alpha.filter(ImageFilter.GaussianBlur(0.7))


def upright_alpha(rgb: Image.Image) -> Image.Image:
    w, h = rgb.size
    shape = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(shape)
    d.ellipse((24, 20, w - 18, h - 16), fill=95)
    d.ellipse((48, 32, w - 40, h - 42), fill=180)
    detail = green_alpha(rgb, min_area=8)
    alpha = Image.composite(Image.new("L", (w, h), 255), shape, detail.point(lambda p: 255 if p > 35 else 0))
    alpha = Image.composite(alpha, shape, shape.point(lambda p: 255 if p > 0 else 0))
    return alpha.filter(ImageFilter.GaussianBlur(0.55))


def make_sprite(crop_box, alpha_func, target_axis: str, target_size: float) -> Image.Image:
    crop = Image.open(REF).convert("RGB").crop(crop_box)
    rgba = crop.convert("RGBA")
    rgba.putalpha(alpha_func(crop))
    rgba = crop_to_alpha(rgba)
    bbox = rgba.getchannel("A").getbbox()
    if not bbox:
        raise RuntimeError(f"No foreground extracted for crop {crop_box}")
    aw = bbox[2] - bbox[0]
    ah = bbox[3] - bbox[1]
    base = ah if target_axis == "height" else aw
    scale = target_size / base
    new_size = (max(1, round(rgba.width * scale)), max(1, round(rgba.height * scale)))
    sprite = rgba.resize(new_size, Image.Resampling.LANCZOS)
    return ImageEnhance.Sharpness(sprite).enhance(1.05)


def proxy_mask(rgb: Image.Image, bbox) -> tuple[tuple[int, int, int, int], np.ndarray]:
    arr = np.array(rgb.convert("RGB"))
    x1, y1, x2, y2 = [int(v) for v in bbox]
    pad = 18
    rx1, ry1 = max(0, x1 - pad), max(0, y1 - pad)
    rx2, ry2 = min(arr.shape[1], x2 + pad), min(arr.shape[0], y2 + pad)
    roi = arr[ry1:ry2, rx1:rx2]
    hsv = cv2.cvtColor(roi, cv2.COLOR_RGB2HSV)
    _, s, v = cv2.split(hsv)
    raw = ((v < 85) & (s < 95)).astype(np.uint8) * 255
    raw = cv2.morphologyEx(raw, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    n, labels, stats, centroids = cv2.connectedComponentsWithStats(raw)
    kept = np.zeros_like(raw)
    cx = (x1 + x2) / 2 - rx1
    cy = (y1 + y2) / 2 - ry1
    best = None
    for idx in range(1, n):
        x, y, w, h, area = stats[idx]
        ccx, ccy = centroids[idx]
        near = abs(ccx - cx) <= (rx2 - rx1) * 0.42 and abs(ccy - cy) <= (ry2 - ry1) * 0.42
        substantial = area >= 90 or max(w, h) >= 24
        if near and substantial:
            score = area - 0.6 * math.hypot(ccx - cx, ccy - cy)
            if best is None or score > best[0]:
                best = (score, idx)
    if best is not None:
        kept[labels == best[1]] = 255
    else:
        # Fallback for tiny upright dots.
        bx1, by1 = max(0, x1 - rx1), max(0, y1 - ry1)
        bx2, by2 = min(raw.shape[1], x2 - rx1), min(raw.shape[0], y2 - ry1)
        kept[by1:by2, bx1:bx2] = raw[by1:by2, bx1:bx2]
    kept = cv2.dilate(kept, np.ones((7, 7), np.uint8), iterations=1)
    kept = cv2.GaussianBlur(kept, (5, 5), 0)
    return (rx1, ry1, rx2, ry2), kept


def inpaint_proxy(rgb: Image.Image, bbox) -> Image.Image:
    arr = np.array(rgb.convert("RGB"))
    (x1, y1, x2, y2), mask = proxy_mask(rgb, bbox)
    if mask.max() == 0:
        return rgb
    roi = arr[y1:y2, x1:x2]
    fixed = cv2.inpaint(cv2.cvtColor(roi, cv2.COLOR_RGB2BGR), mask, 5, cv2.INPAINT_TELEA)
    arr[y1:y2, x1:x2] = cv2.cvtColor(fixed, cv2.COLOR_BGR2RGB)
    return Image.fromarray(arr, "RGB")


def shadow(sprite: Image.Image, opacity: float, blur: int) -> Image.Image:
    out = Image.new("RGBA", sprite.size, (0, 0, 0, 0))
    out.putalpha(sprite.getchannel("A").filter(ImageFilter.GaussianBlur(blur)).point(lambda p: int(p * opacity)))
    return out


def paste_centered(canvas: Image.Image, sprite: Image.Image, center, offset=(5, 7)) -> None:
    x = round(center[0] - sprite.width / 2)
    y = round(center[1] - sprite.height / 2)
    canvas.alpha_composite(shadow(sprite, 0.20, 5), (x + offset[0], y + offset[1]))
    canvas.alpha_composite(sprite, (x, y))


def task_number(task_id: str) -> int:
    return int(task_id.split("-")[1])


def read_tasks() -> list[dict]:
    with QUEUE.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return [r for r in rows if TASK_START <= task_number(r["task_id"]) <= TASK_END]


def center_from_bbox(bbox):
    x1, y1, x2, y2 = bbox
    return ((x1 + x2) / 2, (y1 + y2) / 2)


def render_task(row: dict, lying_base: Image.Image, top_base: Image.Image) -> str:
    src = Path(row["input_image_path"])
    out = Path(row["output_path"])
    image = Image.open(src).convert("RGB")
    if image.size != CANVAS_SIZE:
        raise RuntimeError(f"{row['task_id']}: input size {image.size}")
    state = row["bottle_proxy_state"]
    bbox = ast.literal_eval(row["bottle_proxy_bbox_xyxy"]) if row["bottle_proxy_bbox_xyxy"] else None
    if state != "no_bottle" and bbox:
        image = inpaint_proxy(image, bbox).convert("RGBA")
        if state == "upright_dot":
            target = max(1, bbox[2] - bbox[0])
            sprite = top_base.resize((target, target), Image.Resampling.LANCZOS)
            paste_centered(image, sprite, center_from_bbox(bbox), offset=(3, 4))
        else:
            angle = float(row["bottle_proxy_angle_degrees"])
            sprite = lying_base.rotate(angle, expand=True, resample=Image.Resampling.BICUBIC)
            sprite = crop_to_alpha(sprite)
            paste_centered(image, sprite, center_from_bbox(bbox))
        image = image.convert("RGB")
    out.parent.mkdir(parents=True, exist_ok=True)
    image.save(out, compress_level=4)
    check = Image.open(out)
    if check.size != CANVAS_SIZE or check.format != "PNG":
        raise RuntimeError(f"{row['task_id']}: bad output {check.size} {check.format}")
    return hashlib.sha256(out.read_bytes()).hexdigest()


def make_contact_sheet(rows: list[dict]) -> Path:
    thumb_w, thumb_h = 260, 195
    label_h = 24
    cols = 4
    cell_w, cell_h = thumb_w * 2, thumb_h + label_h
    sheet = Image.new("RGB", (cols * cell_w, math.ceil(len(rows) / cols) * cell_h), "white")
    draw = ImageDraw.Draw(sheet)
    for idx, row in enumerate(rows):
        r = idx // cols
        c = idx % cols
        x, y = c * cell_w, r * cell_h
        inp = Image.open(row["input_image_path"]).convert("RGB")
        out = Image.open(row["output_path"]).convert("RGB")
        bbox = ast.literal_eval(row["bottle_proxy_bbox_xyxy"]) if row["bottle_proxy_bbox_xyxy"] else None
        if bbox:
            d = ImageDraw.Draw(inp)
            d.rectangle(bbox, outline=(255, 0, 0), width=5)
        inp_t = ImageOps.contain(inp, (thumb_w, thumb_h), Image.Resampling.LANCZOS)
        out_t = ImageOps.contain(out, (thumb_w, thumb_h), Image.Resampling.LANCZOS)
        sheet.paste(inp_t, (x, y + label_h))
        sheet.paste(out_t, (x + thumb_w, y + label_h))
        draw.text((x + 6, y + 5), f"{row['task_id']} {row['bottle_proxy_state']}  input | output", fill=(0, 0, 0))
    QA_DIR.mkdir(parents=True, exist_ok=True)
    path = QA_DIR / "image2_prod01_0057_0106_proxy_vs_output.jpg"
    sheet.save(path, quality=92)
    return path


def main():
    rows = read_tasks()
    if len(rows) != TASK_END - TASK_START + 1:
        raise RuntimeError(f"Expected 50 rows, got {len(rows)}")
    # Side-view bottle from the vertical pose in the generated collection.
    lying_base = make_sprite((300, 320, 475, 650), lying_alpha, "height", 315)
    # Upright/top-down bottle from the generated collection; resized per dot bbox.
    top_base = make_sprite((1080, 120, 1285, 335), upright_alpha, "width", 39)
    hashes = []
    for row in rows:
        hashes.append((row["task_id"], render_task(row, lying_base, top_base)))
        print(f"wrote {row['task_id']} {Path(row['output_path']).name}")
    qa_path = make_contact_sheet(rows)
    print(f"written={len(hashes)}")
    print(f"qa_sheet={qa_path}")
    print(f"first_hash={hashes[0][1]}")
    print(f"last_hash={hashes[-1][1]}")


if __name__ == "__main__":
    main()
