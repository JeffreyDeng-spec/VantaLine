"""Account-owned, persisted, at-most-once document classification and tombstones."""
import copy
import os
import threading
import time
import uuid
from fastapi import HTTPException
from . import document_label_classifier as classifier


class DocumentJobs:
    def __init__(self, server):
        self.s = server
        self.slots = threading.BoundedSemaphore(2)

    def mutate(self, identity, owner, change):
        repo = self.s.runtime_postgres_repository_or_none()
        if repo is not None:
            return repo.mutate_text_document(identity, owner, change)
        with self.s._incoming_text_store_lock:
            standard = self.s._text_v2_owned('standards', identity, owner)
            if not standard:
                raise HTTPException(404, '标准不存在')
            assets = [a for a in self.s._text_v2_load('assets') if a.get('standard_id') == identity and a.get('owner_user_id') == owner]
            before_standard, before_assets = copy.deepcopy(standard), copy.deepcopy(assets)
            result = change(standard, assets)
            if standard != before_standard:
                self.s._text_v2_save('standards', standard)
            for previous, asset in zip(before_assets, assets):
                if previous != asset:
                    self.s._text_v2_save('assets', asset)
            return result

    def settings(self, owner):
        allowed = set(os.getenv('VANTALINE_DOCUMENT_CLASSIFICATION_ACCOUNTS', '').split(','))
        if owner not in allowed or not self.s.TEXT_INSPECTION_EXTERNAL_VLM_ENABLED:
            raise HTTPException(409, '该账户尚未启用文档图片分类或图片外发授权')
        settings = self.s.ai_detection_settings()
        if settings.get('provider') != 'qwen' or not settings.get('api_key') or not settings.get('base_url', '').startswith('https://'):
            raise HTTPException(409, '文档分类需要已配置的千问视觉模型和密钥')
        return settings

    def start(self, identity, owner):
        # No classification or paid retry on GET, duplicate POST or document reimport.
        settings = self.settings(owner)
        if not self.slots.acquire(blocking=False):
            raise HTTPException(429, '图片分类繁忙，请稍后点击识别标签')
        run_id = uuid.uuid4().hex
        def claim(standard, assets):
            if standard.get('status') != 'draft' or standard.get('standard_type') != 'label':
                raise HTTPException(409, '仅未启用的标签订单可以识别')
            if standard.get('classification', {}).get('id'):
                return False
            standard['classification'] = dict(id=run_id, state='processing', done=0, total=len(assets),
                heartbeat=time.time(), prompt_version=classifier.VERSION, model=settings['model'])
            standard['updated_at'] = int(time.time())
            for asset in assets:
                if asset.get('classification_source') != 'human':
                    asset['status'] = 'needs_confirmation'
                    asset['classification_reason'] = '等待视觉模型识别'
            return True
        try:
            claimed = self.mutate(identity, owner, claim)
        except Exception:
            self.slots.release()
            raise
        if not claimed:
            self.slots.release()
            return
        thread = threading.Thread(target=self.run, args=(identity, owner, run_id, settings), daemon=True)
        try:
            thread.start()
        except Exception:
            self.slots.release()
            raise

    def mark_unavailable(self, identity, owner, reason):
        def change(standard, assets):
            if not standard.get('classification', {}).get('id'):
                standard['classification'] = dict(state='unavailable', reason=reason)
        self.mutate(identity, owner, change)

    def refresh(self, identity, owner):
        def change(standard, assets):
            job = standard.get('classification', {})
            if job.get('state') == 'processing' and time.time() - job.get('heartbeat', 0) > 150:
                job.update(state='interrupted', reason='识别进程中断或结果不明；不会自动重复调用，请人工确认剩余图片')
        self.mutate(identity, owner, change)

    def run(self, identity, owner, run_id, settings):
        cache = {}
        try:
            assets = [a for a in self.s._text_v2_load('assets') if a.get('standard_id') == identity and a.get('owner_user_id') == owner]
            for asset in sorted(assets, key=lambda a: a.get('ordinal', 0)):
                def claim(standard, current):
                    job = standard.get('classification', {})
                    if standard.get('status') != 'draft' or job.get('id') != run_id or job.get('state') != 'processing':
                        return None
                    target = next(a for a in current if a['id'] == asset['id'])
                    job['heartbeat'] = time.time()
                    if target.get('classification_source') == 'human' or target.get('classification_attempt'):
                        job['done'] += 1
                        return False
                    # Commit the attempt before reading media or making any external call.
                    target['classification_attempt'] = dict(id=run_id, state='attempting', started_at=time.time())
                    return copy.deepcopy(target)
                target = self.mutate(identity, owner, claim)
                if target is None:
                    break
                if target is False:
                    continue
                digest = target.get('sha256')
                if digest and digest in cache:
                    value, diagnostic = copy.deepcopy(cache[digest])
                    diagnostic['reused_source_sha256'] = digest
                else:
                    try:
                        data = self.s._text_v2_asset_bytes(target, owner)
                        preview = classifier.prepare_image(data)
                        value, diagnostic = classifier.classify_once(preview, target.get('context', ''), settings, self.s.ai_urlopen)
                    except Exception as exc:
                        value = dict(category='uncertain', status='needs_confirmation', reason='图片无法安全预览，需人工确认')
                        diagnostic = dict(error_type=type(exc).__name__, external_call=False)
                    if digest:
                        cache[digest] = copy.deepcopy((value, diagnostic))
                def finish(standard, current):
                    job = standard.get('classification', {})
                    item = next(a for a in current if a['id'] == target['id'])
                    attempt = item.get('classification_attempt', {})
                    if attempt.get('id') != run_id:
                        return
                    attempt.update(state='finished', result=value, diagnostics=diagnostic, finished_at=time.time())
                    if standard.get('status') != 'draft' or job.get('state') != 'processing':
                        return
                    if item.get('classification_source') != 'human':
                        item.update(status=value['status'], category=value['category'], classification_source='vlm',
                            classification_reason=value['reason'], updated_at=int(time.time()))
                    job['done'] += 1
                    job['heartbeat'] = time.time()
                self.mutate(identity, owner, finish)
            def complete(standard, assets):
                job = standard.get('classification', {})
                if job.get('id') == run_id and job.get('state') == 'processing':
                    job.update(state='completed', finished_at=time.time())
            self.mutate(identity, owner, complete)
        except Exception as exc:
            # Persisted attempts remain non-replayable. Polling marks stale jobs interrupted.
            print({'event': 'document_classification_failure', 'standard_id': identity, 'error_type': type(exc).__name__}, flush=True)
        finally:
            self.s.clear_thread_runtime_repository_selection()
            self.slots.release()

    def delete(self, identity, owner):
        def change(standard, assets):
            if standard.get('standard_type') != 'label':
                raise HTTPException(409, '此入口仅支持删除标签订单')
            if standard.get('status') != 'deleted':
                standard.update(status_before_delete=standard['status'], status='deleted', deleted_at=int(time.time()), deleted_by=owner)
                if standard.get('classification', {}).get('state') == 'processing':
                    standard['classification']['state'] = 'cancelled'
            return copy.deepcopy(standard)
        return self.mutate(identity, owner, change)


def register(namespace):
    class Services:
        def __getattr__(self, name):
            return namespace[name]
    s = Services()
    jobs = DocumentJobs(s)
    @s.app.post('/api/text-inspection/standards/{standard_id}/classify')
    def classify(standard_id: str):
        s.require_permission('inspection', detail='没有文字检验权限')
        owner, _ = s._text_v2_owner()
        if not s._text_v2_owned('standards', standard_id, owner):
            raise HTTPException(404, '标准不存在')
        jobs.start(standard_id, owner)
        return s._text_v2_public(s._text_v2_owned('standards', standard_id, owner))
    @s.app.delete('/api/text-inspection/standards/{standard_id}')
    def delete(standard_id: str):
        s.require_permission('inspection', detail='没有文字检验权限')
        owner, _ = s._text_v2_owner()
        if not s._text_v2_owned('standards', standard_id, owner):
            raise HTTPException(404, '标准不存在')
        return s._text_v2_public(jobs.delete(standard_id, owner))
    return jobs
