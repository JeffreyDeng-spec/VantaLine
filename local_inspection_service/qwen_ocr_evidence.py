"""Independent OCR transport and strict, original-pixel evidence normalization.

No standard text is accepted by this module. There are no retries or provider
fallbacks. Callers MUST persist a call claim before invoking ``recognize``.
"""
import base64
import hashlib
import io
import json
import math
import time
from urllib.parse import urlparse

MODEL = "qwen-vl-ocr-2025-11-20"
VERSION = "qwen-ocr-bounded-transport-v2"
PRESENCE_VERSION = "independent-presence-evidence-v1"
# Provider permits 10 MB after Base64. Leave room for JSON/data-URI overhead.
MAX_BASE64_BYTES = 9_000_000
MAX_PIXELS = 12_582_912
MAX_WORDS = 4096
MAX_TEXT = 100_000
MAX_RESPONSE = 4_000_000


class EvidenceError(ValueError):
    def __init__(self, message, diagnostics=None):
        super().__init__(message)
        self.diagnostics = diagnostics or {}


def response_metadata(raw, body):
    """Allowlisted measurements only; provider content can echo private inputs."""
    choices = raw.get('output', {}).get('choices', [])
    finish = choices[0].get('finish_reason') if len(choices) == 1 and isinstance(choices[0], dict) else None
    usage = raw.get('usage', {})
    return dict(response_bytes=len(body), response_sha256=hashlib.sha256(body).hexdigest(),
        finish_reason=finish if finish in ('stop', 'length', 'null', 'content_filter') else 'unknown',
        choice_count=len(choices), usage={key: usage[key] for key in
            ('input_tokens', 'output_tokens', 'total_tokens', 'image_tokens')
            if isinstance(usage, dict) and type(usage.get(key)) is int and usage[key] >= 0})


def endpoint(base_url):
    value = urlparse(base_url)
    host = value.hostname or ""
    # Never forward credentials to a model-supplied URL, redirect or arbitrary host.
    if value.scheme != "https" or value.username or value.password or value.port not in (None, 443):
        raise EvidenceError("unapproved_ocr_endpoint")
    if host != "dashscope.aliyuncs.com" and not (host.startswith("ws-") and host.endswith(".cn-beijing.maas.aliyuncs.com")):
        raise EvidenceError("ocr_requires_verified_beijing_endpoint")
    return f"https://{host}/api/v1/services/aigc/multimodal-generation/generation"


def prepare(image):
    # Orientation was normalized by the shared content decoder. Composite alpha
    # on white, not black; do not silently shrink small text in dense sheets.
    if image.width * image.height > MAX_PIXELS or min(image.size) < 28:
        raise EvidenceError("image_capacity_requires_review")
    from PIL import Image
    picture = image.convert("RGBA")
    white = Image.new("RGBA", picture.size, "white")
    white.alpha_composite(picture)
    stream = io.BytesIO()
    rgb = white.convert("RGB")
    rgb.save(stream, format="PNG")
    blob, encoding, quality = stream.getvalue(), "png", None
    if encoded_size(blob) > MAX_BASE64_BYTES:
        # Transport copy only: keep resolution and avoid chroma subsampling.
        # Original business evidence is never overwritten by this lossy copy.
        for quality in (95, 92, 90, 85):
            stream = io.BytesIO()
            rgb.save(stream, format="JPEG", quality=quality, subsampling=0)
            blob, encoding = stream.getvalue(), "jpeg"
            if encoded_size(blob) <= MAX_BASE64_BYTES:
                break
        else:
            raise EvidenceError("ocr_transport_capacity_requires_review")
    return blob, dict(source_size=list(image.size), input_size=list(image.size),
        encoding=encoding, jpeg_quality=quality, lossy=encoding == "jpeg",
        input_sha256=hashlib.sha256(blob).hexdigest(), input_bytes=len(blob),
        base64_bytes=encoded_size(blob),
        scale_x=1, scale_y=1, coordinate_space="orientation_normalized_original_pixels", version=VERSION)


