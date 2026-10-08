#!/usr/bin/env python3
"""Isolated single-attempt Doubao bbox calls; never edits platform bindings."""
import argparse
import base64
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image
from local_inspection_service.training.bbox_benchmark import box, digest

ENDPOINT = 'https://ark.cn-beijing.volces.com/api/v3/chat/completions'
PROMPT = '''你是工业配件定位标注员。只标注最后一张实拍原图，前面的图片仅是类别参考图。
框定义：可见目标区域的紧致外接框，不推测被遮挡或超出画面部分。每袋打磨轮或打磨片算一个目标，排除透明包装膜。充电器包含其可见电线和接头。
逐个定位所有可见目标，不根据任务预期数量补框。不要把参考图中的物体作为检测结果。
只输出 JSON 对象 {"objects":[{"class_id":"类别 ID","bbox":[x1,y1,x2,y2]}]}。
bbox 使用最后一张原图的像素坐标，左上包含、右下不包含，禁止使用归一化坐标。
没有目标时返回空 objects。不要输出 mask 或额外文字。'''


def photo(path):
    with Image.open(path) as image:
        if image.format not in ('JPEG', 'PNG'):
            raise ValueError('only original JPEG/PNG input supported')
        if image.getexif().get(274, 1) != 1:
            raise ValueError('EXIF rotation requires explicit original-coordinate mapping')
        width, height = image.size
        mime = 'image/jpeg' if image.format == 'JPEG' else 'image/png'
    return (width, height), 'data:'+mime+';base64,'+base64.b64encode(Path(path).read_bytes()).decode()


def prepare(manifest, coordinate_space='pixels'):
    """Allowlist the B input shape: ground truth and A artifacts are rejected."""
    if set(manifest) != {'owner_user_id', 'classes', 'samples'} or not manifest['owner_user_id']:
        raise ValueError('explicit owner, classes and real-photo samples required')
    if coordinate_space not in ('pixels', 'normalized_1000'):
        raise ValueError('explicit supported coordinate space required')
    prompt = PROMPT if coordinate_space == 'pixels' else PROMPT.replace('bbox 使用最后一张原图的像素坐标，左上包含、右下不包含，禁止使用归一化坐标。', 'bbox 使用明确的 0–1000 归一化 xyxy 坐标：x 按最后一张原图宽度归一化，y 按高度归一化，画面左上为[0,0]、右下为[1000,1000]。不要输出原图像素坐标。')
    classes = manifest['classes']
    if not classes or len(classes) > 30:
        raise ValueError('1..30 accessory classes required')
    content, class_ids = [{'type': 'text', 'text': prompt}], set()
    reference_evidence = []
    for item in classes:
        if set(item) != {'class_id', 'name', 'definition', 'reference_path'} or item['class_id'] in class_ids:
            raise ValueError('unique explicit accessory definitions and reference photos required')
        class_ids.add(item['class_id'])
        size, url = photo(item['reference_path'])
        content.extend([{'type': 'text', 'text': json.dumps({k:item[k] for k in ('class_id','name','definition')}, ensure_ascii=False)},
                        {'type': 'image_url', 'image_url': {'url': url, 'detail': 'high'}}])
        reference_evidence.append({'class_id':item['class_id'], 'sha256':digest(item['reference_path']), 'size':size})
    samples, seen = manifest['samples'], set()
    if not 1 <= len(samples) <= 30:
        raise ValueError('1..30 samples required')
    prepared = []
    for sample in samples:
        if set(sample) != {'image_path','image_sha256','source_kind','owner_user_id'}:
            raise ValueError('B sample cannot contain historical annotations or reference boxes')
        if sample['source_kind'] != 'real_photo' or sample['owner_user_id'] != manifest['owner_user_id']:
            raise ValueError('only requested owner real photos allowed')
        identity = digest(sample['image_path'])
        if identity != sample['image_sha256'] or identity in seen:
            raise ValueError('source hash mismatch or duplicate original')
        seen.add(identity)
        size, url = photo(sample['image_path'])
        parts = content + [{'type':'text', 'text':f'待标注原图：宽 {size[0]} 像素，高 {size[1]} 像素。'},
                           {'type':'image_url', 'image_url':{'url':url, 'detail':'high'}}]
        prepared.append((identity, size, parts))
    return prepared, reference_evidence


