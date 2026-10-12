"""Administrator-only, stored evidence projections. No reconciliation or paid work."""
import base64
import hashlib
import json
from urllib.parse import quote, urlsplit
from fastapi import HTTPException, Query, Response
from fastapi.responses import RedirectResponse
from ..storage.postgres_runtime_repository import _decode_value
from ..training.real_photo_annotation import canonical

STATUSES = ('eligible', 'excluded', 'uncertain', 'processing', 'annotation_failed', 'disabled', 'not_collected', 'unknown')
CURRENT = {'accept_positive': 'eligible', 'accept_negative': 'eligible', 'exclude': 'excluded',
           'uncertain': 'uncertain', 'usage_disabled': 'disabled', 'annotation_failed': 'annotation_failed',
           'pending_annotation': 'processing', 'pending_review': 'processing', 'unconfirmed_source': 'processing'}
REASONS = {'processing': '等待标注、有效审核或来源确认', 'annotation_failed': '标注失败，不代表 Agent 排除',
           'disabled': '当前训练用途已停用', 'not_collected': '没有回流采集记录',
           'unknown': '没有足够的有效关联或当前结论证据', 'eligible': '通过当前训练准入判断'}


def rows(value):
    return [x for x in value or [] if isinstance(x, dict)] if isinstance(value, list) else []


def object_value(value):
    return value if isinstance(value, dict) else {}


def bounded(value, maximum=4000):
    return str(value or '')[:maximum]


def page(items, scope, cursor, limit, key):
    ordered = sorted(items, key=key, reverse=True)
    anchor = key(ordered[0]) if ordered else None
    before = None
    if cursor:
        try:
            token = json.loads(base64.urlsafe_b64decode(cursor + '=' * (-len(cursor) % 4)))
            if token['scope'] != scope or not isinstance(token['anchor'], list) or (token['before'] is not None and not isinstance(token['before'], list)):
                raise ValueError()
            anchor, before = tuple(token['anchor']), tuple(token['before']) if token['before'] is not None else None
            if len(anchor) != 2 or type(anchor[0]) not in (int, float) or not isinstance(anchor[1], str) or (before is not None and (len(before) != 2 or type(before[0]) not in (int, float) or not isinstance(before[1], str) or before > anchor)):
                raise ValueError()
        except (KeyError, ValueError, TypeError, UnicodeError):
            raise HTTPException(422, '分页游标无效，请刷新列表') from None
    anchored = [x for x in ordered if anchor is not None and key(x) <= anchor]
    remaining = [x for x in anchored if before is None or key(x) < before]
    selected = remaining[:limit]
    next_cursor = None
    if len(remaining) > limit:
        next_cursor = base64.urlsafe_b64encode(json.dumps({'scope': scope, 'anchor': anchor, 'before': key(selected[-1])}).encode()).decode()
    refresh_cursor = base64.urlsafe_b64encode(json.dumps({'scope': scope, 'anchor': anchor, 'before': None}).encode()).decode() if anchor is not None else None
    return selected, next_cursor, refresh_cursor


