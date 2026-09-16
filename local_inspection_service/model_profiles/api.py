"""Admin-only settings API. Credentials never appear in public profiles or task snapshots."""
import time
from urllib.parse import urlsplit
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from .repository import Conflict
from .service import Service
from .dependencies import ProfileApiDependencies


class ProfileInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1,max_length=100)
    provider: str = Field(max_length=50)
    model: str = Field(max_length=200)
    base_url: str = Field(default='',max_length=1000)
    api_key: str = Field(default='',max_length=8192)
    timeout_seconds: float = Field(default=30,ge=1,le=600)
    enabled: bool = True
    version: int | None = None


class BindingInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    revision: int = Field(ge=1)
    bindings: dict[str,str]


def register(app, service: Service, dependencies: ProfileApiDependencies):
    prefix = '/api/admin/model-profiles'

    def admin():
        return dependencies.require_admin()

    def run(fn):
        try:
            return fn()
        except Conflict as e:
            raise HTTPException(409,str(e)) from None
        except KeyError:
            raise HTTPException(404,'配置不存在') from None
        except ValueError as e:
            raise HTTPException(422,str(e)) from None

    @app.get(prefix)
    def read_profiles():
        admin()
        return run(service.public)

    @app.post(prefix)
    def create_profile(request: ProfileInput):
        user = admin()
        return run(lambda:service.save_profile(request.model_dump(),user['id']))

    @app.put(prefix+'/bindings')
    def save_bindings(request: BindingInput):
        user = admin()
        run(lambda:service.save_bindings(request.revision,request.bindings,user['id']))
        return service.public()

    @app.get(prefix+'/usage')
    def profile_usage():
        admin()
        rows = service.calls()
        for row in rows:
            cost, tokens, priced = dependencies.cost_from_usage(row['model'], row['usage'])
            priced = priced and bool(row['usage'])
            row['priced'] = priced
            row['cost'] = cost if priced else None
        return {'items':rows,'limit':500}

    @app.get(prefix+'/engines')
    def engines():
        admin()
        import os
        assistant = service.resolve('training_assistant')
        return {'items':[
            {'name':'标签检查 Beta','engine':'Codex 专用引擎','status':'已配置' if os.getenv('VANTALINE_CODEX_COMPARE_MODEL') else '未配置模型','path':'/text-compare-codex'},
            {'name':'本地 OCR / YOLO','engine':'本地模型','status':'模型与任务状态见模型库','path':'/training-library?tab=models'},
            {'name':'训练执行器','engine':'现有训练工作流','status':'任务状态见任务流水线','path':'/pipeline'},
            {'name':'训练助手','engine':assistant.get('model') or '规则逻辑','status':assistant.get('connection_status') or ('已配置，未验证连接' if assistant.get('configured') else '规则逻辑'), 'path':'/pipeline'},
        ]}

    @app.put(prefix+'/{identity}')
    def edit_profile(identity:str,request:ProfileInput):
        user = admin()
        return run(lambda:service.save_profile(request.model_dump(),user['id'],identity))

    @app.post(prefix+'/{identity}/test')
    def test_profile(identity:str):
        user = admin()
        data = service.public()
        profile = next((p for p in data['profiles'] if p['id']==identity),None)
        if not profile:
            raise HTTPException(404,'配置不存在')
        settings = service.resolve('connection_test',{'id':identity,'version':profile['version']})
        start = time.monotonic()
        ok = False
        # Metadata-only request: never generate an image or silently change a model.
        import requests
        provider = settings['provider']
        base = settings['base_url'].rstrip('/')
        host = urlsplit(base)
        headers = {'Authorization':'Bearer '+settings['api_key']}
        if provider == 'gemini':
            url = base+'/models/'+settings['model']
            headers = {'x-goog-api-key':settings['api_key']}
        elif provider == 'qwen_image':
            url = host.scheme+'://'+host.netloc+'/compatible-mode/v1/models'
        elif provider == 'cursor':
            url = dependencies.cursor_api_url(base, '/v1/models')
            headers = dependencies.cursor_auth_headers(settings['api_key'])
        elif '/chat/completions' in base:
            url = base.rsplit('/chat/completions',1)[0]+'/models'
        elif '/images/generations' in base:
            url = base.rsplit('/images/generations',1)[0]+'/models'
        else:
            url = base+'/models'
        model_options = []
        proxy = settings.get('proxy_url_raw')
        try:
            with requests.get(url,proxies={'http':proxy,'https':proxy} if proxy else None,headers=headers,timeout=10,allow_redirects=False,stream=True) as response:
                ok = response.status_code == 200
                if ok and provider == 'cursor':
                    raw = bytearray()
                    for chunk in response.iter_content(16384):
                        raw.extend(chunk)
                        if len(raw) > 1024*1024:
                            raise ValueError('Model list too large')
                    import json
                    payload = json.loads(raw)
                    model_options = dependencies.model_options_from_items(payload.get('items', payload.get('models', payload.get('data', []))), prepend=[{'id':'auto','label':'auto · Cursor 默认模型'}])
                message = '凭据与服务可连接；未验证实际生成或检测效果' if ok else f'连接验证未通过（HTTP {response.status_code}）；服务可能不支持模型列表接口'
        except Exception:
            ok = False
            message = '连接验证失败，请检查接口、凭据和网络'
        repo = service.repository()
        with repo.transaction() as c:
            repo.put(c,f"test:{identity}:{profile['version']}",'test',dict(ok=ok,at=time.time(),model_options=model_options),replace=True)
            repo.event(c,user['id'],'connection_test',dict(id=identity,version=profile['version'],ok=ok,elapsed_ms=round((time.monotonic()-start)*1000)))
        return {'ok':ok,'message':message}
    return service