def parse_response(value, size, model, coordinate_space='pixels'):
    if value.get('model') != model:
        raise ValueError('provider returned a different model identifier')
    choices = value.get('choices') or []
    if len(choices) != 1 or choices[0].get('finish_reason') != 'stop':
        raise ValueError('incomplete model response')
    output = json.loads(choices[0]['message']['content'])
    if set(output) != {'objects'} or not isinstance(output['objects'], list) or len(output['objects']) > 200:
        raise ValueError('invalid annotation schema')
    for item in output['objects']:
        if set(item) != {'class_id','bbox'} or not isinstance(item['class_id'], str) or not item['class_id']:
            raise ValueError('invalid class/box record')
        if coordinate_space == 'normalized_1000':
            raw_box = box(item['bbox'], 1000, 1000)
            item['bbox'] = [raw_box[i]*size[i % 2]/1000 for i in range(4)]
        elif coordinate_space != 'pixels':
            raise ValueError('unsupported coordinate space')
        box(item['bbox'], *size)
    return output['objects']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--model', required=True, help='Exact fixed model verified in official catalog')
    parser.add_argument('--coordinate-space', choices=('pixels','normalized_1000'), default='pixels')
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'doubao-seed-[0-9]-[0-9]-(pro|lite|turbo)-[0-9]{6}', args.model):
        parser.error('fixed version identifier required; rolling aliases are not allowed')
    key = os.environ.get('ARK_API_KEY')
    if not key:
        parser.error('ARK_API_KEY must be supplied through the existing private credential environment')
    manifest = json.loads(args.manifest.read_text(encoding='utf-8'))
    prepared, references = prepare(manifest, args.coordinate_space)
    args.output_dir.mkdir(mode=0o700, parents=True, exist_ok=False)
    receipt = {'requested_model':args.model,'endpoint':ENDPOINT,'prompt':prepared[0][2][0]['text'],'coordinate_space':args.coordinate_space,'output_coordinate_space':'original_pixels','references':references,
               'manifest_sha256':digest(args.manifest),'parameters':{'temperature':0,'max_tokens':2048,'thinking':{'type':'disabled'},'response_format':{'type':'json_object'}},
               'calls':[],'transport':{'connect_upload_timeout_seconds':60,'read_timeout_seconds':180},'timing_comparable_to_cached_mask':False}
    results = []
    import requests
    for index, (identity, size, content) in enumerate(prepared):
        body = dict(receipt['parameters'], model=args.model, messages=[{'role':'user','content':content}])
        start, call = time.monotonic(), {'image_sha256':identity,'input_size':size,'payload_sha256':hashlib.sha256(json.dumps(body,sort_keys=True).encode()).hexdigest()}
        try:
            # No session retries, fallback, production binding writes or training calls.
            with requests.post(ENDPOINT, headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'}, json=body,
                               timeout=(60,180), allow_redirects=False, stream=True) as response:
                call['http_status'] = response.status_code
                raw = bytearray()
                for chunk in response.iter_content(16384):
                    raw.extend(chunk)
                    if len(raw)>1024*1024 or time.monotonic()-start>180:
                        raise ValueError('response capacity/time exceeded')
                value = json.loads(raw.decode().replace(key,'[REDACTED]'))
                (args.output_dir/f'response-{index+1}.json').write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
                if response.status_code != 200:
                    raise ValueError('requested model call unavailable')
                objects = parse_response(value,size,args.model,args.coordinate_space)
                call.update(returned_model=value['model'],usage=value.get('usage'),status='completed')
                results.append({'image_sha256':identity,'status':'completed','objects':objects})
        except Exception as error:
            # Exception bodies may contain credential-bearing URLs; record type only.
            call.update(status='failed',error_type=type(error).__name__)
        call['elapsed_seconds'] = time.monotonic()-start
        receipt['calls'].append(call)
        (args.output_dir/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
        (args.output_dir/'predictions.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
        if call['status'] != 'completed':
            print('Requested fixed-model call failed; stopped without retry or substitution.',file=sys.stderr)
            return 1
    print(f'Collected {len(results)} isolated bbox results; no training submitted.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