class DatasetPhotos:
    def __init__(self, workbench, owner, *, load_training=True, classify=True):
        self.workbench = workbench
        self.actor, self.target = workbench.target(owner)
        self.owner = owner
        self.feedback = workbench.feedback(self.target)
        self.datasets = {}
        self.samples = {}
        self.real_tasks = set()
        self.legacy_tasks = set()
        self.tasks = {str(t['id']): t for t in self.feedback.ports.tasks() if t.get('owner_user_id') == owner and t.get('id')}
        if load_training:
            self._load_training(classify)

    def _manifest(self, dataset):
        if isinstance(dataset.get('samples'), list):
            return dataset
        if dataset.get('manifest_path'):
            try:
                raw = self.feedback.ports.read(str(dataset['manifest_path']))
                if len(raw) > 32 * 1024 * 1024:
                    return {}
                value = json.loads(raw)
                if isinstance(value, dict) and value.get('owner_user_id') in (None, '', self.owner) and str(value.get('id') or dataset['id']) == str(dataset['id']):
                    return value
            except (OSError, ValueError, HTTPException):
                pass
        return {}

    def _add_dataset(self, dataset, task_id=''):
        identifier = str(dataset.get('id') or '')
        if not identifier or dataset.get('owner_user_id') not in (None, '', self.owner):
            return
        if identifier in self.datasets and self.datasets[identifier]['members_available']:
            return
        manifest = self._manifest(dataset)
        members = rows(manifest.get('samples'))
        self.datasets[identifier] = {'id': identifier, 'name': bounded(dataset.get('display_name') or identifier, 200),
            'task_id': str(dataset.get('task_id') or manifest.get('task_id') or task_id), 'sample_count': len(members) if not str(dataset.get('sample_count') or '').isdigit() else int(dataset['sample_count']),
            'created_at': dataset.get('created_at') or 0, 'members_available': isinstance(manifest.get('samples'), list),
            '_members': members}

    def _load_training(self, classify):
        with self.feedback.repo() as repo:
            states = repo.states({self.owner})
        for state in states:
            task_id = str(state.get('task_id') or '')
            if task_id not in self.tasks or state.get('owner_user_id') != self.owner:
                continue
            self.real_tasks.add(task_id)
            # Reuse the authoritative current-review/definition/usage projection.
            public = {}
            cursor = None
            while classify:
                result = self.feedback.sample_page(task_id, cursor=cursor, limit=100)
                public.update({s['sample_id']: s for s in result['samples']})
                cursor = result['next_cursor']
                if not cursor:
                    break
            for sample in rows(state.get('samples')):
                sid = str(sample.get('sample_id') or '')
                if not sid or sample.get('owner_user_id') not in (None, '', self.owner):
                    continue
                projection = public.get(sid, {})
                status = CURRENT.get(projection.get('current_status'), 'unknown')
                review = object_value(projection.get('review'))
                self.samples[(task_id, sid)] = {'task_id': task_id, 'sample_id': sid, 'record_id': str(sample.get('record_id') or ''),
                    'status': status, 'reason': bounded(review.get('reason') or REASONS.get(status)),
                    'sample_type': 'positive' if projection.get('current_status') == 'accept_positive' else 'negative' if projection.get('current_status') == 'accept_negative' else None,
                    'annotation': projection.get('annotation'), '_sample': sample, 'mode': 'real_photo'}
            for dataset in rows(state.get('datasets')):
                self._add_dataset(dataset, task_id)
        for task_id in self.tasks:
            legacy = self.feedback.ports.legacy_state(task_id)
            if legacy.get('owner_user_id') != self.owner:
                continue
            self.legacy_tasks.add(task_id)
            for sample in rows(legacy.get('samples')):
                sid = str(sample.get('sample_id') or '')
                if not sid or sample.get('owner_user_id') not in (None, '', self.owner):
                    continue
                label_status = sample.get('label_status')
                status = 'disabled' if sample.get('usage_enabled', True) is False else 'annotation_failed' if label_status == 'failed' else 'processing' if label_status in ('pending', 'labeling', 'running') else 'unknown'
                self.samples[(task_id, sid)] = {'task_id': task_id, 'sample_id': sid, 'record_id': str(sample.get('record_id') or ''),
                    'status': status, 'reason': bounded(sample.get('label_reject_reason') or ('旧模式标注状态：' + str(label_status or '未知') + '；不推断实拍 Agent 结论')),
                    'legacy_label_status': label_status, '_sample': sample, 'mode': 'legacy'}
            for dataset in rows(legacy.get('datasets')):
                self._add_dataset(dataset, task_id)
        resources = self.workbench.ports.resources(user=self.actor, target_user_id=self.owner, include_samples=False)
        for dataset in rows(resources.get('datasets')):
            if dataset.get('owner_user_id') == self.owner:
                self._add_dataset(dataset)

    def records(self, record_id=None):
        repo = self.workbench.repository()
        c = repo._cursor()
        try:
            condition = ' AND record_id=%s' if record_id is not None else ''
            c.execute(f'SELECT record_id,task_id,created_at,image_path,raw_json FROM {repo._qualified_table("data_analysis_records")} WHERE owner_user_id=%s{condition} ORDER BY created_at DESC,record_id DESC', [self.owner] + ([record_id] if record_id is not None else []))
            values = [repo._row_to_dict(c, x) for x in c.fetchall()]
            repo._end_read_transaction()
            return values
        finally:
            c.close()

    def memberships(self, task_id, sample_ids, record_id=''):
        result = []
        for dataset in self.datasets.values():
            matching = [m for m in dataset['_members'] if (dataset['task_id'] == task_id and m.get('source_sample_id') and str(m['source_sample_id']) in sample_ids) or (record_id and str(m.get('source_record_id') or '') == record_id)]
            if matching:
                result.append({'dataset_id': dataset['id'], 'name': dataset['name'], 'splits': sorted({str(m.get('split') or 'unknown') for m in matching}),
                    'member_count': len(matching), 'created_at': dataset['created_at']})
        return result

    def project_record(self, row):
        raw = object_value(_decode_value('raw_json', row['raw_json']))
        task_id, rid = str(row['task_id']), str(row['record_id'])
        matched = [s for s in self.samples.values() if s['record_id'] == rid]
        states = {s['status'] for s in matched}
        status = next(iter(states)) if len(states) == 1 else 'unknown' if matched or task_id in self.real_tasks or task_id in self.legacy_tasks else 'not_collected'
        membership_map = {m['dataset_id']: m for m in self.memberships(task_id, set(), rid)}
        for sample in matched:
            membership_map.update({m['dataset_id']:m for m in self.memberships(sample['task_id'], {sample['sample_id']}, rid)})
        memberships = list(membership_map.values())
        result = {'record_id': rid, 'created_at': row['created_at'], 'task_id': task_id,
            'task_name': bounded(object_value(raw.get('task')).get('name') or self.tasks.get(task_id, {}).get('name') or task_id, 200),
            'status': status, 'reason': matched[0]['reason'] if len(matched) == 1 else REASONS.get(status, ''),
            'samples': [{k:v for k,v in s.items() if not k.startswith('_')} for s in matched], 'memberships': memberships,
            'image_type': 'original' if row['image_path'] else 'annotated' if self.annotated_url(raw) else 'unavailable',
            'image_url': self.base() + '/detection-photos/' + quote(rid, safe='') + '/image'}
        return result

    def base(self):
        return '/api/auth/users/' + quote(self.owner, safe='') + '/data'

    @staticmethod
    def annotated_url(raw):
        value = str(raw.get('image_url') or object_value(raw.get('source_image')).get('url') or '')
        parsed = urlsplit(value)
        # Never fetch a remote URL or permit an arbitrary redirect.
        if not parsed.scheme and not parsed.netloc and parsed.path.startswith('/outputs/') and '..' not in parsed.path and '\\' not in value and '%' not in value and not parsed.query and not parsed.fragment:
            return value
        return None

    def photo_page(self, task_id=None, status=None, cursor=None, limit=24):
        if status not in (None, 'included', *STATUSES):
            raise HTTPException(422, '未知照片分类')
        all_records = self.records()
        values = [self.project_record(r) for r in all_records if not task_id or str(r['task_id']) == task_id]
        counts = {s: sum(v['status'] == s for v in values) for s in STATUSES}
        counts['included'] = sum(bool(v['memberships']) for v in values)
        selected = [v for v in values if not status or (bool(v['memberships']) if status == 'included' else v['status'] == status)]
        items, next_cursor, refresh_cursor = page(selected, [self.owner, 'photos', task_id, status], cursor, limit, lambda v: (v['created_at'], v['record_id']))
        task_options = {str(r['task_id']): bounded(object_value(object_value(_decode_value('raw_json', r['raw_json'])).get('task')).get('name') or r['task_id'], 200) for r in all_records}
        revision = hashlib.sha256(json.dumps([(v['record_id'], v['status'], v['memberships']) for v in values], sort_keys=True).encode()).hexdigest()
        return {'items': items, 'total': len(selected), 'record_total': len(values), 'counts': counts, 'next_cursor': next_cursor,
                'revision': revision, 'refresh_cursor': refresh_cursor, 'latest_record_id': items[0]['record_id'] if items else None,
                'tasks': [{'id': k, 'name': v} for k,v in sorted(task_options.items())]}

    def detail(self, record_id):
        values = self.records(record_id)
        if not values:
            raise HTTPException(404, '检测照片记录不存在')
        result = self.project_record(values[0])
        for sample in result['samples']:
            if sample['mode'] == 'real_photo':
                sample['versions_url'] = self.base() + '/tasks/' + quote(sample['task_id'], safe='') + '/samples/' + quote(sample['sample_id'], safe='') + '/versions'
        return result

    def photo_image(self, record_id):
        values = self.records(record_id)
        if not values:
            raise HTTPException(404, '检测照片记录不存在')
        value = values[0]
        if value['image_path']:
            return self.image_response(value['image_path'])
        url = self.annotated_url(object_value(_decode_value('raw_json', value['raw_json'])))
        if url:
            return RedirectResponse(url, status_code=307, headers={'Cache-Control': 'private, no-store'})
        raise HTTPException(404, '图片文件不可用，记录仍然保留')

    def dataset(self, identifier):
        dataset = self.datasets.get(identifier)
        if not dataset:
            raise HTTPException(404, '数据集不存在或不属于该账号')
        return dataset

    def member(self, dataset, index):
        if index < 0 or index >= len(dataset['_members']):
            raise HTTPException(404, '训练集成员不存在')
        return dataset['_members'][index]

    def dataset_page(self, identifier, cursor=None, limit=24):
        dataset = self.dataset(identifier)
        items = []
        for index, member in enumerate(dataset['_members']):
            sid = str(member.get('source_sample_id') or '')
            sample = self.samples.get((dataset['task_id'], sid), {})
            items.append({'id': str(index), 'sample_id': sid, 'record_id': str(member.get('source_record_id') or sample.get('record_id') or ''),
                'split': str(member.get('split') or 'unknown'), 'annotation_version': member.get('annotation_version'),
                'label_count': member.get('label_count'), 'current_status': sample.get('status', 'unknown'),
                'current_reason': sample.get('reason', REASONS['unknown']),
                'versions_url': self.base() + '/tasks/' + quote(sample['task_id'], safe='') + '/samples/' + quote(sid, safe='') + '/versions' if sample.get('mode') == 'real_photo' else None,
                'sample_type': member.get('sample_type'), 'image_type': 'dataset',
                'image_url': self.base() + '/datasets/' + quote(identifier, safe='') + '/members/' + str(index) + '/image'})
        selected, next_cursor, _ = page(items, [self.owner, 'dataset', identifier], cursor, limit, lambda v: (int(v['id']), v['id']))
        return {'dataset': {k:v for k,v in dataset.items() if not k.startswith('_')}, 'items': selected,
            'total': len(items), 'next_cursor': next_cursor, 'reason': None if dataset['members_available'] else '历史数据集没有可读取的成员清单；不推断其图片组成'}

    def image_response(self, path):
        try:
            data = self.feedback.ports.read(str(path))
            if len(data) > 32 * 1024 * 1024:
                raise ValueError()
            clean, _ = canonical(data)
        except (OSError, ValueError, HTTPException):
            raise HTTPException(404, '图片文件不可用，记录仍然保留') from None
        return Response(clean, media_type='image/png', headers={'Cache-Control': 'private, no-store'})


