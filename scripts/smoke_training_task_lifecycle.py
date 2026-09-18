"""Training state, deletion and public-view contracts using process substitutes."""
from contextlib import ExitStack
import copy
import json
import os
from pathlib import Path
import signal
import sys
import tempfile
import threading
import unittest
import uuid
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
PG_CHECK='--postgres' in sys.argv
if PG_CHECK:sys.argv.remove('--postgres')


def available(lock):
    values=[]
    def probe():
        acquired=lock.acquire(blocking=False);values.append(acquired)
        if acquired:lock.release()
    thread=threading.Thread(target=probe);thread.start();thread.join(timeout=5)
    if thread.is_alive():raise AssertionError('lock probe stalled')
    return values[0]


class Fixture:
    def __init__(self,root):
        self.root=Path(root);self.guard=threading.RLock();self.threads={};self.tombstones={}
        self.records={};self.events=[];self.found=None;self.repo=None;self.user={'id':'alice','username':'Alice'}
        self.path=Mock(side_effect=lambda job:self._path(job))
        self.load=Mock(side_effect=lambda path:self._load(path))
        self.save=Mock(side_effect=lambda task:self._save(task))
        self.find=Mock(side_effect=lambda job:self._find(job))
        self.access=Mock(side_effect=lambda *args,**kwargs:self.events.append(('access',args,kwargs)))
        self.repository=Mock(side_effect=lambda:self._repository())
        self.invalidate=Mock(side_effect=lambda key:self.events.append(('invalidate',key)))
        self.list=Mock(return_value=[])
        self.enrich=Mock(side_effect=lambda record:self.events.append('enrich') or dict(record))
        self.sanitize=Mock(side_effect=lambda record:self.events.append('sanitize') or {key:value for key,value in record.items() if key!='private'})
        self.visible=Mock(side_effect=lambda record,user,target:record.get('owner_user_id')==user['id'])
    def _path(self,job):self.events.append(('path',job,available(self.guard)));return self.root/(str(job)+'.json')
    def _load(self,path):self.events.append(('load',path.stem,available(self.guard)));return self.records.get(path.stem)
    def _save(self,task):self.events.append(('save',task,available(self.guard)));self.records[task['job_id']]=task
    def _find(self,job):self.events.append(('find',job));return self.found
    def _repository(self):
        self.events.append(('repository',available(self.guard)))
        if isinstance(self.repo,Exception):raise self.repo
        return self.repo
    def bind(self,api,stack):
        values={'_training_task_lock':self.guard,'_training_task_threads':self.threads,'_training_task_delete_tombstones':self.tombstones,
            'training_task_path':self.path,'load_training_task':self.load,'save_training_task':self.save,'find_training_task':self.find,
            'require_record_access':self.access,'runtime_postgres_repository_or_none':self.repository,'store_read_cache_invalidate':self.invalidate,
            'load_training_task_records':self.list,'enrich_record_audit_fields':self.enrich,'public_path_sanitized':self.sanitize,
            'record_visible_to_user':self.visible}
        for name,value in values.items():stack.enter_context(patch.object(api,name,value))


class TrainingLifecycleContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.environment=patch.dict(os.environ);cls.environment.start()
        cls.runtime=tempfile.TemporaryDirectory(prefix='training-lifecycle-root-');root=Path(cls.runtime.name)
        (root/'local_inspection_service/static').mkdir(parents=True)
        os.environ.update(LOCAL_INSPECTION_ROOT=str(root),VANTALINE_DATA_STORE='json',LOCAL_INSPECTION_AUTO_RESUME_WORKER='0',VANTALINE_LABEL_INSPECTION_ENABLED='false')
        from local_inspection_service import server
        cls.api=server
        cls.originals={name:getattr(server,name) for name in ('training_task_path','load_training_task','save_training_task','find_training_task')}
        cls.runtime_aliases=(server._training_task_lock,server._training_task_threads,server._training_task_delete_tombstones)
    @classmethod
    def tearDownClass(cls):cls.runtime.cleanup();cls.environment.stop()
    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.f=Fixture(self.stack.enter_context(tempfile.TemporaryDirectory(prefix='training-lifecycle-')));self.f.bind(self.api,self.stack)
        self.kill=self.stack.enter_context(patch.object(os,'kill',side_effect=AssertionError('unexpected process signal')))

    def test_worker_classification_and_process_activity_boundaries(self):
        api=self.api;f=self.f
        for record,expected in [({'training_executor':' RunPod ','remote_training_job_id':'worker_x','worker_transfer_required':True},False),
                ({'training_executor':' WORKER '},True),({'remote_training_job_id':' worker_x '},True),({'worker_transfer_required':'0'},True),({},False)]:
            self.assertIs(api.training_task_uses_worker(record),expected)
        thread=Mock();thread.is_alive.return_value=True;f.threads['job']=thread
        with patch.object(Path,'exists',side_effect=AssertionError('unexpected proc lookup')):
            self.assertFalse(api.local_training_task_is_active({'training_pid':123}))
            self.assertTrue(api.local_training_task_is_active({'job_id':' job ','training_pid':123}))
        thread.is_alive.assert_called_once();thread.is_alive.return_value=False
        paths=[]
        with patch.object(Path,'exists',lambda path:paths.append(path) or True):
            self.assertTrue(api.local_training_task_is_active({'job_id':'job','training_pid':'123'}))
        self.assertEqual(paths,[Path('/proc/123')])
        for pid in (None,0,[],{},'bad'):
            self.assertFalse(api.local_training_task_is_active({'task_id':'task','training_pid':pid}))
        with self.assertRaises(OverflowError):api.local_training_task_is_active({'job_id':'job','training_pid':float('inf')})
        with patch.object(Path,'exists',side_effect=OSError('proc')):
            with self.assertRaisesRegex(OSError,'proc'):api.local_training_task_is_active({'job_id':'job','training_pid':123})
        self.kill.assert_not_called()

    def test_refresh_guards_timestamps_and_exact_stopped_messages(self):
        api=self.api;f=self.f
        for value in ({'job_id':'job','status':'completed'},{'job_id':'job','status':'running','training_executor':'worker'},
                      {'status':'queued'}):self.assertIs(api.refresh_interrupted_local_training_task(value),value)
        f.path.assert_not_called();f.save.assert_not_called()
        value={'job_id':'job','status':'running'};f.records['job']=value
        with patch('time.time',side_effect=[101.9,102.9]):result=api.refresh_interrupted_local_training_task(value)
        self.assertIs(result,value);self.assertEqual(result,{'job_id':'job','status':'stopped','progress':100,'stopped_at':101,'completed_at':102,
            'error':'Local training worker is no longer active. Delete and retry the task.','note':'本地训练任务已中断；请删除后重试。'})
        f.save.assert_called_once_with(value);self.kill.assert_not_called()

    def test_update_path_before_lock_tombstones_and_late_completion(self):
        api=self.api;f=self.f;existing={'job_id':'job','status':'queued'};f.records['job']=existing
        self.assertIs(api.update_training_task('job',status='running'),existing)
        self.assertEqual(f.events[0],('path','job',True));self.assertEqual(f.events[1],('load','job',False));self.assertFalse(f.events[2][2])
        f.save.reset_mock();tombstone={'job_id':'job','status':'stopped','nested':[]};f.tombstones['job']=tombstone
        result=api.update_training_task('job',status='completed');self.assertEqual(result,existing);self.assertIsNot(result,existing)
        f.save.assert_not_called();self.assertEqual(existing['status'],'running')
        f.records['job']={};result=api.update_training_task('job',status='completed')
        self.assertEqual(result,tombstone);self.assertIsNot(result,tombstone);self.assertIs(result['nested'],tombstone['nested'])
        f.tombstones['job']={}
        with patch('time.time',return_value=123.9):value=api.update_training_task('job',status='queued')
        self.assertEqual(value,{'job_id':'job','created_at':123,'status':'queued'});f.save.assert_called_once()
        f.save.side_effect=RuntimeError('save')
        with self.assertRaisesRegex(RuntimeError,'save'):api.update_training_task('job',progress=42)
        self.assertTrue(available(f.guard));self.assertEqual(f.records['job']['progress'],42)

    def test_stop_single_signal_time_order_and_exception_boundaries(self):
        api=self.api;f=self.f;self.kill.side_effect=None
        value={'job_id':'job','status':'running','training_pid':'123'};f.records['job']=value
        with patch('time.time',side_effect=[1.9,2.9]):result=api.stop_training_task_process(value,note='stop-note')
        self.kill.assert_called_once_with(123,signal.SIGTERM);self.assertIs(result,value)
        self.assertEqual((result['status'],result['stopped_at'],result['completed_at'],result['note']),('stopped',1,2,'stop-note'))
        self.kill.reset_mock();f.save.reset_mock()
        for value in ({'status':'running','training_pid':123},{'job_id':'job','status':'completed','training_pid':123}):
            self.assertIs(api.stop_training_task_process(value,note='unused'),value)
        self.kill.assert_not_called();f.save.assert_not_called()
        for failure in (OSError('kill'),ValueError('kill')):
            self.kill.reset_mock()
            self.kill.side_effect=failure;value={'job_id':'job','status':'running','training_pid':123};f.records['job']=value
            self.assertEqual(api.stop_training_task_process(value,note='stopped')['status'],'stopped')
            self.kill.assert_called_once_with(123,signal.SIGTERM)
        self.kill.side_effect=None;f.save.reset_mock()
        with self.assertRaises(TypeError):api.stop_training_task_process({'job_id':'job','status':'running','training_pid':[1]},note='bad')
        with self.assertRaises(OverflowError):api.stop_training_task_process({'job_id':'job','status':'running','training_pid':float('inf')},note='bad')
        f.save.assert_not_called()

    def test_delete_missing_authorization_and_stop_failures_do_not_set_tombstones(self):
        api=self.api;f=self.f
        self.assertIsNone(api.delete_training_task_record(' ',f.user));f.find.assert_not_called()
        self.assertIsNone(api.delete_training_task_record('missing',f.user,missing_ok=True))
        with self.assertRaises(api.HTTPException) as error:api.delete_training_task_record('missing',f.user)
        self.assertEqual((error.exception.status_code,error.exception.detail),(404,'Training task not found'))
        f.found={'job_id':' canonical ','status':'running'};f.access.side_effect=api.HTTPException(404,'Resource not found')
        thread=Mock();thread.is_alive.side_effect=AssertionError('activity checked before authorization');f.threads['canonical']=thread
        with self.assertRaises(api.HTTPException):api.delete_training_task_record('alias',f.user)
        f.path.assert_called_once_with('canonical');f.access.assert_called_once_with(f.found,f.user,write=True)
        f.save.assert_not_called();self.kill.assert_not_called();self.assertEqual(f.tombstones,{})
        thread.is_alive.assert_not_called();f.threads.clear()
        f.access.side_effect=None;f.found['training_pid']=[1]
        with self.assertRaises(TypeError):api.delete_training_task_record('alias',f.user)
        self.assertEqual(f.tombstones,{});f.repository.assert_not_called()

    def test_delete_inactive_json_aliases_return_identity_and_four_timestamps(self):
        api=self.api;f=self.f;value={'job_id':' canonical ','task_id':'task-id','status':'completed'};f.found=value
        path=f.root/'canonical.json';path.write_text('old')
        registrations=[];clock_checks=[];timestamps=iter([11.9,12.9,13.9,14.9]);case=self
        class GuardedTombstones(dict):
            def __setitem__(self,key,value):
                case.assertFalse(available(f.guard),'tombstone registration must hold the shared guard')
                registrations.append((key,value));super().__setitem__(key,value)
        def clock():
            case.assertFalse(available(f.guard),'tombstone construction must hold the shared guard')
            clock_checks.append(True);return next(timestamps)
        f.tombstones=GuardedTombstones()
        with patch.object(api,'_training_task_delete_tombstones',f.tombstones),patch('time.time',side_effect=clock):
            result=api.delete_training_task_record(' alias ',f.user)
        self.assertIs(result,value);self.assertFalse(path.exists());self.assertEqual(value['status'],'completed')
        tombstone=f.tombstones['alias'];self.assertIs(f.tombstones['canonical'],tombstone)
        self.assertEqual(len(clock_checks),4);self.assertEqual([key for key,_ in registrations],['alias','canonical'])
        self.assertTrue(all(marker is tombstone for _,marker in registrations))
        self.assertEqual(tombstone,{'job_id':'canonical','task_id':'task-id','status':'stopped','progress':100,
            'stopped_at':11,'completed_at':12,'cancelled_at':13,'deleted_at':14,'delete_tombstone':True,'note':'关联流水线任务已删除，训练任务已停止。'})
        f.invalidate.assert_not_called();f.save.assert_not_called();self.kill.assert_not_called();self.assertTrue(available(f.guard))
        with patch.object(api,'_training_task_delete_tombstones',f.tombstones):
            for identity in ('alias','canonical'):
                self.assertEqual(api.update_training_task(identity,status='completed'),tombstone)
        f.save.assert_not_called()

    def test_delete_failure_residue_and_active_preservation(self):
        api=self.api;f=self.f;value={'job_id':'job','status':'completed'};f.found=value
        with patch.object(Path,'unlink',side_effect=PermissionError('denied')):
            with self.assertRaises(api.HTTPException) as error:api.delete_training_task_record('alias',f.user)
        self.assertEqual(error.exception.status_code,500);self.assertEqual(error.exception.detail,'Failed to delete task: denied')
        self.assertIsInstance(error.exception.__cause__,PermissionError);self.assertIs(f.tombstones['alias'],f.tombstones['job'])
        self.assertTrue(available(f.guard));f.invalidate.assert_not_called()
        f.tombstones.clear();thread=Mock();thread.is_alive.return_value=True;f.threads['job']=thread
        f.found={'job_id':'job','status':'running'};f.records['job']=dict(f.found)
        result=api.delete_training_task_record('alias',f.user)
        self.assertEqual(result['status'],'stopped');self.assertFalse(result.get('delete_tombstone',False))
        self.assertTrue(f.records['job']['delete_tombstone']);self.assertIs(f.records['job'],f.tombstones['job'])
        self.assertEqual(f.save.call_count,2);f.repository.assert_called_once()  # Only the earlier failed JSON delete selected it.
        late=api.update_training_task('job',status='completed');self.assertEqual(late['status'],'stopped')
        self.assertEqual(f.save.call_count,2)
        f.tombstones.clear();f.found={'job_id':'job','status':'running'};f.records['job']=dict(f.found)
        def fail_tombstone_save(task):
            if task.get('delete_tombstone'):raise RuntimeError('tombstone-save')
            f._save(task)
        f.save.side_effect=fail_tombstone_save
        with self.assertRaisesRegex(RuntimeError,'tombstone-save'):api.delete_training_task_record('failed-alias',f.user)
        self.assertIs(f.tombstones['failed-alias'],f.tombstones['job']);self.assertTrue(available(f.guard))
        self.assertFalse(f.records['job'].get('delete_tombstone',False))
        self.assertEqual(api.update_training_task('job',status='completed')['status'],'stopped')

    def test_delete_postgres_row_validity_failure_residue_and_lock(self):
        api=self.api;f=self.f;f.found={'job_id':'job','task_id':'row-id','status':'completed'};repo=Mock();f.repo=repo
        def delete(table,keys):
            self.assertFalse(available(f.guard));self.assertEqual((table,keys),('training_tasks',{'id':'row-id'}))
        repo.delete_by_primary_key.side_effect=delete
        self.assertIs(api.delete_training_task_record('alias',f.user),f.found)
        f.invalidate.assert_called_once_with('training_task_pairs');repo.delete_by_primary_key.assert_called_once()
        f.invalidate.reset_mock();repo.delete_by_primary_key.reset_mock()
        with patch.object(api,'training_task_row',return_value=None):api.delete_training_task_record('second-alias',f.user)
        f.invalidate.assert_not_called();repo.delete_by_primary_key.assert_not_called()
        f.repo=RuntimeError('repository')
        with self.assertRaisesRegex(RuntimeError,'repository'):api.delete_training_task_record('factory-alias',f.user)
        self.assertIs(f.tombstones['factory-alias'],f.tombstones['job']);self.assertTrue(available(f.guard))
        f.repo=repo
        with patch.object(api,'training_task_row',side_effect=ValueError('row')):
            with self.assertRaisesRegex(ValueError,'row'):api.delete_training_task_record('row-alias',f.user)
        self.assertIs(f.tombstones['row-alias'],f.tombstones['job']);self.assertTrue(available(f.guard))
        repo.delete_by_primary_key.side_effect=RuntimeError('delete-row')
        with self.assertRaisesRegex(RuntimeError,'delete-row'):api.delete_training_task_record('write-alias',f.user)
        self.assertIs(f.tombstones['write-alias'],f.tombstones['job']);self.assertTrue(available(f.guard))
        f.invalidate.assert_called_once_with('training_task_pairs')

    def test_public_projection_defaults_first_command_and_sanitization_order(self):
        api=self.api;f=self.f
        value={'job_id':'job','status':'completed','action':'train_model','training_command':['epochs=bad','epochs=9','imgsz=64','imgsz=99'],'private':'removed'}
        result=api.public_training_task(value)
        self.assertEqual(f.events,['enrich','sanitize']);self.assertNotIn('private',result);self.assertNotIn('epochs',result)
        self.assertEqual(result['image_size'],64);self.assertEqual(result['total_epochs'],0);self.assertIsNone(result['current_epoch'])
        self.assertEqual((result['candidate_id'],result['candidate_name'],result['task_id'],result['label'],result['queue_kind']),('job','训练任务','job','训练任务','training'))
        self.assertIn('private',value);self.assertNotIn('image_size',value)
        existing={'job_id':'job','candidate_id':None,'candidate_name':'','task_id':None,'progress':None,'total_epochs':None,'current_epoch':0,'label':'',
                  'epochs':0,'image_size':None,'training_command':['epochs=0','imgsz=bad','imgsz=128']}
        result=api.public_training_task(existing)
        for key in ('candidate_id','candidate_name','task_id','progress','total_epochs','current_epoch','label'):self.assertEqual(result[key],existing[key])
        self.assertEqual(result['epochs'],0);self.assertIsNone(result['image_size'])

    def test_public_worker_readonly_and_list_visibility_precedes_refresh(self):
        api=self.api;f=self.f;worker={'job_id':'worker','status':'running','training_executor':'worker'}
        for allowed in (False,True):
            result=api.public_refreshed_training_task(worker,allow_remote_refresh=allowed)
            self.assertTrue(result['executor_retired']);self.assertTrue(result['remote_refresh_retired'])
            self.assertEqual(result['status'],'running');self.assertEqual(result['note'],'历史 Windows-worker 训练记录仅保留只读展示；生产训练执行已切换为 RunPod。')
        f.save.assert_not_called();self.kill.assert_not_called()
        private={'job_id':'private','status':'queued','owner_user_id':'bob'};public={'job_id':'public','status':'completed','owner_user_id':'alice'}
        f.list.return_value=[private,public];f.events.clear()
        result=api.list_training_tasks(f.user,'target',allow_remote_refresh=True)
        self.assertEqual([item['job_id'] for item in result],['public']);self.assertEqual(f.visible.call_count,2)
        f.visible.assert_any_call(private,f.user,'target');f.path.assert_not_called();f.save.assert_not_called()
        f.visible.reset_mock();f.list.return_value=[public]
        self.assertEqual(len(api.list_training_tasks({})),1);f.visible.assert_not_called()

    def test_runtime_ownership_independent_services_and_late_root_state(self):
        from local_inspection_service.runtime.training_tasks import TrainingTaskRuntime,TrainingTaskState
        from local_inspection_service.training.task_lifecycle import TrainingTaskLifecycle,TrainingTaskRecords,TrainingTaskWrites,training_task_uses_worker
        from local_inspection_service.training.task_views import TrainingTaskViews,TrainingViewAccess
        from local_inspection_service.storage.runtime_records import training_task_row
        runtime=self.api._training_task_runtime
        for actual,alias in zip((runtime.lock,runtime.threads,runtime.tombstones),self.runtime_aliases):self.assertIs(actual,alias)
        second_runtime=TrainingTaskRuntime()
        self.assertIsNot(runtime.lock,second_runtime.lock);self.assertIsNot(runtime.threads,second_runtime.threads);self.assertIsNot(runtime.tombstones,second_runtime.tombstones)
        self.assertIs(self.api.training_task_uses_worker,training_task_uses_worker)
        other_root=self.f.root/'other';other_root.mkdir();other=Fixture(other_root)
        def compose(f):
            lifecycle=TrainingTaskLifecycle(TrainingTaskState(lambda:f.guard,lambda:f.threads,lambda:f.tombstones),
                TrainingTaskRecords(f.path,f.load,f.save,f.find),TrainingTaskWrites(f.repository,training_task_row,f.invalidate),f.access)
            views=TrainingTaskViews(f.list,lifecycle.refresh_interrupted_local_training_task,TrainingViewAccess(f.enrich,lambda:f.sanitize,f.visible))
            self.assertEqual(f.events,[]);return lifecycle,views
        first,first_views=compose(self.f);second,second_views=compose(other)
        first.update_training_task('one',status='completed');second.update_training_task('two',status='queued')
        self.assertEqual(set(self.f.records),{'one'});self.assertEqual(set(other.records),{'two'})
        self.f.tombstones['one']={'job_id':'one','status':'stopped'}
        self.assertEqual(first.update_training_task('one',status='running')['status'],'completed')
        self.assertEqual(second.update_training_task('one',status='running')['status'],'running')
        self.f.list.return_value=[self.f.records['one']];other.list.return_value=[{'job_id':'worker','training_executor':'worker','status':'running'}]
        self.assertEqual(first_views.list_training_tasks()[0]['job_id'],'one')
        self.assertTrue(second_views.list_training_tasks()[0]['executor_retired'])
        thread=Mock();thread.is_alive.return_value=True
        with patch.object(self.api,'_training_task_threads',{'late':thread}):
            self.assertTrue(self.api.local_training_task_is_active({'job_id':'late'}))
        self.assertFalse(first.local_training_task_is_active({'job_id':'late'}))

    def test_public_sanitizer_is_captured_before_enrichment(self):
        api=self.api;f=self.f;value={'job_id':'job','status':'completed'}
        for mode in ('normal','prior','missing'):
            with self.subTest(mode=mode),ExitStack() as stack:
                events=[]
                def callback(label):
                    def sanitize(record):events.append(label);return {**record,'chosen':label}
                    return sanitize
                a,b,c=(callback(label) for label in ('A','B','C'))
                stack.enter_context(patch.object(api,'public_path_sanitized',None if mode=='missing' else a))
                def records():
                    events.append('records')
                    if mode=='prior':events.append('prior');api.public_path_sanitized=b
                    return [value]
                def enrich(record):events.append('enrich');api.public_path_sanitized=c;return dict(record)
                f.list.side_effect=records;f.enrich.side_effect=enrich
                if mode=='missing':
                    with self.assertRaises(TypeError):api.list_training_tasks()
                else:self.assertEqual(api.list_training_tasks()[0]['chosen'],'B' if mode=='prior' else 'A')
                self.assertEqual(events,['records']+(['prior'] if mode=='prior' else [])+['enrich']+([] if mode=='missing' else ['B' if mode=='prior' else 'A']))

    def test_lifecycle_and_view_first_failures_are_not_retried(self):
        api=self.api
        cases=('path_update','path_delete','load_update','load_tombstone','save_update','save_stop','save_preserve',
               'find','access','repository','row','invalidate','delete','list','enrich','sanitize','visible','refresh','thread','proc')
        for case in cases:
            with self.subTest(case=case),ExitStack() as stack:
                f=Fixture(stack.enter_context(tempfile.TemporaryDirectory(prefix='lifecycle-first-error-')));f.bind(api,stack)
                value={'job_id':'job','status':'completed','owner_user_id':'alice'};f.records['job']=value;f.found=value;f.repo=Mock()
                f.list.return_value=[value,{'job_id':'other','status':'completed','owner_user_id':'alice'}]
                if case=='load_tombstone':f.tombstones['job']={'job_id':'job','status':'stopped'}
                if case in ('save_stop','save_preserve'):
                    value['status']='running';thread=Mock();thread.is_alive.return_value=True;f.threads['job']=thread
                mapping={'path_update':(api,'training_task_path',f.root/'job.json'),'path_delete':(api,'training_task_path',f.root/'job.json'),
                         'load_update':(api,'load_training_task',value),'load_tombstone':(api,'load_training_task',value),
                         'save_update':(api,'save_training_task',None),'save_stop':(api,'save_training_task',None),'save_preserve':(api,'save_training_task',None),
                         'find':(api,'find_training_task',value),'access':(api,'require_record_access',None),
                         'repository':(api,'runtime_postgres_repository_or_none',f.repo),'row':(api,'training_task_row',{'id':'job'}),
                         'invalidate':(api,'store_read_cache_invalidate',None),'delete':(f.repo,'delete_by_primary_key',None),
                         'list':(api,'load_training_task_records',[value]),'enrich':(api,'enrich_record_audit_fields',value),
                         'sanitize':(api,'public_path_sanitized',value),'visible':(api,'record_visible_to_user',True),
                         'refresh':(api,'refresh_interrupted_local_training_task',value)}
                if case=='thread':
                    thread=Mock();f.threads['job']=thread;mapping[case]=(thread,'is_alive',False)
                elif case=='proc':mapping[case]=(Path,'exists',False);value['training_pid']=123
                owner,name,valid=mapping[case];error=RuntimeError(case);fail_at=2 if case=='save_preserve' else 1
                callback=Mock()
                def fail(*args,**kwargs):
                    if callback.call_count==fail_at:raise error
                    if case=='save_preserve':f._save(args[0])
                    return valid
                callback.side_effect=fail;stack.enter_context(patch.object(owner,name,callback))
                if case in ('path_update','load_update','load_tombstone','save_update'):action=lambda:api.update_training_task('job',progress=42)
                elif case in ('list','enrich','sanitize','visible','refresh'):action=lambda:api.list_training_tasks(f.user)
                elif case in ('thread','proc'):action=lambda:api.local_training_task_is_active(value)
                else:action=lambda:api.delete_training_task_record('alias',f.user)
                with self.assertRaises(RuntimeError) as caught:action()
                self.assertIs(caught.exception,error);self.assertEqual(callback.call_count,fail_at);self.assertTrue(available(f.guard))
                if case in ('repository','row','invalidate','delete','save_preserve'):
                    self.assertIs(f.tombstones['alias'],f.tombstones['job']);self.assertTrue(f.tombstones['job']['delete_tombstone'])
                elif case!='load_tombstone':self.assertEqual(f.tombstones,{})
                if case=='save_update':self.assertEqual(value['progress'],42)
                if case=='save_preserve':self.assertEqual(f.records['job']['status'],'stopped');self.assertNotIn('delete_tombstone',f.records['job'])
                if case in ('enrich','sanitize','refresh'):self.assertEqual(f.visible.call_count,1)
                self.kill.assert_not_called()

    def test_stop_signal_first_failure_and_status_recheck(self):
        api=self.api;f=self.f
        for error in (OSError('signal'),ValueError('signal'),RuntimeError('signal'),KeyboardInterrupt('signal')):
            with self.subTest(error=type(error).__name__):
                value={'job_id':'job','status':'running','training_pid':123};f.records['job']=value;f.save.reset_mock();self.kill.reset_mock()
                def kill(*args):
                    if self.kill.call_count==1:raise error
                self.kill.side_effect=kill
                if isinstance(error,(OSError,ValueError)):self.assertEqual(api.stop_training_task_process(value,note='stop')['status'],'stopped')
                else:
                    with self.assertRaises(type(error)) as caught:api.stop_training_task_process(value,note='stop')
                    self.assertIs(caught.exception,error);f.save.assert_not_called();self.assertEqual(value['status'],'running')
                self.kill.assert_called_once_with(123,signal.SIGTERM);self.assertTrue(available(f.guard))
        value={'job_id':'job','status':'running','training_pid':123};f.save.reset_mock();self.kill.reset_mock()
        def finish(*args):value['status']='completed'
        self.kill.side_effect=finish
        with patch('time.time',side_effect=AssertionError('completed task timestamped')):
            self.assertIs(api.stop_training_task_process(value,note='unused'),value)
        self.kill.assert_called_once_with(123,signal.SIGTERM);f.save.assert_not_called()

    def test_delete_clock_registration_and_unlink_first_failures(self):
        api=self.api
        for fail_at in range(1,5):
            with self.subTest(clock=fail_at),ExitStack() as stack:
                f=Fixture(stack.enter_context(tempfile.TemporaryDirectory(prefix='lifecycle-clock-')));f.bind(api,stack);f.found={'job_id':'job','status':'completed'}
                error=RuntimeError('clock');calls=[]
                def clock():
                    calls.append(available(f.guard))
                    if len(calls)==fail_at:raise error
                    return 10
                stack.enter_context(patch('time.time',clock))
                with self.assertRaises(RuntimeError) as caught:api.delete_training_task_record('alias',f.user)
                self.assertIs(caught.exception,error);self.assertEqual(calls,[False]*fail_at);self.assertEqual(f.tombstones,{})
                f.repository.assert_not_called();f.save.assert_not_called();self.assertTrue(available(f.guard))
        for fail_at in (1,2):
            with self.subTest(registration=fail_at),ExitStack() as stack:
                f=Fixture(stack.enter_context(tempfile.TemporaryDirectory(prefix='lifecycle-register-')));f.bind(api,stack);f.found={'job_id':'job','status':'completed'}
                calls=[];error=RuntimeError('register')
                class Tombstones(dict):
                    def __setitem__(self,key,value):
                        calls.append(key)
                        if len(calls)==fail_at:raise error
                        return super().__setitem__(key,value)
                markers=Tombstones();stack.enter_context(patch.object(api,'_training_task_delete_tombstones',markers))
                with self.assertRaises(RuntimeError) as caught:api.delete_training_task_record('alias',f.user)
                self.assertIs(caught.exception,error);self.assertEqual(calls,['alias','job'][:fail_at]);self.assertEqual(list(markers),[] if fail_at==1 else ['alias'])
                f.repository.assert_not_called();self.assertTrue(available(f.guard))
        for error in (FileNotFoundError('gone'),PermissionError('denied')):
            with self.subTest(unlink=type(error).__name__),ExitStack() as stack:
                f=Fixture(stack.enter_context(tempfile.TemporaryDirectory(prefix='lifecycle-unlink-')));f.bind(api,stack);f.found={'job_id':'job','status':'completed'}
                path=f.root/'job.json';path.write_text('original');original=Path.unlink;callback=Mock()
                def unlink(actual,*args,**kwargs):
                    if actual!=path:return original(actual,*args,**kwargs)
                    callback()
                    if callback.call_count==1:raise error
                    return original(actual,*args,**kwargs)
                stack.enter_context(patch.object(Path,'unlink',unlink))
                if isinstance(error,FileNotFoundError):self.assertIs(api.delete_training_task_record('alias',f.user),f.found)
                else:
                    with self.assertRaises(api.HTTPException) as caught:api.delete_training_task_record('alias',f.user)
                    self.assertEqual(caught.exception.status_code,500);self.assertIs(caught.exception.__cause__,error)
                self.assertEqual(callback.call_count,1);self.assertEqual(path.read_text(),'original');self.assertIs(f.tombstones['alias'],f.tombstones['job']);self.assertTrue(available(f.guard))

    def test_new_state_and_sanitizer_getters_fail_once(self):
        from dataclasses import replace
        api=self.api;life=api._training_lifecycle;views=api._training_views
        for case in ('guard_update','guard_delete','threads','markers_update','markers_first','markers_second','sanitizer'):
            with self.subTest(case=case),ExitStack() as stack:
                f=Fixture(stack.enter_context(tempfile.TemporaryDirectory(prefix='lifecycle-getter-')));f.bind(api,stack)
                value={'job_id':'job','status':'completed'};f.found=value;f.records['job']=value
                field='guard' if case.startswith('guard') else 'threads' if case=='threads' else 'tombstones'
                original=views.access.sanitize if case=='sanitizer' else getattr(life.state,field)
                fail_at=2 if case=='markers_second' else 1;error=RuntimeError(case);callback=Mock()
                def getter():
                    if callback.call_count==fail_at:raise error
                    return original()
                callback.side_effect=getter
                if case=='sanitizer':stack.enter_context(patch.object(views,'access',replace(views.access,sanitize=callback)))
                else:stack.enter_context(patch.object(life,'state',replace(life.state,**{field:callback})))
                if case.endswith('update'):action=lambda:life.update_training_task('job',progress=42)
                elif case=='threads':action=lambda:life.local_training_task_is_active(value)
                elif case=='sanitizer':action=lambda:views.public_training_task(value)
                else:action=lambda:life.delete_training_task_record('alias',f.user)
                with self.assertRaises(RuntimeError) as caught:action()
                self.assertIs(caught.exception,error);self.assertEqual(callback.call_count,fail_at);self.assertTrue(available(f.guard))
                self.assertEqual(list(f.tombstones),['alias'] if case=='markers_second' else [])
                f.save.assert_not_called();f.repository.assert_not_called()
                if case=='sanitizer':f.enrich.assert_not_called();f.sanitize.assert_not_called()

    def test_update_guard_covers_marker_read_and_in_place_change(self):
        api=self.api;f=self.f;events=[]
        class Markers(dict):
            def get(self,*args):events.append(('marker',available(f.guard)));return super().get(*args)
        class Record(dict):
            def update(self,*args,**kwargs):events.append(('update',available(f.guard)));return super().update(*args,**kwargs)
        value=Record(job_id='job',status='queued');f.records['job']=value
        with patch.object(api,'_training_task_delete_tombstones',Markers()):
            self.assertIs(api.update_training_task('job',status='running'),value)
        self.assertEqual(events,[('marker',False),('update',False)]);self.assertTrue(available(f.guard))

    def test_internal_lifecycle_first_failures_are_not_retried(self):
        api=self.api;life=api._training_lifecycle;views=api._training_views;f=self.f
        for case in ('refresh_active','delete_active','refresh_update','worker_public'):
            with self.subTest(case=case),ExitStack() as stack:
                value={'job_id':'job','status':'running'};f.found=value;f.records['job']=value;f.tombstones.clear()
                if case=='worker_public':value['training_executor']='worker'
                owner=views if case=='worker_public' else life
                name='public_training_task' if case=='worker_public' else 'update_training_task' if case=='refresh_update' else 'local_training_task_is_active'
                valid={} if case=='worker_public' else value if case=='refresh_update' else False
                error=RuntimeError(case);callback=Mock()
                def fail(*args,**kwargs):
                    if callback.call_count==1:raise error
                    return valid
                callback.side_effect=fail;stack.enter_context(patch.object(owner,name,callback))
                action=(lambda:life.delete_training_task_record('alias',f.user)) if case=='delete_active' else (lambda:views.public_refreshed_training_task(value)) if case=='worker_public' else (lambda:life.refresh_interrupted_local_training_task(value))
                with self.assertRaises(RuntimeError) as caught:action()
                self.assertIs(caught.exception,error);self.assertEqual(callback.call_count,1);self.assertEqual(f.tombstones,{});self.assertTrue(available(f.guard))
                self.kill.assert_not_called()

    def test_refresh_stop_and_create_clock_failures_are_not_retried(self):
        api=self.api
        for operation,fail_at in [('refresh',1),('refresh',2),('stop',1),('stop',2),('create',1)]:
            with self.subTest(operation=operation,clock=fail_at),ExitStack() as stack:
                f=Fixture(stack.enter_context(tempfile.TemporaryDirectory(prefix='lifecycle-other-clock-')));f.bind(api,stack)
                value={'job_id':'job','status':'running'};error=RuntimeError(operation);calls=[]
                def clock():
                    calls.append(available(f.guard))
                    if len(calls)==fail_at:raise error
                    return 10
                stack.enter_context(patch('time.time',clock))
                action=(lambda:api.refresh_interrupted_local_training_task(value)) if operation=='refresh' else (lambda:api.stop_training_task_process(value,note='stop')) if operation=='stop' else lambda:api.update_training_task('job',status='queued')
                with self.assertRaises(RuntimeError) as caught:action()
                self.assertIs(caught.exception,error);self.assertEqual(calls,[operation!='create']*fail_at)
                f.save.assert_not_called();self.assertEqual(f.records,{});self.assertEqual(f.tombstones,{});self.assertTrue(available(f.guard));self.kill.assert_not_called()
                if operation!='create':f.path.assert_not_called();f.load.assert_not_called()

    def test_state_containers_are_selected_at_original_expressions(self):
        api=self.api;f=self.f;events=[];thread=Mock()
        thread.is_alive.side_effect=lambda:events.append('alive') or True
        class Identifier:
            def __str__(self):events.append('str');api._training_task_threads={'job':thread};return 'job'
        with patch.object(api,'_training_task_threads',{}):self.assertTrue(api.local_training_task_is_active({'job_id':Identifier()}))
        self.assertEqual(events,['str','alive'])
        for missing in (False,True):
            with self.subTest(missing=missing),ExitStack() as stack:
                events=[];f.records.clear()
                class Markers(dict):
                    def __init__(self,label):super().__init__(job={'job_id':label,'status':'stopped'});self.label=label
                    def get(self,*args):events.append(self.label);return super().get(*args)
                a,b,c=(Markers(label) for label in ('A','B','C'))
                class Key:
                    def __str__(self):events.append('str');api._training_task_delete_tombstones=c;return 'job'
                def path(job):events.append('path');api._training_task_delete_tombstones=None if missing else b;return f.root/'job.json'
                stack.enter_context(patch.object(api,'_training_task_delete_tombstones',a));stack.enter_context(patch.object(api,'training_task_path',path))
                if missing:
                    with self.assertRaises(AttributeError):api.update_training_task(Key(),status='completed')
                    self.assertEqual(events,['path'])
                else:
                    self.assertEqual(api.update_training_task(Key(),status='completed'),{'job_id':'B','status':'stopped'})
                    self.assertEqual(events,['path','str','B'])
                self.assertTrue(available(f.guard));f.save.assert_not_called()

    @unittest.skipUnless(PG_CHECK,'use --postgres with an isolated test DSN')
    def test_real_postgres_delete_alias_and_preserved_task_rejects_late_completion(self):
        import psycopg
        from psycopg import sql
        from local_inspection_service.storage.postgres_schema import postgres_ddl
        from local_inspection_service.storage.postgres_runtime_repository import PostgresRuntimeRepository
        schema='training_lifecycle_'+uuid.uuid4().hex;dsn=os.environ['VANTALINE_POSTGRES_DSN']
        api=self.api;f=self.f
        with ExitStack() as stack:
            for name,operation in self.originals.items():stack.enter_context(patch.object(api,name,operation))
            stack.enter_context(patch.object(api,'TRAINING_TASKS_DIR',f.root))
            with psycopg.connect(dsn,autocommit=True) as control:
                control.execute(postgres_ddl(schema))
                try:
                    with psycopg.connect(dsn) as connection:
                        f.repo=PostgresRuntimeRepository(connection,'test',schema)
                        snapshot={'pipeline':{'version':7,'secret_ref':'fixture-ref','prompt_version':'historical'}}
                        value={'job_id':'job','task_id':'canonical','remote_training_job_id':'remote','status':'completed','model_profiles':snapshot}
                        api.save_training_task(value)
                        result=api.delete_training_task_record('remote',f.user)
                        self.assertEqual(result['status'],'completed');self.assertIsNone(api.find_training_task('job'))
                        self.assertIs(f.tombstones['remote'],f.tombstones['job'])
                        late=api.update_training_task('remote',status='completed',model_profiles={})
                        self.assertEqual(late['status'],'stopped');self.assertEqual(late['model_profiles'],snapshot)
                        self.assertEqual(f.repo.count_rows(('training_tasks',))['training_tasks'],0)
                        active={'job_id':'active','task_id':'active-row','remote_training_job_id':'remote-active','status':'running','model_profiles':snapshot}
                        api.save_training_task(active);thread=Mock();thread.is_alive.return_value=True;f.threads['active']=thread
                        stopped=api.delete_training_task_record('remote-active',f.user)
                        self.assertEqual(stopped['status'],'stopped');self.assertFalse(stopped.get('delete_tombstone',False))
                        persisted=api.find_training_task('active');self.assertTrue(persisted['delete_tombstone'])
                        for identifier in ('active','remote-active'):
                            late=api.update_training_task(identifier,status='completed',model_profiles={})
                            self.assertEqual(late['status'],'stopped');self.assertEqual(late['model_profiles'],snapshot)
                        self.assertEqual(api.find_training_task('active')['status'],'stopped')
                        self.assertEqual(f.repo.count_rows(('training_tasks',))['training_tasks'],1)
                        self.assertEqual(list(f.root.iterdir()),[]);self.kill.assert_not_called()
                finally:control.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))


if __name__=='__main__':unittest.main()
