import itertools
import json
import math
import random
import shutil
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter


ROOT = Path("/mnt/f/CodexWorkspace/assembly_line_optimize")
BACKGROUND = ROOT / "backgrounds" / "conveyor_surface_topdown_ai_reference5.png"
OUT_DIR = ROOT / "synthetic_31_item_proxy_combinations"
MANUAL_DIR = ROOT / "standardized_manuals"

ITEMS = [
    {
        "id": "bottle_proxy",
        "type": "bottle_proxy",
    },
    {
        "id": "manual_warranty_service",
        "type": "manual",
        "path": MANUAL_DIR / "manual_from_2_warranty_service_precise_1240x1754.png",
    },
    {
        "id": "manual_battery_instruction",
        "type": "manual",
        "path": MANUAL_DIR / "manual_from_3_battery_instruction_precise_1240x1754.png",
    },
    {
        "id": "manual_download_service",
        "type": "manual",
        "path": MANUAL_DIR / "manual_from_4_download_service_precise_1240x1754.png",
    },
    {
        "id": "manual_service_qr",
        "type": "manual",
        "path": MANUAL_DIR / "manual_from_6_service_qr_precise_1240x1754.png",
    },
]

CANVAS_SIZE = (1448, 1086)
MANUAL_LONG_SIDE = 560
BOTTLE_BAR_LENGTH = 315
BOTTLE_BAR_WIDTH = 13
BOTTLE_DOT_DIAMETER = 38


def load_background():
    bg = Image.open(BACKGROUND).convert("RGB")
    bg = bg.resize(CANVAS_SIZE, Image.Resampling.LANCZOS)
    bg = ImageEnhance.Color(bg).enhance(0.96)
    bg = ImageEnhance.Contrast(bg).enhance(1.04)
    return bg.convert("RGBA")


def resize_long_side(im, long_side):
    w, h = im.size
    scale = long_side / max(w, h)
    return im.resize((round(w * scale), round(h * scale)), Image.Resampling.LANCZOS)


def make_manual(path):
    im = Image.open(path).convert("RGBA")
    im = resize_long_side(im, MANUAL_LONG_SIDE)
    alpha = Image.new("L", im.size, 255)
    im.putalpha(alpha)
    return im


