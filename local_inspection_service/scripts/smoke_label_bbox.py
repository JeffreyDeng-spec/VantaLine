"""Offline port/geometry contract, no paid requests."""
import io
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import numpy as np
from PIL import Image
from local_inspection_service import label_bbox as b, label_extraction as g


def body(rect=None, **kwargs):
    result = {"isMultiLabel":True,"labelCount":6,"cropRect":rect or {"x":.2,"y":.2,"w":.3,"h":.4},**kwargs}
    return json.dumps({"choices":[{"message":{"content":json.dumps(result)}}]})


def main():
    for w,h in [(4096,3072),(3072,4096),(1080,1919),(201,333)]:
        data = np.random.default_rng(7).integers(0,256,(h,w,3),dtype=np.uint8)
        output=io.BytesIO();Image.fromarray(data).save(output,"PNG")
        original=output.getvalue()
        model,meta=b.prepare(original)
        assert max(Image.open(io.BytesIO(model)).size)<=1600
        _,rect=b.parse(body())
        crop,points,quality=b.crop_rectangle(original,rect)
        x,y,cw,ch=quality["bbox"]
        assert np.array_equal(np.asarray(Image.open(io.BytesIO(crop))),data[y:y+ch,x:x+cw])
        if min(cw,ch)>=100:
            revision,_=b.crop_revision(original,points)
            assert revision==crop or np.array_equal(np.asarray(Image.open(io.BytesIO(revision))),np.asarray(Image.open(io.BytesIO(crop))))
        for p,(px,py) in zip(points,[(x,y),(x+cw-1,y),(x+cw-1,y+ch-1),(x,y+ch-1)]):
            assert abs(p[0]*(w-1)-px)<1e-6 and abs(p[1]*(h-1)-py)<1e-6
    raw=io.BytesIO(); im=Image.new("RGB",(200,300));exif=Image.Exif();exif[274]=6;im.save(raw,"JPEG",exif=exif)
    assert Image.open(io.BytesIO(g.normalized_image(raw.getvalue()))).size==(300,200)
    for bad in ["oops","{}",body(isMultiLabel=False),body(labelCount=0),body(labelCount=True),body({"x":-.1,"y":0,"w":.2,"h":.2}),body({"x":.9,"y":0,"w":.2,"h":.2}),body({"x":True,"y":0,"w":.2,"h":.2}),body({"x":0,"y":0,"w":float('nan'),"h":.2})]:
        try:b.parse(bad)
        except ValueError:pass
        else:raise AssertionError(bad)
    assert b.payload(b"fixture","model")["max_tokens"]==512
    assert b.payload(b"fixture","model")["temperature"]==.1
    secret_body=json.dumps({"choices":[{"message":{"content":'```json\n{"api_key":"never-show", "image_url":"data:image/png;base64,YWJj"}\n```'}}]})
    safe=json.dumps(b.evidence(secret_body))
    assert 'never-show' not in safe and 'YWJj' not in safe
    print("label bbox geometry and parser: PASS")


if __name__ == "__main__": main()
