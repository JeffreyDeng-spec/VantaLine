"""One immutable batch/session with independently addressable label reports."""
from copy import deepcopy
import re
from .validation import box, text, summary
from . import label_contracts as label

VERSION = 'label-batch-v3'
MAX_LABELS = 50
MAX_REFERENCES = 500


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', value):
        raise ValueError('Invalid label/reference ID')
    return value


def new_label(lid, actual, name):
    return {'id': identifier(lid), 'name': text(name, 200), 'actual': actual,
            'match': {'status': 'pending', 'reason': '', 'reference_id': None, 'candidate_ids': []},
            'elements': {}, 'checks': {}, 'issues': {}, 'artifacts': {}, 'decodes': {},
            'summary': None, 'reviews': [], 'finalized': False}


def get_label(task, lid):
    identifier(lid)
    if lid not in task.get('labels', {}):
        raise ValueError('Unknown label in this batch')
    return task['labels'][lid]


def card(task, lid):
    entry = get_label(task, lid)
    match = entry['match']
    ref = task['references'].get(match.get('reference_id'))
    asset = task['inputs']['references'].get(ref['asset_id']) if ref else None
    return {**entry, 'report_version': label.VERSION, 'items': {},
            'inputs': {'reference': asset['media'] if asset else None, 'actual': entry['actual'],
                       'reference_region': ref['region'] if ref else None,
                       'standard_name': task['inputs'].get('standard_name', ''),
                       'standard_revision_id': task['inputs'].get('standard_revision_id', ''),
                       'standard_revision_number': task['inputs'].get('standard_revision_number', 0)}}


def require_matched(task, lid):
    entry = get_label(task, lid)
    if entry['match']['status'] != 'matched':
        raise ValueError('Publish an unambiguous match before inspecting this label')
    return card(task, lid)


def reference(task, value):
    label.fields(value, 'id asset_id name region')
    rid, aid = identifier(value.get('id')), identifier(value.get('asset_id'))
    asset = task['inputs']['references'].get(aid)
    if not asset or not asset.get('media'):
        raise ValueError('Reference image unavailable')
    bounds = box(value.get('region'))
    if bounds is None:
        raise ValueError('Select exactly one label region')
    result = {'id': rid, 'asset_id': aid, 'name': text(value.get('name'), 200), 'region': bounds}
    old = task['references'].get(rid)
    if old and old != result and any(x['match'].get('reference_id') == rid and (x['elements'] or x['checks'] or x['artifacts'] or x['decodes'] or x['finalized']) for x in task['labels'].values()):
        raise ValueError('Reference used by inspection is frozen; cannot change its geometry')
    if not old and len(task['references']) >= MAX_REFERENCES:
        raise ValueError('Too many reference regions')
    task['references'][rid] = result
    return result


def matching(task, lid, value):
    label.fields(value, 'status reference_id candidate_ids reason')
    entry = get_label(task, lid)
    state = value.get('status')
    if state not in {'matched', 'needs_confirmation'}:
        raise ValueError('Match must be matched or needs_confirmation')
    rid = value.get('reference_id')
    candidates = label.ids(value.get('candidate_ids', []), 20)
    if any(x not in task['references'] for x in candidates) or (rid is not None and rid not in task['references']):
        raise ValueError('Unknown reference region')
    if state == 'matched' and rid is None:
        raise ValueError('Matched label needs one reference')
    if state == 'needs_confirmation' and rid is not None:
        raise ValueError('An uncertain match must not assert a reference')
    result = {'status': state, 'reference_id': rid, 'candidate_ids': candidates, 'reason': text(value.get('reason'))}
    if entry.get('human_match') and result != entry['match']:
        raise ValueError('Human-selected correspondence is frozen for this run; report inspection uncertainty instead')
    if (entry['elements'] or entry['checks'] or entry['artifacts'] or entry['decodes'] or entry['finalized']) and result != entry['match']:
        raise ValueError('Cannot rematch a label after inspection has begun; create a new batch')
    entry['match'] = result
    return result