def encoded_size(blob):
    return 4 * ((len(blob) + 2) // 3)


def payload(blob, *, auto_rotate=False):
    if type(auto_rotate) is not bool:
        raise EvidenceError("ocr_invalid_rotation_option")
    if encoded_size(blob) > MAX_BASE64_BYTES:
        raise EvidenceError("ocr_transport_capacity_requires_review")
    mime = "image/jpeg" if blob.startswith(b"\xff\xd8\xff") else "image/png"
    return {"model": MODEL, "input": {"messages": [{"role": "user", "content": [{
        "image": "data:" + mime + ";base64," + base64.b64encode(blob).decode(),
        "min_pixels": 3072, "max_pixels": MAX_PIXELS, "enable_rotate": auto_rotate,
    }]}]}, "parameters": {"ocr_options": {"task": "advanced_recognition"}, "max_tokens": 8192}}


def normalize(response, size):
    choices = response.get("output", {}).get("choices", [])
    if len(choices) != 1 or choices[0].get("finish_reason") != "stop":
        raise EvidenceError("ocr_incomplete_or_truncated")
    content = choices[0].get("message", {}).get("content", [])
    results = [c["ocr_result"] for c in content if isinstance(c, dict) and "ocr_result" in c]
    if len(results) != 1 or not isinstance(results[0], dict):
        raise EvidenceError("ocr_position_schema_missing")
    words = results[0].get("words_info")
    if not isinstance(words, list) or not 1 <= len(words) <= MAX_WORDS:
        raise EvidenceError("ocr_empty_or_over_capacity")
    width, height = size
    observations = []
    characters = 0
    for order, word in enumerate(words):
        text, location = word.get("text"), word.get("location")
        if not isinstance(text, str) or not text.strip() or len(text) > 8192:
            raise EvidenceError("ocr_invalid_text")
        if not isinstance(location, list) or len(location) != 8 or any(type(v) not in (int, float) or not math.isfinite(v) for v in location):
            raise EvidenceError("ocr_invalid_coordinates")
        points = list(zip(location[::2], location[1::2]))
        if any(not (0 <= x <= width and 0 <= y <= height) for x, y in points):
            raise EvidenceError("ocr_coordinates_outside_original")
        area = abs(sum(points[i][0]*points[(i+1)%4][1] - points[(i+1)%4][0]*points[i][1] for i in range(4))) / 2
        turns = [(points[(i+1)%4][0]-points[i][0])*(points[(i+2)%4][1]-points[(i+1)%4][1]) -
                 (points[(i+1)%4][1]-points[i][1])*(points[(i+2)%4][0]-points[(i+1)%4][0]) for i in range(4)]
        if area <= 0 or not (all(t >= 0 for t in turns) or all(t <= 0 for t in turns)):
            raise EvidenceError("ocr_degenerate_polygon")
        score = word.get("confidence")
        if score is not None and (type(score) not in (int, float) or not math.isfinite(score) or not 0 <= score <= 1):
            raise EvidenceError("ocr_unknown_confidence_scale")
        characters += len(text)
        if characters > MAX_TEXT:
            raise EvidenceError("ocr_text_capacity")
        digest = hashlib.sha256(json.dumps([order, text, location], ensure_ascii=False).encode()).hexdigest()[:20]
        observations.append(dict(id="o_"+digest, text=text, type="text", polygon=points,
            box=[min(location[::2])/width, min(location[1::2])/height, max(location[::2])/width, max(location[1::2])/height],
            order=order, confidence=score, provenance="qwen_ocr"))
    return observations


def validated_subset(response, size, *, allow_empty=False):
    """Independent rows from a complete envelope; never clamp or invent evidence."""
    if type(allow_empty) is not bool:
        raise EvidenceError('ocr_invalid_presence_option')
    choices=response.get('output',{}).get('choices',[])
    if len(choices)!=1 or choices[0].get('finish_reason')!='stop':
        raise EvidenceError('ocr_incomplete_or_truncated')
    results=[c['ocr_result'] for c in choices[0].get('message',{}).get('content',[])
             if isinstance(c,dict) and 'ocr_result' in c]
    if len(results)!=1 or not isinstance(results[0],dict):raise EvidenceError('ocr_position_schema_missing')
    words=results[0].get('words_info')
    if not isinstance(words,list) or len(words)>MAX_WORDS:raise EvidenceError('ocr_empty_or_over_capacity')
    if not words:
        if allow_empty:return [],[]
        raise EvidenceError('ocr_empty_or_over_capacity')
    valid,rejected,total=[],[],0
    for index,word in enumerate(words):
        single={'output':{'choices':[{'finish_reason':'stop','message':{'content':[{'ocr_result':{'words_info':[word]}}]}}]}}
        try:
            row=normalize(single,size)[0]
        except (EvidenceError,TypeError,AttributeError,KeyError) as error:
            rejected.append(dict(index=index,reason=str(error) if isinstance(error,EvidenceError) else 'ocr_invalid_word_schema'))
            continue
        total+=len(row['text'])
        if total>MAX_TEXT:raise EvidenceError('ocr_text_capacity')
        row['order']=index
        row['id']='o_'+hashlib.sha256(json.dumps([index,word['text'],word['location']],ensure_ascii=False).encode()).hexdigest()[:20]
        valid.append(row)
    if not valid:raise EvidenceError('ocr_no_valid_word_evidence')
    return valid,rejected


from .model_profiles.audit import metered_function

@metered_function(0)
def recognize(settings, blob, size, timeout, post=None, *, allow_rejected_words=False, auto_rotate=False, presence_evidence=False, region_text=False, audit=None, record_usage=None):
    import requests
    if type(presence_evidence) is not bool:
        raise EvidenceError('ocr_invalid_presence_option')
    if settings.get("provider") != "qwen" or not settings.get("api_key"):
        raise EvidenceError("qwen_credentials_unavailable")
    if type(region_text) is not bool:
        raise EvidenceError('ocr_invalid_region_option')
    post = post or requests.post
    request = payload(blob, auto_rotate=auto_rotate)
    if region_text:
        request['parameters']['ocr_options']['task'] = 'text_recognition'
    if audit:
        import copy
        audit('input_image', blob)
        logged = copy.deepcopy(request)
        logged['input']['messages'][0]['content'][0]['image'] = dict(sha256=hashlib.sha256(blob).hexdigest(), bytes=len(blob))
        audit('request', dict(payload=logged, preprocess_version=VERSION, source_size=list(size)))
    # Explicit no redirects; requests' default adapter does not retry POST.
    network_started = time.monotonic()
    try:
        response = post(endpoint(settings["base_url"]), headers={"Authorization": "Bearer "+settings["api_key"]},
                        json=request, timeout=max(.1, timeout), allow_redirects=False, stream=True)
    except Exception as error:
        if audit: audit('transport_error', dict(error_type=type(error).__name__,elapsed_ms=round((time.monotonic()-network_started)*1000)))
        raise
    headers_ms = round((time.monotonic()-network_started)*1000)
    try:
        chunks, total = [], 0
        for chunk in response.iter_content(65536):
            total += len(chunk)
            if total > MAX_RESPONSE:
                if audit:
                    audit('response', dict(http_status=response.status_code, truncated=True,
                        body=(b''.join(chunks)+chunk)[:MAX_RESPONSE].decode('utf-8', errors='replace')))
                raise EvidenceError("ocr_response_capacity")
            chunks.append(chunk)
        body = b"".join(chunks)
        if audit:
            audit('response', dict(http_status=response.status_code, truncated=False,
                body=body.decode('utf-8', errors='replace'), response_sha256=hashlib.sha256(body).hexdigest(),
                headers_ms=headers_ms, network_ms=round((time.monotonic()-network_started)*1000)))
        if response.status_code != 200:
            raise EvidenceError("ocr_http_"+str(response.status_code))
        try:
            raw = json.loads(body)
        except (ValueError, UnicodeError):
            raise EvidenceError('ocr_invalid_json', dict(response_bytes=len(body),
                response_sha256=hashlib.sha256(body).hexdigest())) from None
        if not isinstance(raw, dict) or not isinstance(raw.get('output'), dict) or not isinstance(raw['output'].get('choices'), list):
            raise EvidenceError('ocr_invalid_response_envelope')
        metadata = response_metadata(raw, body)
        metadata.update(auto_rotate=auto_rotate, coordinate_space="original_input_pixels")
        try:
            if region_text:
                choices = raw['output']['choices']
                if len(choices) != 1 or choices[0].get('finish_reason') != 'stop':
                    raise EvidenceError('ocr_incomplete_or_truncated')
                content = choices[0].get('message', {}).get('content', [])
                if len(content) != 1 or not isinstance(content[0].get('text'), str) or len(content[0]['text']) > 8192:
                    raise EvidenceError('ocr_invalid_region_text')
                text = content[0]['text']
                width, height = size
                observations = [] if not text.strip() else [dict(
                    id='region_' + hashlib.sha256(blob + text.encode()).hexdigest()[:20],
                    text=text, type='text', polygon=[[0,0],[width,0],[width,height],[0,height]],
                    box=[0,0,1,1], order=0, confidence=None,
                    provenance='region_transcription_bounds_not_word_boxes')]
                metadata.update(scan_complete=True, coordinate_precision='input_crop_region_only_not_word_localization')
            elif presence_evidence or allow_rejected_words:
                observations,rejected=validated_subset(raw,size,allow_empty=presence_evidence)
                metadata.update(rejected_words=rejected,all_word_rows_valid=not rejected,
                                scan_complete=not rejected,empty_scan=not observations,
                                validation_policy=PRESENCE_VERSION if presence_evidence else 'independent_tile_rows_v1')
            else:
                observations = normalize(raw, size)
        except EvidenceError as error:
            error.diagnostics = metadata
            raise
        except (KeyError, TypeError, AttributeError, ValueError):
            raise EvidenceError('ocr_invalid_response_schema', metadata) from None
        # Do not retain arbitrary provider fields (could echo credentials/input).
        return observations, dict(model=MODEL, preprocess_version=VERSION,
            **metadata, words_info=observations)
    except Exception as error:
        if audit:
            audit('failure', dict(error_type=type(error).__name__,
                parse_error=getattr(error,'diagnostics',{}), elapsed_ms=round((time.monotonic()-network_started)*1000),
                received_prefix=b''.join(chunks).decode('utf-8',errors='replace') if 'chunks' in locals() else ''))
        raise
    finally:
        response.close()
