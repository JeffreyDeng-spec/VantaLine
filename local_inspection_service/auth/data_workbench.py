"""Explicit administrator actor/owner boundary; browsing never reconciles work."""
from contextlib import nullcontext
from dataclasses import dataclass
from typing import Any, Callable, Literal
import base64
import json
import hashlib
import time
import uuid
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field, StrictBool
from .policy import public_user, find_user
from ..schemas.pipeline import PipelineTaskUpdateRequest
from ..training.real_photo_api import FeedbackService, EnableRequest, accounts

Record = dict[str, Any]


class DataOperation(BaseModel):
    action: Literal['pause', 'resume', 'params', 'archive', 'restore', 'image_usage']
    kind: Literal['pipeline', 'training', 'dataset', 'model', 'real_photo', 'sample', 'reference', 'legacy']
    resource_id: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=1, max_length=300)
    task_id: str | None = Field(default=None, max_length=200)
    enabled: StrictBool | None = None
    epochs: int | None = Field(default=None, ge=1, le=500)
    image_size: int | None = Field(default=None, ge=320, le=1280)
    sample_count: int | None = Field(default=None, ge=50, le=20000)


@dataclass(frozen=True)
class WorkbenchPorts:
    admin: Callable[[], Record]
    auth_load: Callable[[], Record]
    auth_save_user: Callable[[Record], Any]
    repository: Callable[[], Any]
    config: Callable[[], Record]
    accessory_save: Callable[..., Any]
    pipelines: Callable[[], list[Record]]
    pipeline_save: Callable[[Record], Any]
    pipeline_update: Callable[..., Any]
    pipeline_pause: Callable[[str], Any]
    training_records: Callable[[], list[Record]]
    resources: Callable[..., Record]
    feedback: Callable[[], FeedbackService]
    business_records: Callable[[str], Record] | None = None
    operation_lock: Callable[[], Any] | None = None
    legacy_update: Callable[..., Record] | None = None


