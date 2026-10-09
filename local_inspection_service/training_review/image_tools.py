"""The existing deterministic crop helper; read-only inputs and mapped crop evidence."""
import json
import math
from pathlib import Path


def crop(source, target, bounds, scale=1):
    from PIL import Image
    if not Path(source).resolve().is_relative_to('/input') or not Path(target).resolve().is_relative_to('/work'):
        raise ValueError('only /input to /work crops are allowed')
    if len(bounds)!=4 or any(type(v) not in (int,float) or not math.isfinite(v) for v in bounds):
        raise ValueError('finite pixel xyxy required')
    if not math.isfinite(scale) or not 0<scale<=8:
        raise ValueError('invalid scale')
    with Image.open(source) as im:
        x1,y1,x2,y2=bounds
        if not 0<=x1<x2<=im.width or not 0<=y1<y2<=im.height:
            raise ValueError('crop exceeds original')
        pixels=[round(v) for v in bounds]
        size=[round((x2-x1)*scale),round((y2-y1)*scale)]
        if min(size)<1 or max(size)>4096 or size[0]*size[1]>16000000:
            raise ValueError('crop output exceeds bounds')
        resampler=getattr(Image,'Resampling',Image).LANCZOS
        im.crop(pixels).resize(size,resampler).save(target,'PNG')
    evidence={'source':source,'crop_pixels':pixels,'output_size':size,'resampler':'LANCZOS','image':target}
    Path(target+'.transform.json').write_text(json.dumps(evidence))
    return evidence
