"""Real-photo feedback contracts. No provider, filesystem or training side effects."""
import hashlib
import json
import math

STRATEGY = 'real_photo_vlm'
MODEL = 'doubao-seed-2-1-pro-260915'
VERSION = 'real-photo-v1'
DECISIONS = {'accept_positive', 'accept_negative', 'exclude', 'uncertain'}
TERMINAL = {'completed', 'failed', 'interrupted', 'cancelled', 'stale'}


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(value if isinstance(value, bytes) else encode(value).encode()).hexdigest()


def integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError('integer outside permitted range')
    return value


def objects(value, classes, width, height, *, normalized=False):
    if not isinstance(value, list) or len(value) > 200:
        raise ValueError('bounded object list required')
    result = []
    for item in value:
        if not isinstance(item, dict) or set(item) != {'class_id', 'bbox'} or item['class_id'] not in classes:
            raise ValueError('unknown class or object fields')
        box = item['bbox']
        if not isinstance(box, list) or len(box) != 4:
            raise ValueError('four explicit xyxy coordinates required')
        if any(type(v) not in (float, int) or not math.isfinite(v) for v in box):
            raise ValueError('finite numeric coordinates required')
        w, h = (1000, 1000) if normalized else (width, height)
        x1, y1, x2, y2 = box
        if not (0 <= x1 < x2 <= w and 0 <= y1 < y2 <= h):
            raise ValueError('bbox outside declared coordinate system')
        clean = [x1*width/w, y1*height/h, x2*width/w, y2*height/h]
        row = {'class_id': item['class_id'], 'bbox': clean}
        if row in result:
            raise ValueError('duplicate object')
        result.append(row)
    return result


def annotation_key(sample, classes):
    return digest({'image': sample['image_sha256'], 'classes': classes, 'model': MODEL, 'version': VERSION})


def review_key(sample, classes):
    return digest({'image': sample['image_sha256'], 'annotation': sample.get('annotation'), 'classes': classes})


def review_report(job, result):
    if not isinstance(result, dict):
        raise ValueError('review report required')
    kind = job['kind']
    if kind == 'initialize':
        if set(result) != {'review_trigger', 'approved_real_target', 'reason'}:
            raise ValueError('initialization fields required')
        integer(result['review_trigger'], 20, 50)
        integer(result['approved_real_target'], 20, 50)
    elif kind == 'review':
        if set(result) != {'decisions'} or not isinstance(result['decisions'], list):
            raise ValueError('whole-image decisions required')
        expected = {s['sample_id']: s for s in job['inputs']['samples']}
        seen = set()
        for decision in result['decisions']:
            if set(decision) != {'sample_id', 'review_key', 'decision', 'reason'}:
                raise ValueError('agent may not change annotation fields')
            s = expected.get(decision['sample_id'])
            if not s or s['sample_id'] in seen or decision['review_key'] != s['review_key']:
                raise ValueError('missing, duplicate or stale review identity')
            if decision['decision'] not in DECISIONS:
                raise ValueError('unknown review decision')
            if decision['decision'] == 'accept_positive' and not s['annotation']['objects']:
                raise ValueError('positive review requires existing boxes')
            if decision['decision'] == 'accept_positive':
                objects(s['annotation']['objects'],{c['class_id'] for c in job['inputs']['classes']},
                        s['geometry']['width'],s['geometry']['height'])
            if decision['decision'] == 'accept_negative' and s['annotation']['objects']:
                raise ValueError('negative review cannot remove boxes')
            reason(decision['reason'])
            seen.add(s['sample_id'])
        if seen != set(expected):
            raise ValueError('every image requires a decision')
        return result
    elif kind == 'assess':
        if set(result) != {'action', 'approved_real_target', 'next_increment', 'reason', 'gaps'}:
            raise ValueError('dataset assessment fields required')
        if result['action'] not in {'train', 'collect', 'pause'}:
            raise ValueError('unknown dataset action')
        integer(result['approved_real_target'], 20, 50)
        integer(result['next_increment'], 1, 50)
        if not isinstance(result['gaps'], list) or len(result['gaps']) > 50:
            raise ValueError('bounded gap descriptions required')
        for gap in result['gaps']:
            reason(gap)
    else:
        raise ValueError('not an agent task')
    reason(result['reason'])
    return result


def reason(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 1000:
        raise ValueError('bounded nonempty reason required')


def approved(state):
    classes = state['classes']
    return [s for s in state['samples'] if s.get('annotation', {}).get('status') == 'completed'
            and s.get('review', {}).get('key') == review_key(s, classes)
            and s['review'].get('decision') in {'accept_positive', 'accept_negative'}]


def split_samples(samples, previous=None):
    """Stable group-first split; entire videos/sessions and known hashes stay together."""
    groups = {}
    for s in samples:
        if not s.get('source_group'):
            raise ValueError('source group missing')
        groups.setdefault(s['source_group'], []).append(s)
    if len(groups) < 3:
        raise ValueError('at least three independent source groups required')
    assignments = dict(previous or {})
    order = sorted(groups, key=lambda g: digest(g))
    if not any(assignments.get(g)=='train' for g in groups):
        positive=next((g for g in order if any(s['annotation']['objects'] for s in groups[g]) and g not in assignments),None)
        if positive:assignments[positive]='train'
    for g in order:
        if g not in assignments:
            counts = {v: sum(len(groups[k]) for k in groups if assignments.get(k) == v)
                      for v in ('train', 'val', 'test')}
            missing = [v for v in ('train', 'val', 'test') if counts[v] == 0]
            assignments[g] = missing[0] if missing else min(counts, key=lambda v: counts[v] / {'train': .8, 'val': .1, 'test': .1}[v])
    if not any(assignments[s['source_group']] == 'train' and s['annotation']['objects'] for s in samples):
        raise ValueError('training split requires a positive image; adjust groups before training')
    if set(assignments[g] for g in groups) != {'train', 'val', 'test'}:
        raise ValueError('all three splits required')
    identities = {}
    for s in samples:
        split = assignments[s['source_group']]
        for identity in {s['image_sha256'],*s.get('lineage_hashes',[])}:
            if identities.setdefault(identity, split) != split:
                raise ValueError('same original or lineage cannot cross splits')
    return assignments


def dataset_gate(state, target):
    selected = approved(state)
    if len({s['image_sha256'] for s in selected})!=len(selected):
        raise ValueError('approved images must be distinct originals')
    if len(selected) < max(20, integer(target, 20, 50)) or not any(s['annotation']['objects'] for s in selected):
        raise ValueError('insufficient approved real photos or no positive image')
    assignments = split_samples(selected, state.get('split_assignments'))
    supported = {o['class_id'] for s in selected for o in s['annotation']['objects']}
    return selected, assignments, [c['class_id'] for c in state['classes'] if c['class_id'] not in supported]