class UserDataWorkbench:
    def __init__(self, ports: WorkbenchPorts):
        self.ports = ports

    def target(self, owner):
        actor = self.ports.admin()
        target = find_user(self.ports.auth_load(), owner)
        if target is None:
            raise HTTPException(404, '用户不存在')
        return actor, target

    def repository(self):
        repo = self.ports.repository()
        if repo is None:
            raise HTTPException(503, '用户数据管理需要 PostgreSQL')
        return repo

    def audit(self, actor, owner, action, resource, reason, result='succeeded', change=None):
        now = int(time.time())
        event = {'kind': 'admin_user_data', 'actor_user_id': actor['id'],
                 'actor_username': actor.get('username'), 'owner_user_id': owner,
                 'action': action, 'resource_id': resource, 'reason': reason,
                 'result': result, 'change': change, 'created_at': now}
        self.repository().insert_row_once('agent_operation_audit', {
            'id': f'admin_{time.time_ns():020d}_' + uuid.uuid4().hex, 'owner_user_id': owner,
            'created_at': now, 'raw_json': event})

    def events(self, owner, before=None, limit=50):
        self.ports.admin()
        repo = self.repository()
        c = repo._cursor()
        try:
            c.execute(f'''SELECT raw_json FROM {repo._qualified_table('agent_operation_audit')}
                WHERE owner_user_id=%s AND raw_json->>'kind'='admin_user_data'
                ORDER BY created_at DESC, id DESC LIMIT %s''',
                (owner, limit))
            rows = [repo._row_to_dict(c, r)['raw_json'] for r in c.fetchall()]
            repo._end_read_transaction()
            return sorted(rows[:limit], key=lambda r: r['created_at'], reverse=True)
        finally:
            c.close()

    @staticmethod
    def project(record, keys):
        return {k: record[k] for k in keys if k in record}

    def feedback(self, target):
        return FeedbackService(self.ports.feedback().ports, managed_owner=target)

    def summary(self):
        self.ports.admin()
        pipelines = self.ports.pipelines()
        training = self.ports.training_records()
        return {'counts': {u['id']: {
            'tasks': sum(t.get('owner_user_id') == u['id'] for t in pipelines),
            'training': sum(t.get('owner_user_id') == u['id'] for t in training),
        } for u in self.ports.auth_load()['users']}}

    def snapshot(self, owner):
        actor, target = self.target(owner)
        pipelines = [t for t in self.ports.pipelines() if t.get('owner_user_id') == owner]
        training = [t for t in self.ports.training_records() if t.get('owner_user_id') == owner]
        resources = self.ports.resources(user=actor, target_user_id=owner, include_samples=False)
        metadata = target.get('admin_data') or {}
        archived = set(metadata.get('archived', []))
        def projection(t, kind):
            v = self.project(t, ('id', 'job_id', 'task_id', 'name', 'label', 'status', 'stage', 'params', 'created_at', 'updated_at', 'auto_advance', 'advancing', 'pause_requested', 'job_note', 'progress', 'action', 'executor'))
            v['kind'] = kind
            v['resource_id'] = str(t.get('id') or t.get('job_id') or t.get('task_id'))
            v['archived'] = kind+':'+v['resource_id'] in archived
            return v
        task_items = [projection(t, 'pipeline') for t in pipelines] + [projection(t, 'training') for t in training]
        assets = []
        for kind, key in [('dataset', 'datasets'), ('model', 'models')]:
            for item in resources.get(key, []):
                if item.get('owner_user_id') != owner:
                    continue
                v = self.project(item, ('id', 'run_id', 'display_name', 'note', 'sample_count', 'created_at', 'task_id', 'missing_files', 'variant'))
                v['kind'] = kind
                v['resource_id'] = str(item.get('id'))
                v['archived'] = kind+':'+v['resource_id'] in archived
                assets.append(v)
        # Only opted-in feedback states; no definition refresh, cache creation or work enqueue.
        with self.ports.feedback().repo() as repo:
            states = repo.states({owner})
        photos = []
        for state in states:
            aid = state['task_id']
            if not any(t.get('id') == aid and t.get('owner_user_id') == owner for t in self.ports.feedback().ports.tasks()):
                continue
            photos.append({'task_id': aid, 'available': owner in accounts(), 'enabled': state['enabled'], 'candidate_count': len(state['samples']),
                          'pause_reason': state.get('pause_reason'), 'datasets': self.project_datasets(state),
                          'candidate_models': [self.project(m, ('job_id', 'dataset_id', 'status', 'model_id')) for m in state.get('candidate_models', [])]})
        legacy_feedback = []
        for task in self.ports.feedback().ports.tasks():
            if task.get('owner_user_id') != owner or any(p['task_id'] == task['id'] for p in photos):
                continue
            legacy = self.ports.feedback().ports.legacy_state(task['id'])
            if legacy.get('owner_user_id') != owner:
                continue
            legacy_feedback.append({'task_id': task['id'], 'enabled': bool(legacy.get('settings', {}).get('enabled')),
                                    'sample_count': sum(bool(s.get('sample_id')) and s.get('owner_user_id') in (None, '', owner) for s in legacy.get('samples', [])),
                                    'params': {'epochs': legacy.get('settings', {}).get('training_epochs', 80),
                                               'image_size': legacy.get('settings', {}).get('training_image_size', 640)}})
        # Frozen real-photo snapshots and candidates share the resource list, while their history remains visible.
        for photo in photos:
            for kind, entries in (('dataset', photo['datasets']), ('model', photo['candidate_models'])):
                for entry in entries:
                    identifier = str(entry.get('id') if kind == 'dataset' else entry.get('model_id'))
                    if not identifier or any(a['kind'] == kind and a['resource_id'] == identifier for a in assets):
                        continue
                    assets.append({'kind': kind, 'resource_id': identifier,
                                   'display_name': '实拍冻结训练集' if kind == 'dataset' else '实拍候选模型',
                                   'sample_count': entry.get('sample_count'), 'status': entry.get('status', 'frozen'),
                                   'archived': kind+':'+identifier in archived})
        for item in task_items:
            if item['kind'] != 'pipeline':
                continue
            raw = next(t for t in pipelines if t['id'] == item['resource_id'])
            aid = str(raw.get('ai_task_id') or (item['resource_id'][8:] if item['resource_id'].startswith('pipe_ai_') else ''))
            mode = next((p for p in photos if p['task_id'] == aid), None)
            old = next((p for p in legacy_feedback if p['task_id'] == aid), None)
            if mode or old:
                chosen = mode or old
                item.update(control_kind='real_photo' if mode else 'legacy', control_id=aid,
                            control_enabled=chosen['enabled'], params_locked=bool(mode),
                            control_reason=chosen.get('pause_reason'), control_available=chosen.get('available', True))
                item['status'] = 'blocked' if chosen.get('pause_reason') else 'running' if chosen['enabled'] else 'paused'
                if old:
                    item['params'] = old['params']
        business = self.ports.business_records(owner) if self.ports.business_records else {}
        return {'user': public_user(target), 'actor': public_user(actor), 'tasks': task_items,
                'resources': assets, 'real_photo': photos, 'legacy_feedback': legacy_feedback, 'references': self.references(owner), 'business': business, 'audit': self.events(owner),
                'counts': {'tasks': len(pipelines), 'training': len(training), 'images': sum(s['candidate_count'] for s in photos)+len(self.references(owner))+sum(s['sample_count'] for s in legacy_feedback), 'resources': len(assets)}}

    def references(self, owner):
        result = []
        for item in self.ports.config().get('accessories', []):
            if item.get('owner_user_id') != owner:
                continue
            disabled = set(item.get('disabled_ai_profile_reference_files') or [])
            for path in item.get('ai_profile_reference_files') or []:
                key = str(item['id'])+':'+hashlib.sha256(path.encode()).hexdigest()[:24]
                result.append({'resource_id': key, 'accessory_id': item['id'],
                               'name': item.get('name') or item['id'], 'enabled': path not in disabled,
                               'usage': 'reference'})
        return result

    def reference(self, owner, resource):
        config = self.ports.config()
        for item in config.get('accessories', []):
            if item.get('owner_user_id') != owner:
                continue
            for path in item.get('ai_profile_reference_files') or []:
                key = str(item['id'])+':'+hashlib.sha256(path.encode()).hexdigest()[:24]
                if key == resource:
                    return config, item, path
        raise HTTPException(404, '参考图不存在')

    def legacy_state(self, target, identifier):
        self.feedback(target).task(identifier)
        state = self.ports.feedback().ports.legacy_state(identifier)
        if state.get('owner_user_id') != target['id']:
            raise HTTPException(404, '旧回流状态不存在')
        return state

    def legacy_page(self, target, identifier, cursor=None, limit=24):
        state = self.legacy_state(target, identifier)
        entries = [s for s in state.get('samples', []) if s.get('sample_id') and s.get('owner_user_id') in (None, '', target['id'])]
        scope = hashlib.sha256((target['id']+':'+identifier+':legacy').encode()).hexdigest()
        anchor = entries[0]['sample_id'] if entries else None
        start = 0
        if cursor:
            try:
                value = json.loads(base64.urlsafe_b64decode(cursor.encode()))
                if set(value) != {'scope', 'anchor', 'after'} or value['scope'] != scope:
                    raise ValueError()
                ids = [s['sample_id'] for s in entries]
                anchor = value['anchor']
                anchor_index = ids.index(anchor)
                start = ids.index(value['after']) + 1
                if start <= anchor_index:
                    raise ValueError()
            except (ValueError, KeyError, TypeError):
                raise HTTPException(422, '旧样本游标已失效，请刷新') from None
        else:
            anchor_index = 0
        page = entries[start:start+limit]
        following = None
        if start+limit < len(entries):
            following = base64.urlsafe_b64encode(json.dumps({'scope': scope, 'anchor': anchor, 'after': page[-1]['sample_id']}).encode()).decode()
        return {'samples': [self.project(s, ('sample_id', 'label_status', 'created_at')) for s in page],
                'total': len(entries)-anchor_index, 'next_cursor': following}

    def project_datasets(self, state):
        return [self.project(d, ('id', 'created_at', 'sample_count', 'real_source_count')) for d in state.get('datasets', [])]

    def operate(self, owner, request):
        with self.ports.operation_lock() if self.ports.operation_lock else nullcontext():
            return self._operate(owner, request)

    def _operate(self, owner, request):
        actor, target = self.target(owner)
        reason = request.reason.strip()
        if not reason:
            raise HTTPException(422, '请填写操作原因')
        # Reserve durable intent before any business mutation; uncertain responses are never replayed.
        self.audit(actor, owner, request.action, request.resource_id, reason, 'requested')
        try:
            change = self.apply(target, request)
        except HTTPException as exc:
            self.audit(actor, owner, request.action, request.resource_id, reason, 'failed', {'status_code': exc.status_code})
            raise
        except Exception:
            self.audit(actor, owner, request.action, request.resource_id, reason, 'uncertain')
            raise HTTPException(503, '操作结果需要核查，请刷新现有状态，不要自动重试') from None
        self.audit(actor, owner, request.action, request.resource_id, reason, change=change)
        return {'status': 'updated', 'change': change}

    def apply(self, target, r):
        owner = target['id']
        if r.action == 'resume' and not target.get('active', True):
            raise HTTPException(409, '先启用账号，再显式恢复任务')
        if r.action == 'resume' and r.kind in {'real_photo', 'legacy'}:
            archived = set((target.get('admin_data') or {}).get('archived', []))
            if any(t.get('owner_user_id') == owner and 'pipeline:'+t['id'] in archived
                   and (t.get('ai_task_id') == r.resource_id or t['id'] == 'pipe_ai_'+r.resource_id)
                   for t in self.ports.pipelines()):
                raise HTTPException(409, '先恢复归档任务')
        if r.kind == 'pipeline':
            task = next((t for t in self.ports.pipelines() if t.get('id') == r.resource_id and t.get('owner_user_id') == owner), None)
            if not task:
                raise HTTPException(404, '任务不存在')
            if r.action == 'pause':
                self.ports.pipeline_pause(r.resource_id)
                return {'auto_advance': False, 'scope': 'next_checkpoint'}
            if r.action == 'resume':
                if 'pipeline:'+r.resource_id in (target.get('admin_data') or {}).get('archived', []):
                    raise HTTPException(409, '先恢复归档任务')
                self.ports.pipeline_update(r.resource_id, PipelineTaskUpdateRequest(auto_advance=True))
                return {'auto_advance': True}
            if r.action == 'params':
                params = {k: getattr(r, k) for k in ('epochs', 'image_size', 'sample_count') if getattr(r, k) is not None}
                if not params:
                    raise HTTPException(422, '没有参数修改')
                self.ports.pipeline_update(r.resource_id, PipelineTaskUpdateRequest(params=params))
                return {'params': params, 'scope': 'future_work'}
        elif r.kind == 'legacy':
            state = self.legacy_state(target, r.resource_id)
            if r.action not in {'pause', 'resume', 'params'} or self.ports.legacy_update is None:
                raise HTTPException(409, '旧回流只支持启停现有自动流程')
            with self.feedback(target).repo() as repo:
                if r.action == 'resume' and repo.get(owner, r.resource_id):
                    raise HTTPException(409, '此任务已选择实拍模式，不能恢复旧流程')
            from ..schemas.training import AutoOptimizeSettingsRequest
            if r.action == 'params':
                if state.get('settings', {}).get('enabled'):
                    raise HTTPException(409, '请先暂停旧回流，再修改后续训练参数')
                update = {k: v for k, v in {'training_epochs': r.epochs, 'training_image_size': r.image_size}.items() if v is not None}
                if not update:
                    raise HTTPException(422, '没有旧训练参数修改')
                request = AutoOptimizeSettingsRequest(**update)
            else:
                request = AutoOptimizeSettingsRequest(enabled=r.action == 'resume')
            result = self.ports.legacy_update(r.resource_id, request)
            if r.action == 'resume' and not result.get('settings', {}).get('enabled'):
                raise HTTPException(409, '旧流程保持停止；请核查现有完成模型，不自动重试')
            return {'enabled': bool(result.get('settings', {}).get('enabled')), 'scope': 'legacy_automatic'}
        elif r.kind == 'real_photo':
            if r.action not in {'pause', 'resume'}:
                raise HTTPException(409, '实拍训练配置固定，不能修改冻结参数')
            result = self.feedback(target).enable(r.resource_id, EnableRequest(enabled=r.action == 'resume'))
            return {'enabled': result['enabled'], 'scope': 'new_dispatch'}
        elif r.kind == 'reference':
            if r.action != 'image_usage' or r.enabled is None:
                raise HTTPException(422, '请指定参考用途和状态')
            config, item, path = self.reference(owner, r.resource_id)
            disabled = set(item.get('disabled_ai_profile_reference_files') or [])
            if r.enabled:
                disabled.discard(path)
            else:
                disabled.add(path)
                if not any(p not in disabled for p in item.get('ai_profile_reference_files') or []):
                    raise HTTPException(409, '每类配件至少保留一张启用参考图')
            item['disabled_ai_profile_reference_files'] = sorted(disabled)
            self.ports.accessory_save(item, config)
            return {'usage': 'reference', 'enabled': r.enabled}
        elif r.kind == 'sample':
            if r.action != 'image_usage' or r.enabled is None or not r.task_id:
                raise HTTPException(422, '请指定图片训练用途和状态')
            service = self.feedback(target)
            service.task(r.task_id, True)
            with service.repo() as repo:
                def update(state, c):
                    s = next((s for s in state['samples'] if s['sample_id'] == r.resource_id), None)
                    if not s:
                        raise HTTPException(404, '样本不存在')
                    if s.get('source_group') in state.get('split_assignments', {}):
                        raise HTTPException(409, '已冻结训练集的样本不能原地修改')
                    if state.get('round') or state.get('enabled'):
                        raise HTTPException(409, '请先暂停实拍回流再调整用途')
                    s.setdefault('usage_history', []).append({'enabled': s.get('usage_enabled', True), 'at': time.time(), 'actor_user_id': self.ports.admin()['id']})
                    s['usage_enabled'] = r.enabled
                repo.mutate(owner, r.task_id, update)
            return {'usage': 'training', 'enabled': r.enabled}
        else:
            snap = self.snapshot(owner)
            collection = snap['tasks'] if r.kind == 'training' else snap['resources']
            if not any(t['kind'] == r.kind and t['resource_id'] == r.resource_id for t in collection):
                raise HTTPException(404, '资源不存在')
        if r.action not in {'archive', 'restore'}:
            raise HTTPException(409, '此资源不支持该操作；已发出训练的远程取消不可确认')
        if r.kind == 'pipeline':
            aid = str(task.get('ai_task_id') or (r.resource_id[8:] if r.resource_id.startswith('pipe_ai_') else ''))
            if aid and self.ports.legacy_update:
                old = self.ports.feedback().ports.legacy_state(aid)
                if old.get('owner_user_id') == owner and old.get('settings', {}).get('enabled'):
                    from ..schemas.training import AutoOptimizeSettingsRequest
                    self.ports.legacy_update(aid, AutoOptimizeSettingsRequest(enabled=False))
            self.ports.pipeline_pause(r.resource_id)
            # Pause real feedback independently; restoring an archive never enables it.
            for photo in self.snapshot(owner)['real_photo']:
                if photo['task_id'] == aid and photo['enabled']:
                    self.feedback(target).enable(photo['task_id'], EnableRequest(enabled=False))
        if r.kind == 'training':
            task = next(t for t in self.ports.training_records() if str(t.get('id') or t.get('job_id') or t.get('task_id')) == r.resource_id and t.get('owner_user_id') == owner)
            if task.get('status') in {'queued', 'running'}:
                raise HTTPException(409, '活动训练不可归档，等待结算后再操作')
        fresh = find_user(self.ports.auth_load(), owner)
        meta = fresh.setdefault('admin_data', {})
        archived = set(meta.get('archived', []))
        key = r.kind+':'+r.resource_id
        if r.action == 'archive':
            archived.add(key)
        else:
            archived.discard(key)
        meta['archived'] = sorted(archived)
        if not self.ports.auth_save_user(fresh):
            raise HTTPException(503, '归档状态未保存')
        return {'archived': r.action == 'archive', 'scope': 'admin_list_only'}


