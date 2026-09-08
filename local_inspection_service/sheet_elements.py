"""Whole-sheet content evidence, independent of silhouette extraction and PLC.

Coordinates are normalized against the orientation-normalized source. OCR is
injected so matching/geometry tests never need a model or an external service.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import time
from typing import Callable

import cv2
import numpy as np

VERSION = "sheet-elements-3"
TILE_SIZE = 1536
OVERLAP = 256
MIN_CONFIDENCE = .90
MAX_OBSERVATIONS = 6000
TYPES = {"text", "parameter", "code", "graphic"}


class ObservationTimeout(TimeoutError):
    def __init__(self, observations, stages):
        super().__init__("sheet_deadline_exceeded")
        self.observations = deduplicate(observations)
        self.stages = stages


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def rectangle(value):
    if not isinstance(value, list) or len(value) != 4 or any(
        type(v) not in (int, float) or not math.isfinite(v) for v in value
    ):
        raise ValueError("invalid_element_rectangle")
    x, y, w, h = map(float, value)
    if min(x, y) < 0 or min(w, h) <= 0 or x+w > 1.00000001 or y+h > 1.00000001:
        raise ValueError("element_rectangle_outside_image")
    return [x, y, w, h]


def validate_elements(values):
    if not isinstance(values, list) or not 1 <= len(values) <= 200:
        raise ValueError("require_1_to_200_elements")
    result, ids = [], set()
    for value in values:
        if not isinstance(value, dict):
            raise ValueError("invalid_element")
        identifier = value.get("id", "")
        kind = value.get("type")
        expected = value.get("expected", "")
        if not isinstance(identifier, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", identifier) or identifier in ids:
            raise ValueError("invalid_or_duplicate_element_id")
        if kind not in TYPES or not isinstance(expected, str) or len(expected) > 2000:
            raise ValueError("invalid_element_content")
        if kind != "graphic" and not expected.strip():
            raise ValueError("empty_expected_content")
        required = value.get("required", True)
        if type(required) is not bool:
            raise ValueError("invalid_required_flag")
        reason = value.get("ignore_reason", "")
        if not isinstance(reason, str) or len(reason) > 500 or (not required and not reason.strip()):
            raise ValueError("ignored_elements_require_reason")
        mode = value.get("match", "exact")
        if mode not in {"exact", "whitespace"} or (kind != "text" and mode != "exact"):
            raise ValueError("invalid_matching_rule")
        ids.add(identifier)
        result.append({"id": identifier, "type": kind, "expected": expected.strip(),
                       "box": rectangle(value.get("box")), "required": required,
                       "ignore_reason": reason, "match": mode})
    if not any(v["required"] for v in result):
        raise ValueError("at_least_one_required_element")
    return result


def tile_boxes(width, height, size=TILE_SIZE, overlap=OVERLAP):
    def starts(length):
        values = list(range(0, max(1, length-size+1), size-overlap))
        return sorted(set(values+[max(0, length-size)]))
    for y in starts(height):
        for x in starts(width):
            yield x, y, min(width, x+size), min(height, y+size)


def restore_points(points, quarter_turns, width, height, x=0, y=0):
    """Inverse of np.rot90 on pixel centers; no resize or perspective warp."""
    p = np.asarray(points, dtype=float).reshape(-1, 2)
    a, b = p[:, 0].copy(), p[:, 1].copy()
    if quarter_turns == 1:
        p[:, 0], p[:, 1] = width-1-b, a
    elif quarter_turns == 2:
        p[:, 0], p[:, 1] = width-1-a, height-1-b
    elif quarter_turns == 3:
        p[:, 0], p[:, 1] = b, height-1-a
    p += [x, y]
    return p


def normalized_box(points, width, height):
    p = np.asarray(points, dtype=float)
    if p.shape != (4, 2) or not np.isfinite(p).all():
        raise ValueError("invalid_observation_polygon")
    lo = np.maximum([0, 0], p.min(axis=0))
    hi = np.minimum([width, height], p.max(axis=0)+1)
    return rectangle([float(lo[0]/width), float(lo[1]/height), float((hi[0]-lo[0])/width), float((hi[1]-lo[1])/height)])


def overlap_ratio(a, b):
    x = max(0, min(a[0]+a[2], b[0]+b[2])-max(a[0], b[0]))
    y = max(0, min(a[1]+a[3], b[1]+b[3])-max(a[1], b[1]))
    return x*y / max(1e-12, min(a[2]*a[3], b[2]*b[3]))


def deduplicate(observations):
    # Only same-content observations at the same source location are duplicates.
    groups = {}
    for value in sorted(observations, key=lambda o: -o["confidence"]):
        key = (value["kind"], value["text"])
        kept = groups.setdefault(key, [])
        if not any(overlap_ratio(value["box"], previous["box"]) > .7 for previous in kept):
            kept.append(value)
    return [item for values in groups.values() for item in values]


def decode_codes(image):
    """ZXing if provisioned; OpenCV QR fallback never claims barcode coverage."""
    try:
        import zxingcpp
    except ImportError:
        detector = cv2.QRCodeDetector()
        try:
            ok, texts, points, _ = detector.detectAndDecodeMulti(image)
        except cv2.error:
            return [], "opencv_qr_only"
        return ([{"text": text, "polygon": polygon.tolist()} for text, polygon in zip(texts, points)
                 if text] if ok else []), "opencv_qr_only"
    values = []
    for result in zxingcpp.read_barcodes(image):
        if result.valid:
            p = result.position
            values.append({"text": result.text, "polygon": [[v.x, v.y] for v in
                          (p.top_left, p.top_right, p.bottom_right, p.bottom_left)]})
    return values, "zxingcpp"


def observe(image, ocr: Callable, deadline, progress=lambda *_: None, rotations=(0, 1)):
    height, width = image.shape[:2]
    observations, stages, decoder = [], [], "not_run"
    tiles = list(tile_boxes(width, height))
    for i, (x, y, x2, y2) in enumerate(tiles):
        tile = image[y:y2, x:x2]
        for rotation in rotations:
            if time.time() >= deadline:
                raise ObservationTimeout(observations, stages)
            start = time.monotonic()
            rotated = np.ascontiguousarray(np.rot90(tile, rotation))
            try:
                raw_observations=ocr(rotated)
            except TimeoutError:
                raise ObservationTimeout(observations,stages) from None
            for raw in raw_observations:
                text, confidence = str(raw["text"]), float(raw["confidence"])
                if not text.strip() or len(text) > 2000 or not math.isfinite(confidence) or not 0 <= confidence <= 1:
                    continue
                try:
                    points = restore_points(raw["polygon"], rotation, x2-x, y2-y, x, y)
                    box = normalized_box(points, width, height)
                except (ValueError, TypeError):
                    continue
                observations.append({"text": text, "confidence": confidence, "box": box,
                                     "kind": "text", "rotation": rotation, "tile": i})
            stages.append({"tile": i, "rotation": rotation, "source_box": [x,y,x2,y2],
                           "elapsed_ms": round((time.monotonic()-start)*1000)})
            if len(observations) > MAX_OBSERVATIONS*2:
                observations = deduplicate(observations)
                if len(observations) > MAX_OBSERVATIONS:
                    raise ValueError("too_many_observations")
            try:
                progress("recognizing", {"tile": i+1, "tiles": len(tiles), "rotation": rotation})
            except TimeoutError:
                raise ObservationTimeout(observations, stages) from None
        codes, decoder = decode_codes(tile)
        for code in codes:
            points = np.asarray(code["polygon"], dtype=float)+[x,y]
            observations.append({"text": code["text"], "confidence": 1., "kind": "code",
                                 "box": normalized_box(points, width, height), "rotation": 0, "tile": i})
    if time.time() >= deadline:
        raise ObservationTimeout(observations, stages)
    values = deduplicate(observations)
    if len(values) > MAX_OBSERVATIONS:
        raise ValueError("too_many_observations")
    return values, {"version": VERSION, "source_size": [width,height], "tiles": stages,
                    "code_decoder": decoder, "observations": len(values)}


def draft_elements(observations):
    result = []
    for value in observations[:200]:
        kind = "code" if value["kind"] == "code" else "parameter" if re.search(r"\d", value["text"]) else "text"
        result.append({"id": "el_"+str(len(result)+1), "type": kind, "expected": value["text"],
                       "box": value["box"], "required": True, "ignore_reason": "",
                       "match": "whitespace" if kind == "text" else "exact"})
    return result


def normalized_text(text, mode):
    return re.sub(r"\s+", " ", text).strip() if mode == "whitespace" else text.strip()


def contains_content(expected, actual, mode):
    expected, actual = normalized_text(expected, mode), normalized_text(actual, mode)
    # Boundaries prevent 20V within 120V, ABC within ABC-123, and 2 within 2.5.
    return any((m.start() == 0 or not re.match(r"[\w.+/-]", actual[m.start()-1])) and
               (m.end() == len(actual) or not re.match(r"[\w.+/-]", actual[m.end()]))
               for m in re.finditer(re.escape(expected), actual))


def candidates(observations, mode):
    values = [v for v in observations if v["kind"] == "text"]
    yield from values
    if mode != "whitespace":
        return
    # Join only spatially adjacent horizontal lines from the same orientation.
    # Never concatenate all page tokens. Rotated/more ambiguous runs remain review.
    ordered = sorted((v for v in values if v["rotation"] == 0), key=lambda v: v["box"][1])
    for first in ordered:
        chain = [first]
        last = first
        for _ in range(3):
            a = last["box"]
            nearby = [v for v in ordered if v not in chain and
                      0 <= v["box"][1]-(a[1]+a[3]) <= a[3]*.65 and
                      abs(v["box"][0]-a[0]) <= max(a[3], v["box"][3])*.75 and
                      .5 <= v["box"][2]/a[2] <= 2]
            if len(nearby) != 1:
                break
            last = nearby[0]
            chain.append(last)
            x = min(v["box"][0] for v in chain); y = min(v["box"][1] for v in chain)
            right = max(v["box"][0]+v["box"][2] for v in chain)
            bottom = max(v["box"][1]+v["box"][3] for v in chain)
            yield {**first, "text": " ".join(v["text"] for v in chain), "box": [x,y,right-x,bottom-y],
                   "confidence": min(v["confidence"] for v in chain), "joined": True}


def numeric_signature(text):
    return re.sub(r"\d+(?:[.,]\d+)?", "#", re.sub(r"\s+", "", text))


def graphic_evidence(reference, actual, box, deadline):
    """Retrieve a diagnostic candidate, NOT certification of a tiny-symbol match."""
    h, w = reference.shape[:2]
    x,y,bw,bh = box
    patch = reference[int(y*h):math.ceil((y+bh)*h), int(x*w):math.ceil((x+bw)*w)]
    gray = cv2.cvtColor(actual, cv2.COLOR_BGR2GRAY)
    best = None
    for rotation in range(4):
        for scale in (.5, .75, 1., 1.5, 2.):
            if time.time() >= deadline:
                raise TimeoutError("sheet_deadline_exceeded")
            p = cv2.resize(np.rot90(patch, rotation).copy(), None, fx=scale, fy=scale)
            p = cv2.cvtColor(p, cv2.COLOR_BGR2GRAY)
            ph,pw = p.shape
            if min(ph,pw) < 8 or ph > gray.shape[0] or pw > gray.shape[1] or p.std() < 5:
                continue
            _, score, _, loc = cv2.minMaxLoc(cv2.matchTemplate(gray,p,cv2.TM_CCOEFF_NORMED))
            if best is None or score > best["score"]:
                best = {"score": float(score), "rotation": rotation, "scale": scale,
                        "box": [loc[0]/gray.shape[1],loc[1]/gray.shape[0],pw/gray.shape[1],ph/gray.shape[0]]}
    if best:
        # Geometric verification is independent of correlation. Repeated
        # texture and a missing slash must not pass based on one similarity.
        ax,ay,aw,ah=best["box"]; sh,sw=actual.shape[:2]
        left=max(0,int(ax*sw)-12);top=max(0,int(ay*sh)-12)
        region=actual[top:min(sh,math.ceil((ay+ah)*sh)+12),left:min(sw,math.ceil((ax+aw)*sw)+12)]
        orb=cv2.ORB_create(nfeatures=1200,edgeThreshold=5,fastThreshold=7)
        pg=cv2.cvtColor(patch,cv2.COLOR_BGR2GRAY);rg=cv2.cvtColor(region,cv2.COLOR_BGR2GRAY)
        kp1,d1=orb.detectAndCompute(pg,None);kp2,d2=orb.detectAndCompute(rg,None)
        best["geometry_verified"]=False
        if d1 is not None and d2 is not None and len(d2)>=2:
            pairs=cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(d1,d2,k=2)
            good=[pair[0] for pair in pairs if len(pair)==2 and pair[0].distance < .7*pair[1].distance]
            if len(good)>=12:
                a=np.float32([kp1[m.queryIdx].pt for m in good]);b=np.float32([kp2[m.trainIdx].pt for m in good])
                homography,inliers=cv2.findHomography(a,b,cv2.RANSAC,2.)
                if homography is not None and inliers is not None and np.isfinite(homography).all() and abs(np.linalg.det(homography))>1e-8:
                    ph,pw=pg.shape
                    corners=np.float32([[[0,0],[pw-1,0],[pw-1,ph-1],[0,ph-1]]])
                    mapped=cv2.perspectiveTransform(corners,homography)[0]
                    valid=bool(np.isfinite(mapped).all() and cv2.isContourConvex(mapped.astype(np.float32)))
                    if valid and inliers.sum()>=12 and inliers.mean()>=.6:
                        aligned=cv2.warpPerspective(rg,np.linalg.inv(homography),(pw,ph))
                        coverage=cv2.warpPerspective(np.full(rg.shape,255,np.uint8),np.linalg.inv(homography),(pw,ph))
                        edge1=cv2.Canny(pg,60,150);edge2=cv2.Canny(aligned,60,150)
                        delta=cv2.absdiff(pg,aligned)
                        edge_union=(edge1>0)|(edge2>0)
                        edge_disagreement=float(np.mean((edge1!=edge2)[edge_union])) if edge_union.any() else 1.
                        best.update(inliers=int(inliers.sum()),inlier_ratio=float(inliers.mean()),
                                    coverage=float(np.mean(coverage==255)),pixel_difference_fraction=float(np.mean(delta>35)),
                                    edge_disagreement=edge_disagreement,homography=homography.tolist())
                        best["geometry_verified"]=best["coverage"]>=.995 and best["pixel_difference_fraction"]<=.005 and edge_disagreement<=.02
    return best


def compare(elements, observations, reference=None, actual=None, deadline=float("inf"), graphic_verified=False):
    rows = []
    exact = list(candidates(observations, "exact"))
    joined = list(candidates(observations, "whitespace")) if any(e["match"] == "whitespace" for e in elements) else exact
    for element in elements:
        if time.time() >= deadline:
            raise TimeoutError("sheet_deadline_exceeded")
        row = {"element_id": element["id"], "expected": element["expected"], "standard_box": element["box"],
               "type": element["type"], "evidence": [], "state": "unreadable", "reason": "not_detected"}
        if not element["required"]:
            row.update(state="ignored", reason=element["ignore_reason"])
        elif element["type"] == "graphic":
            row["reason"] = "graphic_not_commissioned"
            if reference is not None and actual is not None:
                row["candidate"] = graphic_evidence(reference, actual, element["box"], deadline)
                candidate=row["candidate"]
                if graphic_verified and candidate and candidate.get("geometry_verified"):
                    row.update(state="matched",reason="local_geometric_evidence",evidence=[{"text":"graphic","box":candidate["box"],"confidence":candidate["score"]}])
        else:
            pool = [v for v in observations if v["kind"] == "code"] if element["type"] == "code" else joined if element["match"] == "whitespace" else exact
            matches = [v for v in pool if v["confidence"] >= MIN_CONFIDENCE and
                       (v["text"] == element["expected"] if element["type"] == "code" else
                        contains_content(element["expected"],v["text"],element["match"]))]
            if matches:
                row.update(state="matched", reason="local_evidence", evidence=matches[:8], evidence_count=len(matches))
            if element["type"] == "parameter" and re.search(r"\d",element["expected"]):
                signature = numeric_signature(element["expected"])
                conflicts = [v for v in exact if v["confidence"] >= MIN_CONFIDENCE and
                             numeric_signature(v["text"]) == signature and
                             re.sub(r"\s+","",v["text"]) != re.sub(r"\s+","",element["expected"])]
                if conflicts:
                    row.update(state="conflict",reason="conflicting_parameter",conflicts=conflicts[:8])
                    corroborated={}
                    for value in deduplicate(conflicts):
                        if value["confidence"]>=.98:
                            corroborated.setdefault(value["text"],[]).append(value)
                    if not matches and any(len(values)>=2 for values in corroborated.values()):
                        row.update(state="wrong",reason="consistent_parameter_mismatch")
        rows.append(row)
    complete = all(r["state"] in {"matched","ignored"} for r in rows) and any(r["state"] == "matched" for r in rows)
    return {"decision": "DIFFERENCES" if any(r["state"]=="wrong" for r in rows) else "MATCH" if complete else "REVIEW_REQUIRED", "elements": rows,
            "counts": {state: sum(r["state"] == state for r in rows) for state in
                       ("matched","ignored","unreadable","conflict","wrong")}, "version": VERSION,
            "scope": "whole_sheet_content_presence_not_individual_print_defects"}


def annotate(image, result, standard=True):
    output = image.copy(); h,w = output.shape[:2]
    for index, row in enumerate(result["elements"]):
        color = (40,170,40) if row["state"] == "matched" else (30,30,220) if row["state"] in {"conflict","wrong"} else (0,180,240)
        boxes = [row["standard_box"]] if standard else [v["box"] for v in row.get("evidence",[]) + row.get("conflicts",[])]
        for x,y,bw,bh in boxes:
            a,b = (round(x*w),round(y*h)),(round((x+bw)*w),round((y+bh)*h))
            cv2.rectangle(output,a,b,color,max(1,round(max(w,h)/800)))
            cv2.putText(output,str(index+1),a,cv2.FONT_HERSHEY_SIMPLEX,.6,color,2)
    ok,data = cv2.imencode(".png",output)
    if not ok: raise ValueError("annotation_encode_failed")
    return data.tobytes()
