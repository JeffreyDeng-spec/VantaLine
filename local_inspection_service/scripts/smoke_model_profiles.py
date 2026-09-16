"""Actual PostgreSQL registry, immutable snapshots, atomic admin writes and secret safety."""
import asyncio
import json
import os
import sys
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import psycopg
from psycopg import sql
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from local_inspection_service.model_profiles.api import register
from local_inspection_service.model_profiles.service import Service, DEFAULTS
from local_inspection_service.model_profiles.snapshots import pinned, public_record
from local_inspection_service.model_profiles.audit import metered
from local_inspection_service.model_profiles.dependencies import ProfileDependencies, ProfileApiDependencies
from local_inspection_service.storage.postgres_schema import postgres_ddl
from local_inspection_service.storage.postgres_runtime_repository import PostgresRuntimeRepository


def main():
    dsn=os.environ['VANTALINE_POSTGRES_DSN']
    schema='profiles_'+uuid.uuid4().hex
    secrets={}
    connections=[]
    admin=ContextVar('admin',default=False)
    app=FastAPI()
    def runtime():
        connection=psycopg.connect(dsn)
        connections.append(connection)
        return PostgresRuntimeRepository(connection,'test',schema)
    def require_admin():
        if not admin.get(): raise HTTPException(403,'admin only')
        return {'id':'test-admin'}
    @app.middleware('http')
    async def identity(request,call_next):
        token=admin.set(request.headers.get('x-admin')=='true')
        try: return await call_next(request)
        finally: admin.reset(token)
    dependencies=ProfileDependencies(runtime_repository=runtime,
        write_secret=lambda k,v:secrets.update({k:v}), read_secret=lambda k:secrets.get(k,''),
        mask_secret=lambda k:'****'+k[-4:], validate_model=lambda v:None,
        validate_base_url=lambda v:None, legacy_sources=lambda:[])
    api_dependencies=ProfileApiDependencies(require_admin=require_admin,
        cost_from_usage=lambda m,u:(0,0,False), cursor_api_url=lambda b,p:b+p,
        cursor_auth_headers=lambda key:{}, model_options_from_items=lambda items,**kw:items)
    ai=dict(provider='gemini',model='gemini-2.5-flash',api_key='legacy-key-A',base_url=DEFAULTS['gemini'][1],enabled=True,
            api_key_candidates=[dict(provider='qwen',label='unused qwen',key='unused-key-B')])
    agent=dict(provider='openai_compatible',model='agent-model',api_key='disabled-agent-key',base_url='https://example.com/v1',enabled=False)
    source=lambda self:[('legacy AI',ai,['pipeline','manual','accessory','training_vision','document']),('disabled agent',agent,['training_assistant'])]
    with psycopg.connect(dsn,autocommit=True) as control, patch.object(Service,'legacy_sources',source):
        control.execute(postgres_ddl(schema))
        try:
            service=Service(dependencies)
            register(app, service, api_dependencies)
            client=TestClient(app)
            base='/api/admin/model-profiles'
            def req(method,path='',body=None,status=200,member=False):
                response=client.request(method,base+path,json=body,headers={} if member else {'x-admin':'true'})
                assert response.status_code==status,(method,path,response.status_code,response.text)
                return response.json()
            for method,path,body in [('GET','',None),('POST','',dict(name='bad',provider='qwen',model='qwen3-vl-flash',api_key='key')),('PUT','/bindings',dict(revision=1,bindings={})),('POST','/missing/test',None),('GET','/usage',None)]:
                req(method,path,body,403,True)
            initial=req('GET')
            assert not service.resolve('training_assistant')['enabled']
            assert len(initial['profiles'])==3 and any(p['pending'] for p in initial['profiles'])
            old=service.snapshot()
            assert old['pipeline']['model']=='gemini-2.5-flash' and old['pipeline']['prompt_version'].startswith('source-sha256:')
            old_id=old['pipeline']['id']
            legacy=next(p for p in initial['profiles'] if p['id']==old_id)
            body={k:legacy[k] for k in ('name','provider','model','base_url','timeout_seconds','enabled','version')}
            body.update(name='renamed legacy',api_key='rotated-key-A')
            req('PUT','/'+old_id,body)
            with service.scope(old): assert service.resolve('pipeline')['api_key']=='legacy-key-A'
            assert service.resolve('pipeline')['api_key']=='rotated-key-A'
            body=dict(name='doubao one',provider='doubao',model='doubao-seed-evolving',api_key='doubao-key-one')
            one=req('POST','',body)
            two=req('POST','',{**body,'name':'doubao two','api_key':'doubao-key-two'})
            assert one['id']!=two['id']
            before=req('GET')
            assert before['bindings']['label']=='' # Creating does not bind.
            selected={**before['bindings'],'label':one['id'],'pipeline':two['id']}
            saved=req('PUT','/bindings',dict(revision=before['revision'],bindings=selected))
            req('PUT','/bindings',dict(revision=before['revision'],bindings=selected),409)
            assert service.resolve('label')['api_key']=='doubao-key-one'
            assert service.resolve('pipeline')['api_key']=='doubao-key-two'
            assert service.resolve('manual')['api_key']=='rotated-key-A'
            req('PUT','/'+one['id'],{**body,'enabled':False,'version':1},422)
            text=req('POST','',dict(name='text',provider='openai_compatible',model='text-only',base_url='https://example.com/v1',api_key='text-key'))
            current=req('GET')
            req('PUT','/bindings',dict(revision=current['revision'],bindings={'label':text['id']}),422)
            req('PUT','/bindings',dict(revision=current['revision'],bindings={'unknown':''}),422)
            req('PUT','/bindings',dict(revision=current['revision'],bindings={'label':'missing'}),422)
            # Two administrators racing with one revision: exactly one commits.
            barrier=threading.Barrier(2)
            def race():
                barrier.wait()
                try: service.save_bindings(current['revision'],{'accessory':one['id']},'admin');return 'ok'
                except ValueError:return 'conflict'
            with ThreadPoolExecutor(2) as pool: assert sorted(pool.map(lambda _:race(),range(2)))==['conflict','ok']
            service.record_call(service.resolve('label'),321,False,dict(total_tokens=12,secret='never-store'))
            usage=req('GET','/usage')['items'][0]
            assert usage['cost'] is None and not usage['priced'] and usage['usage']=={'total_tokens':12}
            rows=control.execute(sql.SQL('SELECT raw_json FROM {}.model_profile_objects').format(sql.Identifier(schema))).fetchall()
            serialized=json.dumps(rows)
            assert all(key not in serialized for key in ['legacy-key-A','rotated-key-A','unused-key-B','doubao-key-one','disabled-agent-key'])
            assert 'secret_ref' not in json.dumps(req('GET'))
            # Process restart resolves persisted bindings; old tasks retain migration snapshot.
            restarted=Service(dependencies)
            assert restarted.resolve('pipeline')['api_key']=='doubao-key-two'
            assert restarted.snapshot_for_record({'created_at':1})==old
            @pinned(lambda: service)
            async def video():
                first=service.resolve('pipeline')['api_key']
                state=service.public()
                service.save_bindings(state['revision'],{'pipeline':one['id']},'admin')
                await asyncio.sleep(0)
                return first,service.resolve('pipeline')['api_key']
            assert asyncio.run(video())==('doubao-key-two','doubao-key-two')
            assert service.resolve('pipeline')['api_key']=='doubao-key-one'
            assert public_record({'nested':{'profile_snapshot':old,'value':1},'model_profiles':old})=={'nested':{'value':1}}
            class Provider:
                settings=service.resolve('label')
                @metered(lambda: service)
                def generate_json(self): return {'valid':True}
            with patch.object(service,'record_call',side_effect=RuntimeError('db unavailable')):
                assert Provider().generate_json()=={'valid':True}
            print('PASS model profiles: PostgreSQL migration, permissions, atomic bindings, immutable versions, async snapshots, usage and secret projections')
        finally:
            for connection in connections: connection.close()
            control.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))

if __name__=='__main__':main()
