"""Actual assembled application against a disposable database; no native startup."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import os, tempfile, uuid, json
import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
from psycopg.conninfo import make_conninfo
from fastapi.testclient import TestClient
from smoke_application_factory import environment
from local_inspection_service.runtime.application import create_application
from local_inspection_service.storage.postgres_schema import postgres_ddl


def main():
    dsn=os.environ.get('ADMIN_USER_TEST_DATABASE_URL')
    if not dsn:raise RuntimeError('An explicit disposable PostgreSQL test connection is required')
    name='admin_data_'+uuid.uuid4().hex
    control=psycopg.connect(dsn,autocommit=True)
    owned=None
    try:
        control.execute(sql.SQL("CREATE DATABASE {} WITH TEMPLATE template0 ENCODING 'UTF8' LC_COLLATE 'C' LC_CTYPE 'C'").format(sql.Identifier(name)))
        connection=make_conninfo(dsn,dbname=name)
        with psycopg.connect(connection) as c:c.execute(postgres_ddl())
        with tempfile.TemporaryDirectory(prefix='admin-user-app-') as tmp:
            env=environment(Path(tmp));env.update(VANTALINE_DATA_STORE='postgres',DATABASE_URL=connection)
            owned=create_application(env)
            client=TestClient(owned.app,base_url='https://testserver')
            password='isolated-fixture-password'
            result=client.post('/api/auth/bootstrap',json={'username':'admin','password':password})
            assert result.status_code==200,result.text
            actor=result.json()['user']['id']
            result=client.post('/api/auth/users',json={'username':'owner','password':password,'reason':'isolated acceptance'})
            assert result.status_code==200,result.text
            owner=result.json()['user']['id']
            result=client.get(f'/api/auth/users/{owner}/data')
            assert result.status_code==200,result.text
            payload=result.json()
            assert payload['actor']['id']==actor and payload['user']['id']==owner
            assert payload['business']['text_inspection_records']==[]
            assert payload['counts']=={'tasks':0,'training':0,'images':0,'resources':0}
            assert payload['audit'] and all(password not in json.dumps(e) for e in payload['audit'])
            # Synthetic evidence only; reads must not mutate PLC state or enqueue work.
            with psycopg.connect(connection) as c:
                c.execute("CREATE TABLE vantaline.plc_diagnostic_events(owner_user_id text,event_id text,station_id text,received_at bigint,step text,result text,code text,payload_json jsonb)")
                for sid, creator in [('own-station',owner),('shared-station',actor)]:
                    c.execute("INSERT INTO vantaline.plc_workstations VALUES (%s,%s,%s,'enabled',1,true,%s,1,1,%s)", (sid,'secret-token-'+sid,sid,creator,Jsonb({'secret':'must-not-return'})))
                for sid, account, session in [('own-station',owner,'private-session'),('shared-station',actor,'foreign-session')]:
                    c.execute("INSERT INTO vantaline.plc_workstation_leases VALUES (%s,%s,'active',1,%s,'model','private-client','fixture',1,1,2,%s)",(sid,session,account,Jsonb({'secret':'must-not-return'})))
                dispatches=[('owned',{'owner_user_id':owner},'shared-station','old-session'),('foreign',{'owner_user_id':actor},'own-station','private-session'),('legacy',{},'own-station','private-session'),('unattributed',{},'own-station','old-session')]
                for rid,raw,sid,session in dispatches:
                    c.execute("INSERT INTO vantaline.plc_web_serial_dispatches VALUES (%s,%s,%s,%s,1,1,'uncertain',true,0,1,1,%s)",(rid,sid,rid,session,Jsonb({**raw,'frames':['secret-frame'],'source_path':'private/path'})))
                c.execute("INSERT INTO vantaline.plc_diagnostic_events VALUES (%s,'diag','shared-station',1234567,'open','failed','serial_open_failed',%s)",(owner,Jsonb({'secret':'must-not-return','duration_ms':12})))
                for i in range(101):
                    rid=f'record-{i:03d}'
                    c.execute("INSERT INTO vantaline.text_inspection_records VALUES (%s,%s,'standard',%s,'done','MATCH','MATCH','hash',%s,%s,%s)",(rid,owner,rid,i+1,i+1,Jsonb({'title':rid,'secret':'must-not-return','source_path':'private/path'})))
                c.execute("INSERT INTO vantaline.text_inspection_records VALUES ('foreign-record',%s,'standard','foreign-record','done','MATCH','MATCH','hash',1000,1000,%s)",(actor,Jsonb({'title':'foreign'})))
                before=c.execute("SELECT jsonb_agg(to_jsonb(d) ORDER BY id) FROM vantaline.plc_web_serial_dispatches d").fetchone()[0]
                lease_before=c.execute("SELECT jsonb_agg(to_jsonb(l) ORDER BY station_id) FROM vantaline.plc_workstation_leases l").fetchone()[0]
            path=f'/api/auth/users/{owner}/data/records'
            def page(category, **query):
                response=client.get(path,params={'category':category,**query})
                assert response.status_code==200,response.text
                assert all(secret not in response.text for secret in ['must-not-return','secret-frame','private-session','private-client','private/path','secret-token'])
                return response.json()
            first=page('text_inspection_records')
            assert first['total']==101 and len(first['items'])==24
            assert first['items'][0]['id']=='record-100'
            with psycopg.connect(connection) as c:
                c.execute("INSERT INTO vantaline.text_inspection_records VALUES ('new-record',%s,'standard','new-record','done','MATCH','MATCH','hash',2000,2000,%s)",(owner,Jsonb({'title':'new'})))
            ids=[r['id'] for r in first['items']]; cursor=first['next_cursor']
            while cursor:
                result=page('text_inspection_records',cursor=cursor)
                assert result['total']==102
                ids.extend(r['id'] for r in result['items']); cursor=result['next_cursor']
            assert len(ids)==101 and len(set(ids))==101 and 'new-record' not in ids
            assert page('text_inspection_records')['items'][0]['id']=='new-record'
            assert client.get(path,params={'category':'connections','cursor':first['next_cursor']}).status_code==422
            assert client.get(f'/api/auth/users/{actor}/data/records',params={'category':'text_inspection_records','cursor':first['next_cursor']}).status_code==422
            assert client.get(path,params={'category':'bad'}).status_code==422
            assert client.get(path,params={'category':'stations','limit':101}).status_code==422
            assert client.get('/api/auth/users/missing/data/records',params={'category':'stations'}).status_code==404
            leases=page('connections')['items'];assert len(leases)==1 and leases[0]['station_id']=='own-station' and leases[0]['status']=='expired'
            assert {r['id'] for r in page('stations')['items']}=={'own-station','shared-station'}
            executed=page('plc_executions')['items'];assert {r['id'] for r in executed}=={'owned','legacy'}
            assert all(r['status']=='uncertain' for r in executed)
            diag=page('diagnostics')['items'];assert len(diag)==1 and diag[0]['created_at']==1234.567 and diag[0]['code']=='serial_open_failed'
            for category in ['incoming_text_inspections','data_analysis_records','label_inspection_objects','codex_comparison_tasks','text_inspection_standards']:
                assert page(category)['total']==0
            with psycopg.connect(connection) as c:
                assert c.execute("SELECT jsonb_agg(to_jsonb(d) ORDER BY id) FROM vantaline.plc_web_serial_dispatches d").fetchone()[0]==before
                assert c.execute("SELECT jsonb_agg(to_jsonb(l) ORDER BY station_id) FROM vantaline.plc_workstation_leases l").fetchone()[0]==lease_before
                c.execute("UPDATE vantaline.plc_workstation_leases SET owner_user_id=%s,session_id='replacement',lease_epoch=2 WHERE station_id='own-station'",(actor,))
            assert {r['id'] for r in page('plc_executions')['items']}=={'owned'}
            assert page('connections')['total']==0
            result=client.patch(f'/api/auth/users/{owner}',json={'active':False,'reason':'pause acceptance'})
            assert result.status_code==200,result.text
            result=client.patch(f'/api/auth/users/{owner}',json={'active':True,'reason':'restore acceptance'})
            assert result.status_code==200,result.text
            result=client.post(f'/api/auth/users/{owner}/password',json={'password':'second-fixture-password','revoke_sessions':True,'reason':'reset acceptance'})
            assert result.status_code==200,result.text
            result=client.delete(f'/api/auth/users/{actor}')
            assert result.status_code==400,result.text
            outsider=TestClient(owned.app,base_url='https://testserver')
            assert outsider.post('/api/auth/login',json={'username':'owner','password':'second-fixture-password'}).status_code==200
            assert outsider.get(f'/api/auth/users/{owner}/data').status_code==403
            assert outsider.get('/api/auth/users-data-summary').status_code==403
            assert outsider.get(path,params={'category':'connections'}).status_code==403
            assert outsider.get('/api/auth/users/missing/data/records',params={'category':'connections'}).status_code==403
            assert outsider.post(f'/api/auth/users/{owner}/data/operations',json={'action':'pause','kind':'pipeline','resource_id':'missing','reason':'unauthorized'}).status_code==403
            assert client.get('/api/auth/users-data-summary').status_code==200
            with psycopg.connect(connection) as c:
                assert c.execute('SELECT count(*) FROM vantaline.real_photo_jobs').fetchone()[0]==0
                assert c.execute('SELECT count(*) FROM vantaline.training_tasks').fetchone()[0]==0
                rows=c.execute("SELECT raw_json FROM vantaline.agent_operation_audit WHERE raw_json->>'kind'='admin_user_data'").fetchall()
                assert len(rows)>=8
                assert all('fixture-password' not in json.dumps(r[0]) for r in rows)
            client.close();outsider.close()
            assert owned.lifetime.close(10)
            owned=None
        print('PASS actual PostgreSQL application: admin/owner isolation, readonly PLC/business evidence, 101-record stable pagination, shared stations and historical attribution, account lifecycle, password redaction, current-account guard, empty job queues, durable audit')
    finally:
        if owned:owned.lifetime.close(10)
        control.execute(sql.SQL('DROP DATABASE IF EXISTS {} WITH (FORCE)').format(sql.Identifier(name)))
        control.close()

if __name__=='__main__':main()
