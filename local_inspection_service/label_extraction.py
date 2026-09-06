"""Single-label geometry. Generated pixels never enter the comparison image."""
from __future__ import annotations

import io
import math
import cv2
import numpy as np
from PIL import Image, ImageOps

PROMPT_VERSION = "single-label-mask-1"


def normalized_image(data: bytes) -> bytes:
    if not data or len(data) > 10 * 1024 * 1024:
        raise ValueError("图片必须存在且不超过 10MB")
    with Image.open(io.BytesIO(data)) as im:
        if im.width * im.height > 20_000_000 or min(im.size) < 100:
            raise ValueError("图片像素尺寸不符合要求")
        im.seek(0)
        im.load()
        rgba = ImageOps.exif_transpose(im).convert("RGBA")
        rgb = Image.new("RGB", rgba.size, "white")
        rgb.paste(rgba, mask=rgba.getchannel("A"))
        out = io.BytesIO()
        rgb.save(out, format="PNG")
        return out.getvalue()


def decode(data: bytes) -> np.ndarray:
    # Bound generated output before OpenCV allocates the decoded pixel buffer.
    if len(data) > 100 * 1024 * 1024:
        raise ValueError("mask_too_large")
    with Image.open(io.BytesIO(data)) as im:
        if im.width * im.height > 20_000_000:
            raise ValueError("mask_too_large")
    image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("image_unreadable")
    return image


def box(value) -> list[float]:
    if not isinstance(value, list) or len(value) != 4:
        raise ValueError("目标框需要四个归一化坐标")
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in value):
        raise ValueError("目标框坐标无效")
    x, y, w, h = map(float, value)
    if min(x, y) < 0 or min(w, h) < .02 or x + w > 1.000001 or y + h > 1.000001:
        raise ValueError("目标框越界或过小")
    return [x, y, w, h]


def cross(a, b, c):
    return (b[0]-a[0])*(c[1]-a[1]) - (b[1]-a[1])*(c[0]-a[0])


def polygon(value) -> list[list[float]]:
    if not isinstance(value, list) or not 3 <= len(value) <= 128:
        raise ValueError("轮廓需要 3–128 个顶点")
    points = []
    for p in value:
        if not isinstance(p, list) or len(p) != 2 or any(isinstance(v, bool) or not isinstance(v, (float, int)) or not math.isfinite(v) or not 0 <= v <= 1 for v in p):
            raise ValueError("轮廓坐标无效")
        points.append(list(map(float, p)))
    n = len(points)
    for i in range(n):
        a, b = points[i], points[(i+1) % n]
        if math.dist(a, b) < 1e-6:
            raise ValueError("轮廓存在重复顶点")
        for j in range(i+1, n):
            if j == i+1 or (i == 0 and j == n-1):
                continue
            c, d = points[j], points[(j+1) % n]
            if (max(a[0], b[0]) >= min(c[0], d[0]) and max(c[0], d[0]) >= min(a[0], b[0])
                    and max(a[1], b[1]) >= min(c[1], d[1]) and max(c[1], d[1]) >= min(a[1], b[1])
                    and cross(a,b,c)*cross(a,b,d) <= 0 and cross(c,d,a)*cross(c,d,b) <= 0):
                raise ValueError("轮廓不能自交或接触自身")
    if abs(sum(cross([0,0], points[i], points[(i+1)%n]) for i in range(n))) < .0001:
        raise ValueError("轮廓面积过小")
    return points


def crop(original: bytes, points) -> tuple[bytes, dict]:
    points = polygon(points)
    image = decode(original)
    h, w = image.shape[:2]
    contour = np.rint(np.array(points) * [w-1, h-1]).astype(np.int32)
    mask = np.zeros((h, w), np.uint8)
    cv2.fillPoly(mask, [contour], 255)
    # A two-pixel outward safety margin preserves edge printing; never erode.
    mask = cv2.dilate(mask, np.ones((5, 5), np.uint8))
    x, y, cw, ch = cv2.boundingRect(contour)
    x0, y0, x1, y1 = max(0,x-4), max(0,y-4), min(w,x+cw+4), min(h,y+ch+4)
    if min(cw, ch) < 100:
        raise ValueError("标签太小，请靠近后重拍")
    image[mask == 0] = 255
    result = image[y0:y1, x0:x1]
    ok, encoded = cv2.imencode(".png", result)
    if not ok:
        raise ValueError("crop_encode_failed")
    gray = cv2.cvtColor(result, cv2.COLOR_BGR2GRAY)
    return encoded.tobytes(), {"bbox": [x0,y0,x1,y1], "width": x1-x0, "height": y1-y0,
                              "laplacian_variance": float(cv2.Laplacian(gray, cv2.CV_64F).var())}


