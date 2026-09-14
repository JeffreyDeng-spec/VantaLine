"""Local deterministic crop/coordinate helpers, no network or input mutation."""
import json
import math
from pathlib import Path


def bounds(raw):
    v = json.loads(raw)
    if (not isinstance(v, list) or len(v) != 4 or
        any(type(n) not in (int, float) or not math.isfinite(n) for n in v) or
        min(v[:2]) < 0 or min(v[2:]) <= 0 or v[0]+v[2] > 1 or v[1]+v[3] > 1):
        raise ValueError('Expected original-normalized XYWH within image')
    return v


def local_image(args):
    b = bounds(args.box)
    if args.action == 'map':
        c = bounds(args.crop)
        return {'box': [c[0]+b[0]*c[2], c[1]+b[1]*c[3], b[2]*c[2], b[3]*c[3]]}
    from PIL import Image
    target = Path(args.file).resolve()
    if not target.is_relative_to(Path('/work')):
        raise ValueError('Output must be inside /work')
    if not math.isfinite(args.scale) or not 0 < args.scale <= 8:
        raise ValueError('Scale must be in (0,8]')
    with Image.open('/input/'+args.source+'.png') as image:
        x,y,w,h = b
        pixels = [round(x*image.width), round(y*image.height), round((x+w)*image.width), round((y+h)*image.height)]
        size = [round((pixels[2]-pixels[0])*args.scale), round((pixels[3]-pixels[1])*args.scale)]
        if min(size) < 32 or max(size) > 4096 or size[0]*size[1] > 16_000_000:
            raise ValueError('Crop output size out of bounds')
        image.crop(pixels).resize(size, Image.Resampling.LANCZOS).save(target, 'PNG')
    return {'file': str(target), 'source': args.source, 'box': b,
            'transform': {'crop_pixels': pixels, 'output_size': size, 'resampler': 'LANCZOS'}}
