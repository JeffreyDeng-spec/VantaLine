import csv
import itertools
import json
import math
import random
import shutil
from collections import Counter, defaultdict
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter


ROOT = Path("/mnt/f/CodexWorkspace/assembly_line_optimize")
BACKGROUND = ROOT / "backgrounds" / "conveyor_surface_topdown_ai_reference5.png"
MANUAL_DIR = ROOT / "standardized_manuals"
OUT_DIR = ROOT / "synthetic_1000_atom_proxy_combinations"

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

TRUE_COUNT = 500
FALSE_MISSING_1_COUNT = 450
FALSE_MISSING_2_COUNT = 35
FALSE_MISSING_3_COUNT = 15


def distribute(total, n):
    base, extra = divmod(total, n)
    return [base + (1 if i < extra else 0) for i in range(n)]


def item_by_id():
    return {item["id"]: item for item in ITEMS}


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


def make_manual(path, scale=1.0):
    im = Image.open(path).convert("RGBA")
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


def rotate_manual(manual, angle):
    return manual.rotate(angle, expand=True, resample=Image.Resampling.BICUBIC)


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


def overlap_ratio(box_a, box_b):
    ax1, ay1, ax2, ay2 = box_a
    bx1, by1, bx2, by2 = box_b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
    inter = iw * ih
    if inter == 0:
        return 0.0
    area_a = max(1, (ax2 - ax1) * (ay2 - ay1))
    area_b = max(1, (bx2 - bx1) * (by2 - by1))
    return inter / min(area_a, area_b)


def sample_center_for(obj_size, rng, placed_boxes):
    w, h = obj_size
    margin = 20
    min_x = math.ceil(w / 2 + margin)
    max_x = math.floor(CANVAS_SIZE[0] - w / 2 - margin)
    min_y = math.ceil(h / 2 + margin)
    max_y = math.floor(CANVAS_SIZE[1] - h / 2 - margin)
    if min_x > max_x or min_y > max_y:
        return CANVAS_SIZE[0] / 2, CANVAS_SIZE[1] / 2

    best = None
    best_score = 999
    for _ in range(80):
        x = rng.randint(min_x, max_x)
        y = rng.randint(min_y, max_y)
        box = [x - w / 2, y - h / 2, x + w / 2, y + h / 2]
        score = max((overlap_ratio(box, prev) for prev in placed_boxes), default=0.0)
        if score < 0.24:
            return x, y
        if score < best_score:
            best_score = score
            best = (x, y)
    return best


def make_render_object(item, rng):
    if item["type"] == "manual":
        scale = rng.uniform(0.98, 1.02)
        angle = rng.uniform(-44, 44)
        obj = rotate_manual(make_manual(item["path"], scale=scale), angle)
        state = "flat_manual"
        meta = {"angle_degrees": round(angle, 3), "scale": round(scale, 4)}
    else:
        if rng.random() < 0.24:
            obj = make_dot_proxy()
            state = "upright_dot"
            meta = {"angle_degrees": None, "scale": 1.0}
        else:
            angle = rng.uniform(0, 180)
            obj = make_bar_proxy(angle)
            state = "lying_bar"
            meta = {"angle_degrees": round(angle, 3), "scale": 1.0}
    return obj, state, meta


def make_image(present_ids, sample_index):
    rng = random.Random(2026051901 + sample_index * 7919)
    id_map = item_by_id()
    items = [id_map[item_id] for item_id in present_ids]
    render_items = []
    placement_boxes = []

    # Generate positions independently from paste order so stacking order is truly random.
    for item in items:
        obj, state, meta = make_render_object(item, rng)
        bbox = alpha_bbox(obj)
        if bbox:
            obj = obj.crop(bbox)
        center = sample_center_for(obj.size, rng, placement_boxes)
        estimated = [
            center[0] - obj.size[0] / 2,
            center[1] - obj.size[1] / 2,
            center[0] + obj.size[0] / 2,
            center[1] + obj.size[1] / 2,
        ]
        placement_boxes.append(estimated)
        render_items.append(
            {
                "item": item,
                "object": obj,
                "state": state,
                "center": center,
                "meta": meta,
            }
        )

    z_order = list(range(len(render_items)))
    rng.shuffle(z_order)
    bottle_indices = [
        idx for idx, entry in enumerate(render_items) if entry["item"]["id"] == "bottle_proxy"
    ]
    for bottle_idx in bottle_indices:
        if bottle_idx in z_order:
            z_order.remove(bottle_idx)
            z_order.append(bottle_idx)
    canvas = load_background()
    annotations = []
    for z_index, render_idx in enumerate(z_order):
        entry = render_items[render_idx]
        bbox = paste_object(canvas, entry["object"], entry["center"])
        annotations.append(
            {
                "item_id": entry["item"]["id"],
                "state": entry["state"],
                "bbox_xyxy": bbox,
                "center_xy": [round(entry["center"][0], 3), round(entry["center"][1], 3)],
                "z_index": z_index,
                **entry["meta"],
            }
        )

    signature_parts = []
    for entry in render_items:
        signature_parts.append(
            (
                entry["item"]["id"],
                round(entry["center"][0] / 4) * 4,
                round(entry["center"][1] / 4) * 4,
                entry["state"],
                entry["meta"]["angle_degrees"],
            )
        )
    signature = json.dumps({"items": signature_parts, "z": z_order}, sort_keys=True)
    return canvas.convert("RGB"), annotations, z_order, signature


