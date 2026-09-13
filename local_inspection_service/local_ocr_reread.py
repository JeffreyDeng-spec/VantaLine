"""Bounded, independent rereads of first-pass candidates; never template-fed OCR.

Each view is matched on its own. Only afterwards are its coordinates mapped back
for display. Different views can satisfy different elements, not combine letters.
"""
import copy
import difflib
import hashlib
import io
import math
import os

from PIL import Image

from . import evidence_matching as matching
from . import local_evidence_search
from . import standard_preparation as engine

VERSION = 'local-ocr-reread-v1'
LIMIT = 8
PAD = 64


def enabled(owner):
    return owner in {v.strip() for v in os.getenv('VANTALINE_QWEN_REREAD_ACCOUNTS', '').split(',') if v.strip()}


def select(image, request, observations):
    lookup = {o['id']: o for o in observations if o.get('type') == 'text'}
    selected = []
    for element in request.get('elements', []):
        for oid in element.get('evidence_ids', [])[:2]:
            observation = lookup.get(oid)
            if observation and difflib.SequenceMatcher(None, element['expected'], observation['text']).ratio() >= .35 and oid not in selected:
                selected.append(oid)
    regions = []
    for oid in selected[:LIMIT]:
        points = lookup[oid].get('polygon', [])
        if len(points) != 4 or any(len(p) != 2 or any(type(v) not in (int, float) or not math.isfinite(v) for v in p) for p in points):
            continue
        xs, ys = zip(*points)
        if min(xs) < 0 or min(ys) < 0 or max(xs) > image.width or max(ys) > image.height:
            continue
        margin = max(3, (max(ys)-min(ys))*.2)
        box = [max(0, math.floor(min(xs)-margin)), max(0, math.floor(min(ys)-margin)),
               min(image.width, math.ceil(max(xs)+margin)), min(image.height, math.ceil(max(ys)+margin))]
        width, height = box[2]-box[0], box[3]-box[1]
        if min(width, height) <= 0:
            continue
        scale = min(4, max(1, 100/height))
        size = [max(28, round(width*scale)), max(28, round(height*scale))]
        if size[0] > 2400 or (size[0]+2*PAD)*(size[1]+2*PAD) > 4_000_000:
            continue
        picture = image.convert('RGB').crop(box).resize(size, Image.Resampling.LANCZOS)
        padded = Image.new('RGB', (size[0]+2*PAD, size[1]+2*PAD), 'white')
        padded.paste(picture, (PAD, PAD))
        blob = engine.png(padded)
        regions.append(dict(source_evidence_id=oid, source_box=box, source_size=list(image.size),
            content_size=size, input_size=list(padded.size), padding=PAD,
            input_sha256=hashlib.sha256(blob).hexdigest(), blob=blob))
    return regions


def needs_text(region, request, rows):
    pending = {r['element_id'] for r in rows if r['state'] != 'matched' and r.get('type') == 'text'}
    return any(e['element_id'] in pending and region['source_evidence_id'] in e.get('evidence_ids', [])[:2]
               for e in request.get('elements', []))


def text_region(region):
    result = dict(region)
    pad = region['padding']
    width, height = region['content_size']
    with Image.open(io.BytesIO(region['blob'])) as image:
        result['blob'] = engine.png(image.crop((pad, pad, pad+width, pad+height)))
    result.update(padding=0, input_size=[width, height], input_sha256=hashlib.sha256(result['blob']).hexdigest())
    return result


def merge(rows, elements, raw, region, mode, identity):
    """Return rows and mapped evidence; coarse text bounds are never word boxes."""
    local = []
    x0, y0, x1, y1 = region['source_box']
    sw, sh = region['source_size']
    cw, ch = region['content_size']
    pad = region['padding']
    mapped = []
    for index, source in enumerate(raw):
        observation = copy.deepcopy(source)
        if observation.get('type') != 'text':
            continue
        points = observation.get('polygon', [])
        coarse = mode == 'text_recognition'
        if mode == 'advanced_recognition':
            if not points:
                continue
            if any(not (pad <= x <= pad+cw and pad <= y <= pad+ch) for x, y in points):
                # A small provider-box overhang is not precise word localization.
                # Keep only predominantly real-pixel regions, with explicit coarse
                # crop evidence; never clamp a word polygon into false precision.
                left, top = min(p[0] for p in points), min(p[1] for p in points)
                right, bottom = max(p[0] for p in points), max(p[1] for p in points)
                area = (right-left)*(bottom-top)
                overlap = max(0, min(right,pad+cw)-max(left,pad))*max(0, min(bottom,pad+ch)-max(top,pad))
                if area <= 0 or overlap/area < .9:
                    continue
                coarse = True
                polygon = [[x0,y0],[x1,y0],[x1,y1],[x0,y1]]
            else:
                polygon = [[x0+(x-pad)*(x1-x0)/cw, y0+(y-pad)*(y1-y0)/ch] for x,y in points]
        else:
            polygon = [[x0,y0],[x1,y0],[x1,y1],[x0,y1]]
        observation['id'] = f'{identity}_{index}'
        local.append(observation)
        display = copy.deepcopy(observation)
        display.update(polygon=polygon, box=[min(p[0] for p in polygon)/sw, min(p[1] for p in polygon)/sh,
            max(p[0] for p in polygon)/sw, max(p[1] for p in polygon)/sh],
            reread_mode=mode, reread_id=identity,
            coordinate_precision='crop_region_only' if coarse else 'word_polygon')
        mapped.append(display)
    candidates = matching.direct([e for e in elements if e.get('type') == 'text'], local)
    candidates, _ = local_evidence_search.complete(candidates, local)
    winners = {r['element_id']: r for r in candidates if r['state'] == 'matched'}
    result = copy.deepcopy(rows)
    for row in result:
        winner = winners.get(row['element_id'])
        if row['state'] != 'matched' and winner:
            row.update(winner, reread_id=identity, reread_mode=mode)
    return result, mapped
