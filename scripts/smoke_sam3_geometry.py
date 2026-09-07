"""Synthetic geometry acceptance; does not claim model/sample accuracy."""
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cv2
import numpy as np
from PIL import Image
from local_inspection_service import sam3_geometry as geometry


def png(array):
    stream = io.BytesIO()
    Image.fromarray(array).save(stream, format="PNG")
    return stream.getvalue()


def rejected(data, meta, expected):
    try:
        geometry.parse(data, meta)
    except ValueError as exc:
        assert str(exc) == expected, (str(exc), expected)
    else:
        raise AssertionError("invalid mask accepted")


def main():
    for w,h in [(4096,3072), (3072,4096), (800,600)]:
        source = png(np.zeros((h,w,3), np.uint8))
        _, meta = geometry.prepare(source, [.15,.2,.7,.6])
        iw,ih = meta["input_size"]
        x0,y0,x1,y1 = meta["roi"]
        for x,y in [(x0,y0), (x1-1,y1-1), ((x0+x1)/2,(y0+y1)/2)]:
            local = [((x-x0+.5)*iw/(x1-x0)-.5), ((y-y0+.5)*ih/(y1-y0)-.5)]
            restored = geometry.source_points([local], meta)[0]
            assert abs(restored[0]*(w-1)-x) < 1e-6
            assert abs(restored[1]*(h-1)-y) < 1e-6
        mask = np.zeros((ih,iw), np.uint8)
        cv2.rectangle(mask, (iw//4,ih//4), (iw*3//4,ih*3//4), 255, -1)
        points, metrics = geometry.parse(png(mask), meta)
        assert len(points) == 4 and metrics["contour_iou"] == 1
        rejected(png(mask[:ih-1]), meta, "mask_format_or_size_mismatch")
        damaged = mask.copy()
        damaged[ih//2,iw//2] = 127
        rejected(png(damaged), meta, "not_binary_mask")
        damaged[ih//2,iw//2] = 0
        rejected(png(damaged), meta, "mask_contains_holes")
        damaged = mask.copy()
        damaged[2,2] = 255
        rejected(png(damaged), meta, "multiple_components")
        rejected(png(np.zeros_like(mask)), meta, "no_label")
    print("SAM3 synthetic geometry checks passed (not model acceptance)")


if __name__ == "__main__":
    main()
