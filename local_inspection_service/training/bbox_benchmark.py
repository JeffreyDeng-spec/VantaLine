"""Offline, human-confirmed real-photo benchmark; never submits training jobs."""
import hashlib
import json
import math
import re
from pathlib import Path

import numpy as np
from PIL import Image


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def box(value, width, height):
    if not isinstance(value, list) or len(value) != 4:
        raise ValueError('bbox must contain four pixel coordinates')
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in value):
        raise ValueError('bbox coordinates must be finite numbers')
    x1, y1, x2, y2 = value
    if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
        raise ValueError('bbox outside original image or degenerate')
    return value


def mask_box(path, width, height, *, crop=None):
    """Same >8 alpha rule as alpha_bbox; RGB highlight sheets are not binary masks.

    Full-image masks must match original dimensions. Cropped masks require an
    explicit original-pixel crop rectangle; no guessed offsets or rescaling.
    """
    with Image.open(path) as image:
        if image.mode == 'RGBA':
            mask = np.asarray(image.getchannel('A'))
        elif image.mode == 'L':
            mask = np.asarray(image)
        else:
            raise ValueError('requires decoded grayscale mask or RGBA alpha')
    x0, y0 = 0, 0
    expected = (width, height)
    if crop is not None:
        x0, y0, x2, y2 = box(crop, width, height)
        if any(int(v) != v for v in crop):
            raise ValueError('crop coordinates must be integer pixels')
        expected = (int(x2-x0), int(y2-y0))
    if (mask.shape[1], mask.shape[0]) != expected:
        raise ValueError('mask geometry does not match original/crop metadata')
    ys, xs = np.where(mask > 8)
    if not len(xs):
        raise ValueError('empty mask is unavailable, not a negative example')
    return [int(xs.min()+x0), int(ys.min()+y0), int(xs.max()+x0+1), int(ys.max()+y0+1)]


def select_samples(records, owner_id, limit=30):
    if not owner_id or not 1 <= limit <= 30:
        raise ValueError('explicit owner and limit 1..30 required')
    selected, seen = [], set()
    for record in sorted(records, key=lambda r: r.get('created_at', 0), reverse=True):
        if record.get('owner_user_id') != owner_id or record.get('source_kind') != 'real_photo':
            continue
        path = record['image_path']
        identity = digest(path)
        with Image.open(path) as image:
            width, height = image.size
        if identity in seen:
            continue
        seen.add(identity)
        selected.append({**record, 'image_sha256': identity, 'width': width, 'height': height})
        if len(selected) == limit:
            break
    return selected


def iou(a, b):
    intersection = max(0, min(a[2], b[2])-max(a[0], b[0])) * max(0, min(a[3], b[3])-max(a[1], b[1]))
    union = (a[2]-a[0])*(a[3]-a[1]) + (b[2]-b[0])*(b[3]-b[1]) - intersection
    return intersection/union if union else 0.0


