"""Real PostgreSQL native history aggregation against the frozen parent endpoint."""
import ast
import copy
from concurrent.futures import ThreadPoolExecutor
import functools
import hashlib
import inspect
import json
from pathlib import Path
import sys
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from smoke_label_summary_reads import Fixture
from local_inspection_service.label_inspection import api
from local_inspection_service.label_inspection.history_summary import RunHistorySummary
from local_inspection_service.label_inspection.run_summary import VERSION
from local_inspection_service.storage.label_inspection import RUN_BATCH_SIZE
ROOT=Path(__file__).resolve().parents[1]


@functools.lru_cache(maxsize=1)
def parent_register():
    data=(ROOT/'tests/backend_contract/label_history_tasks_baseline.py').read_bytes().replace(b"\r\n",b"\n")
    assert hashlib.sha256(data).hexdigest()=='ce5b2beaacf9b6d16957ed22470b2cec36da30596ad1fccab6f60cd4bf2bb086'
    original=next(n for n in ast.parse(data).body if isinstance(n,ast.FunctionDef) and n.name=='tasks')
    register=ast.parse(inspect.getsource(api.register)).body[0]
    register.body=[original if isinstance(n,ast.FunctionDef) and n.name=='tasks' else n for n in register.body]
    namespace=dict(vars(api));exec(compile(ast.fix_missing_locations(ast.Module(body=[register],type_ignores=[])),str(ROOT/'tests/backend_contract/label_history_tasks_baseline.py'),'exec'),namespace)
    return namespace['register']


class StatisticsFixture(Fixture):
    def __enter__(self):
        super().__enter__();self.parent_client=None
        try:
            self.candidate_endpoint=self.endpoint
            app=FastAPI()
            with patch.object(api.pdf_import,'register',lambda *_:None):
                parent_register()(app,SimpleNamespace(require_permission=lambda *_:None,owner=lambda:(self.owner,'test')),
                    SimpleNamespace(repository=lambda:self.reader),SimpleNamespace(data_directory=lambda:Path(self.directory.name)),
                    lambda:None,lambda:{'enabled':True})
            self.parent_endpoint=next(r.endpoint for r in app.routes if getattr(r,'path',None)==api.PREFIX+'/tasks' and 'GET' in r.methods)
            self.parent_client=TestClient(app,raise_server_exceptions=False)
            return self
        except BaseException:
            self.__exit__(*sys.exc_info());raise

    def __exit__(self,*args):
        try:
            if getattr(self,'parent_client',None):self.parent_client.close()
        finally:super().__exit__(*args)

    @contextmanager
    def variant(self,baseline=False):
        previous=self.endpoint
        self.endpoint=self.parent_endpoint if baseline else self.candidate_endpoint
        try:yield
        finally:self.endpoint=previous


