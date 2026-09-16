"""Profiles contain metadata only; immutable secret references live in the existing secret store."""
import copy
import json
import hashlib
from functools import lru_cache
from pathlib import Path
import os
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from urllib.parse import urlsplit
from fastapi import HTTPException
from .repository import Repository, Conflict

PURPOSES = {
    'label': ('标签对比', 'vision', False),
    'manual': ('说明书检验', 'vision', False),
    'pipeline': ('流水线配件检测', 'vision', False),
    'image': ('图片生成', 'image', False),
    'training_assistant': ('训练助手', 'text', True),
    'accessory': ('配件建档', 'vision', True),
    'training_vision': ('训练视觉辅助', 'vision', True),
    'document': ('文档准备与旧版文字检验', 'qwen_vision', True),
    'ocr': ('专用 OCR', 'ocr', True),
}
DEFAULTS = {
    'doubao': ('doubao-seed-evolving', 'https://ark.cn-beijing.volces.com/api/v3/chat/completions'),
    'qwen': ('qwen3-vl-flash', 'https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions'),
    'gemini': ('gemini-2.5-flash', 'https://generativelanguage.googleapis.com/v1beta'),
    'agnes': ('agnes-image-2.0-flash', 'https://apihub.agnes-ai.com/v1/images/generations'),
    'qwen_image': ('qwen-image-2.0-pro', 'https://dashscope-intl.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation'),
    'openai_compatible': ('', ''),
    'cursor': ('', 'https://api.cursor.com'),
}
_scope = ContextVar('model_profile_snapshot', default=None)
_UNSET = object()


def capabilities(provider, model):
    m = model.lower()
    if provider in {'agnes', 'qwen_image'} or ('image' in m and provider == 'gemini'):
        return ['image']
    if m == 'qwen-vl-ocr-2025-11-20' and provider == 'qwen':
        return ['ocr']
    if provider == 'qwen':
        return ['text', 'vision', 'qwen_vision'] if ('vl' in m or any(x in m for x in ('qwen3.5', 'qwen3.6', 'qwen3.7'))) else ['text']
    if provider == 'doubao' and ('seed' in m or 'vision' in m):
        return ['text', 'vision']
    if provider == 'gemini':
        return ['text', 'vision']
    return ['text']


def validate_binding(purpose, profile):
    if purpose not in PURPOSES:
        raise ValueError('未知配置用途')
    if profile is None:
        return
    if not profile.get('enabled') or profile.get('pending'):
        raise ValueError('配置未启用或尚未完善')
    if PURPOSES[purpose][1] not in profile['capabilities']:
        raise ValueError('模型与此用途不兼容')
    if profile['provider'] == 'cursor' and purpose != 'training_assistant':
        raise ValueError('Cursor 仅用于保留的训练助手连接')


@lru_cache(maxsize=1)
def prompt_source_version():
    """Fingerprint shipped prompt-producing code; task inputs remain in their records."""
    root = Path(__file__).resolve().parents[1]
    digest = hashlib.sha256()
    for name in ('server.py','label_inspection/prompts.json','document_label_classifier.py',
                 'standard_preparation.py','qwen_evidence_jobs.py','qwen_ocr_evidence.py'):
        digest.update(name.encode())
        digest.update((root/name).read_bytes())
    return 'source-sha256:' + digest.hexdigest()


def profile_reference(profile):
    return {k:profile[k] for k in ('id','version','provider','model')} | {'prompt_version':prompt_source_version()}


