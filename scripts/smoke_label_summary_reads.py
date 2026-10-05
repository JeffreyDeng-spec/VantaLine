"""Real PostgreSQL list-only cached-read and complete API contracts.

The baseline method is loaded from an explicitly frozen pre-reader source file.
All other API/persistence code is the same candidate; no provider or PLC is used.
"""
import ast
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import copy
import functools
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import uuid
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import psycopg
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from local_inspection_service.label_inspection import api
from local_inspection_service.label_inspection.run_summary import VERSION
from local_inspection_service.storage.label_inspection import LabelRepository
from local_inspection_service.storage.label_run_projection import LabelRunProjection
from local_inspection_service.storage.postgres_runtime_repository import PostgresRuntimeRepository
from local_inspection_service.storage.postgres_schema import postgres_ddl
from local_inspection_service.storage.schema import TABLES


@functools.lru_cache(maxsize=1)
def baseline_method():
    source=Path(__file__).resolve().parents[1]/'tests/backend_contract/label_summary_reader_baseline.py'
    data=source.read_bytes().replace(b"\r\n",b"\n")  # Git checkout line endings only.
    assert hashlib.sha256(data).hexdigest()=='4b3c1704705ac6aa85cbac613d3f6fa710134023a5d5a23f437898091ca6ddb5', 'frozen parent reader changed'
    namespace=dict(LabelRepository.list_run_payloads_for_tasks.__globals__)
    exec(compile(data,str(source),'exec'),namespace)
    return namespace['list_run_payloads_for_tasks']


