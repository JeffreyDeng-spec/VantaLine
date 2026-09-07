"""Lossless binary-mask transport geometry, separate from generated color masks."""
import io
import math

import cv2
import numpy as np
from PIL import Image

from . import label_extraction as geometry


def prepare(original, target):
    x, y, bw, bh = geometry.box(target)
    image = geometry.decode(original)
    h, w = image.shape[:2]
    x0, y0 = max(0, math.floor((x-bw*.1)*w)), max(0, math.floor((y-bh*.1)*h))
    x1, y1 = min(w, math.ceil((x+bw*1.1)*w)), min(h, math.ceil((y+bh*1.1)*h))
    roi = image[y0:y1, x0:x1]
    scale = min(1., 2048/max(roi.shape[:2]))
    iw, ih = round(roi.shape[1]*scale), round(roi.shape[0]*scale)
    if min(iw, ih) < 100:
        raise ValueError("target_too_small")
    if scale < 1:
        roi = cv2.resize(roi, (iw, ih), interpolation=cv2.INTER_AREA)
    sx, sy = iw/(x1-x0), ih/(y1-y0)
    # Pixel-center mapping, consistent with OpenCV resize in both directions.
    box = [(x*w-x0+.5)*sx-.5, (y*h-y0+.5)*sy-.5,
           ((x+bw)*w-x0+.5)*sx-.5, ((y+bh)*h-y0+.5)*sy-.5]
    if box[0] < 0 or box[1] < 0 or box[2] >= iw or box[3] >= ih:
        raise ValueError("guide_touches_source_edge")
    ok, encoded = cv2.imencode(".png", roi)
    if not ok:
        raise ValueError("roi_encode_failed")
    return encoded.tobytes(), {"roi": [x0,y0,x1,y1], "source_size": [w,h],
                              "input_size": [iw,ih], "box": box, "target": target}


def source_points(points, meta):
    x0,y0,x1,y1 = meta["roi"]
    iw,ih = meta["input_size"]
    w,h = meta["source_size"]
    return [[(x0+(float(x)+.5)*(x1-x0)/iw-.5)/(w-1),
             (y0+(float(y)+.5)*(y1-y0)/ih-.5)/(h-1)] for x,y in points]


def parse(data, meta):
    if not data or len(data) > 8*1024*1024:
        raise ValueError("invalid_binary_mask")
    with Image.open(io.BytesIO(data)) as image:
        if image.format != "PNG" or image.mode != "L" or list(image.size) != meta["input_size"]:
            raise ValueError("mask_format_or_size_mismatch")
        mask = np.asarray(image)
        if not np.isin(mask, [0,255]).all():
            raise ValueError("not_binary_mask")
    count, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    # No largest-component fallback, fragment removal, dilation or hole filling.
    if count != 2:
        raise ValueError("multiple_components" if count > 2 else "no_label")
    x,y,w,h,area = map(int, stats[1])
    iw,ih = meta["input_size"]
    if x <= 1 or y <= 1 or x+w >= iw-1 or y+h >= ih-1:
        raise ValueError("label_touches_image_edge")
    bx,by,ex,ey = meta["box"]
    if x < bx-1 or y < by-1 or x+w-1 > ex+1 or y+h-1 > ey+1:
        raise ValueError("label_outside_guide")
    contours, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    if len(contours) != 1:
        raise ValueError("mask_contains_holes")
    contour = contours[0]
    epsilon = .25
    approx = cv2.approxPolyDP(contour, epsilon, True)
    while len(approx) > 128 and epsilon < 2:
        epsilon *= 1.5
        approx = cv2.approxPolyDP(contour, epsilon, True)
    points = geometry.polygon(source_points(approx[:,0,:], meta))
    reconstructed = np.zeros_like(mask)
    cv2.fillPoly(reconstructed, [approx], 255)
    intersection = np.count_nonzero((mask > 0) & (reconstructed > 0))
    union = np.count_nonzero((mask > 0) | (reconstructed > 0))
    if intersection/union < .995:
        raise ValueError("contour_approximation_loss")
    return points, {"area": area, "contour_iou": intersection/union,
                    "requires_manual_adjustment": False}
