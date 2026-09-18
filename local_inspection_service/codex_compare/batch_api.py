"""Persistent upload drafts and frozen single-session batches. No OCR/Qwen calls."""
import asyncio
import copy
from pathlib import Path
import time
from fastapi import FastAPI, File, Form, HTTPException, UploadFile, Query
from collections.abc import Callable
from .dependencies import (ComparisonAccess, StandardLibrary, ComparisonMedia, DocumentImports, Context, OwnedTask, MapErrors)
from ..schemas.codex_compare import Retry, Review, SelectOrder, Rename, Rerun
from .http_contract import PREFIX
from .contracts import MAX_BYTES, TERMINAL, digest, box
from .batch_contracts import VERSION, MAX_LABELS, MAX_REFERENCES, new_label, public_batch, public_label, matching, reference
from ..storage.agent_operations import OperationConflict


def register(app: FastAPI, access: ComparisonAccess, standards: StandardLibrary,
             media_dependencies: ComparisonMedia, documents: DocumentImports, context: Context,
             enabled: Callable[[str], None], owned: OwnedTask, call: MapErrors):

    def batch(repo, owner, bid):
        value = owned(repo, owner, bid)
        if value.get('report_version') != VERSION:
            raise HTTPException(404, '批次不存在')
        return value

    def frozen_order(owner, standard_id, media):
        standard = standards.owned('standards', standard_id, owner)
        if not standard or standard.get('status') == 'deleted' or standard.get('standard_type') != 'label':
            raise HTTPException(404, '标签订单不存在')
        assets = [a for a in standards.load('assets') if a.get('standard_id') == standard_id and a.get('owner_user_id') == owner]
        if not assets or len(assets) > MAX_REFERENCES:
            raise HTTPException(422, '订单图片为空或超过 500 张')
        refs, hashes = {}, {}
        for a in sorted(assets, key=lambda a: a.get('ordinal', 0)):
            data = media_dependencies.asset_bytes(a, owner)
            sha = digest(data)
            source = {k: a[k] for k in ('id', 'ordinal', 'source_part', 'paragraph_index', 'context') if k in a}
            if sha in hashes:
                refs[hashes[sha]]['sources'].append(source)
                continue
            aid = a['id']
            hashes[sha] = aid
            info = {'id': aid, 'name': f"标准图 {a.get('ordinal', len(refs)+1)}", 'sources': [source], 'original': media.put(owner, data)}
            try:
                info['media'] = media.image(owner, data)
            except (ValueError, OSError):
                info.update(media=None, error='图片无法预览或超过图像安全限制，需要人工处理')
            refs[aid] = info
        return {'standard_id': standard_id, 'standard_name': standard['name'],
                'standard_revision_id': standard.get('current_revision_id', ''),
                'standard_revision_number': standard.get('revision_number', 0),
                'source_sha256': standard.get('source_sha256', ''), 'references': refs,
                'order_fingerprint': digest(sorted((a['id'], a.get('sha256'), a.get('updated_at')) for a in assets))}

    def set_order(t, inputs):
        t['inputs'] = inputs
        t['references'] = {}
        for e in t['labels'].values():
            e['match'] = {'status': 'pending', 'reason': '', 'reference_id': None, 'candidate_ids': []}
        t['import_state'] = 'ready'
        t.pop('import_active_key', None)

    @app.post(PREFIX+'/batches')
    def create(body: Retry):
        owner, repo, _ = context(); enabled(owner)
        return call(lambda: public_batch(repo.create(owner, body.request_id, {'references': {}}, report_version=VERSION)))

    @app.get(PREFIX+'/batches')
    def listing(before: str = Query('', max_length=100)):
        owner, repo, _ = context()
        with repo.tx() as c:
            c.execute(f"SELECT raw_json FROM {repo.table('codex_comparison_tasks')} WHERE owner_user_id=%s AND raw_json->>'report_version'=%s AND (%s='' OR id<%s) ORDER BY id DESC LIMIT 31", (owner, VERSION, before, before))
            rows = repo.rows(c)
        # Batch summaries contain per-label progress, not raw check/evidence collections.
        return {'items': [public_batch(t) for t in rows[:30]], 'next_cursor': rows[29]['id'] if len(rows)>30 else None}

    @app.get(PREFIX+'/batches/{bid}')
    def get(bid: str):
        owner, repo, _ = context()
        return public_batch(batch(repo, owner, bid))

    @app.get(PREFIX+'/batches/{bid}/labels/{lid}')
    def get_label(bid: str, lid: str):
        owner, repo, _ = context()
        return call(lambda: public_label(batch(repo, owner, bid), lid, True))

    @app.post(PREFIX+'/batches/{bid}/order')
    async def select_order(bid: str, body: SelectOrder):
        def work():
            owner, repo, media = context(); enabled(owner)
            batch(repo, owner, bid)
            inputs = frozen_order(owner, body.standard_id, media)
            return public_batch(repo.edit_draft(owner, bid, body.request_id, 'order', inputs, lambda t: set_order(t, inputs)))
        return await asyncio.to_thread(lambda: call(work))

    @app.post(PREFIX+'/batches/{bid}/name')
    def rename(bid: str, body: Rename):
        owner, repo, _ = context(); enabled(owner)
        def change(t):
            if not body.name.strip():
                raise ValueError('名称不能为空')
            t['inputs']['standard_name'] = body.name.strip()
        return call(lambda: public_batch(repo.edit_draft(owner, bid, body.request_id, 'name', {'name': body.name}, change)))

    @app.post(PREFIX+'/batches/{bid}/document')
    async def document(bid: str, file: UploadFile = File(...), request_id: str = Form(..., min_length=8, max_length=128, pattern=r'^[A-Za-z0-9_.-]+$')):
        # Authorize before reading/parsing potentially large documents.
        owner, repo, _ = context(); enabled(owner)
        batch(repo, owner, bid)
        data = await file.read(100*1024*1024+1)
        filename = Path(file.filename or '订单.docx').name
        def work():
            owner, repo, media = context(); enabled(owner)
            metadata = {'sha256': digest(data), 'filename': filename}
            current = repo.edit_draft(owner, bid, request_id+'-begin', 'import_started', metadata, lambda t: t.update(import_state='extracting', import_active_key=request_id))
            if current.get('import_completed_key') == request_id:
                return public_batch(current)
            try:
                if filename.lower().endswith('.docx'):
                    entries, blobs = documents.docx(data)
                    ext = '.docx'
                elif filename.lower().endswith('.doc'):
                    entries, blobs = documents.doc(data)
                    ext = '.doc'
                else:
                    raise ValueError('仅支持 DOC / DOCX')
                stdid = 'std_' + digest({'owner': owner, 'batch': bid, 'request': request_id})[:32]
                now = int(time.time())
                old = standards.owned('standards', stdid, owner)
                if not old:
                    path = media_dependencies.media_path(owner, stdid, 'source'+ext)
                    media_dependencies.write(path, data)
                    standard = {'id': stdid, 'owner_user_id': owner, 'owner_username': access.owner()[1],
                                'name': Path(filename).stem[:120] or '新订单', 'material_code': 'IMPORT-'+stdid[-12:],
                                'version_label': 'V1', 'standard_type': 'label', 'status': 'draft', 'source_sha256': digest(data),
                                'source_path': str(path), 'created_at': now, 'updated_at': now, 'asset_count': len(entries),
                                'import_source': VERSION}
                    standards.save('standards', standard, insert_only=True)
                # Deterministic IDs permit explicit import retry after interrupted persistence.
                for index, entry in enumerate(entries):
                    aid = 'ast_'+digest({'standard': stdid, 'index': index})[:32]
                    if standards.owned('assets', aid, owner):
                        continue
                    path = media_dependencies.media_path(owner, stdid, aid+'.bin')
                    media_dependencies.write(path, blobs[index])
                    standards.save('assets', {**entry, 'id': aid, 'standard_id': stdid, 'owner_user_id': owner,
                         'asset_kind': 'label_candidate', 'media_path': str(path), 'status': 'needs_confirmation',
                         'classification_source': 'unclassified', 'classification_reason': '由 Codex 批次匹配，不调用旧分类流程',
                         'created_at': now, 'updated_at': now}, insert_only=True)
                inputs = frozen_order(owner, stdid, media)
                def done(t):
                    if t.get('import_active_key') != request_id:
                        raise OperationConflict('已有更新的订单选择，旧导入结果未覆盖当前批次')
                    set_order(t, inputs)
                    t['import_completed_key'] = request_id
                return public_batch(repo.edit_draft(owner, bid, request_id, 'import_completed', metadata, done))
            except Exception:
                repo.edit_draft(owner, bid, request_id+'-failed', 'import_failed', metadata, lambda t: t.update(import_state='failed') if t.get('import_active_key') == request_id else None)
                raise
        return await asyncio.to_thread(lambda: call(work))

    @app.post(PREFIX+'/batches/{bid}/photos')
    async def upload(bid: str, file: UploadFile = File(...), request_id: str = Form(..., min_length=8, max_length=128, pattern=r'^[A-Za-z0-9_.-]+$'), allow_duplicate: bool = Form(False)):
        owner, repo, _ = context(); enabled(owner)
        batch(repo, owner, bid)
        data = await file.read(MAX_BYTES+1)
        def work():
            owner, repo, media = context(); enabled(owner)
            evidence = media.image(owner, data)
            lid = 'label_'+digest(request_id.encode())[:20]
            name = (file.filename or '实拍图片')[:200]
            def add(t):
                if len(t['labels']) >= MAX_LABELS:
                    raise ValueError('单批最多 50 张实拍图')
                if not allow_duplicate and any(e['actual']['original'] == evidence['original'] for e in t['labels'].values()):
                    raise OperationConflict('同一文件已上传；可明确选择保留为另一枚样品')
                t['labels'][lid] = new_label(lid, evidence, name)
            return public_batch(repo.edit_draft(owner, bid, request_id, 'photo_added', {'id': lid, 'name': name, 'media': evidence, 'allow_duplicate': allow_duplicate}, add))
        return await asyncio.to_thread(lambda: call(work))

    @app.post(PREFIX+'/batches/{bid}/labels/{lid}/remove')
    def remove(bid: str, lid: str, body: Retry):
        owner, repo, _ = context(); enabled(owner)
        def change(t):
            if lid not in t['labels']:
                raise ValueError('图片不存在')
            del t['labels'][lid]
        return call(lambda: public_batch(repo.edit_draft(owner, bid, body.request_id, 'photo_removed', {'id': lid}, change)))

    @app.post(PREFIX+'/batches/{bid}/submit')
    def submit(bid: str, body: Retry):
        owner, repo, _ = context(); enabled(owner)
        current = batch(repo, owner, bid)
        standard = standards.owned('standards', current['inputs'].get('standard_id', ''), owner)
        assets = [a for a in standards.load('assets') if a.get('standard_id') == current['inputs'].get('standard_id') and a.get('owner_user_id') == owner]
        # Library helpers end read transactions; never call them under the queue lock.
        order_digest = digest(sorted((a['id'], a.get('sha256'), a.get('updated_at')) for a in assets))
        def freeze(t):
            if t.get('import_state') != 'ready' or not t['labels'] or not any(r.get('media') for r in t['inputs']['references'].values()):
                raise ValueError('请完成订单导入并至少上传一张实拍图')
            if not standard or standard.get('status') == 'deleted' or t['inputs']['standard_id'] != standard['id']:
                raise OperationConflict('订单已删除，请重新选择')
            if not t.get('parent_id') and (standard.get('current_revision_id', '') != t['inputs']['standard_revision_id'] or order_digest != t['inputs']['order_fingerprint']):
                raise OperationConflict('订单已修改，请重新选择以冻结最新版本')
            t['status'] = 'queued'
            t['submitted_at'] = time.time()
        return call(lambda: public_batch(repo.edit_draft(owner, bid, body.request_id, 'queued', {}, freeze)))

    @app.post(PREFIX+'/batches/{bid}/labels/{lid}/review')
    def review(bid: str, lid: str, body: Review):
        owner, repo, _ = context()
        batch(repo, owner, bid)
        return call(lambda: public_label(repo.review_label(owner, bid, lid, {'decision': body.decision, 'note': body.note}, body.request_id), lid, True))

    @app.post(PREFIX+'/batches/{bid}/retry')
    def retry(bid: str, body: Rerun):
        owner, repo, _ = context(); enabled(owner)
        old = batch(repo, owner, bid)
        if old['status'] not in TERMINAL:
            raise HTTPException(409, '请等待或取消当前批次')
        def work():
            if len(set(body.label_ids)) != len(body.label_ids) or any(lid not in old['labels'] for lid in body.label_ids) or any(lid not in body.label_ids for lid in body.matches):
                raise ValueError('请选择当前批次的标签')
            inputs = copy.deepcopy(old['inputs'])
            inputs['actuals'] = {lid: {'name': old['labels'][lid]['name'], 'media': old['labels'][lid]['actual']} for lid in body.label_ids}
            inputs['regions'] = copy.deepcopy(old['references'])
            inputs['human_matches'] = {}
            dummy = {'inputs': inputs, 'references': inputs['regions'], 'labels': {lid: new_label(lid, a['media'], a['name']) for lid,a in inputs['actuals'].items()}}
            for lid, value in body.matches.items():
                # Human can select any frozen source image and adjust the label bounds.
                aid = value.get('asset_id')
                rid = 'human_'+lid
                reference(dummy, {'id': rid, 'asset_id': aid, 'name': '人工指定标准', 'region': box(value.get('region'))})
                inputs['human_matches'][lid] = matching(dummy, lid, {'status': 'matched', 'reference_id': rid, 'candidate_ids': [], 'reason': '人工指定对应关系；仍须完整检查'})
            task = repo.create(owner, body.request_id, inputs, parent_id=bid, report_version=VERSION)
            def ready(t):
                t['import_state'] = 'ready'
                t.pop('import_active_key', None)
                t['status'] = 'queued'
            return public_batch(repo.edit_draft(owner, task['id'], body.request_id+'-queue', 'queued', {}, ready))
        return call(work)
