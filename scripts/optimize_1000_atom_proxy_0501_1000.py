import json
import shutil
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter


ROOT = Path("/mnt/f/CodexWorkspace/assembly_line_optimize")
INPUT_DIR = ROOT / "synthetic_1000_atom_proxy_combinations"
OUTPUT_DIR = ROOT / "image2_optimized_1000_atom_proxy_combinations"
MANIFEST = INPUT_DIR / "manifest.json"

IMAGE2_LYING_SOURCE = ROOT / "image2_optimized_31_item_combinations" / "01__bottle_proxy.png"
IMAGE2_UPRIGHT_SOURCE = ROOT / "generated_bottle_pose_collection" / "overhead_bottle_pose_collection_v1.png"

CANVAS_SIZE = (1448, 1086)
LYING_TARGET_ALPHA_HEIGHT = 315
UPRIGHT_TARGET_ALPHA_WIDTH = 108


def green_screen_alpha(rgb_image: Image.Image) -> Image.Image:
    arr = np.array(rgb_image.convert("RGB"))
    hsv = cv2.cvtColor(arr, cv2.COLOR_RGB2HSV)
    h, s, v = cv2.split(hsv)

    # The Image2 bottle assets sit on the same green conveyor. Treat broad green
    # pixels as background while keeping white glass highlights, black cap, and
    # orange nozzle as foreground.
    background = (h > 35) & (h < 95) & (s > 35) & (v < 185)
    alpha = (~background).astype(np.uint8) * 255
    alpha = cv2.morphologyEx(alpha, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    alpha = cv2.morphologyEx(alpha, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))

    n, labels, stats, _ = cv2.connectedComponentsWithStats(alpha)
    kept = np.zeros_like(alpha)
    for idx in range(1, n):
        if stats[idx, cv2.CC_STAT_AREA] > 20:
            kept[labels == idx] = 255
    return Image.fromarray(kept).filter(ImageFilter.GaussianBlur(0.9))


def lying_bottle_alpha(rgb_image: Image.Image) -> Image.Image:
    # Fixed geometry for the vertical single-bottle Image2 asset. This avoids
    # retaining any rectangular source-background patch around transparent glass.
    silhouette = Image.new("L", rgb_image.size, 0)
    draw = ImageDraw.Draw(silhouette)
    draw.rounded_rectangle([34, 108, 106, 326], radius=22, fill=230)
    draw.rectangle([43, 84, 98, 125], fill=240)
    draw.rounded_rectangle([42, 63, 103, 106], radius=12, fill=255)
    draw.polygon([(57, 27), (92, 12), (104, 64), (48, 72)], fill=255)

    arr = np.array(rgb_image.convert("RGB"))
    hsv = cv2.cvtColor(arr, cv2.COLOR_RGB2HSV)
    h, s, v = cv2.split(hsv)
    background = (h > 35) & (h < 95) & (s > 35) & (v < 185)
    strong_foreground = Image.fromarray((~background).astype(np.uint8) * 255)
    strong_foreground = Image.composite(
        strong_foreground, Image.new("L", rgb_image.size, 0), silhouette
    )
    alpha = Image.composite(
        Image.new("L", rgb_image.size, 255),
        silhouette,
        strong_foreground.point(lambda p: 255 if p > 40 else 0),
    )
    return alpha.filter(ImageFilter.GaussianBlur(1.0))


def crop_to_alpha(rgba: Image.Image) -> Image.Image:
    bbox = rgba.getchannel("A").getbbox()
    if bbox is None:
        return rgba
    return rgba.crop(bbox)


def make_sprite(
    path: Path, crop_box, target_axis: str, target_size: int, alpha_mode: str = "green"
) -> Image.Image:
    crop = Image.open(path).convert("RGB").crop(crop_box)
    rgba = crop.convert("RGBA")
    alpha = lying_bottle_alpha(crop) if alpha_mode == "lying" else green_screen_alpha(crop)
    rgba.putalpha(alpha)
    rgba = crop_to_alpha(rgba)

    alpha_bbox = rgba.getchannel("A").getbbox()
    if alpha_bbox is None:
        raise RuntimeError(f"No foreground extracted from {path}")
    alpha_w = alpha_bbox[2] - alpha_bbox[0]
    alpha_h = alpha_bbox[3] - alpha_bbox[1]
    base = alpha_h if target_axis == "height" else alpha_w
    scale = target_size / base
    new_size = (round(rgba.width * scale), round(rgba.height * scale))
    return rgba.resize(new_size, Image.Resampling.LANCZOS)


def build_lifted_shadow(sprite: Image.Image) -> Image.Image:
    alpha = sprite.getchannel("A")
    shadow = Image.new("RGBA", sprite.size, (0, 0, 0, 0))
    shadow.putalpha(alpha.filter(ImageFilter.GaussianBlur(5)).point(lambda p: int(p * 0.22)))
    return shadow


