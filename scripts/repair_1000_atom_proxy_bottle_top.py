import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter


ROOT = Path("/mnt/f/CodexWorkspace/assembly_line_optimize")
BACKGROUND = ROOT / "backgrounds" / "conveyor_surface_topdown_ai_reference5.png"
MANUAL_DIR = ROOT / "standardized_manuals"
OUT_DIR = ROOT / "synthetic_1000_atom_proxy_combinations"

CANVAS_SIZE = (1448, 1086)
MANUAL_LONG_SIDE = 560
BOTTLE_BAR_LENGTH = 315
BOTTLE_BAR_WIDTH = 13
BOTTLE_DOT_DIAMETER = 38

ITEMS = {
    "bottle_proxy": {"id": "bottle_proxy", "type": "bottle_proxy"},
    "manual_warranty_service": {
        "id": "manual_warranty_service",
        "type": "manual",
        "path": MANUAL_DIR / "manual_from_2_warranty_service_precise_1240x1754.png",
    },
    "manual_battery_instruction": {
        "id": "manual_battery_instruction",
        "type": "manual",
        "path": MANUAL_DIR / "manual_from_3_battery_instruction_precise_1240x1754.png",
    },
    "manual_download_service": {
        "id": "manual_download_service",
        "type": "manual",
        "path": MANUAL_DIR / "manual_from_4_download_service_precise_1240x1754.png",
    },
    "manual_service_qr": {
        "id": "manual_service_qr",
        "type": "manual",
        "path": MANUAL_DIR / "manual_from_6_service_qr_precise_1240x1754.png",
    },
}

BACKGROUND_BASE = None
MANUAL_BASES = {}


def load_background():
    global BACKGROUND_BASE
    if BACKGROUND_BASE is None:
        bg = Image.open(BACKGROUND).convert("RGB")
        bg = bg.resize(CANVAS_SIZE, Image.Resampling.LANCZOS)
        bg = ImageEnhance.Color(bg).enhance(0.96)
        bg = ImageEnhance.Contrast(bg).enhance(1.04)
        BACKGROUND_BASE = bg.convert("RGBA")
    return BACKGROUND_BASE.copy()


def resize_long_side(im, long_side):
    w, h = im.size
    scale = long_side / max(w, h)
    return im.resize((round(w * scale), round(h * scale)), Image.Resampling.LANCZOS)


def make_manual(path, scale):
    path = Path(path)
    if path not in MANUAL_BASES:
        MANUAL_BASES[path] = Image.open(path).convert("RGBA")
    im = MANUAL_BASES[path].copy()
    im = resize_long_side(im, round(MANUAL_LONG_SIDE * scale))
    im.putalpha(Image.new("L", im.size, 255))
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
        shadow_im.putalpha(alpha.filter(ImageFilter.GaussianBlur(7)).point(lambda p: int(p * 0.28)))
        canvas.alpha_composite(shadow_im, (x + 7, y + 9))
    canvas.alpha_composite(obj, (x, y))
    return [x, y, x + obj.size[0], y + obj.size[1]]


def object_from_annotation(annotation):
    item = ITEMS[annotation["item_id"]]
    if item["type"] == "manual":
        scale = float(annotation.get("scale", 1.0))
        angle = float(annotation.get("angle_degrees", 0.0))
        obj = make_manual(item["path"], scale)
        obj = obj.rotate(angle, expand=True, resample=Image.Resampling.BICUBIC)
    elif annotation["state"] == "upright_dot":
        obj = make_dot_proxy()
    else:
        obj = make_bar_proxy(float(annotation["angle_degrees"]))
    bbox = alpha_bbox(obj)
    return obj.crop(bbox) if bbox else obj


def repair_record(record):
    annotations = record["annotations"]
    bottle = [ann for ann in annotations if ann["item_id"] == "bottle_proxy"]
    if not bottle:
        return False, record
    max_z = max(ann["z_index"] for ann in annotations)
    if bottle[0]["z_index"] == max_z:
        return False, record

    ordered = sorted(annotations, key=lambda ann: ann["z_index"])
    ordered = [ann for ann in ordered if ann["item_id"] != "bottle_proxy"] + bottle

    canvas = load_background()
    repaired_annotations = []
    for z_index, ann in enumerate(ordered):
        obj = object_from_annotation(ann)
        bbox = paste_object(canvas, obj, ann["center_xy"])
        new_ann = dict(ann)
        new_ann["z_index"] = z_index
        new_ann["bbox_xyxy"] = bbox
        repaired_annotations.append(new_ann)

    canvas.convert("RGB").save(OUT_DIR / record["file"], quality=96)
    record["annotations"] = repaired_annotations
    record["z_order_item_ids"] = [ann["item_id"] for ann in repaired_annotations]
    return True, record


def main():
    manifest_path = OUT_DIR / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    to_repair = []
    for record in manifest["records"]:
        anns = record["annotations"]
        bottle = [ann for ann in anns if ann["item_id"] == "bottle_proxy"]
        if not bottle:
            continue
        if bottle[0]["z_index"] != max(ann["z_index"] for ann in anns):
            to_repair.append(record["file"])

    print(f"to_repair={len(to_repair)}", flush=True)

    repaired = []
    updated_records = []
    for idx, record in enumerate(manifest["records"], start=1):
        changed, new_record = repair_record(record)
        if changed:
            repaired.append(new_record["file"])
            if len(repaired) % 50 == 0:
                print(f"repaired_progress={len(repaired)}/{len(to_repair)}", flush=True)
        updated_records.append(new_record)

    manifest["records"] = updated_records
    manifest["repair_policy"] = {
        "bottle_proxy_z_order": "bottle_proxy is always rendered above every manual when present",
        "repaired_file_count": len(repaired),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    (OUT_DIR / "repaired_bottle_top_files.txt").write_text(
        "\n".join(repaired) + ("\n" if repaired else ""),
        encoding="utf-8",
    )

    print(f"repaired_count={len(repaired)}")
    print(OUT_DIR / "repaired_bottle_top_files.txt")


if __name__ == "__main__":
    main()