class Service:
    def __init__(self, ns):
        self.ns = ns

    def repository(self):
        runtime = self.ns['runtime_postgres_repository_or_none']()
        if runtime is None:
            raise HTTPException(503, '模型配置需要 PostgreSQL 存储')
        return Repository(runtime)

    def secret(self, value):
        # All profile writers hold the same DB advisory lock, across processes.
        ref = 'VANTALINE_PROFILE_' + uuid.uuid4().hex.upper()
        self.ns['set_local_secret_env'](ref, value)
        return ref

    def legacy_sources(self):
        ai = self.ns['_legacy_ai_detection_settings']()
        image = self.ns['_legacy_image_generation_settings']()
        agent = self.ns['_legacy_load_agent_config']()
        local = self.ns['load_ai_local_config']()
        ai['api_key_candidates'] = self.ns['normalize_ai_key_items'](local)
        image['api_key_candidates'] = self.ns['normalize_image_key_items'](local, image['provider'])
        agent['api_key_candidates'] = self.ns['normalize_agent_key_items'](agent)
        key = agent.get('api_key', '')
        sources = [('原 AI 配置', ai, ['pipeline','manual','accessory','training_vision','document']),
                   ('原图片生成配置', image, ['image']),
                   ('原训练助手', {**agent, 'api_key': key}, ['training_assistant'])]
        from ..label_inspection.model import legacy_settings, MODEL, URL
        label = legacy_settings()
        sources.append(('原标签配置', dict(provider='doubao',model=MODEL,base_url=URL,api_key=label['key'],timeout_seconds=180), ['label']))
        if ai.get('provider') == 'qwen' and ai.get('api_key'):
            sources.append(('原专用 OCR', {**ai, 'model':'qwen-vl-ocr-2025-11-20'}, ['ocr']))
        return sources

    def initialize(self):
        repo = self.repository()
        with repo.transaction() as c:
            if repo.state(c):
                return
            state = dict(revision=1, heads={}, bindings={p: '' for p in PURPOSES}, migrated_at=time.time())
            for name, settings, purposes in self.legacy_sources():
                if settings.get('api_key'):
                    profile = self.make_profile(dict(name=name, provider=settings.get('provider','qwen'),
                        model=settings.get('model',''), base_url=settings.get('base_url',''),
                        timeout_seconds=settings.get('timeout_seconds',30), enabled=settings.get('enabled', True)),
                        settings['api_key'], migrated=True)
                    # Preserve non-secret operational options needed by existing adapters.
                    profile['operational'] = {k:settings[k] for k in ('auto_local_proxy_enabled','auto_advance_default','connection_status','connection_message','last_tested_at','model_options') if k in settings}
                    if settings.get('proxy_url_raw'):
                        profile['proxy_ref'] = self.secret(settings['proxy_url_raw'])
                    repo.put(c, f"{profile['id']}:1", 'profile', profile)
                    state['heads'][profile['id']] = 1
                    for purpose in purposes:
                        # Preserve pre-existing provider bindings on migration, including gated legacy paths.
                        state['bindings'][purpose] = profile['id']
                # Previously unused keys have no reliable model association: preserve as pending.
                for candidate in settings.get('api_key_candidates', []):
                    if not candidate.get('key') or candidate['key'] == settings.get('api_key'):
                        continue
                    pending = self.make_profile(dict(name=candidate.get('label') or '待完善旧 Key', provider=candidate.get('provider') or settings['provider'],model='',base_url=DEFAULTS.get(candidate.get('provider'), ('',''))[1] or settings['base_url'],timeout_seconds=30,enabled=False), candidate['key'], migrated=True)
                    pending['pending'] = True
                    repo.put(c, f"{pending['id']}:1", 'profile', pending)
                    state['heads'][pending['id']] = 1
            state['initial_snapshot'] = {p:profile_reference(repo.get(c, f"{i}:{state['heads'][i]}")) if i else None for p,i in state['bindings'].items()}
            repo.put(c, 'state', 'state', state)
            repo.event(c, 'migration', 'initialized', {'profiles':list(state['heads'])})

    def make_profile(self, data, key, previous=None, migrated=False):
        provider = data['provider']
        if provider not in DEFAULTS:
            raise ValueError('不支持的服务商')
        model = str(data.get('model','')).strip()
        if not migrated and not str(data['name']).strip():
            raise ValueError('请输入配置名称')
        if not migrated and not model:
            raise ValueError('请输入模型 ID')
        if model:
            self.ns['validate_ai_model'](model)
        endpoint = str(data.get('base_url') or DEFAULTS[provider][1]).strip().rstrip('/')
        if not migrated:
            url = urlsplit(endpoint)
            if url.scheme != 'https' or not url.hostname or url.username or url.password or url.query or url.fragment:
                raise ValueError('接口地址须为不含凭据或查询参数的 HTTPS 地址')
            self.ns['validate_ai_base_url'](endpoint)
        timeout = float(data.get('timeout_seconds', 30))
        if not 1 <= timeout <= 600:
            raise ValueError('超时必须为 1–600 秒')
        if not key and previous is None:
            raise ValueError('请输入 API Key')
        return dict(id=previous['id'] if previous else 'mp_'+uuid.uuid4().hex,
                    version=previous['version']+1 if previous else 1,
                    name=str(data['name']).strip(), provider=provider, model=model,
                    base_url=endpoint, timeout_seconds=timeout, enabled=bool(data.get('enabled',True)),
                    capabilities=capabilities(provider,model), pending=not bool(model),
                    secret_ref=self.secret(key) if key else previous['secret_ref'],
                    masked_key=self.ns['mask_secret'](key) if key else previous['masked_key'],
                    proxy_ref=previous.get('proxy_ref','') if previous else '',
                    created_at=time.time(), operational=copy.deepcopy(previous.get('operational',{})) if previous else {})

    def snapshot(self):
        self.initialize()
        repo = self.repository()
        with repo.transaction() as c:
            state = repo.state(c)
            return {p: profile_reference(repo.get(c, f"{identity}:{state['heads'][identity]}")) if identity else None for p,identity in state['bindings'].items()}

    def snapshot_for_record(self, record):
        self.initialize()
        repo = self.repository()
        with repo.transaction() as c:
            state = repo.state(c)
            created = record.get('created_at')
            if created and float(created) < state['migrated_at']:
                return copy.deepcopy(state['initial_snapshot'])
        return self.snapshot()

    @contextmanager
    def scope(self, snapshot=None):
        token = _scope.set(snapshot if snapshot is not None else self.snapshot())
        try:
            yield
        finally:
            _scope.reset(token)

    def resolve(self, purpose, reference=_UNSET):
        if reference is _UNSET:
            bindings = _scope.get()
            if bindings is None:
                bindings = self.snapshot()
            reference = bindings.get(purpose)
        if not reference:
            return dict(enabled=False, configured=False, provider='', model='', api_key='', base_url='', timeout_seconds=30, status='unconfigured', message='请管理员配置此功能的模型', profile_purpose=purpose)
        repo = self.repository()
        with repo.transaction() as c:
            p = repo.get(c, f"{reference['id']}:{reference['version']}")
            tested = repo.get(c, f"test:{reference['id']}:{reference['version']}")
        if not p:
            raise HTTPException(503, '任务引用的模型配置版本不存在')
        key = self.ns['local_secret_env_value'](p['secret_ref'])
        return {**p.get('operational',{}), **({'connection_status':'connected' if tested['ok'] else 'failed', 'last_tested_at':tested['at'], **({'model_options':tested['model_options']} if tested.get('model_options') else {})} if tested else {}), 'proxy_url_raw': self.ns['local_secret_env_value'](p['proxy_ref']) if p.get('proxy_ref') else '', **{k:p[k] for k in ('provider','model','base_url','timeout_seconds')},
                'enabled':bool(key) and p.get('enabled',True), 'configured':bool(key) and p.get('enabled',True), 'api_key':key,
                'profile_id':p['id'], 'profile_version':p['version'], 'profile_purpose':purpose,
                'profile_name':p['name'], 'active_key_id':p['id'], 'api_key_candidates':[],
                'key_present':bool(key), 'api_key_present':bool(key), 'api_keys':[],
                'provider_label':p['provider'], 'masked_key':p['masked_key'],
                'key_source':'profile', 'key_source_name':p['name'],
                'status':'ready' if key else 'missing_api_key', 'message':'已配置' if key else '配置密钥不可用'}

    def public(self):
        self.initialize()
        repo = self.repository()
        with repo.transaction() as c:
            state = repo.state(c)
            profiles = []
            for p in repo.versions(c,state):
                public = {k:p[k] for k in ('id','version','name','provider','model','base_url','timeout_seconds','enabled','capabilities','pending','masked_key')}
                public['used_by'] = [k for k,v in state['bindings'].items() if v == p['id']]
                tested = repo.get(c, f"test:{p['id']}:{p['version']}")
                public['connection_status'] = ('connected' if tested['ok'] else 'failed') if tested else p.get('operational',{}).get('connection_status','not_tested')
                profiles.append(public)
            return dict(revision=state['revision'],bindings=state['bindings'],profiles=profiles,
                purposes=[dict(id=k,label=v[0],capability=v[1],advanced=v[2]) for k,v in PURPOSES.items()],
                providers=[dict(id=k,model=v[0],base_url=v[1]) for k,v in DEFAULTS.items()])

    def save_profile(self, data, actor, identity=None):
        self.initialize()
        repo = self.repository()
        with repo.transaction() as c:
            state = repo.state(c)
            previous = None
            if identity:
                if identity not in state['heads']:
                    raise KeyError(identity)
                previous = repo.get(c, f"{identity}:{state['heads'][identity]}")
                if data.get('version') != previous['version']:
                    raise Conflict('配置版本已更新，请刷新')
            key = str(data.get('api_key') or '').strip()
            profile = self.make_profile(data,key,previous)
            if previous and (key or any(profile[k] != previous[k] for k in ('provider','model','base_url'))):
                for field in ('connection_status','connection_message','last_tested_at','model_options'):
                    profile['operational'].pop(field,None)
            bound = [purpose for purpose,selected in state['bindings'].items() if selected == identity]
            for purpose in bound:
                if previous and profile['enabled'] and (profile['provider'],profile['model']) == (previous['provider'],previous['model']):
                    continue  # Preserve existing migrated bindings on metadata/key edits.
                validate_binding(purpose,profile)
            repo.put(c,f"{profile['id']}:{profile['version']}",'profile',profile)
            state['heads'][profile['id']] = profile['version']
            state['revision'] += 1
            repo.put(c,'state','state',state,replace=True)
            repo.event(c,actor,'profile',dict(id=profile['id'],version=profile['version']))
            return dict(id=profile['id'],version=profile['version'])

    def save_bindings(self, revision, bindings, actor):
        self.initialize()
        repo = self.repository()
        # Reject unknown IDs, not accidentally treat them as an unbound purpose.
        with repo.transaction() as c:
            state = repo.state(c)
            if any(v and v not in state['heads'] for v in bindings.values()):
                raise ValueError('配置不存在')
        return repo.save_bindings(revision,bindings,actor,validate_binding)

    def record_call(self, settings, elapsed_ms, ok, usage):
        if not settings.get('profile_id'):
            return
        repo = self.repository()
        safe_usage = {k:v for k,v in (usage or {}).items() if k in {'prompt_tokens','completion_tokens','total_tokens','input_tokens','output_tokens','promptTokenCount','candidatesTokenCount','totalTokenCount','cachedContentTokenCount','thoughtsTokenCount'} and isinstance(v,(int,float)) and not isinstance(v,bool)}
        for field in ('candidatesTokensDetails','outputTokensDetails','promptTokensDetails'):
            details = (usage or {}).get(field)
            if isinstance(details,list):
                safe_usage[field] = [dict(modality=d['modality'],tokenCount=d['tokenCount']) for d in details if isinstance(d,dict) and d.get('modality') in {'TEXT','IMAGE','AUDIO','VIDEO'} and type(d.get('tokenCount')) is int and d['tokenCount']>=0]
        with repo.transaction() as c:
            repo.put(c,uuid.uuid4().hex,'call',dict(profile_id=settings['profile_id'],version=settings['profile_version'],purpose=settings['profile_purpose'],model=settings['model'],provider=settings['provider'],elapsed_ms=elapsed_ms,ok=ok,usage=safe_usage,at=time.time()))

    def calls(self):
        repo = self.repository()
        with repo.transaction() as c:
            c.execute(f"SELECT raw_json FROM {repo.table} WHERE kind='call' ORDER BY created_at DESC,id DESC LIMIT 500")
            rows = [repo.runtime._row_to_dict(c,r)['raw_json'] for r in c.fetchall()]
        return [json.loads(r) if isinstance(r,str) else r for r in rows]