def make_bar_proxy(angle):
    pad = 52
    w = BOTTLE_BAR_WIDTH + pad * 2
    h = BOTTLE_BAR_LENGTH + pad * 2
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    cx = w // 2
    y0 = pad
    y1 = pad + BOTTLE_BAR_LENGTH
    d.rounded_rectangle(
        (cx - BOTTLE_BAR_WIDTH // 2, y0, cx + BOTTLE_BAR_WIDTH // 2, y1),
        radius=7,
        fill=(18, 18, 18, 255),
    )
    d.line((cx + 5, y0 + 12, cx + 5, y1 - 12), fill=(95, 95, 95, 170), width=2)
    return im.rotate(angle, expand=True, resample=Image.Resampling.BICUBIC)


def make_dot_proxy():
    pad = 38
    dia = BOTTLE_DOT_DIAMETER
    im = Image.new("RGBA", (dia + pad * 2, dia + pad * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    box = (pad, pad, pad + dia, pad + dia)
    d.ellipse(box, fill=(18, 18, 18, 255))
    d.ellipse((pad + 8, pad + 7, pad + dia - 10, pad + dia - 12), fill=(58, 58, 58, 245))
    d.ellipse((pad + 13, pad + 10, pad + 21, pad + 18), fill=(145, 145, 145, 130))
    return im


def alpha_bbox(im):
    return im.getchannel("A").getbbox()


def paste_object(canvas, obj, center, shadow=True):
    bbox = alpha_bbox(obj)
    if bbox:
        obj = obj.crop(bbox)
    x = round(center[0] - obj.size[0] / 2)
    y = round(center[1] - obj.size[1] / 2)
    if shadow:
        alpha = obj.getchannel("A")
        shadow_im = Image.new("RGBA", obj.size, (0, 0, 0, 0))
        shadow_im.putalpha(alpha.filter(ImageFilter.GaussianBlur(7)).point(lambda p: int(p * 0.30)))
        canvas.alpha_composite(shadow_im, (x + 7, y + 9))
    canvas.alpha_composite(obj, (x, y))
    return [x, y, x + obj.size[0], y + obj.size[1]]


def rotate_manual(manual, angle):
    return manual.rotate(angle, expand=True, resample=Image.Resampling.BICUBIC)


def slot_centers(count, rng):
    layouts = {
        1: [(724, 545)],
        2: [(440, 545), (1008, 545)],
        3: [(355, 360), (1015, 395), (720, 755)],
        4: [(330, 300), (1030, 300), (400, 790), (1040, 790)],
        5: [(270, 285), (740, 285), (1180, 330), (440, 790), (980, 805)],
    }
    pts = layouts[count][:]
    return [(x + rng.randint(-38, 38), y + rng.randint(-34, 34)) for x, y in pts]


def clamp_center_for_size(center, size):
    w, h = size
    margin = 16
    x = min(max(center[0], w / 2 + margin), CANVAS_SIZE[0] - w / 2 - margin)
    y = min(max(center[1], h / 2 + margin), CANVAS_SIZE[1] - h / 2 - margin)
    return x, y


def make_image(combo, index):
    rng = random.Random(20260518 + index * 31)
    canvas = load_background()
    annotations = []
    centers = slot_centers(len(combo), rng)
    angle_pool = [-22, -11, 7, 16, 31, 43, -36, 58]

    # Put larger manuals first, so the bottle proxy stays visible when present.
    ordered = sorted(combo, key=lambda item: item["type"] == "bottle_proxy")
    for item, center in zip(ordered, centers):
        if item["type"] == "manual":
            obj = make_manual(item["path"])
            obj = rotate_manual(obj, rng.choice(angle_pool) + rng.uniform(-4, 4))
            center = clamp_center_for_size(center, obj.size)
            bbox = paste_object(canvas, obj, center)
            annotations.append({"item_id": item["id"], "state": "flat_manual", "bbox_xyxy": bbox})
        else:
            if index % 3 == 0:
                obj = make_dot_proxy()
                state = "upright_dot"
            else:
                obj = make_bar_proxy(rng.choice([0, 18, 43, 74, 105, 132, 161]))
                state = "lying_bar"
            center = clamp_center_for_size(center, obj.size)
            bbox = paste_object(canvas, obj, center)
            annotations.append({"item_id": item["id"], "state": state, "bbox_xyxy": bbox})

    return canvas.convert("RGB"), annotations


def make_contact_sheet(image_paths):
    thumbs = []
    for p in image_paths:
        im = Image.open(p).convert("RGB")
        im.thumbnail((230, 172), Image.Resampling.LANCZOS)
        tile = Image.new("RGB", (230, 172), (245, 245, 245))
        tile.paste(im, ((230 - im.size[0]) // 2, (172 - im.size[1]) // 2))
        thumbs.append(tile)
    cols = 4
    rows = math.ceil(len(thumbs) / cols)
    sheet = Image.new("RGB", (cols * 230, rows * 172), (32, 32, 32))
    for i, thumb in enumerate(thumbs):
        sheet.paste(thumb, ((i % cols) * 230, (i // cols) * 172))
    out = OUT_DIR / "contact_sheet_31_item_proxy.jpg"
    sheet.save(out, quality=92)
    return out


def main():
    if OUT_DIR.exists():
        for p in OUT_DIR.glob("*.png"):
            p.unlink()
        for p in OUT_DIR.glob("*.json"):
            p.unlink()
        for p in OUT_DIR.glob("*.txt"):
            p.unlink()
        for p in OUT_DIR.glob("*.jpg"):
            p.unlink()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    all_records = []
    image_paths = []
    combinations = []
    for r in range(1, len(ITEMS) + 1):
        combinations.extend(itertools.combinations(ITEMS, r))

    for index, combo in enumerate(combinations, start=1):
        img, annotations = make_image(combo, index)
        combo_ids = [item["id"] for item in combo]
        name = f"{index:02d}__{'__'.join(combo_ids)}.png"
        out = OUT_DIR / name
        img.save(out, quality=96)
        image_paths.append(out)
        all_records.append(
            {
                "index": index,
                "file": name,
                "width": CANVAS_SIZE[0],
                "height": CANVAS_SIZE[1],
                "items": combo_ids,
                "annotations": annotations,
            }
        )

    (OUT_DIR / "manifest.json").write_text(
        json.dumps(
            {
                "description": "31 non-empty combinations of 4 real manuals plus bottle proxy over conveyor background.",
                "background": str(BACKGROUND),
                "manual_sources": [str(item["path"]) for item in ITEMS if item["type"] == "manual"],
                "bottle_proxy": {
                    "lying_bar_length_px": BOTTLE_BAR_LENGTH,
                    "lying_bar_width_px": BOTTLE_BAR_WIDTH,
                    "upright_dot_diameter_px": BOTTLE_DOT_DIAMETER,
                },
                "records": all_records,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (OUT_DIR / "combinations.txt").write_text(
        "\n".join(f"{r['index']:02d}: {', '.join(r['items'])}" for r in all_records) + "\n",
        encoding="utf-8",
    )
    contact = make_contact_sheet(image_paths)
    shutil.make_archive(str(ROOT / "synthetic_31_item_proxy_combinations"), "gztar", OUT_DIR)
    print(OUT_DIR)
    print(contact)
    print(len(image_paths))


if __name__ == "__main__":
    main()