def make_plan():
    item_ids = [item["id"] for item in ITEMS]
    plan = []

    for _ in range(TRUE_COUNT):
        plan.append(("true", 0, tuple(item_ids)))

    false_groups = [
        (1, FALSE_MISSING_1_COUNT),
        (2, FALSE_MISSING_2_COUNT),
        (3, FALSE_MISSING_3_COUNT),
    ]
    for missing_count, total in false_groups:
        present_combos = []
        for missing in itertools.combinations(item_ids, missing_count):
            present = tuple(item_id for item_id in item_ids if item_id not in set(missing))
            present_combos.append(present)
        present_combos.sort()
        for copies, present in zip(distribute(total, len(present_combos)), present_combos):
            for _ in range(copies):
                plan.append(("false", missing_count, present))

    return plan


def main():
    plan = make_plan()
    if len(plan) != 1000:
        raise RuntimeError(f"Expected 1000 samples, got {len(plan)}")

    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    rows = []
    records = []
    signatures = set()
    per_combo_seen = defaultdict(int)
    for sample_idx, (label, missing_count, present_ids) in enumerate(plan, start=1):
        img, annotations, z_order, signature = make_image(present_ids, sample_idx)
        if signature in signatures:
            raise RuntimeError(f"Duplicate layout signature at sample {sample_idx}")
        signatures.add(signature)

        missing_items = [item["id"] for item in ITEMS if item["id"] not in set(present_ids)]
        combo_key = "__".join(present_ids)
        per_combo_seen[combo_key] += 1
        out_name = (
            f"{sample_idx:04d}__{label}"
            f"__missing_{missing_count}"
            f"__combo_{combo_key}"
            f"__copy_{per_combo_seen[combo_key]:03d}.png"
        )
        img.save(OUT_DIR / out_name, quality=96)

        row = {
            "sample_index": sample_idx,
            "file": out_name,
            "label": label,
            "missing_count": missing_count,
            "present_items": "|".join(present_ids),
            "missing_items": "|".join(missing_items),
            "width": CANVAS_SIZE[0],
            "height": CANVAS_SIZE[1],
        }
        rows.append(row)
        records.append(
            {
                **row,
                "present_items": list(present_ids),
                "missing_items": missing_items,
                "z_order_item_ids": [annotations[i]["item_id"] for i in range(len(annotations))],
                "annotations": annotations,
            }
        )

    label_counts = Counter(row["label"] for row in rows)
    missing_counts = Counter(row["missing_count"] for row in rows)
    combo_counts = Counter(row["present_items"] for row in rows)

    with (OUT_DIR / "labels.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "sample_index",
                "file",
                "label",
                "missing_count",
                "present_items",
                "missing_items",
                "width",
                "height",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    (OUT_DIR / "manifest.json").write_text(
        json.dumps(
            {
                "description": (
                    "1000 randomized atom proxy samples. Background is fixed; object "
                    "positions, rotations, bottle proxy state, and z-order are randomized "
                    "per sample."
                ),
                "background": str(BACKGROUND),
                "manual_sources": [str(item["path"]) for item in ITEMS if item["type"] == "manual"],
                "items": [item["id"] for item in ITEMS],
                "bottle_proxy": {
                    "lying_bar_length_px": BOTTLE_BAR_LENGTH,
                    "lying_bar_width_px": BOTTLE_BAR_WIDTH,
                    "upright_dot_diameter_px": BOTTLE_DOT_DIAMETER,
                    "note": "Lying bottle is represented by a black bar; upright bottle is represented by a black dot.",
                },
                "sampling_policy": {
                    "total": 1000,
                    "true": TRUE_COUNT,
                    "false": TRUE_COUNT,
                    "false_by_missing_count": {
                        "1": FALSE_MISSING_1_COUNT,
                        "2": FALSE_MISSING_2_COUNT,
                        "3": FALSE_MISSING_3_COUNT,
                    },
                    "excluded_missing_counts": [4, 5],
                    "randomization": [
                        "object center position",
                        "manual rotation",
                        "lying bottle proxy rotation",
                        "upright vs lying bottle proxy state",
                        "z-order / stacking order",
                    ],
                },
                "label_counts": dict(label_counts),
                "missing_count_counts": {str(k): v for k, v in sorted(missing_counts.items())},
                "combo_counts": {k: v for k, v in sorted(combo_counts.items())},
                "records": records,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print(OUT_DIR)
    print(f"png_count={len(list(OUT_DIR.glob('*.png')))}")
    print(f"label_counts={dict(label_counts)}")
    print(f"missing_count_counts={dict(sorted(missing_counts.items()))}")
    print(f"unique_layout_signatures={len(signatures)}")


if __name__ == "__main__":
    main()
