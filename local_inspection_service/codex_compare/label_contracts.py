"""Version 2 label card contract; pure validation before transactional projection writes."""
from .validation import box, text

VERSION = 'label-v2'
DIMENSIONS = ('text', 'typography', 'color', 'graphics', 'completeness', 'orientation', 'shape', 'layout', 'codes', 'print')
STATES = {'pending', 'running', 'match', 'difference', 'uncertain', 'not_applicable'}
CATEGORIES = {'text', 'logo', 'symbol', 'diagram', 'code', 'color_block', 'outline', 'engineering'}
REQUIRED = {
    'text': ('text', 'typography', 'color'), 'logo': ('graphics', 'color', 'shape'),
    'symbol': ('graphics', 'orientation', 'color'), 'diagram': ('graphics', 'orientation'),
    'code': ('codes',), 'color_block': ('color', 'shape'), 'outline': ('shape',),
    'engineering': ('text',),
}


def fields(value, allowed):
    if not isinstance(value, dict) or set(value) - set(allowed.split()):
        raise ValueError('Unknown or invalid fields')


def ids(value, maximum=500):
    if not isinstance(value, list) or len(value) > maximum:
        raise ValueError('Expected bounded ID list')
    result = [text(x, 80) for x in value]
    if len(set(result)) != len(result):
        raise ValueError('Duplicate IDs')
    return result


def region(value):
    if value is None:
        return None
    fields(value, 'box polygon')
    bounds = box(value.get('box'))
    points = value.get('polygon')
    if points is not None:
        import math
        if not isinstance(points, list) or not 3 <= len(points) <= 64:
            raise ValueError('Polygon needs 3–64 points')
        for point in points:
            if (not isinstance(point, list) or len(point) != 2 or
                any(type(n) not in (int, float) or not math.isfinite(n) or not 0 <= n <= 1 for n in point)):
                raise ValueError('Polygon outside original image')
        area = abs(sum(points[i][0]*points[(i+1)%len(points)][1]-points[(i+1)%len(points)][0]*points[i][1] for i in range(len(points))))
        if area <= 1e-8:
            raise ValueError('Empty polygon')
        xs, ys = zip(*points)
        bounds = [min(xs), min(ys), max(xs)-min(xs), max(ys)-min(ys)]
    if bounds is None:
        raise ValueError('Region needs box or polygon')
    return {'box': bounds, 'polygon': points}


def element(value):
    fields(value, 'id category name description reference actual')
    if value.get('category') not in CATEGORIES:
        raise ValueError('Invalid element category')
    result = {k: text(value.get(k), 80 if k == 'id' else 4000) for k in ('id', 'name', 'description')}
    result.update(category=value['category'], reference=region(value.get('reference')), actual=region(value.get('actual')))
    return result


def check(value, task):
    fields(value, 'id element_ids dimension expected observed status explanation artifact_ids decode_ids')
    if value.get('dimension') not in DIMENSIONS or value.get('status') not in STATES:
        raise ValueError('Invalid dimension/status')
    result = {k: text(value.get(k), 80 if k == 'id' else 4000) for k in ('id', 'expected')}
    result.update(element_ids=ids(value.get('element_ids', [])), dimension=value['dimension'], status=value['status'])
    if any(x not in task['elements'] for x in result['element_ids']):
        raise ValueError('Unknown element')
    for key in ('observed', 'explanation'):
        result[key] = value.get(key, '')
        if not isinstance(result[key], str) or len(result[key]) > 4000:
            raise ValueError('Invalid observation/explanation')
        if result['status'] not in {'pending', 'running'}:
            text(result[key])
    for key, collection in (('artifact_ids', 'artifacts'), ('decode_ids', 'decodes')):
        result[key] = ids(value.get(key, []), 8)
        if any(x not in task.get(collection, {}) for x in result[key]):
            raise ValueError('Unknown evidence')
    old = task['checks'].get(result['id'])
    if old and any(old[k] != result[k] for k in ('dimension', 'element_ids', 'expected')):
        raise ValueError('Check identity is immutable; append a new check instead')
    if result['status'] == 'not_applicable':
        for eid in result['element_ids']:
            e = task['elements'][eid]
            if e['category'] != 'engineering' and result['dimension'] in set(REQUIRED[e['category']]) | {'completeness', 'layout'}:
                raise ValueError('Required element dimensions cannot be inapplicable; use uncertainty if unverifiable')
    if result['dimension'] == 'codes' and result['status'] == 'match':
        decoded = [task['decodes'][x] for x in result['decode_ids']]
        if any(not any(d['source'] == side and d['values'] for d in decoded) for side in ('reference', 'actual')):
            raise ValueError('Code match requires local decoding on both sides')
        if {v for d in decoded if d['source'] == 'reference' for v in d['values']} != {v for d in decoded if d['source'] == 'actual' for v in d['values']}:
            raise ValueError('Decoded payloads differ')
    return result


