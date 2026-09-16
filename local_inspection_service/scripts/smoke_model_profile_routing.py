"""Actual provider adapters and retired HTTP/automation role boundaries, no network."""
import io
import json
import os
import sys
import tempfile
import urllib.error
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
os.environ['LOCAL_INSPECTION_ROOT']=tempfile.mkdtemp(prefix='model-routing-')
(Path(os.environ['LOCAL_INSPECTION_ROOT'])/'local_inspection_service'/'static').mkdir(parents=True)
os.environ['VANTALINE_DATA_STORE']='json'
from local_inspection_service import server as s
from local_inspection_service.scripts import testclient_threadpool_shim as shim
from local_inspection_service.scripts.model_profiles_fixture import install
install(s)
shim.install()

def main():
    client=shim.SmokeASGIClient(s.app,base_url='https://testserver')
    assert client.post('/api/auth/bootstrap',json={'username':'admin','password':'fixture-password'}).status_code==200
    assert client.post('/api/auth/users',json={'username':'member','password':'fixture-password','role':'user','permissions':['inspection','ai_config','agent_config','system_settings']}).status_code==200
    member=shim.SmokeASGIClient(s.app,base_url='https://testserver')
    assert member.post('/api/auth/login',json={'username':'member','password':'fixture-password'}).status_code==200
    for method,path in [('GET','/api/ai/config'),('POST','/api/ai/config'),('DELETE','/api/ai/config/key'),('GET','/api/agent/config'),('POST','/api/agent/config'),('POST','/api/agent/config/test'),('GET','/api/admin/model-profiles'),('POST','/api/admin/model-profiles')]:
        response=member.request(method,path,json={})
        assert response.status_code==403,(method,path,response.status_code,response.text)
    assert client.request('DELETE','/api/ai/config/key').status_code==409
    for permission in ('ai_config','agent_config','system_settings'):
        assert not s.user_has_permission({'id':'member','role':'user','permissions':[permission]},permission)
    with patch.object(s,'current_auth_user',return_value={'id':'member','role':'user'}):
        public=s.public_agent_config({**s.DEFAULT_AGENT_CONFIG,'api_key':'private-key','model':'fixture','base_url':'https://fixture.invalid'})
        assert not {'api_keys','api_key_masked','api_key_env','active_key_id','base_url'} & public.keys()
    for provider,model in [('qwen','qwen3-vl-flash'),('doubao','doubao-seed-evolving'),('gemini','gemini-2.5-flash')]:
        settings=dict(configured=True,enabled=True,provider=provider,model=model,base_url='https://fixture.invalid/v1',api_key='fixture-secret-never-log',timeout_seconds=5,profile_id='object',profile_version=1,profile_purpose='pipeline')
        calls=[]
        value={'result':'fixture'}
        response={'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':json.dumps(value)}]}}]} if provider=='gemini' else {'choices':[{'finish_reason':'stop','message':{'content':json.dumps(value)}}]}
        def transport(request,*args,**kwargs):
            calls.append(json.loads(request.data))
            return io.BytesIO(json.dumps(response).encode())
        with patch.object(s,'ai_urlopen',transport):
            output,_=s.ai_provider_from_settings(settings).generate_json('fixture',[{'type':'text','text':'fixture'}])
        assert output==value and len(calls)==1
        if provider=='qwen': assert calls[0]['enable_thinking'] is False
        if provider=='doubao': assert calls[0]['thinking']=={'type':'disabled'}
        if provider=='gemini': response['candidates'][0]['finishReason']='MAX_TOKENS'
        else: response['choices'][0]['finish_reason']='length'
        with patch.object(s,'ai_urlopen',transport):
            try:s.ai_provider_from_settings(settings).generate_json('fixture',[])
            except s.AiProviderError:pass
            else:raise AssertionError('truncated completion accepted')
        def denied(*args,**kwargs):raise urllib.error.HTTPError('https://fixture.invalid',401,'denied',{},io.BytesIO(b'invalid key fixture-secret-never-log'))
        with patch.object(s,'ai_urlopen',denied):
            try:s.ai_provider_from_settings(settings).generate_json('fixture',[])
            except s.AiProviderAuthError as exc:assert settings['api_key'] not in str(exc)
            else:raise AssertionError('bad key accepted')
    print('PASS model profile real provider routing, truncated/error rejection, secret redaction and old HTTP/admin permissions')
if __name__=='__main__':main()
