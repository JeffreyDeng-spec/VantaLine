import json
import sys
from pathlib import Path


ROOT = Path("/mnt/f/CodexWorkspace/assembly_line_optimize")
SCRIPT_DIR = ROOT / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import optimize_1000_atom_proxy_0501_1000 as opt  # noqa: E402


INPUT_DIR = ROOT / "synthetic_3000_atom_proxy_full_rotation_combinations"
OUTPUT_DIR = ROOT / "image2_optimized_3000_atom_proxy_full_rotation_combinations"
MANIFEST = INPUT_DIR / "manifest.json"


def main() -> None:
    records = json.loads(MANIFEST.read_text(encoding="utf-8"))["records"]
    if len(records) != 3000:
        raise RuntimeError(f"Expected 3000 records, got {len(records)}")

    opt.INPUT_DIR = INPUT_DIR
    opt.OUTPUT_DIR = OUTPUT_DIR
    opt.MANIFEST = MANIFEST

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for stale in OUTPUT_DIR.glob("*.png"):
        stale.unlink()

    lying_sprite = opt.make_sprite(
        opt.IMAGE2_LYING_SOURCE,
        crop_box=(670, 320, 820, 670),
        target_axis="height",
        target_size=opt.LYING_TARGET_ALPHA_HEIGHT,
        alpha_mode="lying",
    )
    upright_sprite = opt.make_sprite(
        opt.IMAGE2_UPRIGHT_SOURCE,
        crop_box=(1080, 130, 1260, 310),
        target_axis="width",
        target_size=opt.UPRIGHT_TARGET_ALPHA_WIDTH,
    )

    written = 0
    copied_without_bottle = 0
    for record in records:
        out = opt.make_output(record, lying_sprite, upright_sprite)
        if out.size != opt.CANVAS_SIZE:
            raise RuntimeError(f"{record['file']}: wrong output size {out.size}")
        out.save(OUTPUT_DIR / record["file"], compress_level=2)
        written += 1
        if not any(ann["item_id"] == "bottle_proxy" for ann in record["annotations"]):
            copied_without_bottle += 1

    print(f"written={written}")
    print(f"copied_without_bottle={copied_without_bottle}")
    print(f"output_dir={OUTPUT_DIR}")


if __name__ == "__main__":
    main()