def register_dataset_photos(app, workbench):
    base = '/api/auth/users/{owner}/data'

    @app.get(base + '/detection-photos')
    def photos(owner: str, task_id: str | None = Query(default=None, max_length=200), status: str | None = Query(default=None, max_length=32), cursor: str | None = Query(default=None, max_length=2048), limit: int = Query(default=24, ge=1, le=100)):
        return DatasetPhotos(workbench, owner).photo_page(task_id, status, cursor, limit)

    @app.get(base + '/detection-photos/{record_id}')
    def detail(owner: str, record_id: str):
        return DatasetPhotos(workbench, owner).detail(record_id)

    @app.get(base + '/detection-photos/{record_id}/image')
    def photo_image(owner: str, record_id: str):
        return DatasetPhotos(workbench, owner, load_training=False).photo_image(record_id)

    @app.get(base + '/datasets/{dataset_id}/members')
    def members(owner: str, dataset_id: str, cursor: str | None = Query(default=None, max_length=2048), limit: int = Query(default=24, ge=1, le=100)):
        return DatasetPhotos(workbench, owner).dataset_page(dataset_id, cursor, limit)

    @app.get(base + '/datasets/{dataset_id}/members/{index}/image')
    def member_image(owner: str, dataset_id: str, index: int):
        service = DatasetPhotos(workbench, owner, classify=False)
        member = service.member(service.dataset(dataset_id), index)
        if not member.get('image'):
            raise HTTPException(404, '训练集成员图片不可用')
        return service.image_response(member['image'])
