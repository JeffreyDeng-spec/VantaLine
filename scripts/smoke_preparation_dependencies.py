"""Preparation CAS, transaction order, admission and late-result contracts."""
import copy
from contextlib import contextmanager
import hashlib
from pathlib import Path
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from local_inspection_service import qwen_evidence_jobs as qwen
from local_inspection_service import standard_preparation as engine
from local_inspection_service import standard_preparation_jobs as compatibility
from local_inspection_service.scripts.smoke_standard_preparation import fixture as image_fixture
from local_inspection_service.text_inspection import preparation_api as api, preparation_jobs as jobs_module, preparation_policy as policy
from local_inspection_service.text_inspection.preparation_ports import PreparationAccess, PreparationRecords, PreparationMedia, PreparationModels, PreparationHistory


class Fixture:
    def __init__(self,case):
        self.events=[];self.lock=threading.RLock();self.locked=False;self.pg=False;self.workers=[];self.clears=0;self.calls=[];self.provider_hook=lambda:None
        temporary=tempfile.TemporaryDirectory();case.addCleanup(temporary.cleanup);self.root=Path(temporary.name)
        self.image,self.elements=image_fixture();self.blob=engine.png(self.image)
        self.standard={'id':'order','owner_user_id':'alice','standard_type':'label','status':'draft','confirmed_assets':[]}
        self.assets=[{'id':'asset','owner_user_id':'alice','standard_id':'order','status':'candidate','ordinal':1,'sha256':hashlib.sha256(self.blob).hexdigest()}]
        self.record={'id':'record','owner_user_id':'alice','standard_id':'order','comparison_id':'request','status':'attempting','created_at':10,'preparation_compare':True,'ocr_provider':'qwen_ocr','diagnostics':{}}
        self.config={'configured':True,'provider':'qwen','model':'original-model','api_key':'synthetic','profile_id':'bound','profile_version':7}
        self.repo=SimpleNamespace(mutate_text_document=self.transaction)
        self.records=PreparationRecords(self.repository,self.guard,self.owned,self.load,self.save,self.apply)
        self.media=PreparationMedia(self.path,self.write,lambda b:hashlib.sha256(b).hexdigest(),lambda asset,owner:self.blob,lambda b,m:'synthetic-data-url',lambda *a,**k:b'fixture')
        self.models=PreparationModels(self.settings,lambda:True,self.provider,lambda result,settings:{'ok':result['ok']})
        self.jobs=jobs_module.PreparationJobs(self.records,self.media,self.models,self.clear)
        self.jobs.observe=lambda image,**kwargs:copy.deepcopy(self.elements)
    def owned(self,kind,key,owner):
        self.events.append(('owned',kind,key,owner,self.locked))
        if owner!='alice':return None
        if kind=='standards' and key=='order':return copy.deepcopy(self.standard)
        if kind=='records' and key=='record':return copy.deepcopy(self.record)
        if kind=='assets':return next((copy.deepcopy(a) for a in self.assets if a['id']==key),None)
    def repository(self):self.events.append(('repository',));return self.repo if self.pg else None
    @contextmanager
    def guard(self):
        with self.lock:
            self.locked=True;self.events.append(('enter',))
            try:yield
            finally:self.locked=False;self.events.append(('exit',))
    def load(self,kind):self.events.append(('load',kind));return copy.deepcopy(self.assets if kind=='assets' else [self.record])
    def save(self,kind,value):
        self.events.append(('save',kind,value['id']))
        if kind=='standards':self.standard=copy.deepcopy(value)
        elif kind=='assets':self.assets=[copy.deepcopy(value) if a['id']==value['id'] else a for a in self.assets]
        else:self.record=copy.deepcopy(value)
        return True
    def apply(self,standard,assets,**kwargs):self.events.append(('apply',kwargs));standard['revision_number']=standard.get('revision_number',0)+1;return standard
    def transaction(self,identity,owner,change,**kwargs):self.events.append(('transaction',identity,owner,kwargs));return change(copy.deepcopy(self.standard),copy.deepcopy(self.assets))
    def settings(self,purpose):self.events.append(('settings',purpose));return self.config
    def path(self,owner,identity,name):return self.root/owner/identity/name
    def write(self,path,data):path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    def provider(self,name,payload):
        assert self.assets[0]['preparation_attempt']['state']=='classifying'
        self.calls.append((name,copy.deepcopy(payload)));self.provider_hook()
        return {'ok':True,'parsed':{'kind':'label_design','coverage_complete':True,'missing_regions':[],'reason':'fixture','elements':[{k:e[k] for k in ['id','state','reason']} for e in self.elements]}}
    def clear(self):self.events.append(('clear',));self.clears+=1
    def start(self,fail=False):
        fixture=self
        class Thread:
            def __init__(self,**kwargs):self.kwargs=kwargs
            def start(self):
                if fail:raise RuntimeError('thread start failed')
                fixture.workers.append(self.kwargs)
        with patch.dict('os.environ',{'VANTALINE_STANDARD_PREPARATION_ACCOUNTS':'alice'}),patch.object(jobs_module.threading,'Thread',Thread):return self.jobs.start('order','alice')
    def run(self):task=self.workers.pop(0);task['target'](*task['args'])