class Fixture:
    def __init__(self):
        self.schema='summary_read_'+uuid.uuid4().hex[:12]
        self.connections=[];self.created=False;self.owner='alice'
        self.directory=None;self.client=None

    def raw(self):
        conn=psycopg.connect(os.environ['VANTALINE_POSTGRES_DSN'])
        self.connections.append(conn)
        conn.execute("SET lock_timeout='6000ms'");conn.execute("SET statement_timeout='8000ms'");conn.commit()
        return PostgresRuntimeRepository(conn,'<synthetic>',self.schema)

    def __enter__(self):
        try:
            self.writer=self.raw();self.reader=self.raw();self.other=self.raw()
            self.created=True
            self.writer.connection.execute(postgres_ddl(self.schema));self.writer.connection.commit()
            self.repo=LabelRepository(self.reader);self.store=LabelRunProjection(self.other)
            self.table=self.repo.table;self.cache=self.writer._qualified_table('label_run_projection')
            self.directory=tempfile.TemporaryDirectory(prefix='summary-read-')
            app=FastAPI()
            def permission(*args):
                if self.owner=='anonymous':raise HTTPException(401,'请登录')
                if self.owner=='denied':raise HTTPException(403,'没有权限')
            access=SimpleNamespace(require_permission=permission,owner=lambda:(self.owner,'test'))
            with patch.object(api.pdf_import,'register',lambda *_:None):
                api.register(app,access,SimpleNamespace(repository=lambda:self.reader),
                    SimpleNamespace(data_directory=lambda:Path(self.directory.name)),lambda:None,lambda:{'enabled':True})
            self.endpoint=next(r.endpoint for r in app.routes if getattr(r,'path',None)==api.PREFIX+'/tasks' and 'GET' in r.methods)
            self.client=TestClient(app,raise_server_exceptions=False)
            return self
        except BaseException:
            self.__exit__(*sys.exc_info());raise

    def __exit__(self,kind,*rest):
        errors=[]
        for item in [self.client,*self.connections,self.directory]:
            if item is not None:
                try:
                    (item.cleanup if isinstance(item,tempfile.TemporaryDirectory) else item.close)()
                except Exception as exc:errors.append(exc)
        if self.created:
            try:
                with psycopg.connect(os.environ['VANTALINE_POSTGRES_DSN']) as conn:
                    conn.execute(f'DROP SCHEMA IF EXISTS "{self.schema}" CASCADE')
            except Exception as exc:errors.append(exc)
        if errors and kind is None:raise errors[0]

    def insert(self,table,items):
        schema=next(t for t in TABLES if t.name==table)
        # Every required column has a synthetic fixture value; raw JSON itself is exact.
        with self.writer.connection.cursor() as cursor:
            with cursor.copy(f"COPY {self.writer._qualified_table(table)} ({','.join(schema.columns)}) FROM STDIN") as stream:
                for item in items:
                    row=[]
                    for col in schema.columns:
                        if col=='raw_json':row.append(json.dumps(item,ensure_ascii=False))
                        elif col in ('created_at','updated_at','ordinal'):row.append(int(item.get(col,0)))
                        elif col=='owner_user_id':row.append(item.get(col,'alice'))
                        else:row.append(item.get(col,item['id']))
                    stream.write_row(row)
        self.writer.connection.commit()

    def change(self,identity,value):
        self.writer.connection.execute(f'UPDATE {self.table} SET raw_json=%s::jsonb WHERE id=%s',(json.dumps(value),identity))
        self.writer.connection.commit()

    def task(self,identity,**fields):
        return dict(id=identity,owner_user_id='alice',task_id=identity,kind='task',status='ready',
                    name=identity,revision=1,assets=[],created_at=1,updated_at=1,**fields)

    def run(self,identity,task='task',**fields):
        value=dict(id=identity,owner_user_id='alice',task_id=task,kind='run',status='completed',
                   created_at=1.75,updated_at=2,decision='MATCH',quality={'synthetic':'x'*8192})
        value.update(fields);return value

    @contextmanager
    def variant(self,baseline=False):
        if baseline:
            with patch.object(LabelRepository,'list_run_payloads_for_tasks',baseline_method()), \
                 patch.object(LabelRepository,'list_run_history_for_tasks',lambda repo,owner,task_ids,**_:baseline_method()(repo,owner,task_ids)):yield
        else:yield

    def page(self,baseline=False,**params):
        with self.variant(baseline):
            return self.endpoint(q=params.get('q',''),source=params.get('source','all'),result=params.get('result','all'),
                                 cursor=params.get('cursor',''),limit=params.get('limit',100))

    def traverse(self,baseline=False,**params):
        page=self.page(baseline,**params);rows=page['items'][:]
        while page['next_cursor']:
            page=self.page(baseline,**{**params,'cursor':page['next_cursor']});rows.extend(page['items'])
        return rows


