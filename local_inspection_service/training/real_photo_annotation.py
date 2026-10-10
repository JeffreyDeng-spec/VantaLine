"""Blind, single-attempt VLM localization with auditable first-frame geometry."""
import base64
import io
import json
from PIL import Image
from .real_photo_contracts import MODEL, VERSION, digest, objects
from ..model_profiles.transport import invoke

PROMPT = '''你是工业配件定位标注员。前面的图片是类别参考，只标注最后一张实拍原图。
标注所有任务类别的所有可见实例，不根据预期数量补框。
框为可见区域的紧致外接框，不推测遮挡部分；排除透明包装膜。
每袋打磨轮或打磨片算一个目标；充电器包含可见电线与接头。
只输出JSON对象 {"objects":[{"class_id":"类别ID","bbox":[x1,y1,x2,y2]}]}。
bbox必须是明确0–1000归一化xyxy：按最后原图宽高归一化，右下为[1000,1000]。
无目标返回空objects。不要输出mask、解释或参考图的检测结果。'''


def canonical(data, *, max_edge=None):
    if len(data) > 32*1024*1024:
        raise ValueError('image exceeds byte bound')
    with Image.open(io.BytesIO(data)) as im:
        width, height = im.size
        if not 0 < width*height <= 40_000_000:
            raise ValueError('image exceeds pixel bound')
        orientation = im.getexif().get(274, 1)
        im.seek(0)
        pixels = im.convert('RGB')
        if max_edge is not None and max(pixels.size) > max_edge:
            pixels.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
        input_width, input_height = pixels.size
        output = io.BytesIO()
        # Lossless decoded first frame, no implicit EXIF rotation, no gain-map frame.
        pixels.save(output, 'PNG')
        clean = output.getvalue()
        return clean, {'source_sha256': digest(data), 'input_sha256': digest(clean),
                       'pixel_sha256': digest(pixels.tobytes()), 'width': width, 'height': height,
                       'source_orientation': orientation, 'frame': 0,
                       'input_width': input_width, 'input_height': input_height,
                       'coordinate_transform': [input_width / width, 0, 0, 0, input_height / height, 0], 'encoding': 'png'}


def image_content(data, *, max_edge):
    clean, meta = canonical(data, max_edge=max_edge)
    # Provider-only copy: use the same JPEG90 transport as label comparison.
    # canonical() remains lossless for review and dataset export.
    output = io.BytesIO()
    with Image.open(io.BytesIO(clean)) as pixels:
        pixels.save(output, 'JPEG', quality=90)
    encoded = output.getvalue()
    with Image.open(io.BytesIO(encoded)) as decoded:
        meta.update(canonical_pixel_sha256=meta['pixel_sha256'],
                    pixel_sha256=digest(decoded.convert('RGB').tobytes()),
                    input_sha256=digest(encoded), encoding='jpeg', jpeg_quality=90)
    return {'type': 'image_url', 'image_url': {'url': 'data:image/jpeg;base64,' + base64.b64encode(encoded).decode(), 'detail': 'high'}}, meta


def annotate(image, classes, settings, read_reference, transport=invoke):
    if settings.get('provider') != 'doubao' or settings.get('model') != MODEL or not settings.get('configured'):
        raise ValueError('fixed bbox model must be explicitly configured')
    content = []; references = []; input_bytes=0
    for c in classes:
        part, meta = image_content(read_reference(c), max_edge=1024)
        if meta['source_sha256'] != c['reference_sha256']:
            raise ValueError('reference changed after task snapshot')
        input_bytes+=len(part['image_url']['url'])+len(c['definition'].encode())
        if input_bytes>48*1024*1024:raise ValueError('references exceed aggregate byte bound')
        content += [{'type': 'text', 'text': json.dumps({'class_id': c['class_id'], 'name': c['name'], 'definition': c['definition']}, ensure_ascii=False)}, part]
        references.append({'class_id': c['class_id'], **meta})
    part, meta = image_content(image, max_edge=2048)
    content += [{'type': 'text', 'text': PROMPT}, part]
    payload = {'messages': [{'role': 'user', 'content': content}], 'temperature': 0,
               'max_tokens': 4096, 'thinking': {'type': 'disabled'}}
    if len(json.dumps(payload).encode()) > 48*1024*1024:
        raise ValueError('model input exceeds aggregate byte bound')
    receipt = {'model': MODEL, 'prompt_version': VERSION, 'prompt_sha256': digest(PROMPT),
               'input': meta, 'references': references, 'usage': {},
               'input_policy_version': 'bounded-first-frame-jpeg-v2'}
    stage = 'transport'
    try:
        status, raw = transport(payload, settings)
        stage = 'response_validation'
        receipt['response_sha256'] = digest(raw.encode())
        receipt['response'] = raw[:1024*1024]
        receipt['http_status'] = status
        value = json.loads(raw)
        receipt.update(http_status=status, usage=value.get('usage', {}))
        if status != 200 or value.get('model') != MODEL:
            raise ValueError('provider status or returned model mismatch')
        choices = value.get('choices')
        if not isinstance(choices, list) or len(choices) != 1 or choices[0].get('finish_reason') != 'stop':
            raise ValueError('incomplete provider response')
        parsed = json.loads(choices[0]['message']['content'])
        if not isinstance(parsed, dict) or set(parsed) != {'objects'}:
            raise ValueError('invalid localization response')
        result = objects(parsed['objects'], {c['class_id'] for c in classes}, meta['width'], meta['height'], normalized=True)
        return {'status': 'completed', 'objects': result, 'receipt': receipt}
    except Exception as exc:
        # Store a classification, not exception text that may contain credentials/media.
        receipt['failure_stage'] = stage
        known = {'ConnectionError', 'ProxyError', 'SSLError', 'ConnectTimeout',
                 'ReadTimeout', 'Timeout', 'ProtocolError', 'RemoteDisconnected',
                 'MaxRetryError', 'NewConnectionError', 'ConnectionResetError',
                 'BrokenPipeError', 'JSONDecodeError', 'ValueError'}
        pending = [exc]; seen = set(); types = []
        while pending and len(seen) < 16:
            error = pending.pop()
            if id(error) in seen:continue
            seen.add(id(error))
            name = type(error).__name__
            if name in known and name not in types:types.append(name)
            pending.extend(v for v in (error.__cause__, error.__context__,
                                       getattr(error, 'reason', None), *error.args)
                           if isinstance(v, BaseException))
        receipt['failure_types'] = types
        return {'status': 'failed', 'objects': [], 'error_type': type(exc).__name__,
                'error_code': stage + '_failed', 'receipt': receipt}
