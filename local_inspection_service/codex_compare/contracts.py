"""Bounded, versioned report wire contract shared by API, CLI and runner."""
from __future__ import annotations
import hashlib
import io
import json
import math
from PIL import Image, ImageOps

TERMINAL = {'completed', 'failed', 'timed_out', 'cancelled', 'interrupted'}
DECISIONS = {'MATCH', 'DIFFERENCES', 'REVIEW_REQUIRED'}
MAX_BYTES = 10 * 1024 * 1024
MAX_PIXELS = 16_000_000
PROMPT_VERSION = 'codex-text-v1'


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(value if isinstance(value, bytes) else encode(value).encode()).hexdigest()


def text(value, limit=4000):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f'Expected nonempty text, maximum {limit} characters')
    return value


def box(value):
    if value is None:
        return None
    if not isinstance(value, list) or len(value) != 4 or any(type(x) not in (float, int) or not math.isfinite(x) for x in value):
        raise ValueError('Box must be normalized [x,y,width,height]')
    x, y, w, h = value
    if min(x, y) < 0 or min(w, h) <= 0 or x + w > 1 or y + h > 1:
        raise ValueError('Box lies outside the original image')
    return value


def item(value):
    allowed = {'id', 'status', 'reference_text', 'actual_text', 'explanation', 'reference_box', 'actual_box', 'artifact_ids'}
    if set(value) - allowed:
        raise ValueError('Unknown item field')
    result = {'id': text(value.get('id'), 80), 'status': value.get('status'),
              'explanation': text(value.get('explanation'))}
    if result['status'] not in {'match', 'difference', 'uncertain'}:
        raise ValueError('Invalid item status')
    for key in ('reference_text', 'actual_text'):
        entry = value.get(key, '')
        if not isinstance(entry, str) or len(entry) > 4000:
            raise ValueError('Invalid transcription')
        result[key] = entry
    for key in ('reference_box', 'actual_box'):
        result[key] = box(value.get(key))
    ids = value.get('artifact_ids', [])
    if not isinstance(ids, list) or len(ids) > 8:
        raise ValueError('At most eight evidence images per item')
    result['artifact_ids'] = [text(x, 80) for x in ids]
    return result


def summary(value):
    if set(value) != {'decision', 'message', 'checked_scope', 'unchecked_scope'}:
        raise ValueError('Summary needs decision, message, checked_scope, unchecked_scope')
    if value['decision'] not in DECISIONS:
        raise ValueError('Invalid decision')
    result = {k: text(value[k]) for k in ('message', 'checked_scope')}
    if not isinstance(value['unchecked_scope'], str) or len(value['unchecked_scope']) > 4000:
        raise ValueError('Invalid unchecked_scope')
    return {**result, 'decision': value['decision'], 'unchecked_scope': value['unchecked_scope']}


def validate_report(task):
    if task.get('report_version') == 'label-v2':
        from .label_contracts import validate
        return validate(task)
    report = task.get('summary')
    items = list(task.get('items', {}).values())
    if not report or not items:
        raise ValueError('A summary and at least one checked item are required')
    states = {entry['status'] for entry in items}
    if report['decision'] == 'MATCH' and (states != {'match'} or report['unchecked_scope'].strip()):
        raise ValueError('MATCH requires complete scope and all items matched')
    if report['decision'] == 'DIFFERENCES' and 'difference' not in states:
        raise ValueError('DIFFERENCES requires an evidence item')
    if report['decision'] == 'MATCH' and any(not x['reference_box'] or not x['actual_box'] for x in items):
        raise ValueError('MATCH requires located evidence on both images')


def normalize_image(data):
    if not data or len(data) > MAX_BYTES:
        raise ValueError('图片必须小于 10MB')
    with Image.open(io.BytesIO(data)) as source:
        if source.width * source.height > MAX_PIXELS or min(source.size) < 32:
            raise ValueError('图片尺寸不受支持（上限 1600 万像素）')
        source.load()
        oriented = ImageOps.exif_transpose(source).convert('RGBA')
        rgb = Image.new('RGB', oriented.size, 'white')
        rgb.paste(oriented, mask=oriented.getchannel('A'))
        output = io.BytesIO()
        rgb.save(output, 'PNG')
        preview = rgb.copy()
        preview.thumbnail((1600, 1600))
        thumb = io.BytesIO()
        preview.save(thumb, 'JPEG', quality=85)
        return output.getvalue(), thumb.getvalue(), list(rgb.size)