def main():
    from local_inspection_service.storage.postgres_runtime_repository import PostgresRuntimeRepository
    class NoDescription:
        @property
        def description(self):raise AssertionError('unexpected column metadata access')
    decoder=object.__new__(PostgresRuntimeRepository)
    nested=[];mapping={'raw_json':nested}
    decoded=decoder._row_to_dict(NoDescription(),mapping)
    assert decoded==mapping and decoded is not mapping and decoded['raw_json'] is nested
    assert decoder._row_to_dict(NoDescription(),('first','second'),columns=('same','same'))=={'same':'second'}
    assert decoder._row_to_dict(NoDescription(),('extra',),columns=())=={}
    with StatisticsFixture() as f:
        rows=[f.task('task'),f.task('mixed'),f.task('empty'),f.task('extended',legacy_id='legacy')]
        # SQL C collation and double precision match proven Python string/float keys.
        identities=['ascii','é','é','中','😀']
        for i,identity in enumerate(identities):rows.append(f.run(identity,created_at=1.25))
        rows.extend([f.run('large',created_at=2**53),f.run('negative',created_at=-1.25),
            f.run('mixed-valid','mixed'),f.run('mixed-unsafe','mixed',owner_user_id='alice',quality={}),
            f.run('extended-run','extended',created_at=.5)])
        f.insert('label_inspection_objects',rows)
        f.insert('text_inspection_standards',[dict(id='legacy',owner_user_id='alice',standard_type='label',name='Legacy',created_at=0,updated_at=1)])
        f.insert('text_inspection_records',[dict(id='legacy-run',owner_user_id='alice',standard_id='legacy',created_at=2,status='completed',decision='DIFFERENCES')])
        for row in rows:
            if row['kind']=='run' and row['id']!='mixed-unsafe':assert f.store.publish(row['owner_user_id'],row['id'])
        grouped=f.repo.list_run_history_for_tasks('alice',['task','mixed','empty','extended'],summary_task_ids=['task','mixed','empty','extended'])
        assert isinstance(grouped['task'],RunHistorySummary) and grouped['task'].count==7 and grouped['task'].latest['id']=='large'
        assert isinstance(grouped['mixed'],list) and len(grouped['mixed'])==2
        assert grouped['empty']==[] and isinstance(grouped['extended'],RunHistorySummary)
        assert f.traverse()==f.traverse(True)
        f.writer.connection.execute(f'DELETE FROM {f.table} WHERE id=%s',('large',));f.writer.connection.commit()
        summary=f.repo.list_run_history_for_tasks('alice',['task'],summary_task_ids=['task'])['task']
        assert summary.latest['id']==max(identities)
        assert f.traverse()==f.traverse(True)
        assert f.repo.list_run_history_for_tasks('alice',[],summary_task_ids=[])=={}
        try:f.repo.list_run_history_for_tasks('alice',['task']*(RUN_BATCH_SIZE+1),summary_task_ids=['task']*(RUN_BATCH_SIZE+1))
        except ValueError as exc:assert str(exc)=='run batch exceeds limit'
        else:raise AssertionError('oversized batch accepted')
        assert f.repo.list_run_history_for_tasks('bob',['task'],summary_task_ids=['task'])=={'task':[]}
        # Native/legacy exact-key ties retain native-first stable ordering.
        tie=f.run('legacy:legacy-run','extended',created_at=2)
        f.insert('label_inspection_objects',[tie]);assert f.store.publish('alice',tie['id'])
        assert f.traverse()==f.traverse(True)
        assert next(row for row in f.traverse() if row['id']=='extended')['decision']=='MATCH'
        helper=inspect.getclosurevars(f.candidate_endpoint).nonlocals['list_history']
        native=RunHistorySummary(7,{'id':'latest','created_at':99})
        assert helper(None,'alice',{'id':'ignored','read_only':True},native,{})==(0,{})
        assert helper(None,'alice',{'id':'ignored','revision':0},native,{})==(0,{})
        print('proven count/latest, Unicode/fraction/large/negative sort, mixed fallback, owner and bounds passed',flush=True)

        # An unknown cache version with an unsafe cast value cannot affect fallback.
        f.writer.connection.execute(f'UPDATE {f.cache} SET projection_version=%s,raw_json=%s::jsonb WHERE id=%s',
            (VERSION+1,json.dumps({'created_at':'not-a-float','id':'poison'}),'ascii'));f.writer.connection.commit()
        grouped=f.repo.list_run_history_for_tasks('alice',['task'],summary_task_ids=['task'])['task']
        assert isinstance(grouped,list) and len(grouped)==6 and f.traverse()==f.traverse(True)
        assert f.store.publish('alice','ascii')
        # SQL task column mismatch makes publication unprovable and keeps old membership.
        value=f.run('mismatch','wrong-json-task',created_at=3)
        f.insert('label_inspection_objects',[value])
        f.writer.connection.execute(f'UPDATE {f.table} SET task_id=%s WHERE id=%s',('task','mismatch'));f.writer.connection.commit()
        assert not f.store.publish('alice','mismatch')
        assert isinstance(f.repo.list_run_history_for_tasks('alice',['task'],summary_task_ids=['task'])['task'],list)
        assert f.traverse()==f.traverse(True)
        # Nonlatest malformed native data must fail ahead of malformed legacy evidence.
        invalid=f.run('invalid','extended',created_at=-1,**{'import':None})
        f.insert('label_inspection_objects',[invalid]);assert not f.store.publish('alice','invalid')
        f.writer.connection.execute(f"UPDATE {f.writer._qualified_table('text_inspection_records')} SET raw_json=jsonb_set(raw_json,'{{diagnostics}}','1') WHERE id='legacy-run'");f.writer.connection.commit()
        outcomes=[]
        for baseline in (False,True):
            try:f.traverse(baseline)
            except Exception as error:outcomes.append((type(error).__name__,str(error)))
            else:raise AssertionError('malformed history was ignored')
        assert outcomes==[('AttributeError',"'NoneType' object has no attribute 'items'")]*2,outcomes
        # Once native error is removed, the old legacy error is exposed by both paths.
        f.writer.connection.execute(f'DELETE FROM {f.table} WHERE id=%s',('invalid',));f.writer.connection.commit()
        outcomes=[]
        for baseline in (False,True):
            try:f.traverse(baseline)
            except Exception as error:outcomes.append((type(error).__name__,str(error)))
            else:raise AssertionError('malformed legacy was ignored')
        assert outcomes==[('AttributeError',"'int' object has no attribute 'get'")]*2,outcomes
        f.writer.connection.execute(f"UPDATE {f.writer._qualified_table('text_inspection_records')} SET raw_json=raw_json-'diagnostics' WHERE id='legacy-run'");f.writer.connection.commit()
        for candidate,parent in [(f.client.get(api.PREFIX+'/tasks'),f.parent_client.get(api.PREFIX+'/tasks'))]:
            assert candidate.status_code==parent.status_code==200 and candidate.json()==parent.json()
        print('unknown-version unsafe cast, SQL grouping mismatch, native-before-legacy errors and HTTP passed',flush=True)

        # An old cursor captures the full combined count/decision before data changes.
        before=f.traverse(True);page=f.page(True,limit=1);collected=page['items'][:]
        f.insert('label_inspection_objects',[f.task('new')]);f.change('task',{**rows[0],'name':'renamed','updated_at':100})
        while page['next_cursor']:
            page=f.page(cursor=page['next_cursor'],limit=1);collected.extend(page['items'])
        assert collected==before
        print('parent cursor remains frozen through aggregate-reader rename/insert passed',flush=True)

        # One statement must expose the old source/cache pair while an old writer holds its fence.
        f.writer.connection.execute("SELECT pg_advisory_xact_lock(hashtextextended('label-inspection-v1',0))")
        f.writer.connection.execute(f'UPDATE {f.table} SET raw_json=%s::jsonb WHERE id=%s',
            (json.dumps({**tie,'decision':'DIFFERENCES'}),tie['id']))
        with ThreadPoolExecutor(max_workers=1) as pool:
            previous=pool.submit(f.repo.list_run_history_for_tasks,'alice',['extended'],summary_task_ids=['extended']).result(timeout=3)['extended']
        assert isinstance(previous,RunHistorySummary) and previous.latest['decision']=='MATCH'
        f.writer.connection.commit()
        current=f.repo.list_run_history_for_tasks('alice',['extended'],summary_task_ids=['extended'])['extended']
        assert isinstance(current,list) and next(r for r in current if r['id']==tie['id'])['decision']=='DIFFERENCES'
        from local_inspection_service.storage.postgres_runtime_repository import PostgresRuntimeRepository
        original=PostgresRuntimeRepository._row_to_dict;factory=PostgresRuntimeRepository._cursor;opened=[]
        sentinel=RuntimeError('aggregate row decode sentinel')
        def cursor(raw):
            result=factory(raw)
            if raw is f.reader:opened.append(result)
            return result
        def decode(raw,c,row,**kwargs):
            if raw is f.reader:
                assert f.writer.connection.execute("SELECT pg_try_advisory_xact_lock(hashtextextended('label-inspection-v1',0))").fetchone()[0]
                f.writer.connection.commit()
                raise sentinel
            return original(raw,c,row,**kwargs)
        with patch.object(PostgresRuntimeRepository,'_cursor',cursor),patch.object(PostgresRuntimeRepository,'_row_to_dict',decode):
            try:f.repo.list_run_history_for_tasks('alice',['extended'],summary_task_ids=['extended'])
            except RuntimeError as error:assert error is sentinel
            else:raise AssertionError('aggregate read decode failure hidden')
        assert opened[-1].closed and f.reader.connection.info.transaction_status==0
        assert f.repo.list_run_history_for_tasks('alice',['extended'],summary_task_ids=['extended'])
        print('aggregate SQL old-writer snapshot, no write fence, original error/closed cursor/IDLE/reuse passed',flush=True)
    with StatisticsFixture() as f:
        # Historical JSON text may contain NaN. Its non-total Python sort cannot
        # be replaced by sorting only the latest native row with legacy rows.
        native=[f.task('extension',legacy_id='legacy'),f.run('n0','extension',created_at=1.0),f.run('n1','extension',created_at=0.0)]
        f.insert('label_inspection_objects',native)
        f.insert('text_inspection_standards',[dict(id='legacy',owner_user_id='alice',standard_type='label',name='Legacy',created_at=0,updated_at=1)])
        legacy=[dict(id='l'+str(i),owner_user_id='alice',standard_id='legacy',standard_type='label',created_at=i,status='completed',decision='DIFFERENCES') for i in range(4)]
        f.insert('text_inspection_records',legacy)
        for row,stamp in zip(legacy,[float('nan'),-1.0,-1.0,3.0]):
            row['created_at']=stamp
            f.writer.connection.execute(f'UPDATE {f.writer._qualified_table("text_inspection_records")} SET raw_json=%s::jsonb WHERE id=%s',(json.dumps(json.dumps(row)),row['id']))
        f.writer.connection.commit()
        assert f.store.publish('alice','n0') and f.store.publish('alice','n1')
        old=f.traverse(True);current=f.traverse()
        assert old==current and current[0]['decision']=='MATCH' and current[0]['run_count']==6
        assert isinstance(f.repo.list_run_history_for_tasks('alice',['extension'],summary_task_ids=[])['extension'],list)
        # SQL identity is unique but historical raw JSON task identities need not
        # be. An eligible alias cannot authorize compression for the extension.
        alias={**f.task('raw-alias'),'name':'Alias'}
        f.insert('label_inspection_objects',[alias]);f.change('raw-alias',{**alias,'id':'extension'})
        old=f.traverse(True);current=f.traverse()
        assert old==current and len(current)==2
        assert next(row for row in current if row['name']=='extension')['decision']=='MATCH'
        print('historical NaN full sort and duplicate raw task ID eligibility passed',flush=True)
    with StatisticsFixture() as f:
        # Long fallback histories must retain every source-ordered payload, even
        # when JSON sort keys differ from SQL keys and only some proofs exist.
        tasks=['complete','partial','excluded','unknown']
        rows=[f.task(task) for task in tasks]
        for task in tasks:
            for i in range(40):
                rows.append(f.run(f'{task}_{i:02}',task,created_at=40-i,
                    profile_snapshot={'synthetic':'x'*2048},
                    findings=[{'synthetic':'y'*8192}]))
        f.insert('label_inspection_objects',rows)
        f.writer.connection.execute(f"UPDATE {f.table} SET created_at=-created_at WHERE kind='run'")
        f.writer.connection.commit()
        for row in rows:
            if row['kind']=='run' and (row['task_id']!='partial' or int(row['id'][-2:])%2):
                assert f.store.publish('alice',row['id'])
        f.writer.connection.execute(f"UPDATE {f.cache} SET projection_version=%s,raw_json=%s::jsonb WHERE id LIKE 'unknown_%%'",
            (VERSION+1,json.dumps({'created_at':'unsafe float','id':'poison'})))
        f.writer.connection.commit()
        payloads=f.repo.list_run_payloads_for_tasks('alice',tasks)
        descriptions=[]
        factory=PostgresRuntimeRepository._cursor
        class MetadataCursor:
            def __init__(self,inner):self.inner=inner
            @property
            def description(self):
                descriptions.append(True)
                return self.inner.description
            def __getattr__(self,key):return getattr(self.inner,key)
        def metadata_cursor(repo):
            raw=factory(repo)
            return MetadataCursor(raw) if repo is f.reader else raw
        with patch.object(PostgresRuntimeRepository,'_cursor',metadata_cursor):
            histories=f.repo.list_run_history_for_tasks('alice',tasks,summary_task_ids=['complete','partial','unknown'])
        assert len(descriptions)==1, 'column metadata rebuilt for each historical row'
        complete=histories['complete']
        assert isinstance(complete,RunHistorySummary) and complete.count==40
        assert complete.latest==max(payloads['complete'],key=lambda r:(float(r['created_at']),r['id']))
        for task in ['partial','excluded','unknown']:
            assert len(histories[task])==len(payloads[task])==40
            from local_inspection_service.label_inspection.projection import public
            for actual, original in zip(histories[task],payloads[task]):
                assert public(actual)==public(original)
                # Only the safe quality value may change. Identity/order and
                # every other raw field stay exactly equal to the old reader.
                assert {k:v for k,v in actual.items() if k!='quality'}=={k:v for k,v in original.items() if k!='quality'}
                assert actual.get('quality')==({'checked':True} if original.get('quality') else original.get('quality'))
        assert f.traverse()==f.traverse(True)
        print('wide dense histories preserve complete/latest and every ordered partial/excluded/unknown payload',flush=True)
    with StatisticsFixture() as f:
        from local_inspection_service.label_inspection.projection import public
        f.insert('label_inspection_objects',[f.task('task')])
        qualities=[{}, {'text':'汉字\n'+'x'*8192,'flag':False,'empty':None},
                   {'number':1}, {'number':1.5}, {'nested':{'text':'value'}},
                   {'array':['value']}, [], [1], 'value', '', 0, 1, None, True, False]
        for index, quality in enumerate(qualities):
            row=f.run('quality_'+str(index),quality=quality)
            f.insert('label_inspection_objects',[row])
        raw=f.repo.list_run_payloads_for_tasks('alice',['task'])['task']
        compact=f.repo.list_run_history_for_tasks('alice',['task'],summary_task_ids=['task'])['task']
        assert [public(r) for r in compact]==[public(r) for r in raw]
        for original,actual in zip(raw,compact):
            assert {k:v for k,v in original.items() if k!='quality'}=={k:v for k,v in actual.items() if k!='quality'}
            if original['id']=='quality_1': assert actual['quality']=={'checked':True}
            else: assert actual['quality']==original['quality']
        assert f.repo.get('alice','quality_1')['quality']==qualities[1]
        assert f.traverse()==f.traverse(True)
        assert f.client.get(api.PREFIX+'/tasks').json()==f.parent_client.get(api.PREFIX+'/tasks').json()
        # Numeric and nested quality must keep original decoder failures, even
        # though public() would subsequently hide the evidence value.
        limit=sys.get_int_max_str_digits()
        try:
            sys.set_int_max_str_digits(640)
            for expression in ('{ "number": '+('9'*700)+' }', '{ "nested": { "number": '+('9'*700)+' } }'):
                f.writer.connection.execute(f"UPDATE {f.table} SET raw_json=jsonb_set(raw_json,'{{quality}}',%s::jsonb) WHERE id='quality_1'",(expression,))
                f.writer.connection.commit()
                outcomes=[]
                for baseline in (False,True):
                    try:f.traverse(baseline)
                    except HTTPException as exc:
                        assert exc.status_code==422 and isinstance(exc.__cause__,ValueError)
                        outcomes.append((type(exc),exc.status_code,exc.detail))
                    else:raise AssertionError('numeric quality decode error hidden')
                assert outcomes[0]==outcomes[1]
                assert f.reader.connection.info.transaction_status==0
        finally:sys.set_int_max_str_digits(limit)
        print('safe flat quality shrinks only list payloads; all other fields/shapes/detail/HTTP and numeric errors preserved',flush=True)
    print('PASS PostgreSQL history statistics against frozen complete parent tasks endpoint')


if __name__=='__main__':main()
