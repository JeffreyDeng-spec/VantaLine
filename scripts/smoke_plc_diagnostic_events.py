"""Diagnostic HTTP/real PostgreSQL isolation, boundedness and expiry. No PLC I/O."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import httpx
import psycopg
from fastapi import FastAPI,HTTPException
from local_inspection_service.plc.diagnostic_events_api import register_diagnostic_events
from local_inspection_service.storage.plc_diagnostic_repository import PlcDiagnosticRepository
from local_inspection_service.schemas.plc_diagnostics import PlcDiagnosticEvent
from local_inspection_service.auth.route_permissions import route_allowed_permissions
ROOT=Path(__file__).resolve().parents[1]
DSN=os.environ['VANTALINE_POSTGRES_DSN']
# The command must target a disposable database, never a production schema.
with psycopg.connect(DSN,autocommit=True) as c:
    assert c.info.dbname.startswith('plc_diag_test_'),'requires disposable plc_diag_test_ database'
    c.execute('CREATE SCHEMA vantaline')
    c.execute('CREATE TABLE vantaline.feature_migrations(version TEXT PRIMARY KEY,applied_at BIGINT,metadata_json JSONB)')
    c.execute('CREATE TABLE vantaline.users(id TEXT PRIMARY KEY,username TEXT)')
    c.execute("INSERT INTO vantaline.users VALUES('a','jhc001'),('b','operator_b'),('admin','admin')")
    c.execute('CREATE TABLE vantaline.plc_workstations(id TEXT PRIMARY KEY,token_hash TEXT,config_generation BIGINT,name TEXT)')
    c.execute("INSERT INTO vantaline.plc_workstations VALUES(%s,%s,1,'line')",('station',hashlib.sha256(b'cookie-a').hexdigest()))
    c.execute('CREATE TABLE vantaline.plc_workstation_leases(station_id TEXT,state TEXT,lease_epoch BIGINT,owner_user_id TEXT,config_generation BIGINT)')
    c.execute("INSERT INTO vantaline.plc_workstation_leases VALUES('station','released',1,'a',1)")
    migration=(ROOT/'local_inspection_service/storage/migrations/2026_10_12_plc_diagnostic_events.sql').read_text()
    c.execute(migration);c.execute(migration)
    assert c.execute("SELECT count(*) FROM vantaline.feature_migrations").fetchone()[0]==1

def event(id='event',station='station'):
    return PlcDiagnosticEvent(event_id=id,attempt_id='attempt',sequence=0,station_id=station,step='read',result='failed',code='timeout',client_time_ms=int(time.time()*1000),target='D1',expected_bytes=8).model_dump()

async def test():
    user={'id':'a','username':'jhc001','role':'user','permissions':['inspection']}
    environment={'DATABASE_URL':DSN,'VANTALINE_PLC_DIAGNOSTIC_ACCOUNTS':'jhc001,operator_b'}
    store=PlcDiagnosticRepository(environment)
    app=FastAPI();register_diagnostic_events(app,environment=environment,current_user=lambda:user,repository=store)
    for path in ['/api/plc/diagnostic-events','/api/plc/diagnostic-events/config','/api/plc/diagnostic-events/batch']:
        assert route_allowed_permissions(path,'POST' if path.endswith('batch') else 'GET')==('inspection','ai_detection')
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://testserver',cookies={'vantaline_plc_workstation':'cookie-a'}) as client:
        assert (await client.get('/api/plc/diagnostic-events/config')).json()['enabled']
        for _ in range(2):assert (await client.post('/api/plc/diagnostic-events/batch',json={'events':[event()]})).status_code==200
        page=await client.get('/api/plc/diagnostic-events');items=page.json()['items'];assert len(items)==1 and items[0]['username']=='jhc001'
        assert items[0]['evidence_source']=='browser_report' and items[0]['server_lease_observation']['state']=='released'
        assert not any(k in json.dumps(items) for k in ['cookie-a','token_hash','frame_hex','response_hex','password'])
        assert (await client.post('/api/plc/diagnostic-events/batch',json={'events':[{**event('secret'),'stack':'private'}]})).status_code==422
        assert (await client.post('/api/plc/diagnostic-events/batch',json={'events':[{**event('code'),'code':'arbitrary_error'}]})).status_code==422
        assert (await client.post('/api/plc/diagnostic-events/batch',json={'events':[event('wrong','other')]})).status_code==403
        assert (await client.post('/api/plc/diagnostic-events/batch',json={'events':[event('unpaired',None)]})).status_code==200
        assert (await client.post('/api/plc/diagnostic-events/batch',content=b'x'*32769)).status_code==413
        user.update(id='b',username='operator_b')
        assert (await client.get('/api/plc/diagnostic-events')).json()['items']==[]
        assert (await client.get('/api/plc/diagnostic-events?account=a')).status_code==403
        user.update(id='admin',username='admin',role='admin')
        assert len((await client.get('/api/plc/diagnostic-events?account=jhc001')).json()['items'])==2
        user.update(id='a',username='jhc001',role='user')
        environment['VANTALINE_PLC_DIAGNOSTICS_ENABLED']='0'
        with patch.object(store,'append',side_effect=AssertionError('disabled must not open database')):
            assert (await client.post('/api/plc/diagnostic-events/batch',json={'events':[event()]})).json()['enabled'] is False
        environment['VANTALINE_PLC_DIAGNOSTICS_ENABLED']='1'
        await store.gate.acquire()
        started=time.monotonic()
        try:
            try:await store.append(user,'cookie-a',[event('busy')]);raise AssertionError('busy accepted')
            except HTTPException as e:assert e.status_code==503
        finally:store.gate.release()
        assert time.monotonic()-started<.15
        async def hung(*args,**kwargs):await asyncio.sleep(10)
        unavailable=PlcDiagnosticRepository(environment,connect=hung)
        started=time.monotonic()
        try:await unavailable.append(user,'cookie-a',[event('down')]);raise AssertionError('hung accepted')
        except HTTPException as e:assert e.status_code==503
        assert time.monotonic()-started<.15
        # SQL lock must time out on the independent diagnostic connection.
        with psycopg.connect(DSN) as blocker:
            blocker.execute('LOCK TABLE vantaline.plc_diagnostic_events IN ACCESS EXCLUSIVE MODE')
            started=time.monotonic()
            try:await store.append(user,'cookie-a',[event('locked')]);raise AssertionError('lock accepted')
            except HTTPException as e:assert e.status_code==503
            assert time.monotonic()-started<.35
            blocker.rollback()
        # Read pagination is bounded and cleanup removes only old diagnostics.
        with psycopg.connect(DSN,autocommit=True) as c:
            now=int(time.time()*1000)
            for n in range(55):
                e=event('page_'+str(n));c.execute("INSERT INTO vantaline.plc_diagnostic_events VALUES('a',%s,'attempt','station',%s,'read','failed','timeout',%s::jsonb)",(e['event_id'],now,json.dumps(e)))
            e=event('old');c.execute("INSERT INTO vantaline.plc_diagnostic_events VALUES('a','old','attempt','station',%s,'read','failed','timeout',%s::jsonb)",(now-31*86400000,json.dumps(e)))
            before=c.execute('SELECT state,lease_epoch FROM vantaline.plc_workstation_leases').fetchall()
            assert len((await client.get('/api/plc/diagnostic-events')).json()['items'])==50
            assert (await client.get('/api/plc/diagnostic-events')).json()['next_offset']==50
            assert await store.cleanup()==1
            assert c.execute('SELECT state,lease_epoch FROM vantaline.plc_workstation_leases').fetchall()==before
        for _ in range(15):response=await client.post('/api/plc/diagnostic-events/batch',json={'events':[event('limited')]})
        assert response.status_code==429
        user['permissions']=[]
        assert (await client.get('/api/plc/diagnostic-events')).status_code==403
    print('PASS diagnostic authenticated scope, privacy whitelist, dedupe, stream cap, rate, switch, independent connection/SQL timeout, pagination and additive expiry')
asyncio.run(test())
