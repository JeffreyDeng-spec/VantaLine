"""Owner-scoped website API. Agent writes are exposed only by the worker's task socket."""
from __future__ import annotations
import json
import os
import re
from fastapi import File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal
from ..storage.codex_comparisons import CodexComparisonsRepository
from ..storage.agent_operations import OperationConflict, OperationDenied
from .contracts import MAX_BYTES, digest, box
from .media import MediaStore

PREFIX = '/api/text-compare-codex'


def enabled_owners():
    return {x.strip() for x in os.environ.get('VANTALINE_CODEX_COMPARE_ACCOUNTS', '').split(',') if x.strip()}


def configured():
    return bool(os.environ.get('VANTALINE_CODEX_COMPARE_MODEL', '').strip())


def public(task, detail=True):
    if task.get('report_version') == 'label-batch-v3':
        from .batch_contracts import public_batch
        return public_batch(task)
    fields = ('id', 'status', 'created_at', 'updated_at', 'started_at', 'finished_at', 'parent_id',
              'model', 'reasoning_effort', 'runner_version', 'session_id', 'usage', 'sequence', 'error', 'finalized', 'report_version', 'skill_version', 'skill_sha256', 'tool_version')
    result = {k: task[k] for k in fields if k in task}
    result['inputs'] = task['inputs']
    result['summary'] = task['summary']
    result['counts'] = {state: sum(x['status'] == state for x in task.get('checks', task['items']).values()) for state in ('pending', 'running', 'match', 'difference', 'uncertain', 'not_applicable')}
    if task.get('report_version') == 'label-v2':
        result['progress'] = {'total': len(task['checks']), 'settled': sum(c['status'] not in {'pending', 'running'} for c in task['checks'].values()), 'elements': len(task['elements'])}
        if detail:
            result.update({key: list(task[key].values()) for key in ('elements', 'checks', 'issues', 'decodes')})
    if detail:
        result.update(items=list(task['items'].values()), artifacts=list(task['artifacts'].values()), reviews=task['reviews'])
    return result


