"""Explicit, single-call synthetic OCR probe; never creates a business record.

Run under the service account with its environment and --allow-paid-call.
An exclusive output directory is a durable pre-call claim, not a retry token.
"""
import argparse
import base64
import io
import hashlib
import json
import os
from pathlib import Path
import sys
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--owner', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--image')
    parser.add_argument('--record', help='Existing owned comparison source, read-only')
    parser.add_argument('--allow-paid-call', action='store_true')
    args = parser.parse_args()
    if not args.allow_paid_call:
        parser.error('Explicit paid-call permission required')
    sys.path.insert(0, os.getcwd())
    from local_inspection_service import server
    from PIL import Image, ImageDraw, ImageFont
    from urllib.parse import urlparse
    import requests
    settings = server.document_import_jobs.settings(args.owner)
    folder = Path(args.output)
    folder.mkdir(mode=0o700, parents=False, exist_ok=False)
    image = Image.new('RGB', (640, 240), 'white')
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 30)
    draw.text((30, 40), 'MODEL: TEST-001', fill='black', font=font)
    draw.text((30, 100), '20V 2000mAh', fill='black', font=font)
    if args.image:
        from PIL import ImageOps
        image = ImageOps.exif_transpose(Image.open(args.image)).convert('RGB')
    if args.record:
        from local_inspection_service.standard_preparation import decode
        record = server._text_v2_owned('records', args.record, args.owner)
        if not record:
            raise ValueError('owned_record_missing')
        image = decode(server._text_v2_read_verified(record['source_path'], args.owner, record['standard_id'], expected_sha256=record['source_sha256'])).convert('RGB')
    actual = bool(args.image or args.record)
    image.save(folder / 'input.png')
    buffer = io.BytesIO(); image.save(buffer, format='PNG')
    model = 'qwen-vl-ocr-2025-11-20'
    payload = {'model': model, 'input': {'messages': [{'role': 'user', 'content': [{
        'image': 'data:image/png;base64,' + base64.b64encode(buffer.getvalue()).decode(),
        'min_pixels': 3072, 'max_pixels': 12582912, 'enable_rotate': False}]}]},
        'parameters': {'ocr_options': {'task': 'advanced_recognition'}, 'max_tokens': 8192 if actual else 512}}
    (folder / 'claim.json').write_text(json.dumps({'model': model, 'state': 'attempting', 'started_at': time.time(),
        'source_sha256': hashlib.sha256(buffer.getvalue()).hexdigest(), 'size': image.size,
        'parameters': payload['parameters'], 'min_pixels': 3072, 'max_pixels': 12582912}))
    started = time.monotonic()
    try:
        host = urlparse(settings['base_url']).hostname
        if not host or not (host == 'dashscope.aliyuncs.com' or (host.startswith('ws-') and host.endswith('.cn-beijing.maas.aliyuncs.com'))):
            raise ValueError('unapproved_endpoint')
        response = requests.post('https://' + host + '/api/v1/services/aigc/multimodal-generation/generation',
            headers={'Authorization': 'Bearer ' + settings['api_key']}, json=payload,
            timeout=110 if actual else 45, allow_redirects=False)
        result = {'status': response.status_code, 'elapsed_ms': round((time.monotonic()-started)*1000), 'response': response.json()}
        # This probe sends only synthetic text; remove any unexpected key echo.
        encoded = json.dumps(result, ensure_ascii=False).replace(settings['api_key'], '[REDACTED]')
        (folder / 'result.json').write_text(encoded)
        if actual:
            choices = result['response'].get('output', {}).get('choices', [])
            content = choices[0].get('message', {}).get('content', []) if choices else []
            words = next((c.get('ocr_result', {}).get('words_info', []) for c in content if 'ocr_result' in c), [])
            annotated = image.copy(); marks = ImageDraw.Draw(annotated)
            for item in words:
                loc = item.get('location', [])
                if len(loc) == 8:
                    marks.line([tuple(loc[i:i+2]) for i in range(0,8,2)] + [tuple(loc[:2])], fill='red', width=2)
            annotated.save(folder / 'ocr-boxes.png')
            print(json.dumps({'status':result['status'],'elapsed_ms':result['elapsed_ms'],
                'finish_reason':choices[0].get('finish_reason') if choices else None, 'words':len(words),
                'usage':result['response'].get('usage'), 'code':result['response'].get('code'),
                'message':result['response'].get('message'), 'output':str(folder)}))
        else:
            print(encoded)
    except Exception as error:
        result = {'state': 'unknown', 'error_type': type(error).__name__}
        (folder / 'unknown.json').write_text(json.dumps(result))
        print(json.dumps(result))
        raise SystemExit(1)


if __name__ == '__main__':
    main()
