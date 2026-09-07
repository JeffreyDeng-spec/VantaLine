"""Deterministic evidence tests, not an OCR/model accuracy certificate."""
import math
import sys
import time
import multiprocessing
from pathlib import Path

import numpy as np
import cv2
import zxingcpp

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from local_inspection_service import sheet_elements as e
from local_inspection_service import sheet_elements_vlm as advisory
from local_inspection_service import sheet_elements_runtime as runtime


def item(text="20V", kind="parameter", **kwargs):
    return {"id":"e1","type":kind,"expected":text,"box":[.1,.1,.3,.1],
            "required":True,"ignore_reason":"","match":"exact",**kwargs}


def observation(text="20V", x=.1, confidence=.98, kind="text"):
    return {"text":text,"confidence":confidence,"kind":kind,"box":[x,.1,.2,.1],"rotation":0,"tile":0}


def main():
    # Pixel centers must round-trip in all orientations and all tile origins.
    for w,h in [(4096,3072),(3072,4096),(1080,1919),(317,129)]:
        for k in range(4):
            p=np.array([[0,0],[w-1,0],[w-1,h-1],[0,h-1],[w*.3,h*.6]])
            x,y=p[:,0],p[:,1]
            q=p.copy() if k==0 else np.column_stack((y,w-1-x)) if k==1 else np.column_stack((w-1-x,h-1-y)) if k==2 else np.column_stack((h-1-y,x))
            assert np.max(np.abs(e.restore_points(q,k,w,h,13,27)-(p+[13,27])))<1e-9
    for w,h in [(4000,3000),(100,200),(1600,1700)]:
        covered=np.zeros((h,w),dtype=bool)
        for x,y,x2,y2 in e.tile_boxes(w,h): covered[y:y2,x:x2]=True
        assert covered.all()
    for invalid in ([0,0,float("nan"),.1],[True,0,.1,.1],[.9,.9,.2,.2]):
        try:e.rectangle(invalid)
        except ValueError:pass
        else:raise AssertionError("invalid coordinate accepted")
    assert not e.contains_content("20V","120V","exact")
    assert not e.contains_content("2","2.5","exact")
    assert not e.contains_content("ABC","ABC-123","exact")
    assert not e.contains_content("2Ah","2AH","exact")
    assert e.contains_content("20V","Voltage: 20V","exact")
    assert e.contains_content("read the manual","read\n the  manual","whitespace")
    assert not e.contains_content("20V","20 V","exact")
    assert len(e.deduplicate([observation(),observation(),observation(x=.7)]))==2
    assert e.compare([item()],[observation()])["decision"]=="MATCH"
    assert e.compare([item()],[observation(confidence=.5)])["decision"]=="REVIEW_REQUIRED"
    result=e.compare([item()],[observation(),observation("18V",x=.7)])
    assert result["decision"]=="REVIEW_REQUIRED" and result["elements"][0]["state"]=="conflict"
    assert e.compare([item()],[observation("120V")])["decision"]!="MATCH"
    assert e.compare([item("QR-A","code")],[observation("QR-B",kind="code")])["decision"]!="MATCH"
    assert e.compare([item("QR-A","code")],[observation("QR-A",kind="code")])["decision"]=="MATCH"
    assert e.compare([item("logo","graphic")],[])["elements"][0]["reason"]=="graphic_not_commissioned"
    # Global coverage is intentional: separate copies can provide each element.
    assert e.compare([item(),item("2Ah",id="e2")],[observation(),observation("2Ah",x=.7)])["decision"]=="MATCH"
    for values in ([item(),item()], [item(required=False)], [item("",kind="text")]):
        try:e.validate_elements(values)
        except ValueError:pass
        else:raise AssertionError("invalid template accepted")
    try:e.compare([item()],[],deadline=time.time()-1)
    except TimeoutError:pass
    else:raise AssertionError("deadline ignored")
    img=np.zeros((100,200,3),np.uint8)
    calls=[]
    def ocr(tile):
        calls.append(tile.shape)
        return [{"text":"20V","confidence":.99,"polygon":[[10,10],[60,10],[60,30],[10,30]]}]
    values,metrics=e.observe(img,ocr,time.time()+10,rotations=(0,))
    assert len(calls)==1 and values[0]["text"]=="20V" and metrics["source_size"]==[200,100]
    assert e.annotate(img,e.compare([item()],values)).startswith(b"\x89PNG")
    # A hallucinated VLM transcription cannot create local evidence.
    suggestions={"regions":[{"index":0,"quarter_turns":0,"text":"20V"}]}
    regions=[{"source_pixels":[0,0,200,100]}]
    assert advisory.verify_regions(suggestions,regions,img,lambda _:[],time.time()+10)==[]
    assert advisory.template_suggestions({"elements":[{"type":"text","expected":"x","box":[0,0,float('nan'),1]}]})==[]
    for kind in (zxingcpp.BarcodeFormat.QRCode,zxingcpp.BarcodeFormat.Code128):
        encoded=np.asarray(zxingcpp.write_barcode(kind,"SHEET-123",width=400,height=200))
        codes,decoder=e.decode_codes(cv2.cvtColor(encoded,cv2.COLOR_GRAY2BGR))
        assert decoder=="zxingcpp" and any(v["text"]=="SHEET-123" for v in codes)
    # Hard deadline terminates the native worker without killing a different task.
    context=multiprocessing.get_context("spawn")
    parent,child=context.Pipe()
    process=context.Process(target=time.sleep,args=(10,),daemon=True);process.start()
    runtime._process=process;runtime._connection=parent
    runtime.begin_task("active",time.time()+.1)
    runtime.cancel_task("queued_other")
    assert process.is_alive()
    started=time.time()
    try:runtime.observations(np.zeros((2,2,3),np.uint8))
    except TimeoutError:pass
    else:raise AssertionError("native worker ignored deadline")
    assert time.time()-started<3 and not process.is_alive()
    child.close()
    print("whole-sheet geometry, validation and evidence smoke: PASS")


if __name__=="__main__": main()