def register(app: FastAPI, service: UserDataWorkbench):
    @app.get('/api/auth/users-data-summary')
    def summary():
        return service.summary()

    @app.get('/api/auth/users/{owner}/data')
    def data(owner: str):
        return service.snapshot(owner)

    @app.post('/api/auth/users/{owner}/data/operations')
    def operate(owner: str, request: DataOperation):
        return service.operate(owner, request)

    @app.get('/api/auth/users/{owner}/data/tasks/{task_id}/legacy-samples')
    def legacy_samples(owner: str, task_id: str, cursor: str | None = Query(default=None, max_length=2048), limit: int = Query(default=24, ge=1, le=100)):
        _, target = service.target(owner)
        return service.legacy_page(target, task_id, cursor, limit)

    @app.get('/api/auth/users/{owner}/data/tasks/{task_id}/legacy-samples/{sample_id}/image')
    def legacy_image(owner: str, task_id: str, sample_id: str):
        _, target = service.target(owner)
        state = service.legacy_state(target, task_id)
        if not any(s.get('sample_id') == sample_id and s.get('owner_user_id') in (None, '', owner) for s in state.get('samples', [])):
            raise HTTPException(404, '旧样本不存在')
        _, _, clean, _, _ = service.feedback(target).historical(task_id, sample_id)
        from fastapi import Response
        return Response(clean, media_type='image/png', headers={'Cache-Control': 'private, no-store'})

    @app.get('/api/auth/users/{owner}/data/references/{resource}/image')
    def reference_image(owner: str, resource: str):
        service.target(owner)
        _, _, path = service.reference(owner, resource)
        from ..training.real_photo_annotation import canonical
        from fastapi import Response
        clean, _ = canonical(service.ports.feedback().ports.read(path))
        return Response(clean, media_type='image/png', headers={'Cache-Control': 'private, no-store'})

    @app.get('/api/auth/users/{owner}/data/tasks/{task_id}/samples')
    def samples(owner: str, task_id: str, cursor: str | None = Query(default=None, max_length=2048), limit: int = Query(default=24, ge=1, le=100)):
        _, target = service.target(owner)
        return service.feedback(target).sample_page(task_id, cursor=cursor, limit=limit)

    @app.get('/api/auth/users/{owner}/data/tasks/{task_id}/samples/{sample_id}/image')
    def image(owner: str, task_id: str, sample_id: str):
        _, target = service.target(owner)
        return service.feedback(target).image(task_id, sample_id)

    @app.get('/api/auth/users/{owner}/data/tasks/{task_id}/samples/{sample_id}/versions')
    def versions(owner: str, task_id: str, sample_id: str):
        _, target = service.target(owner)
        return service.feedback(target).versions(task_id, sample_id)
