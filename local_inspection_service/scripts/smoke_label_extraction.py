#!/usr/bin/env python3
"""Deterministic segmentation fixtures; no paid model calls or customer images."""
import io
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import cv2
import numpy as np
from PIL import Image
from local_inspection_service import label_extraction as g


def encoded(image):
    return cv2.imencode(".png",image)[1].tobytes()


def rejects(fn, code=None):
    try:
        fn()
    except ValueError as exc:
        if code:
            assert code in str(exc), str(exc)
    else:
        raise AssertionError("invalid input accepted")


def main():
    for shape in ("rectangle","circle","irregular"):
        original = np.full((800,1000,3),90,np.uint8)
        target_mask = np.zeros((800,1000),np.uint8)
        if shape == "rectangle": cv2.rectangle(target_mask,(300,230),(700,570),255,-1)
        elif shape == "circle": cv2.circle(target_mask,(500,400),170,255,-1)
        else: cv2.fillPoly(target_mask,[np.array([[350,230],[620,240],[710,360],[600,570],[300,500],[360,380]])],255)
        original[target_mask>0] = 240
        cv2.putText(original,"ABC 123",(390,400),cv2.FONT_HERSHEY_SIMPLEX,1,(10,20,30),2)
        source = encoded(original)
        data,meta,_ = g.prepare(source,[.15,.15,.7,.7])
        x0,y0,x1,y1=meta["roi"]
        side=meta["canvas_side"]
        mask=np.zeros((side,side,3),np.uint8)
        mask[:y1-y0,:x1-x0,1]=target_mask[y0:y1,x0:x1]
        points,metrics=g.parse_mask(encoded(mask),source,meta)
        assert metrics["candidate_count"]==1 and metrics["edge_support"]>.35
        crop,quality=g.crop(source,points)
        result=g.decode(crop)
        a,b,c,d=quality["bbox"]
        # No generated pixels: each output pixel is either original or white.
        assert np.all(np.all(result==original[b:d,a:c],axis=2) | np.all(result==255,axis=2))
        assert np.any(np.all(result==[10,20,30],axis=2)), "printed text lost"
        wrong=cv2.resize(mask,(side,side//2))
        rejects(lambda:g.parse_mask(encoded(wrong),source,meta),"aspect")
        rejects(lambda:g.parse_mask(data,source,meta),"not_binary_mask")
    rejects(lambda:g.box([0,0,2,1]))
    rejects(lambda:g.box([0,0,float("nan"),1]))
    rejects(lambda:g.polygon([[.1,.1],[.9,.9],[.1,.9],[.9,.1]]))
    rejects(lambda:g.polygon([[.1,.1],[.5,.5],[.5,.5]]))
    rejects(lambda:g.polygon([[.1,.1],[True,.5],[.8,.9]]))
    # Two equally plausible labels must not silently choose the largest.
    source=encoded(np.full((800,800,3),128,np.uint8))
    _,meta,_=g.prepare(source,[.1,.1,.8,.8])
    side=meta["canvas_side"]
    mask=np.zeros((side,side,3),np.uint8)
    cv2.rectangle(mask,(130,200),(290,450),(0,255,0),-1)
    cv2.rectangle(mask,(350,200),(530,450),(0,255,0),-1)
    rejects(lambda:g.parse_mask(encoded(mask),source,meta),"multiple_labels")
    rejects(lambda:g.parse_mask(encoded(np.zeros_like(mask)),source,meta),"no_label")
    # JPEG orientation is normalized before defining the coordinate space.
    im=Image.new("RGB",(400,200),"red"); exif=im.getexif(); exif[274]=6
    buf=io.BytesIO(); im.save(buf,"JPEG",exif=exif)
    assert g.decode(g.normalized_image(buf.getvalue())).shape[:2]==(400,200)
    print("single label extraction geometry smoke: PASS")


if __name__=="__main__": main()
