"""Actual assembled application against a disposable database; no native startup."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import os, tempfile, uuid, json
import psycopg
from psycopg import sql
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
        print('PASS actual PostgreSQL application: admin/owner isolation, readonly business projections, account lifecycle, password redaction, current-account guard, empty job queues, durable audit')
    finally:
        if owned:owned.lifetime.close(10)
        control.execute(sql.SQL('DROP DATABASE IF EXISTS {} WITH (FORCE)').format(sql.Identifier(name)))
        control.close()

if __name__=='__main__':main()