def issue(value, task):
    fields(value, 'id check_id title explanation reference actual artifact_ids resolved')
    target = value.get('check_id')
    if target not in task['checks']:
        raise ValueError('Unknown check')
    result = {k: text(value.get(k), 80 if k == 'id' else 4000) for k in ('id', 'title', 'explanation')}
    result.update(check_id=target, reference=region(value.get('reference')), actual=region(value.get('actual')),
                  artifact_ids=ids(value.get('artifact_ids', []), 8), resolved=value.get('resolved', False))
    if type(result['resolved']) is not bool or any(x not in task['artifacts'] for x in result['artifact_ids']):
        raise ValueError('Invalid issue evidence/status')
    if result['resolved'] and task['checks'][target]['status'] == 'difference':
        raise ValueError('Cannot resolve an outstanding difference')
    return result


def apply(task, kind, payload):
    if task.get('report_version') != VERSION:
        raise ValueError('Operation requires a label-v2 card')
    if kind == 'element':
        value = element(payload)
        selected = task.get('inputs', {}).get('reference_region', [0, 0, 1, 1])
        if value['reference'] and value['category'] != 'engineering':
            x,y,w,h = value['reference']['box']
            a,b,c,d = selected
            if x < a-1e-6 or y < b-1e-6 or x+w > a+c+1e-6 or y+h > b+d+1e-6:
                raise ValueError('Printed element lies outside selected label region')
        if len(task['elements']) >= 200 and value['id'] not in task['elements']:
            raise ValueError('At most 200 elements')
        task['elements'][value['id']] = value
    elif kind == 'checklist':
        fields(payload, 'checks')
        entries = payload.get('checks')
        if not isinstance(entries, list) or not entries or len(entries) > 500:
            raise ValueError('Checklist requires 1–500 checks')
        values = [check({**x, 'status': 'pending'}, task) for x in entries]
        if len({x['id'] for x in values}) != len(values):
            raise ValueError('Duplicate check IDs')
        if len(set(task['checks']) | {x['id'] for x in values}) > 500:
            raise ValueError('At most 500 checks')
        # Additive only: later planning cannot erase unfinished work or results.
        for entry in values:
            task['checks'].setdefault(entry['id'], entry)
        value = {'checks': values}
    elif kind == 'check':
        if payload.get('id') not in task['checks']:
            raise ValueError('Publish checklist before checking')
        value = check(payload, task)
        task['checks'][value['id']] = value
    elif kind == 'issue':
        value = issue(payload, task)
        if len(task['issues']) >= 500 and value['id'] not in task['issues']:
            raise ValueError('At most 500 issues')
        task['issues'][value['id']] = value
    else:
        raise ValueError('Unknown label operation')
    return value


def validate(task):
    checks = list(task['checks'].values())
    report = task.get('summary')
    if not task['elements'] or not checks or not report:
        raise ValueError('Elements, checklist and summary required')
    if any(c['status'] in {'pending', 'running'} for c in checks):
        raise ValueError('Unfinished checks remain; inspect them or explicitly record uncertainty')
    overall = {c['dimension'] for c in checks if not c['element_ids']}
    if overall != set(DIMENSIONS):
        raise ValueError('All ten overall dimensions must be assessed')
    for eid, entry in task['elements'].items():
        needed = set(REQUIRED[entry['category']]) | {'completeness', 'layout'}
        covered = {c['dimension'] for c in checks if eid in c['element_ids']}
        if not needed <= covered:
            raise ValueError('Missing element dimensions: '+eid+': '+','.join(sorted(needed-covered)))
    active_issues = [i for i in task['issues'].values() if not i['resolved']]
    for c in checks:
        if c['status'] == 'difference' and not any(i['check_id'] == c['id'] for i in active_issues):
            raise ValueError('Every difference needs an issue record')
        if c['status'] == 'match':
            for eid in c['element_ids']:
                e = task['elements'][eid]
                if e['category'] != 'engineering' and (e['reference'] is None or e['actual'] is None):
                    raise ValueError('Matched elements require reliable dual-side locations')
    if report['decision'] == 'MATCH':
        if active_issues or report['unchecked_scope'].strip() or any(c['status'] not in {'match', 'not_applicable'} for c in checks):
            raise ValueError('MATCH requires fully verified scope without open issues')
        if not any(c['status'] == 'match' for c in checks):
            raise ValueError('An entirely inapplicable report cannot match')
        if any(c['status'] != 'match' for c in checks if not c['element_ids'] and c['dimension'] in {'completeness', 'layout', 'shape'}):
            raise ValueError('Overall completeness, layout and shape must match')
    if any(c['status'] == 'difference' for c in checks) and report['decision'] != 'DIFFERENCES':
        raise ValueError('Confirmed differences must be disclosed in the summary decision')
    if report['decision'] == 'DIFFERENCES' and not any(c['status'] == 'difference' for c in checks):
        raise ValueError('DIFFERENCES requires a difference check')
    if any(c['status'] == 'uncertain' for c in checks) and not report['unchecked_scope'].strip():
        raise ValueError('Uncertain checks must be disclosed in summary scope')