def prepare(original: bytes, target) -> tuple[bytes, dict, str]:
    x,y,bw,bh = box(target)
    image = decode(original)
    h,w = image.shape[:2]
    x0,y0 = max(0,math.floor((x-bw*.1)*w)), max(0,math.floor((y-bh*.1)*h))
    x1,y1 = min(w,math.ceil((x+bw*1.1)*w)), min(h,math.ceil((y+bh*1.1)*h))
    roi = image[y0:y1,x0:x1]
    # Explicit square padding matches existing image providers without stretching.
    side = max(roi.shape[:2])
    canvas = np.zeros((side,side,3),np.uint8)
    canvas[:roi.shape[0],:roi.shape[1]] = roi
    roi = canvas
    scale = min(1, 1536/max(roi.shape[:2]))
    small = cv2.resize(roi, (max(1,round(roi.shape[1]*scale)),max(1,round(roi.shape[0]*scale))))
    ok, data = cv2.imencode(".png", small)
    if not ok:
        raise ValueError("roi_encode_failed")
    local = [(x*w-x0)/side, (y*h-y0)/side, bw*w/side, bh*h/side]
    meta = {"roi": [x0,y0,x1,y1], "canvas_side": side, "source_size": [w,h], "input_size": [small.shape[1],small.shape[0]], "target": target, "local_target": local}
    prompt = ("Return ONLY a binary RGB segmentation image, same framing and aspect ratio as input. "
              "Fill ONE complete individual printed label nearest the target center with #00FF00; everything else #000000. "
              "The target may be rectangular, round or irregular. Follow its physical/die-cut outer boundary, not its text glyphs. "
              "Do not select the whole backing sheet, neighbouring labels, shadows or packaging. "
              "Do not move, rotate, redraw, complete hidden parts, add text or annotations. "
              f"Normalized target rectangle x,y,width,height: {local}. Center: {[local[0]+local[2]/2,local[1]+local[3]/2]}. "
              "If no single complete label is identifiable return all black.")
    return data.tobytes(), meta, prompt


def parse_mask(data: bytes, original: bytes, meta: dict) -> tuple[list, dict]:
    image = decode(data)
    mh,mw = image.shape[:2]
    iw,ih = meta["input_size"]
    if abs((mw/mh)/(iw/ih)-1) > .01:
        raise ValueError("mask_aspect_mismatch")
    b,g,r = cv2.split(image.astype(np.int16))
    green = (g >= 145) & (r <= 145) & (b <= 145) & (g-np.maximum(r,b) >= 35)
    black = np.max(image,axis=2) <= 65
    if float((green | black).mean()) < .97:
        raise ValueError("not_binary_mask")
    count,labels,stats,centers = cv2.connectedComponentsWithStats(green.astype(np.uint8),connectivity=8)
    lx,ly,lw,lh = meta["local_target"]
    cx,cy = (lx+lw/2)*mw, (ly+lh/2)*mh
    candidates = []
    for idx in range(1,count):
        sx,sy,sw,sh,area = stats[idx]
        if area < max(20,mw*mh*.001):
            continue
        px,py = centers[idx]
        if lx*mw <= px <= (lx+lw)*mw and ly*mh <= py <= (ly+lh)*mh:
            candidates.append(idx)
    metrics = {"component_count": count-1, "candidate_count": len(candidates), "mask_size": [mw,mh]}
    if len(candidates) != 1:
        raise ValueError("multiple_labels" if candidates else "no_label")
    idx = candidates[0]
    sx,sy,sw,sh,area = map(int, stats[idx])
    if labels[min(mh-1,int(cy)),min(mw-1,int(cx))] != idx:
        raise ValueError("target_not_centered")
    if sx <= 1 or sy <= 1 or sx+sw >= mw-1 or sy+sh >= mh-1:
        raise ValueError("label_touches_image_edge")
    if sx < lx*mw-1 or sy < ly*mh-1 or sx+sw > (lx+lw)*mw+1 or sy+sh > (ly+lh)*mh+1:
        raise ValueError("label_outside_guide")
    contours,_ = cv2.findContours((labels==idx).astype(np.uint8),cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    contour = max(contours,key=cv2.contourArea)
    epsilon = .001*cv2.arcLength(contour,True)
    approx = cv2.approxPolyDP(contour,epsilon,True)
    while len(approx)>128:
        epsilon *= 1.5
        approx = cv2.approxPolyDP(contour,epsilon,True)
    x0,y0,x1,y1 = meta["roi"]
    w,h = meta["source_size"]
    side = meta["canvas_side"]
    points = [[(x0+float(p[0][0])*side/mw)/(w-1),(y0+float(p[0][1])*side/mh)/(h-1)] for p in approx]
    points = polygon(points)
    # Edge support is an advisory gate, not a claim of semantic completeness.
    source = decode(original)[y0:y1,x0:x1]
    canvas = np.zeros((side,side,3),np.uint8)
    canvas[:source.shape[0],:source.shape[1]] = source
    source = cv2.resize(canvas,(mw,mh))
    edges = cv2.Canny(source,50,150)
    nearby = cv2.dilate(edges,np.ones((7,7),np.uint8))
    boundary = np.zeros((mh,mw),np.uint8)
    cv2.drawContours(boundary,[contour],-1,255,1)
    support = float((nearby[boundary>0]>0).mean())
    metrics["edge_support"] = support
    metrics["requires_manual_adjustment"] = support < .35
    return points, metrics