def assignment(weights):
    """Maximum-weight one-to-one assignment, padded Hungarian algorithm."""
    if not weights or not weights[0]:
        return []
    rows, cols = len(weights), len(weights[0])
    n = max(rows, cols)
    costs = [[-weights[i][j] if i < rows and j < cols else 0 for j in range(n)] for i in range(n)]
    u, v, p, way = [0.]*(n+1), [0.]*(n+1), [0]*(n+1), [0]*(n+1)
    for i in range(1, n+1):
        p[0], j0 = i, 0
        distance, used = [float('inf')]*(n+1), [False]*(n+1)
        while True:
            used[j0], i0 = True, p[j0]
            delta, j1 = float('inf'), 0
            for j in range(1, n+1):
                if not used[j]:
                    cost = costs[i0-1][j-1]-u[i0]-v[j]
                    if cost < distance[j]:
                        distance[j], way[j] = cost, j0
                    if distance[j] < delta:
                        delta, j1 = distance[j], j
            for j in range(n+1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    distance[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while j0:
            p[j0] = p[way[j0]]
            j0 = way[j0]
    return [(p[j]-1, j-1) for j in range(1, n+1) if 0 < p[j] <= rows and j <= cols and weights[p[j]-1][j-1] > 0]


def measure(truth, predictions, width, height):
    if len(truth) > 200 or len(predictions) > 200:
        raise ValueError('too many boxes for bounded offline comparison')
    for item in truth + predictions:
        if not isinstance(item.get('class_id'), str) or not item['class_id']:
            raise ValueError('explicit class_id required')
        box(item['bbox'], width, height)
    def match(targets, outputs, same_class):
        weights = []
        for target in targets:
            row = []
            for output in outputs:
                overlap = iou(target['bbox'], output['bbox'])
                compatible = (target['class_id'] == output['class_id']) == same_class
                row.append(1000+overlap if compatible and overlap >= .5 else 0)
            weights.append(row)
        return assignment(weights)
    pairs = match(truth, predictions, True)
    used_t, used_p = {i for i, _ in pairs}, {j for _, j in pairs}
    remaining_t = [t for i, t in enumerate(truth) if i not in used_t]
    remaining_p = [p for j, p in enumerate(predictions) if j not in used_p]
    wrong = match(remaining_t, remaining_p, False)
    overlaps = [iou(truth[i]['bbox'], predictions[j]['bbox']) for i, j in pairs]
    per_class = {}
    for class_id in sorted({t['class_id'] for t in truth + predictions}):
        class_pairs = [(i, j) for i, j in pairs if truth[i]['class_id'] == class_id]
        class_wrong = sum(remaining_t[i]['class_id'] == class_id for i, _ in wrong)
        class_extra = sum(p['class_id'] == class_id for p in remaining_p) - sum(remaining_p[j]['class_id'] == class_id for _, j in wrong)
        target_count = sum(t['class_id'] == class_id for t in truth)
        per_class[class_id] = {'targets': target_count, 'matched': len(class_pairs),
            'wrong_class': class_wrong, 'missed': target_count-len(class_pairs)-class_wrong,
            'extra': class_extra, 'iou_ge_075': sum(iou(truth[i]['bbox'], predictions[j]['bbox']) >= .75 for i, j in class_pairs)}
    return {'per_class': per_class, 'targets': len(truth), 'predictions': len(predictions), 'matched': len(pairs),
            'missed': len(remaining_t)-len(wrong), 'wrong_class': len(wrong),
            'extra': len(remaining_p)-len(wrong), 'iou_sum': sum(overlaps),
            'iou_ge_075': sum(v >= .75 for v in overlaps),
            'localization_corrections': sum(v < .75 for v in overlaps)}


def evaluate(reference, methods):
    if reference.get('review_status') != 'human_confirmed' or not reference.get('confirmed_by'):
        raise ValueError('human-confirmed independent reference required')
    if set(methods) != {'mask', 'doubao'}:
        raise ValueError('both methods required')
    samples = reference['samples']
    if not isinstance(reference.get('owner_user_id'), str) or not reference['owner_user_id']:
        raise ValueError('explicit reference owner required')
    for sample in samples:
        if sample.get('source_kind') != 'real_photo' or not re.fullmatch(r'[0-9a-f]{64}', sample.get('image_sha256', '')):
            raise ValueError('only hashed real original photos may be scored')
        if any(isinstance(sample.get(key), bool) or not isinstance(sample.get(key), int) or sample[key] <= 0 for key in ('width','height')):
            raise ValueError('explicit positive original image dimensions required')
    identities = [s['image_sha256'] for s in samples]
    if not samples or len(samples) > 30 or len(set(identities)) != len(identities):
        raise ValueError('reference must contain 1..30 unique real photos')
    result = {'reference_sha256': hashlib.sha256(json.dumps(reference, sort_keys=True).encode()).hexdigest(),
              'timing_comparable': False, 'conclusion_scope': 'selected_cached_mask_samples_only', 'methods': {}}
    for name, records in methods.items():
        keys = [r['image_sha256'] for r in records]
        if len(set(keys)) != len(keys) or set(keys) != set(identities):
            raise ValueError('methods must cover identical images exactly once')
        lookup = {r['image_sha256']: r for r in records}
        per_image, total, per_class = [], {}, {}
        for sample in samples:
            prediction = lookup[sample['image_sha256']]
            if prediction.get('status') != 'completed':
                raise ValueError('incomplete provider result: no winner may be declared')
            metrics = measure(sample['objects'], prediction['objects'], sample['width'], sample['height'])
            per_image.append({'image_sha256': sample['image_sha256'], **metrics})
            for class_id, values in metrics['per_class'].items():
                aggregate = per_class.setdefault(class_id, {})
                for key, value in values.items():
                    aggregate[key] = aggregate.get(key, 0)+value
            for key, value in metrics.items():
                if key == 'per_class':
                    continue
                total[key] = total.get(key, 0)+value
        total['mean_matched_iou'] = total['iou_sum']/total['matched'] if total['matched'] else None
        total['iou_ge_075_target_ratio'] = total['iou_ge_075']/total['targets'] if total['targets'] else None
        total['estimated_edit_operations'] = total['missed']+total['wrong_class']+total['extra']+total['localization_corrections']
        result['methods'][name] = {'total': total, 'per_image': per_image, 'per_class': per_class}
    def rank(name):
        total = result['methods'][name]['total']
        return (total['missed'], total['wrong_class']+total['extra'], -total['iou_ge_075'],
                -(total['mean_matched_iou'] or 0), total['estimated_edit_operations'])
    result['winner'] = 'tie' if rank('mask') == rank('doubao') else min(methods, key=rank)
    result['edit_operation_note'] = 'estimated counts, not measured human correction time'
    return result
