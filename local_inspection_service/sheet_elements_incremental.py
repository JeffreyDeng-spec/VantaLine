"""One tiled detection pass, then cached, demand-driven recognition batches."""
import math
import time

import cv2
import numpy as np

from . import sheet_elements as e

VERSION = "sheet-incremental-1"
BATCH_SIZE = 32
PARAMETER_EVIDENCE = 3


def crop_line(image, polygon):
    points = np.asarray(polygon, np.float32).reshape(4, 2)
    # Detector quads are ordered TL, TR, BR, BL; rectify only OCR input.
    width = max(np.linalg.norm(points[0]-points[1]), np.linalg.norm(points[2]-points[3]))
    height = max(np.linalg.norm(points[0]-points[3]), np.linalg.norm(points[1]-points[2]))
    w,h = max(2, math.ceil(width)), max(2, math.ceil(height))
    target = np.float32([[0,0],[w-1,0],[w-1,h-1],[0,h-1]])
    patch = cv2.warpPerspective(image, cv2.getPerspectiveTransform(points,target),(w,h))
    return np.ascontiguousarray(np.rot90(patch) if h > 1.5*w else patch)


def audit(elements, observations):
    rows = e.compare([v for v in elements if v["type"] in {"text","parameter"}],observations)["elements"]
    missing = [row["element_id"] for row in rows if row["state"] not in {"matched","ignored"}]
    parameters = [v for v in elements if v["required"] and v["type"] == "parameter"]
    pending = []
    for element in parameters:
        matches = e.deduplicate([v for v in observations if v["kind"] == "text" and
            v["confidence"] >= e.MIN_CONFIDENCE and e.contains_content(element["expected"],v["text"],"exact")])
        if len(matches) < PARAMETER_EVIDENCE: pending.append(element["id"])
    return missing, pending


def observe(image, detect, recognize, deadline, elements=None, progress=lambda *_:None):
    """None inventory means exhaustive standard modelling, never early stopping."""
    height,width = image.shape[:2]
    observations,stages,boxes = [],[],[]
    tiles = list(e.tile_boxes(width,height))
    need_text = elements is None or any(v["required"] and v["type"] in {"text","parameter"} for v in elements)
    need_codes = elements is None or any(v["required"] and v["type"] == "code" for v in elements)
    decoder = "not_required"
    def check():
        if time.time() >= deadline: raise e.ObservationTimeout(observations,stages)
    try:
        for index,(x,y,x2,y2) in enumerate(tiles):
            check(); started=time.monotonic(); tile=image[y:y2,x:x2]
            if need_text:
                for polygon in detect(tile):
                    points=np.asarray(polygon,dtype=float)
                    if points.shape != (4,2) or not np.isfinite(points).all(): continue
                    points += [x,y]
                    try: box=e.normalized_box(points,width,height)
                    except ValueError: continue
                    # Retain only valid convex quads; no synthetic completion at crop borders.
                    if not cv2.isContourConvex(points.astype(np.float32)): continue
                    boxes.append({"polygon":points.tolist(),"box":box,"tile":index})
                    if len(boxes)>e.MAX_OBSERVATIONS*2: raise ValueError("too_many_detected_regions")
            if need_codes:
                codes,decoder=e.decode_codes(tile)
                for value in codes:
                    points=np.asarray(value["polygon"],float)+[x,y]
                    observations.append({"text":value["text"],"kind":"code","confidence":1.,
                        "box":e.normalized_box(points,width,height),"rotation":0,"tile":index})
            stages.append({"stage":"detect","tile":index,"elapsed_ms":round((time.monotonic()-started)*1000)})
            progress("detecting",{"tile":index+1,"tiles":len(tiles)})
        # Larger complete quads precede tile-edge fragments; deduplicate BEFORE recognition.
        unique=[]
        for box in sorted(boxes,key=lambda v: -v["box"][2]*v["box"][3]):
            if any(e.overlap_ratio(box["box"],v["box"])>.75 and
                   min(box["box"][2]*box["box"][3],v["box"][2]*v["box"][3])/
                   max(box["box"][2]*box["box"][3],v["box"][2]*v["box"][3])>.6 for v in unique): continue
            unique.append(box)
        if len(unique)>e.MAX_OBSERVATIONS: raise ValueError("too_many_detected_regions")
        for index,box in enumerate(unique):
            check(); patch=crop_line(image,box["polygon"])
            gray=cv2.cvtColor(patch,cv2.COLOR_BGR2GRAY)
            box.update(id=index,quality=float(np.log1p(cv2.Laplacian(gray,cv2.CV_64F).var())),aspect=patch.shape[1]/patch.shape[0])
        pending=list(unique); recognized=0; batches=[]; reason="exhausted"
        while pending:
            check()
            missing,parameter_pending = audit(elements,observations) if elements is not None else ([],[])
            if elements is not None and not missing and not parameter_pending:
                reason="coverage_and_parameter_audit";break
            wanted=[v for v in (elements or []) if v["id"] in missing+parameter_pending]
            # Aspect only schedules work; never creates matching evidence.
            def rank(box):
                aspect_hint=max((1/(1+abs(math.log(max(.1,box["aspect"])/max(1,len(v["expected"])*.5)))) for v in wanted),default=0.)
                return box["quality"]+2*aspect_hint
            pending.sort(key=rank,reverse=True)
            batch=pending[:BATCH_SIZE];pending=pending[BATCH_SIZE:]
            started=time.monotonic()
            values=recognize([crop_line(image,v["polygon"]) for v in batch])
            if len(values)!=len(batch): raise ValueError("recognition_batch_length_mismatch")
            for box,value in zip(batch,values):
                text=str(value.get("text","")); confidence=float(value.get("confidence",0))
                if text.strip() and len(text)<=2000 and math.isfinite(confidence) and 0<=confidence<=1:
                    observations.append({"text":text,"confidence":confidence,"box":box["box"],"kind":"text",
                        "rotation":1 if box["box"][3]*height>1.5*box["box"][2]*width else 0,
                        "tile":box["tile"],"region_id":box["id"]})
            recognized+=len(batch)
            missing,parameter_pending=audit(elements,observations) if elements is not None else ([],[])
            stage={"stage":"recognize","regions":[v["id"] for v in batch],"elapsed_ms":round((time.monotonic()-started)*1000),
                   "missing_element_ids":missing,"parameter_audit_pending":parameter_pending}
            stages.append(stage);batches.append(stage)
            progress("recognizing",{"recognized_regions":recognized,"detected_regions":len(unique),"missing_element_ids":missing,"parameter_audit_pending":parameter_pending})
        check(); missing,parameter_pending=audit(elements,observations) if elements is not None else ([],[])
        return e.deduplicate(observations),{"version":VERSION,"source_size":[width,height],"tiles":stages,
            "detection_passes":1 if need_text else 0,"detected_regions":len(unique),"recognized_regions":recognized,
            "skipped_regions":len(pending),"stop_reason":reason,"code_decoder":decoder,
            "conflict_audit_complete":not parameter_pending,"parameter_audit_pending":parameter_pending,
            "audit_scope":"three_matching_locations_per_parameter_not_exhaustive_defect_detection"}
    except TimeoutError:
        raise e.ObservationTimeout(observations,stages) from None