def apply(task, kind, payload):
    if kind == 'reference':
        return reference(task, payload)
    if kind in {'progress', 'summary', 'finalize'} and 'label_id' not in payload:
        if kind == 'progress':
            task['progress_message'] = text(payload.get('message'), 1000)
            return {'message': task['progress_message']}
        if kind == 'summary':
            task['summary'] = summary(payload)
            return task['summary']
        validate(task)
        task['finalized'] = True
        return {}
    label.fields(payload, 'label_id value')
    lid = payload.get('label_id')
    value = payload.get('value')
    entry = get_label(task, lid)
    if entry['finalized']:
        raise ValueError('Label report already finalized')
    if kind == 'match':
        result = matching(task, lid, value)
    elif kind == 'progress':
        entry['progress_message'] = text(value.get('message'), 1000)
        result = {'message': entry['progress_message']}
    else:
        view = require_matched(task, lid)
        if kind in {'element', 'checklist', 'check', 'issue'}:
            result = label.apply(view, kind, value)
        elif kind == 'summary':
            entry['summary'] = summary(value)
            result = entry['summary']
        elif kind in {'artifact', 'decode'}:
            collection = 'artifacts' if kind == 'artifact' else 'decodes'
            if len(entry[collection]) >= 200 and value['id'] not in entry[collection]:
                raise ValueError('Evidence record limit reached')
            entry[collection][value['id']] = value
            result = value
        elif kind == 'finalize':
            label.validate(view)
            entry['finalized'] = True
            result = {}
        else:
            raise ValueError('Unsupported batch operation')
    return {'label_id': lid, 'value': result}


def validate(task):
    if not task.get('labels') or not task.get('summary'):
        raise ValueError('Batch labels and summary required')
    decisions = []
    for lid, entry in task['labels'].items():
        if entry['match']['status'] == 'pending':
            raise ValueError('Every uploaded photo needs a match outcome')
        if entry['match']['status'] == 'needs_confirmation':
            decisions.append('REVIEW_REQUIRED')
        else:
            label.validate(card(task, lid))
            decisions.append(entry['summary']['decision'])
    report = task['summary']
    expected = 'DIFFERENCES' if 'DIFFERENCES' in decisions else 'REVIEW_REQUIRED' if 'REVIEW_REQUIRED' in decisions else 'MATCH'
    if report['decision'] != expected:
        raise ValueError('Batch decision must disclose all label outcomes: '+expected)
    uncertain = any(e['match']['status'] != 'matched' or (e['summary'] and e['summary']['unchecked_scope'].strip()) for e in task['labels'].values())
    if uncertain and not report['unchecked_scope'].strip():
        raise ValueError('Disclose unresolved labels and uncertain scope')
    if expected == 'MATCH' and report['unchecked_scope'].strip():
        raise ValueError('MATCH cannot have unchecked scope')


def label_status(task, entry):
    if any(c['status'] == 'difference' for c in entry['checks'].values()):
        return 'difference'
    if entry['match']['status'] == 'needs_confirmation' or any(c['status'] == 'uncertain' for c in entry['checks'].values()):
        return 'uncertain'
    if entry['match']['status'] == 'matched' and entry.get('summary'):
        try:
            label.validate(card(task, entry['id']))
            if entry['summary']['decision'] == 'MATCH':
                return 'match'
            return 'uncertain'
        except ValueError:
            pass
    return 'pending'


def public_label(task, lid, detail=False):
    e = get_label(task, lid)
    result = {k: deepcopy(e[k]) for k in ('id', 'name', 'actual', 'match', 'summary', 'finalized')}
    result['outcome'] = label_status(task, e)
    result['progress_message'] = e.get('progress_message', '')
    result['progress'] = {'total': len(e['checks']), 'settled': sum(c['status'] not in {'pending', 'running'} for c in e['checks'].values()), 'elements': len(e['elements'])}
    result['inputs'] = card(task, lid)['inputs']
    if detail:
        result.update({k: list(e[k].values()) for k in ('elements', 'checks', 'issues', 'artifacts', 'decodes')})
        result['reviews'] = e['reviews']
    return result


def public_batch(task):
    result = {k: deepcopy(task[k]) for k in ('id', 'status', 'created_at', 'updated_at', 'sequence', 'summary', 'finalized', 'report_version', 'parent_id') if k in task}
    for k in ('session_id', 'model', 'error', 'skill_version', 'skill_sha256', 'runner_version', 'tool_version', 'started_at', 'finished_at', 'usage', 'progress_message', 'import_state'):
        if k in task:
            result[k] = deepcopy(task[k])
    result['inputs'] = deepcopy(task['inputs'])
    result['references'] = list(task['references'].values())
    result['labels'] = [public_label(task, lid) for lid in task['labels']]
    result['counts'] = {s: sum(e['outcome'] == s for e in result['labels']) for s in ('difference', 'uncertain', 'pending', 'match')}
    return result


def media_hashes(task):
    values = [r.get('media') for r in task['inputs']['references'].values()]
    for entry in task['labels'].values():
        values += [entry['actual'], *entry['artifacts'].values()]
    return {v[k] for v in values if v for k in ('original', 'image', 'preview')}