class PreparationContracts(unittest.TestCase):
    def slot_free(self,f):
        self.assertTrue(f.jobs.slots.acquire(False));self.assertFalse(f.jobs.slots.acquire(False));f.jobs.slots.release()
    def test_timeout_cas_copy_return_value_reread_and_cleanup(self):
        f=Fixture(self);original=copy.deepcopy(f.record);updater=Mock(return_value=False)
        self.assertIs(qwen.timeout(updater,f.record),False);self.assertEqual(f.record,original)
        updater.assert_called_once();kind,changed=updater.call_args.args
        self.assertEqual(kind,'records');self.assertEqual(changed['diagnostics']['elapsed_ms'],120000);self.assertEqual(changed['status'],'review_required')
        app=FastAPI();calls=[]
        def raced_update(kind,value):calls.append((kind,value));f.record.update(status='completed',decision='MATCH');return False
        history=PreparationHistory(lambda:'text_inspection_records',lambda rows:rows,copy.deepcopy,lambda:raced_update)
        api.register(app,PreparationAccess(lambda *a,**k:None,lambda:('alice','fixture')),f.records,history,f.media,f.jobs)
        client=TestClient(app);self.addCleanup(client.close)
        with patch.object(api.time,'time',return_value=130):
            self.assertEqual(client.get('/api/text-inspection/prepared-comparisons/record').json()['status'],'attempting');self.assertEqual(calls,[])
            self.assertTrue(qwen.expired({'created_at':10,'deadline_at':130}))
        with patch.object(api.time,'time',return_value=130.001):response=client.get('/api/text-inspection/prepared-comparisons/record')
        self.assertEqual(response.json()['status'],'completed');self.assertEqual(response.json()['decision'],'MATCH');self.assertEqual(len(calls),1)
        self.assertFalse(any(e[0]=='save' for e in f.events))
        f.record=copy.deepcopy(original);f.record['ocr_provider']='local';f.events.clear()
        with patch.object(api.time,'time',return_value=131):self.assertEqual(client.get('/api/text-inspection/prepared-comparisons/record').json()['status'],'review_required')
        self.assertEqual([e for e in f.events if e[0]=='save'],[('save','records','record')]);self.assertEqual(len(calls),1)
        clear=Mock();failure=Mock(side_effect=RuntimeError('CAS unavailable'))
        with self.assertRaises(RuntimeError):qwen.settle_timeout(failure,clear,original)
        failure.assert_called_once();clear.assert_called_once()
    def test_json_publication_order_all_writes_pg_arguments_and_failure_unlock(self):
        f=Fixture(self)
        def change(standard,assets):f.events.append(('change',));return {'published':True}
        f.jobs.mutate('order','alice',change,publish=True)
        self.assertEqual([e[0] for e in f.events],['owned','repository','enter','owned','load','change','apply','save','save','exit'])
        self.assertEqual(f.events[0][-1],False);self.assertEqual(f.events[3][-1],True)
        self.assertEqual([e[1] for e in f.events if e[0]=='save'],['assets','standards'])
        self.assertEqual(next(e for e in f.events if e[0]=='apply')[1]['action'],'prepare')
        f.events.clear();f.jobs.view('order','alice');self.assertEqual([e[1] for e in f.events if e[0]=='save'],['assets','standards'])
        f.pg=True
        for publish in [False,True]:
            f.events.clear();f.jobs.mutate('order','alice',change,publish=publish)
            self.assertEqual([e[0] for e in f.events],['owned','repository','transaction','change'])
            self.assertEqual(f.events[2][3],{'revision_action':'prepare' if publish else None})
        for point in ['change','apply','save']:
            f=Fixture(self);failure=Mock(side_effect=RuntimeError(point))
            records=f.records
            if point!='change':
                f.jobs.records=PreparationRecords(records.repository,records.guard,records.owned,records.load,failure if point=='save' else records.save,failure if point=='apply' else records.apply_revision)
            with self.assertRaises(RuntimeError):f.jobs.mutate('order','alice',failure if point=='change' else lambda s,a:{'published':True},publish=True)
            failure.assert_called_once();self.assertFalse(f.locked);self.assertEqual(f.events[-1],('exit',))
    def test_single_slot_admission_thread_failure_and_frozen_provider_settings(self):
        f=Fixture(self)
        with self.assertRaises(RuntimeError):f.start(fail=True)
        self.assertEqual(f.standard['preparation_job']['state'],'processing');self.slot_free(f);self.assertEqual(f.calls,[])
        f.start();self.assertEqual(f.workers,[]);self.slot_free(f)
        first,second=Fixture(self),Fixture(self);first.jobs.slots.acquire();self.slot_free(second)
        with self.assertRaises(HTTPException) as caught:first.start()
        self.assertEqual(caught.exception.status_code,429);self.assertEqual(first.events[1],('settings','document'))
        first.standard['preparation_job']={'state':'processing','heartbeat':time.time()}
        self.assertEqual(first.start()['job']['state'],'processing');self.assertEqual(first.calls,[]);first.jobs.slots.release()
        f=Fixture(self);f.start();f.config={**f.config,'model':'changed-after-submit'};f.run()
        self.assertEqual(len(f.calls),1);name,payload=f.calls[0]
        self.assertEqual(name,'provider.gemini.generate_json');self.assertEqual(payload['provider_config']['model'],'original-model')
        self.assertEqual(payload['provider_config']['timeout_seconds'],60);self.assertEqual(payload['max_attempts'],1)
        self.assertEqual(f.clears,1);self.slot_free(f);self.assertIn('active_preparation',f.assets[0])
    def test_late_attempt_interruption_and_source_changes_keep_distinct_outcomes(self):
        for mode in ['attempt','interrupted','source']:
            with self.subTest(mode=mode):
                f=Fixture(self)
                def hook():
                    if mode=='attempt':f.assets[0]['preparation_attempt']={'id':'newer','state':'classifying'}
                    if mode=='interrupted':
                        f.standard['preparation_job']['heartbeat']=0;f.jobs.view('order','alice')
                    if mode=='source':f.assets[0]['sha256']='changed-source'
                f.provider_hook=hook;f.start();f.run();self.assertEqual(len(f.calls),1);self.assertNotIn('active_preparation',f.assets[0]);self.assertEqual(f.clears,1);self.slot_free(f)
                attempt=f.assets[0]['preparation_attempt']
                if mode=='attempt':self.assertEqual(attempt,{'id':'newer','state':'classifying'});self.assertNotIn('preparation_revisions',f.assets[0])
                if mode=='interrupted':self.assertEqual(attempt['state'],'review');self.assertIn('late_result',attempt);self.assertNotIn('preparation_revisions',f.assets[0])
                if mode=='source':self.assertEqual(attempt['state'],'ready');self.assertEqual(len(f.assets[0]['preparation_revisions']),1);self.assertEqual(f.assets[0]['sha256'],'changed-source')
    def test_unknown_provider_outcome_never_retries_or_publishes(self):
        f=Fixture(self);error=RuntimeError('unknown provider outcome')
        f.provider_hook=Mock(side_effect=[error,None])
        f.start();f.events.clear();f.run()
        self.assertEqual(len(f.calls),1);f.provider_hook.assert_called_once()
        attempt=f.assets[0]['preparation_attempt']
        self.assertEqual(attempt['state'],'review')
        self.assertEqual(attempt['diagnostics']['failure'],'RuntimeError')
        self.assertEqual(attempt['diagnostics']['reason_code'],'processing_failed')
        self.assertNotIn('active_preparation',f.assets[0]);self.assertNotIn('preparation_revisions',f.assets[0])
        self.assertEqual(f.standard['preparation_job']['state'],'completed')
        self.assertEqual(f.clears,1);self.assertEqual(f.events[-1],('clear',));self.slot_free(f)

    def test_final_publication_failure_propagates_once_then_clears_and_releases(self):
        f=Fixture(self);f.start();f.events.clear();error=RuntimeError('unknown publication outcome')
        original=f.jobs.mutate;publications=[];release=f.jobs.slots.release
        def mutate(*args,**kwargs):
            if kwargs.get('publish'):
                publications.append((args,kwargs));f.events.append(('finish',))
                if len(publications)==1:raise error
            return original(*args,**kwargs)
        def released():f.events.append(('release',));release()
        with patch.object(f.jobs,'mutate',side_effect=mutate),patch.object(f.jobs.slots,'release',side_effect=released) as release_spy:
            with self.assertRaises(RuntimeError) as caught:f.run()
            self.assertIs(caught.exception,error);release_spy.assert_called_once()
        self.assertEqual(len(publications),1);self.assertEqual(len(f.calls),1)
        self.assertEqual(f.events[-3:],[('finish',),('clear',),('release',)])
        self.assertEqual(f.assets[0]['preparation_attempt']['state'],'classifying')
        self.assertEqual(f.standard['preparation_job']['state'],'processing')
        self.assertNotIn('active_preparation',f.assets[0]);self.assertNotIn('preparation_revisions',f.assets[0])
        self.assertEqual(f.clears,1);self.slot_free(f)

    def test_worker_timeout_resolves_writer_after_timestamp(self):
        for mode in ['timer','worker']:
            with self.subTest(mode=mode):
                events=[];record={'id':'record','created_at':0,'deadline_at':10,'status':'attempting','diagnostics':{}}
                first=Mock(side_effect=lambda *args:events.append('first'))
                second=Mock(side_effect=lambda *args:events.append('second'))
                clear=Mock(side_effect=lambda:events.append('clear'))
                records=SimpleNamespace(update_attempt=first)
                def now():events.append('clock');records.update_attempt=second;return 100
                if mode=='timer':
                    with patch.object(qwen.time,'time',side_effect=now):qwen.settle_timeout(lambda kind,value:records.update_attempt(kind,value),clear,record)
                    self.assertEqual(events,['clock','second','clear'])
                    self.assertEqual(record['status'],'attempting');self.assertEqual(record['diagnostics'],{})
                else:
                    # The already-expired worker never acquires a slot or reaches a provider.
                    clocks=iter([100,100])
                    def worker_clock():
                        try:return next(clocks)
                        except StopIteration:return now()
                    with patch.object(qwen.threading,'Timer') as timer,patch.object(qwen.time,'time',side_effect=worker_clock),patch.object(qwen,'expired',return_value=True):
                        qwen.run(records,None,clear,None,record,b'',{},None)
                    timer.return_value.start.assert_called_once();timer.return_value.cancel.assert_called_once()
                    self.assertEqual(events,['clock','second','clear'])
                first.assert_not_called();second.assert_called_once();clear.assert_called_once()
                self.assertEqual(second.call_args.args[0],'records');self.assertEqual(second.call_args.args[1]['updated_at'],100)

    def test_http_timeout_captures_writer_before_timestamp_without_retry(self):
        for mode in ['success','missing','failure']:
            with self.subTest(mode=mode):
                f=Fixture(self);app=FastAPI();events=[];error=RuntimeError('unknown CAS outcome')
                first=Mock(side_effect=[error,True] if mode=='failure' else lambda *args:events.append('first'))
                second=Mock(side_effect=lambda *args:events.append('second'))
                current=[None if mode=='missing' else first]
                def writer():events.append('capture');return current[0]
                history=PreparationHistory(lambda:'text_inspection_records',lambda rows:rows,copy.deepcopy,writer)
                api.register(app,PreparationAccess(lambda *a,**k:None,lambda:('alice','fixture')),f.records,history,f.media,f.jobs)
                endpoint=next(r.endpoint for r in app.routes if getattr(r,'path','')=='/api/text-inspection/prepared-comparisons/{record_id}')
                def now():
                    events.append('clock')
                    if events.count('clock')==2:current[0]=second
                    return 131
                with patch.object(api.time,'time',side_effect=now):
                    if mode=='missing':
                        with self.assertRaises(TypeError):endpoint('record')
                    elif mode=='failure':
                        with self.assertRaises(RuntimeError) as caught:endpoint('record')
                        self.assertIs(caught.exception,error)
                    else:self.assertEqual(endpoint('record')['status'],'attempting')
                self.assertEqual(events[:3],['clock','capture','clock']);second.assert_not_called()
                if mode=='missing':first.assert_not_called()
                else:
                    first.assert_called_once();self.assertEqual(first.call_args.args[1]['updated_at'],131)
                self.assertEqual(f.record['status'],'attempting');self.assertEqual(f.calls,[])

    def test_snapshot_compatibility_order_and_deep_copy(self):
        self.assertIs(compatibility.PreparationJobs,jobs_module.PreparationJobs);self.assertIs(compatibility.register,api.register)
        for name in ['PROCESSING','enabled','snapshot']:self.assertIs(getattr(compatibility,name),getattr(policy,name))
        rows=[{'id':'second','ordinal':2,'status':'candidate','preparation_required':True,'preparation_previous_snapshot':{'id':'previous','nested':[]}}, {'id':'first','ordinal':'1','status':'page','sha256':'source','active_preparation':{'sha256':'clean','nested':[]}}, {'id':'missing','ordinal':0,'status':'candidate','preparation_required':True}]
        result=policy.snapshot(rows);self.assertEqual([r['id'] for r in result],['first','previous']);self.assertEqual(result[0]['reference_sha256'],'clean')
        result[0]['preparation']['nested'].append('changed');result[1]['nested'].append('changed');self.assertEqual(rows[1]['active_preparation']['nested'],[]);self.assertEqual(rows[0]['preparation_previous_snapshot']['nested'],[])


if __name__=='__main__':unittest.main(verbosity=2)