def main():
    with Fixture() as f:
        rows=[f.task('task'),f.task('extension',legacy_id='legacy'),f.task('empty'),
              f.run('new'),f.run('old',created_at=1.25,status='failed',decision=None),
              f.run('tie-z',created_at=1.75),f.run('tie-a',created_at=1.75,status='failed'),
              f.run('extended','extension',created_at=0.5),f.run('neighbor',owner_user_id='bob')]
        f.insert('label_inspection_objects',rows)
        f.insert('text_inspection_standards',[
            dict(id='legacy',owner_user_id='alice',standard_type='label',name='Legacy',created_at=0,updated_at=1),
            dict(id='manual',owner_user_id='alice',standard_type='manual',name='Manual',created_at=0,updated_at=1)])
        f.insert('text_inspection_records',[
            dict(id='legacy-r',owner_user_id='alice',standard_id='legacy',standard_type='label',created_at=1.5,status='completed',decision='DIFFERENCES'),
            dict(id='orphan-r',owner_user_id='alice',standard_id='gone',created_at=4,status='failed'),
            dict(id='manual-r',owner_user_id='alice',standard_id='manual',standard_type='manual',created_at=3,status='completed')])
        f.insert('codex_comparison_tasks',[dict(id='beta',owner_user_id='alice',created_at=7,updated_at=7,
            status='succeeded',report_version='label-batch-v3',inputs={'standard_name':'Beta','references':{'a':{}}},labels={'one':{}},summary={'decision':'MATCH'})])
        expected=f.traverse(True)
        assert f.traverse()==expected
        for item in rows:
            if item['kind']=='run':assert f.store.publish(item['owner_user_id'],item['id'])
        projected=f.repo.list_run_payloads_for_tasks('alice',['task'])['task']
        assert all(set(row)<={'id','created_at','status','decision'} for row in projected)
        assert f.traverse()==expected
        assert {x['source'] for x in expected}=={'word','legacy','legacy_manual','beta'}
        for filters in ({'q':'task'},{'source':'legacy'},{'result':'MATCH'},{'source':'legacy_manual'},{'source':'beta'}):
            assert f.traverse(**filters)==f.traverse(True,**filters)
        assert f.repo.list_run_payloads_for_tasks('bob',['task'])['task'][0]['id']=='neighbor'
        f.owner='bob';assert f.traverse()==f.traverse(True)==[];f.owner='alice'
        # Unknown version must fall back; no on-read repair, source rewrite or cache fill.
        f.writer.connection.execute(f'UPDATE {f.cache} SET projection_version=%s WHERE id=%s',(VERSION+1,'new'));f.writer.connection.commit()
        assert 'quality' in next(r for r in f.repo.list_run_payloads_for_tasks('alice',['task'])['task'] if r['id']=='new')
        assert f.traverse()==expected
        assert f.writer.connection.execute(f'SELECT projection_version FROM {f.cache} WHERE id=%s',('new',)).fetchone()[0]==VERSION+1
        f.writer.connection.commit()
        # Snapshot created by old path stays unchanged after new records, rename and completion.
        page=f.page(True,limit=2);collected=page['items'][:]
        f.insert('label_inspection_objects',[f.task('added')])
        changed={**rows[0],'name':'renamed','updated_at':99};f.change('task',changed)
        changed_run={**rows[2+1],'status':'failed','decision':'DIFFERENCES'};f.change('new',changed_run)
        while page['next_cursor']:
            page=f.page(cursor=page['next_cursor'],limit=2);collected.extend(page['items'])
        assert collected==expected and len({r['id'] for r in collected})==len(collected)
        cursor=f.page(limit=1)['next_cursor']
        for owner,params,status in [('bob',{},404),('alice',{'q':'changed'},422)]:
            f.owner=owner
            try:f.page(cursor=cursor,**params)
            except HTTPException as error:assert error.status_code==status
            else:raise AssertionError('cursor owner/filter binding bypassed')
        f.owner='alice'
        # The exact fixed 15-minute expiry is unchanged, including cursor produced by parent.
        with patch('local_inspection_service.storage.label_inspection.time.time',return_value=10000):timed=f.page(True,limit=1)
        with patch('local_inspection_service.storage.label_inspection.time.time',return_value=10899):assert f.page(cursor=timed['next_cursor'])
        with patch('local_inspection_service.storage.label_inspection.time.time',return_value=10901):
            try:f.page(cursor=timed['next_cursor'])
            except HTTPException as error:assert error.status_code==422
            else:raise AssertionError('expired snapshot accepted')
        print('real API mixed sources, ties/fractions, filters, owner isolation and unchanged old cursors passed',flush=True)

        # Source/cache invalidation is observed in one statement snapshot under an old writer fence.
        assert f.store.publish('alice','tie-z')
        f.writer.connection.execute("SELECT pg_advisory_xact_lock(hashtextextended('label-inspection-v1',0))")
        f.writer.connection.execute(f'UPDATE {f.table} SET raw_json=%s::jsonb WHERE id=%s',
            (json.dumps({**rows[5],'decision':'DIFFERENCES'}),'tie-z'))
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending=pool.submit(f.repo.list_run_payloads_for_tasks,'alice',['task']).result(timeout=3)
        assert next(r for r in pending['task'] if r['id']=='tie-z')['decision']=='MATCH'
        f.writer.connection.commit()
        current=f.repo.list_run_payloads_for_tasks('alice',['task'])
        assert next(r for r in current['task'] if r['id']=='tie-z')['decision']=='DIFFERENCES'
        assert f.reader.connection.info.transaction_status==0
        original=PostgresRuntimeRepository._row_to_dict;opened=[];sentinel=RuntimeError('synthetic decode failure')
        cursor_factory=PostgresRuntimeRepository._cursor
        def track(raw):
            cursor=cursor_factory(raw)
            if raw is f.reader:opened.append(cursor)
            return cursor
        def fail(raw,cursor,row):
            if raw is f.reader:raise sentinel
            return original(raw,cursor,row)
        with patch.object(PostgresRuntimeRepository,'_cursor',track),patch.object(PostgresRuntimeRepository,'_row_to_dict',fail):
            try:f.repo.list_run_payloads_for_tasks('alice',['task'])
            except RuntimeError as error:assert error is sentinel
            else:raise AssertionError('decode failure swallowed')
        assert opened[-1].closed and f.reader.connection.info.transaction_status==0
        assert f.repo.list_run_payloads_for_tasks('alice',['task'])
        print('one-snapshot old writer visibility, no advisory wait, failure/IDLE/cursor close/reuse passed',flush=True)

        # Invalid older/nonlatest rows must still fail in unchanged native-before-legacy order.
        invalid=f.run('invalid',created_at=0,**{'import':None})
        f.insert('label_inspection_objects',[invalid]);assert not f.store.publish('alice','invalid')
        def failure(baseline):
            try:f.page(baseline)
            except Exception as exc:return type(exc),str(exc)
            raise AssertionError('invalid nonlatest payload hidden')
        assert failure(False)==failure(True)==(AttributeError,"'NoneType' object has no attribute 'items'")
        # JSONB string containing invalid JSON must retain the exact 422 envelope.
        f.change('invalid','{broken')
        replies=[]
        for baseline in (False,True):
            with f.variant(baseline):response=f.client.get(api.PREFIX+'/tasks')
            assert response.status_code==422
            replies.append(response.json())
        assert replies[0]==replies[1]
        # HTTP status/error response remains identical after source repair.
        f.change('invalid',{'kind':'run','id':'invalid','created_at':0,'import':{},'quality':{}})
        for baseline in (False,True):
            with f.variant(baseline):response=f.client.get(api.PREFIX+'/tasks')
            assert response.status_code==200,response.text[:200]
        # Missing optional fields and explicit null remain different after projection.
        optional=f.run('optional',created_at=100)
        f.insert('label_inspection_objects',[optional])
        for fields in ({},{'status':None,'decision':None}):
            value={k:v for k,v in optional.items() if k not in ('status','decision')};value.update(fields)
            f.change('optional',value);assert f.store.publish('alice','optional')
            assert f.traverse()==f.traverse(True)
            row=next(r for r in f.traverse() if r['id']=='task')
            assert row['decision']==fields.get('decision','REVIEW_REQUIRED')
            assert row['status']==fields.get('status','ready')
        # Authoritative source membership wins even with an orphan derived row.
        f.writer.connection.execute(f'DELETE FROM {f.table} WHERE id=%s',('optional',));f.writer.connection.commit()
        f.writer.connection.execute(f"INSERT INTO {f.cache} (id,projection_version,raw_json) VALUES (%s,%s,%s::jsonb)",
            ('optional',VERSION,json.dumps({'id':'optional','created_at':100,'status':'completed','decision':'MATCH'})))
        f.writer.connection.commit()
        assert all(r['id']!='optional' for r in f.repo.list_run_payloads_for_tasks('alice',['task'])['task'])
        f.owner='anonymous';assert f.client.get(api.PREFIX+'/tasks').status_code==401
        f.owner='denied';assert f.client.get(api.PREFIX+'/tasks').status_code==403
        print('full HTTP, malformed nonlatest fallback and original failure precedence passed',flush=True)
    print('PASS cached label summaries: no model, physical PLC or production data used')


if __name__=='__main__':main()
