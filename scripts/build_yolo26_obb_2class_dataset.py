from __future__ import annotations

import shutil
from pathlib import Path


ROOT = Path("/mnt/f/CodexWorkspace/assembly_line_optimize")
SOURCE = ROOT / "yolo26_obb_trial" / "dataset"
TARGET = ROOT / "yolo26_obb_2class_trial" / "dataset"


def link_or_copy(src: Path, dst: Path) -> None:
    if dst.exists() or dst.is_symlink():
        dst.unlink()
    try:
        dst.symlink_to(src)
    except OSError:
        shutil.copy2(src, dst)


def convert_label_line(line: str) -> str:
    parts = line.strip().split()
    if not parts:
        return ""
    source_class = int(float(parts[0]))
    target_class = 0 if source_class == 0 else 1
    return " ".join([str(target_class), *parts[1:]])


def main() -> None:
    if not SOURCE.exists():
        raise FileNotFoundError(SOURCE)

    for split in ("train", "val", "test"):
        image_out = TARGET / "images" / split
        label_out = TARGET / "labels" / split
        image_out.mkdir(parents=True, exist_ok=True)
        label_out.mkdir(parents=True, exist_ok=True)

        for old in image_out.iterdir():
            if old.is_file() or old.is_symlink():
                old.unlink()
        for old in label_out.iterdir():
            if old.is_file() or old.is_symlink():
                old.unlink()

        for image_path in sorted((SOURCE / "images" / split).iterdir()):
            if image_path.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
                continue
            link_or_copy(image_path, image_out / image_path.name)

            source_label = SOURCE / "labels" / split / f"{image_path.stem}.txt"
            target_label = label_out / f"{image_path.stem}.txt"
            converted = []
            if source_label.exists():
                for line in source_label.read_text(encoding="utf-8").splitlines():
                    converted_line = convert_label_line(line)
                    if converted_line:
                        converted.append(converted_line)
            target_label.write_text("\n".join(converted) + ("\n" if converted else ""), encoding="utf-8")

    (TARGET / "data.yaml").write_text(
        "\n".join(
            [
                f"path: {TARGET}",
                "train: images/train",
                "val: images/val",
                "test: images/test",
                "names:",
                "  0: bottle",
                "  1: manual",
                "",
            ]
        ),
        encoding="utf-8",
    )

    for split in ("train", "val", "test"):
        images = len(list((TARGET / "images" / split).iterdir()))
        objects = 0
        class_counts = {0: 0, 1: 0}
        for label_path in (TARGET / "labels" / split).iterdir():
            for line in label_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                cls = int(line.split()[0])
                objects += 1
                class_counts[cls] += 1
        print(f"{split}: {images} images, {objects} objects, {class_counts}")


if __name__ == "__main__":
    main()
