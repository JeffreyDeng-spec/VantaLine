import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw


DATA_DIR = Path(
    "/mnt/c/Users/Administrator/iCloudDrive/iCloud~md~obsidian/"
    "Jeffrey/assambly_line_optimize/data"
)
OUT_DIR = Path("/mnt/f/CodexWorkspace/assembly_line_optimize/manuals_from_individual_sources_precise")
OUT_SIZE = (1240, 1754)


MANUALS = [
    {
        "id": "manual_from_2_warranty_service",
        "source": DATA_DIR / "2.jpg",
        "rotate_180_after_warp": False,
        "corners": {
            "top_left": [540, 812],
            "top_right": [2582, 918],
            "bottom_right": [2528, 3838],
            "bottom_left": [522, 3862],
        },
    },
    {
        "id": "manual_from_3_battery_instruction",
        "source": DATA_DIR / "3.jpg",
        "rotate_180_after_warp": True,
        "corners": {
            "top_left": [600, 738],
            "top_right": [2568, 798],
            "bottom_right": [2570, 3626],
            "bottom_left": [650, 3656],
        },
    },
    {
        "id": "manual_from_4_download_service",
        "source": DATA_DIR / "4.jpg",
        "rotate_180_after_warp": True,
        "corners": {
            "top_left": [716, 678],
            "top_right": [2612, 672],
            "bottom_right": [2630, 3364],
            "bottom_left": [832, 3504],
        },
    },
    {
        "id": "manual_from_6_service_qr",
        "source": DATA_DIR / "6.jpg",
        "rotate_180_after_warp": False,
        "corners": {
            "top_left": [594, 642],
            "top_right": [2570, 790],
            "bottom_right": [2560, 3538],
            "bottom_left": [604, 3658],
        },
    },
]


def source_points(manual):
    c = manual["corners"]
    return np.array(
        [c["top_left"], c["top_right"], c["bottom_right"], c["bottom_left"]],
        dtype=np.float32,
    )


def clean_border_background(rgb):
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    h, s, v = cv2.split(hsv)
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)
    l_lab, _, b_lab = cv2.split(lab)
    tan = (h > 8) & (h < 55) & (s > 25) & (v > 65)
    yellow_lab = (b_lab > 145) & (l_lab > 80)
    dark = v < 72
    saturated_edge = s > 115
    candidate = (tan | yellow_lab | dark | saturated_edge).astype(np.uint8) * 255
    candidate = cv2.morphologyEx(
        candidate,
        cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)),
        iterations=1,
    )

    connected = np.zeros_like(candidate)
    flood_mask = np.zeros((candidate.shape[0] + 2, candidate.shape[1] + 2), np.uint8)
    hgt, wid = candidate.shape
    seeds = [(x, 0) for x in range(wid)] + [(x, hgt - 1) for x in range(wid)]
    seeds += [(0, y) for y in range(hgt)] + [(wid - 1, y) for y in range(hgt)]

    work = candidate.copy()
    for seed in seeds:
        x, y = seed
        if work[y, x] == 0:
            continue
        cv2.floodFill(work, flood_mask, seed, 128)
        filled = work == 128
        connected[filled] = 255
        work[filled] = 0
        flood_mask[:] = 0

    cleaned = rgb.copy()
    paper_pixels = rgb[(v > 135) & (s < 80)]
    fill = np.median(paper_pixels, axis=0).astype(np.uint8) if len(paper_pixels) else np.array([238, 242, 248], dtype=np.uint8)
    cleaned[connected > 0] = fill
    return cleaned


def sharpen(rgb):
    blur = cv2.GaussianBlur(rgb, (0, 0), 1.0)
    return cv2.addWeighted(rgb, 1.2, blur, -0.2, 0)


def draw_debug_overlay(debug, manual, color):
    draw = ImageDraw.Draw(debug)
    pts = [tuple(manual["corners"][k]) for k in ("top_left", "top_right", "bottom_right", "bottom_left")]
    draw.line(pts + [pts[0]], fill=color, width=14)
    for label, pt in zip(("TL", "TR", "BR", "BL"), pts):
        r = 22
        draw.ellipse([pt[0] - r, pt[1] - r, pt[0] + r, pt[1] + r], fill=color)
        draw.text((pt[0] + 24, pt[1] - 18), label, fill=color)


def make_contact_sheet(paths):
    cell_w, cell_h = 560, 760
    pad = 30
    sheet = Image.new("RGB", (cell_w * 2 + pad * 3, cell_h * 2 + pad * 3), (245, 245, 245))
    draw = ImageDraw.Draw(sheet)
    for idx, p in enumerate(paths):
        im = Image.open(p).convert("RGB")
        im.thumbnail((cell_w - 40, cell_h - 80), Image.Resampling.LANCZOS)
        x = pad + (idx % 2) * (cell_w + pad)
        y = pad + (idx // 2) * (cell_h + pad)
        draw.rectangle([x, y, x + cell_w, y + cell_h], fill=(255, 255, 255), outline=(190, 190, 190))
        draw.text((x + 16, y + 12), p.name, fill=(20, 20, 20))
        sheet.paste(im, (x + (cell_w - im.width) // 2, y + 52 + (cell_h - 80 - im.height) // 2))
    sheet.save(OUT_DIR / "contact_sheet_precise_individual_manuals.jpg", quality=95)


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    dst = np.array(
        [[0, 0], [OUT_SIZE[0] - 1, 0], [OUT_SIZE[0] - 1, OUT_SIZE[1] - 1], [0, OUT_SIZE[1] - 1]],
        dtype=np.float32,
    )
    outputs = []
    manifest = {
        "output_dir": str(OUT_DIR),
        "output_size_px": list(OUT_SIZE),
        "method": "manual precise four-corner annotation from individual source photos plus perspective transform",
        "manuals": [],
    }
    colors = ["red", "cyan", "yellow", "magenta"]

    for idx, manual in enumerate(MANUALS):
        bgr = cv2.imread(str(manual["source"]))
        if bgr is None:
            raise FileNotFoundError(manual["source"])
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)

        matrix = cv2.getPerspectiveTransform(source_points(manual), dst)
        warped = cv2.warpPerspective(
            rgb,
            matrix,
            OUT_SIZE,
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_REPLICATE,
        )
        if manual["rotate_180_after_warp"]:
            warped = cv2.rotate(warped, cv2.ROTATE_180)
        warped = clean_border_background(warped)
        warped = sharpen(warped)

        out_path = OUT_DIR / f"{manual['id']}_precise_1240x1754.png"
        Image.fromarray(warped).save(out_path)
        outputs.append(out_path)

        debug = Image.fromarray(rgb)
        draw_debug_overlay(debug, manual, colors[idx])
        debug_path = OUT_DIR / f"{manual['id']}_corner_annotation.jpg"
        debug.save(debug_path, quality=95)

        manifest["manuals"].append(
            {
                "id": manual["id"],
                "source": str(manual["source"]),
                "output": str(out_path),
                "corner_annotation": str(debug_path),
                "corners_source_px": manual["corners"],
                "rotate_180_after_warp": manual["rotate_180_after_warp"],
            }
        )

    make_contact_sheet(outputs)
    (OUT_DIR / "precise_individual_extraction_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
