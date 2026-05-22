from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps


DATA_DIR = Path(
    "/mnt/c/Users/Administrator/iCloudDrive/iCloud~md~obsidian/"
    "Jeffrey/assambly_line_optimize/data"
)
ROOT = Path("/mnt/f/CodexWorkspace/assembly_line_optimize")
OUT_DIR = ROOT / "generated_bottle_pose_collection"
OUT_PATH = OUT_DIR / "overhead_bottle_pose_collection_v1.png"


def rounded_rect_mask(size, rect, radius):
    mask = Image.new("L", size, 0)
    draw = Image.new("L", size, 0)
    from PIL import ImageDraw

    ImageDraw.Draw(draw).rounded_rectangle(rect, radius=radius, fill=255)
    mask = Image.composite(draw, mask, draw)
    return mask


def feather(mask, radius=3):
    return mask.filter(ImageFilter.GaussianBlur(radius))


def crop_side_bottle():
    src = Image.open(DATA_DIR / "10.jpg").convert("RGB")
    crop = src.crop((1300, 600, 2400, 3000))
    w, h = crop.size
    shape = Image.new("L", (w, h), 0)

    from PIL import ImageDraw

    draw = ImageDraw.Draw(shape)
    draw.rounded_rectangle((330, 845, 825, 2125), radius=150, fill=255)
    draw.rounded_rectangle((310, 545, 760, 910), radius=50, fill=255)
    draw.polygon([(438, 120), (650, 120), (735, 545), (350, 545)], fill=255)
    draw.ellipse((360, 815, 795, 2210), fill=255)

    arr = np.array(crop)
    hsv = cv2.cvtColor(arr, cv2.COLOR_RGB2HSV)
    hch, sch, vch = cv2.split(hsv)
    green = (hch > 35) & (hch < 100) & (sch > 20) & (vch > 45)
    red = (arr[:, :, 0] > 145) & (arr[:, :, 1] < 125) & (arr[:, :, 2] < 115)
    dark = (arr.max(axis=2) < 105) & ~green
    bright = (vch > 192) & (sch < 92)
    detail = red | dark | bright
    shape_arr = np.array(shape) > 0
    strong = (detail & shape_arr).astype(np.uint8) * 255
    strong = cv2.morphologyEx(
        strong,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)),
        iterations=1,
    )
    mask = Image.fromarray(strong, "L").filter(ImageFilter.GaussianBlur(1.2))

    base = Image.new("RGBA", (w, h), (216, 245, 226, 0))
    base.putalpha(shape.filter(ImageFilter.GaussianBlur(1.5)).point(lambda p: min(p, 24)))
    detail_layer = crop.convert("RGBA")
    detail_layer.putalpha(mask)
    rgba = Image.alpha_composite(base, detail_layer)
    rgba = rgba.crop(rgba.getbbox())
    return rgba


def crop_upright_top():
    src = Image.open(DATA_DIR / "11.jpg").convert("RGB")
    crop = src.crop((1900, 900, 2600, 1600))
    w, h = crop.size
    shape = Image.new("L", (w, h), 0)

    from PIL import ImageDraw

    draw = ImageDraw.Draw(shape)
    draw.ellipse((70, 150, 635, 700), fill=215)
    draw.ellipse((145, 110, 590, 590), fill=255)
    draw.polygon([(295, 75), (500, 95), (570, 500), (225, 495)], fill=255)

    arr = np.array(crop)
    hsv = cv2.cvtColor(arr, cv2.COLOR_RGB2HSV)
    hch, sch, vch = cv2.split(hsv)
    green = (hch > 35) & (hch < 100) & (sch > 20) & (vch > 45)
    red = (arr[:, :, 0] > 145) & (arr[:, :, 1] < 135) & (arr[:, :, 2] < 125)
    dark = (arr.max(axis=2) < 110) & ~green
    bright = (vch > 185) & (sch < 115)
    shape_arr = np.array(shape) > 0
    strong = ((red | dark | bright) & shape_arr).astype(np.uint8) * 255
    mask = Image.fromarray(strong, "L").filter(ImageFilter.GaussianBlur(1.5))

    base = Image.new("RGBA", (w, h), (216, 245, 226, 0))
    base.putalpha(shape.filter(ImageFilter.GaussianBlur(1.6)).point(lambda p: min(p, 20)))
    detail_layer = crop.convert("RGBA")
    detail_layer.putalpha(mask)
    rgba = Image.alpha_composite(base, detail_layer)
    rgba = rgba.crop(rgba.getbbox())
    return rgba


def load_background():
    bg = Image.open(ROOT / "backgrounds" / "conveyor_surface_topdown_ai_reference5.png").convert("RGB")
    bg = ImageOps.fit(bg, (1600, 1200), method=Image.Resampling.LANCZOS)
    bg = ImageEnhance.Contrast(bg).enhance(1.06)
    bg = ImageEnhance.Color(bg).enhance(0.92)
    return bg.convert("RGBA")


def resize_keep(im, target_long):
    w, h = im.size
    scale = target_long / max(w, h)
    return im.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)


def paste_with_shadow(canvas, obj, center, angle=0, long_size=420, shadow_opacity=95):
    item = resize_keep(obj, long_size)
    item = item.rotate(angle, expand=True, resample=Image.Resampling.BICUBIC)
    alpha = item.getchannel("A")

    shadow = Image.new("RGBA", item.size, (0, 0, 0, 0))
    shadow.putalpha(alpha.filter(ImageFilter.GaussianBlur(9)))
    shadow = ImageEnhance.Brightness(shadow).enhance(shadow_opacity / 255)

    x = int(center[0] - item.size[0] / 2)
    y = int(center[1] - item.size[1] / 2)
    canvas.alpha_composite(shadow, (x + 9, y + 12))
    canvas.alpha_composite(item, (x, y))


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    canvas = load_background()
    side = crop_side_bottle()
    top = crop_upright_top()

    # Lying bottles: same real side-view bottle, rotated to distinct conveyor-plane angles.
    for center, angle, size in [
        ((340, 230), 70, 430),
        ((760, 255), 16, 470),
        ((1210, 265), -36, 420),
        ((410, 715), -12, 500),
        ((915, 770), 48, 450),
        ((1320, 855), 105, 410),
    ]:
        paste_with_shadow(canvas, side, center, angle=angle, long_size=size, shadow_opacity=100)

    # Upright bottles: overhead top/cap view, so only the top and upper glass shoulder are visible.
    for center, angle, size in [
        ((225, 965), -8, 230),
        ((695, 545), 18, 210),
        ((1145, 565), -22, 190),
    ]:
        paste_with_shadow(canvas, top, center, angle=angle, long_size=size, shadow_opacity=85)

    canvas = ImageEnhance.Sharpness(canvas).enhance(1.08)
    canvas.convert("RGB").save(OUT_PATH, quality=96)
    print(OUT_PATH)


if __name__ == "__main__":
    main()