class Retry(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: str = Field(pattern=r'^[A-Za-z0-9_.-]{8,128}$')


class Review(Retry):
    decision: Literal['MATCH', 'DIFFERENCES', 'REVIEW_REQUIRED']
    note: str = Field(max_length=4000)


def register(ns):
    app = ns['app']

    def context():
        ns['require_permission']('inspection')
        owner = ns['_text_v2_owner']()[0]
        repository = ns['runtime_postgres_repository_or_none']()
        if repository is None:
            raise HTTPException(503, 'Codex Beta 需要 PostgreSQL')
        return owner, CodexComparisonsRepository(repository), MediaStore(ns['DATA_DIR'] / 'codex_comparisons' / 'media')

    def enabled(owner):
        if owner not in enabled_owners():
            raise HTTPException(403, '此账号尚未启用 Codex Beta')
        if not configured():
            raise HTTPException(503, 'Codex Beta 模型尚未固定配置')

    def owned(repo, owner, identifier):
        value = repo.get(owner, identifier)
        if not value:
            raise HTTPException(404, '任务不存在')
        return value

    def call(fn):
        try:
            return fn()
        except KeyError as exc:
            raise HTTPException(404, '任务或标签不存在') from exc
        except OperationConflict as exc:
            raise HTTPException(409, str(exc)) from exc
        except OperationDenied as exc:
            raise HTTPException(403, str(exc)) from exc
        except (ValueError, OSError) as exc:
            raise HTTPException(422, str(exc)[:300] if isinstance(exc, ValueError) else '输入或证据文件无法读取') from exc

    from .batch_api import register as register_batches
    register_batches(ns, context, enabled, owned, call)

    @app.get(PREFIX + '/capabilities')
    def capabilities():
        ns['require_permission']('inspection')
        owner = ns['_text_v2_owner']()[0]
        return {'enabled': owner in enabled_owners() and configured(), 'model': os.environ.get('VANTALINE_CODEX_COMPARE_MODEL', ''), 'timeout_seconds': 600, 'concurrency': 1}

    @app.post(PREFIX + '/tasks')
    async def create(captured_file: UploadFile = File(...), standard_asset_id: str = Form(...),
                     request_id: str = Form(...), expected_revision: str = Form(...), reference_region: str = Form('[0,0,1,1]')):
        captured = await captured_file.read(MAX_BYTES + 1)
        def submit():
            owner, repo, media = context()
            enabled(owner)
            if not re.fullmatch(r'[A-Za-z0-9_.-]{8,128}', request_id):
                raise HTTPException(422, 'Invalid request_id')
            asset = ns['_text_v2_owned']('assets', standard_asset_id, owner)
            standard = ns['_text_v2_owned']('standards', str((asset or {}).get('standard_id', '')), owner)
            snapshot = next((x for x in (standard or {}).get('confirmed_assets', []) if x.get('id') == standard_asset_id), None)
            if not asset or not standard or standard.get('status') != 'confirmed' or standard.get('standard_type') != 'label' or not snapshot:
                raise HTTPException(404, '请选择已确认的标签标准')
            if standard.get('current_revision_id') != expected_revision:
                raise HTTPException(409, '标准版本已更新，请重新选择')
            reference = ns['_text_v2_asset_bytes']({**asset, 'sha256': snapshot['sha256']}, owner)
            if digest(reference) != snapshot['sha256']:
                raise HTTPException(409, '标准原图校验失败')
            if len(reference_region) > 200:
                raise ValueError('Invalid reference region')
            region = box(json.loads(reference_region))
            if region is None:
                raise ValueError('Select one label region')
            if asset.get('category') in {'packaging', 'manual', 'document', 'product'}:
                raise HTTPException(422, '仅支持标签，请选择标签素材')
            inputs = {'reference_region': region, 'standard_id': standard['id'], 'standard_asset_id': standard_asset_id,
                      'standard_name': standard['name'], 'standard_revision_id': expected_revision,
                      'standard_revision_number': standard.get('revision_number', 0),
                      'reference': media.image(owner, reference), 'actual': media.image(owner, captured)}
            return public(repo.create(owner, request_id, inputs, report_version='label-v2'))
        import asyncio
        return await asyncio.to_thread(lambda: call(submit))

    @app.get(PREFIX + '/tasks')
    def tasks(before: str = Query('', max_length=100)):
        owner, repo, _ = context()
        rows = repo.list(owner, before, 31)
        return {'items': [public(x, False) for x in rows[:30]], 'next_cursor': rows[29]['id'] if len(rows) > 30 else None}

    @app.get(PREFIX + '/tasks/{identifier}')
    def get(identifier: str):
        owner, repo, _ = context()
        return public(owned(repo, owner, identifier))

    @app.get(PREFIX + '/tasks/{identifier}/events')
    def events(identifier: str, after: int = Query(0, ge=0)):
        owner, repo, _ = context()
        owned(repo, owner, identifier)
        return {'items': repo.events(owner, identifier, after)}

    @app.post(PREFIX + '/tasks/{identifier}/cancel')
    def cancel(identifier: str):
        owner, repo, _ = context()
        owned(repo, owner, identifier)
        return public(repo.cancel(owner, identifier))

    @app.post(PREFIX + '/tasks/{identifier}/retry')
    def retry(identifier: str, body: Retry):
        owner, repo, _ = context()
        enabled(owner)
        task = owned(repo, owner, identifier)
        if task.get('report_version') == 'label-batch-v3':
            raise HTTPException(409, '请使用批次重跑接口')
        from .contracts import TERMINAL
        if task['status'] not in TERMINAL:
            raise HTTPException(409, '请等待或取消当前任务')
        return call(lambda: public(repo.create(owner, body.request_id, task['inputs'], parent_id=identifier, report_version=task.get('report_version'))))

    @app.post(PREFIX + '/tasks/{identifier}/review')
    def review(identifier: str, body: Review):
        owner, repo, _ = context()
        owned(repo, owner, identifier)
        return call(lambda: public(repo.review(owner, identifier, {'decision': body.decision, 'note': body.note}, body.request_id)))

    @app.get(PREFIX + '/tasks/{identifier}/media/{sha}')
    def image(identifier: str, sha: str):
        owner, repo, media = context()
        task = owned(repo, owner, identifier)
        if task.get('report_version') == 'label-batch-v3':
            from .batch_contracts import media_hashes
            allowed = media_hashes(task)
        else:
            allowed = {x[k] for x in [task['inputs']['reference'], task['inputs']['actual'], *task['artifacts'].values()] for k in ('original', 'image', 'preview')}
        if sha not in allowed:
            raise HTTPException(404, '证据不存在')
        data = call(lambda: media.read(owner, sha))
        mime = 'image/png' if data.startswith(b'\x89PNG') else 'image/jpeg' if data.startswith(b'\xff\xd8') else 'application/octet-stream'
        return Response(data, media_type=mime, headers={'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff'})