def inpaint_proxy(rgb: Image.Image, bbox) -> Image.Image:
    arr = np.array(rgb.convert("RGB"))
    x1, y1, x2, y2 = [int(v) for v in bbox]
    pad = 18
    x1 = max(0, x1 - pad)
    y1 = max(0, y1 - pad)
    x2 = min(arr.shape[1], x2 + pad)
    y2 = min(arr.shape[0], y2 + pad)
    roi = arr[y1:y2, x1:x2]

    hsv = cv2.cvtColor(roi, cv2.COLOR_RGB2HSV)
    _, saturation, value = cv2.split(hsv)
    neutral_dark = (value < 130) & (saturation < 80)
    mask = neutral_dark.astype(np.uint8) * 255
    mask = cv2.dilate(mask, np.ones((5, 5), np.uint8), iterations=1)

    n, labels, stats, centroids = cv2.connectedComponentsWithStats(mask)
    kept = np.zeros_like(mask)
    cx = (x2 - x1) / 2
    cy = (y2 - y1) / 2
    for idx in range(1, n):
        x, y, comp_w, comp_h, area = stats[idx]
        comp_cx, comp_cy = centroids[idx]
        near_proxy = abs(comp_cx - cx) < (x2 - x1) * 0.45 and abs(comp_cy - cy) < (
            y2 - y1
        ) * 0.45
        proxy_sized = area > 80 or max(comp_w, comp_h) > 45
        if near_proxy and proxy_sized:
            kept[labels == idx] = 255
    mask = cv2.morphologyEx(kept, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    if mask.max() == 0:
        return rgb

    roi_bgr = cv2.cvtColor(roi, cv2.COLOR_RGB2BGR)
    fixed = cv2.inpaint(roi_bgr, mask, 5, cv2.INPAINT_TELEA)
    arr[y1:y2, x1:x2] = cv2.cvtColor(fixed, cv2.COLOR_BGR2RGB)
    return Image.fromarray(arr, "RGB")


def paste_centered(canvas: Image.Image, sprite: Image.Image, center):
    x = round(center[0] - sprite.width / 2)
    y = round(center[1] - sprite.height / 2)
    canvas.alpha_composite(build_lifted_shadow(sprite), (x + 5, y + 7))
    canvas.alpha_composite(sprite, (x, y))


def proxy_annotation(record):
    for ann in record["annotations"]:
        if ann["item_id"] == "bottle_proxy":
            return ann
    return None


def make_output(record, lying_sprite: Image.Image, upright_sprite: Image.Image):
    src = INPUT_DIR / record["file"]
    image = Image.open(src).convert("RGB")
    if image.size != CANVAS_SIZE:
        raise RuntimeError(f"{src.name}: wrong input size {image.size}")

    bottle = proxy_annotation(record)
    if bottle is None:
        return image

    image = inpaint_proxy(image, bottle["bbox_xyxy"]).convert("RGBA")
    if bottle["state"] == "upright_dot":
        sprite = upright_sprite
    else:
        # Proxy generator starts from a vertical bar and rotates it by this angle.
        sprite = lying_sprite.rotate(
            bottle["angle_degrees"],
            expand=True,
            resample=Image.Resampling.BICUBIC,
        )
        sprite = crop_to_alpha(sprite)

    paste_centered(image, sprite, bottle["center_xy"])
    return image.convert("RGB")


def main():
    with MANIFEST.open("r", encoding="utf-8") as f:
        records = json.load(f)["records"]
    assigned = [r for r in records if 501 <= int(r["sample_index"]) <= 1000]
    if len(assigned) != 500:
        raise RuntimeError(f"Expected 500 assigned records, got {len(assigned)}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for stale in OUTPUT_DIR.glob("*.png"):
        sample = int(stale.name[:4])
        if 501 <= sample <= 1000:
            stale.unlink()

    lying_sprite = make_sprite(
        IMAGE2_LYING_SOURCE,
        crop_box=(670, 320, 820, 670),
        target_axis="height",
        target_size=LYING_TARGET_ALPHA_HEIGHT,
        alpha_mode="lying",
    )
    upright_sprite = make_sprite(
        IMAGE2_UPRIGHT_SOURCE,
        crop_box=(1080, 130, 1260, 310),
        target_axis="width",
        target_size=UPRIGHT_TARGET_ALPHA_WIDTH,
    )

    written = []
    for record in assigned:
        out = make_output(record, lying_sprite, upright_sprite)
        if out.size != CANVAS_SIZE:
            raise RuntimeError(f"{record['file']}: wrong output size {out.size}")
        out.save(OUTPUT_DIR / record["file"], compress_level=4)
        written.append(record["file"])

    print(f"written={len(written)}")
    print(f"output_dir={OUTPUT_DIR}")
    print(f"first={written[0]}")
    print(f"last={written[-1]}")


if __name__ == "__main__":
    main()
