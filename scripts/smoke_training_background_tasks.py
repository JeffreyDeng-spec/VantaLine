"""Offline background process/task contracts; processes, threads, network and signals are substitutes."""
from contextlib import ExitStack
import copy
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, call, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.smoke_training_runner import Resolver
from local_inspection_service.model_profiles.snapshots import freeze_record


class BackgroundFixture:
    def __init__(self, root):
        self.root = Path(root); self.source = self.root / 'source.png'; self.source.write_bytes(b'synthetic image')
        self.sets = self.root / 'sets'; self.logs = self.root / 'logs'; self.logs.mkdir()
        self.resolver = Resolver(); self.events = []; self.saved = []; self.threads = {}; self.task_updates = []; self.meta_updates = []
        self.binding = {'model_profiles': {'pipeline': {'version': 7, 'secret_ref': 'synthetic-ref', 'prompt_version': 'old'}}}
        self.task = {'job_id': 'job', 'background_set_id': ' raw set ', 'source_path': str(self.source)}
        self.clock = Mock(return_value=101.9); self.uuid = Mock(return_value=SimpleNamespace(hex='abcdef1234'))
        self.safe = Mock(side_effect=lambda value: self.event('safe', value) or 'safe-set')
        self.path = Mock(side_effect=lambda identifier: self.event('path', identifier) or self.root / (identifier + '.json'))
        self.load = Mock(side_effect=lambda path: self.event('load', path) or self.task)
        self.find = Mock(side_effect=lambda identifier: self.event('find', identifier) or self.binding)
        self.update = Mock(side_effect=self.update_task); self.meta = Mock(side_effect=self.update_meta)
        self.local = Mock(side_effect=lambda *args: self.event('local', *args) or [self.root / ('local%d.png' % n) for n in range(5)])
        self.codex = Mock(side_effect=lambda *args: self.event('codex', *args) or [self.root / ('codex%d.png' % n) for n in range(5)])
        self.images = Mock(side_effect=lambda path: self.event('images', path) or [self.root / ('image%d.png' % n) for n in range(11)])
        self.owner = Mock(side_effect=lambda: self.event('owner') or {'owner_user_id': 'alice', 'owner_username': 'Alice'})
        self.save = Mock(side_effect=self.save_task); self.public = Mock(side_effect=lambda task: self.event('public', task) or task)
        self.thread = Mock(); self.thread.start.side_effect=lambda: self.event('start', dict(self.threads))
        self.factory = Mock(side_effect=lambda **kwargs: self.event('thread', kwargs) or self.thread)
    def event(self, name, *args): self.events.append((name, args, copy.deepcopy(self.resolver.current_snapshot())))
    def update_task(self, identifier, **values): self.event('update', identifier, values); self.task_updates.append(values); return None
    def update_meta(self, identifier, **values): self.event('meta', identifier, values); self.meta_updates.append(values); return {}
    def save_task(self, task):
        self.event('save', task); freeze_record(lambda: self.resolver, task); self.saved.append(task); self.binding = task; self.task = task
    def bind(self, api, stack):
        values={'ROOT': self.root, 'IMAGE_WORKER_LOG_DIR': self.logs, 'BACKGROUND_SETS_DIR': self.sets,
                'model_profile_service': self.resolver, 'find_training_task': self.find, 'training_task_path': self.path,
                'load_training_task': self.load, 'update_training_task': self.update, 'update_background_set_manifest': self.meta,
                'create_background_variants_from_source': self.local, 'image_file_list': self.images, 'safe_background_set_id': self.safe,
                'current_owner_fields': self.owner, 'save_training_task': self.save, 'public_training_task': self.public,
                '_training_task_threads': self.threads}
        for name, value in values.items(): stack.enter_context(patch.object(api, name, value))
        stack.enter_context(patch('time.time', self.clock)); stack.enter_context(patch('uuid.uuid4', self.uuid))
        stack.enter_context(patch.object(threading, 'Thread', self.factory))


class TrainingBackgroundTaskContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.environment=patch.dict(os.environ); cls.environment.start(); cls.runtime=tempfile.TemporaryDirectory(prefix='background-task-root-')
        root=Path(cls.runtime.name); (root / 'local_inspection_service/static').mkdir(parents=True)
        os.environ.update(LOCAL_INSPECTION_ROOT=str(root),VANTALINE_DATA_STORE='json',LOCAL_INSPECTION_AUTO_RESUME_WORKER='0',VANTALINE_LABEL_INSPECTION_ENABLED='false')
        from local_inspection_service import server
        cls.api=server
    @classmethod
    def tearDownClass(cls): cls.runtime.cleanup(); cls.environment.stop()
    def setUp(self):
        self.stack=ExitStack(); self.addCleanup(self.stack.close)
        self.f=BackgroundFixture(self.stack.enter_context(tempfile.TemporaryDirectory(prefix='background-task-'))); self.f.bind(self.api,self.stack)
        self.name=self.stack.enter_context(patch.object(self.api,'safe_name',side_effect=lambda value:value.replace(' ','_')))
        self.which=self.stack.enter_context(patch.object(shutil,'which',return_value='fake-codex'))
        self.process=Mock(returncode=17); self.popen=self.stack.enter_context(patch.object(subprocess,'Popen',return_value=self.process))
        for target in ['requests.request','os.kill']: self.stack.enter_context(patch(target,side_effect=AssertionError('unexpected external operation')))
    def run_task(self):
        with patch.object(self.api,'run_codex_background_generation',self.f.codex): self.api.run_background_set_task(job_id='job')
    def test_process_command_prompt_log_and_nonzero_exit_does_not_discard_outputs(self):
        f=self.f; directory=f.root/'generated'; outputs=[directory/('codex_raw_id_%02d.png'%n) for n in range(1,4)]
        def communicate(prompt, *, timeout):
            self.assertEqual(timeout,900); outputs[2].write_bytes(b'third'); outputs[0].write_bytes(b'first')
            self.assertFalse(self.popen.call_args.kwargs['stdout'].closed)
        self.process.communicate.side_effect=communicate
        result=self.api.run_codex_background_generation(f.source,directory,'raw id',3)
        self.assertEqual(result,[outputs[0],outputs[2]]); self.popen.assert_called_once(); self.process.communicate.assert_called_once(); self.process.kill.assert_not_called()
        command=self.popen.call_args.args[0]
        self.assertEqual(command,['codex','exec','--sandbox','workspace-write','-C',str(f.root),'-i',str(f.source),'-'])
        self.assertEqual({key:value for key,value in self.popen.call_args.kwargs.items() if key!='stdout'},
                         {'cwd':str(f.root),'stdin':subprocess.PIPE,'stderr':subprocess.STDOUT,'text':True})
        log=self.popen.call_args.kwargs['stdout']; self.assertTrue(log.closed); self.assertEqual(Path(log.name),f.logs/'background_raw_id_codexcli.log')
        expected='\n'.join(['You are the ImageWorker for the local assembly-line inspection service.','',
            'Use the attached reference image as the source environment. Generate realistic, empty, overhead-view background PNGs of the same surface type and same environment. Keep camera geometry, material texture, scratches, dust, lighting, rails/edges if present, and mild natural variation. Do not add objects, text, labels, watermarks, hands, people, manuals, bottles, tools, or parts.','',
            'Save the final PNG files exactly here:',*[str(path) for path in outputs]])+'\n'
        self.assertEqual(self.process.communicate.call_args.args,(expected,))
    def test_process_unavailable_short_circuit_and_nonpositive_count_still_launches(self):
        f=self.f; self.which.return_value=None
        with patch.object(Path,'exists',side_effect=AssertionError('must short circuit')):
            self.assertEqual(self.api.run_codex_background_generation(f.source,f.root/'none','x'),[])
        self.popen.assert_not_called(); self.assertFalse((f.root/'none').exists())
        self.which.return_value='fake'; self.assertEqual(self.api.run_codex_background_generation(f.root/'missing',f.root/'none','x'),[]); self.popen.assert_not_called()
        self.assertEqual(self.api.run_codex_background_generation(f.source,f.root/'zero','x',0),[])
        self.assertTrue((f.root/'zero').is_dir()); self.popen.assert_called_once(); self.process.communicate.assert_called_once()
    def test_process_timeout_preserves_existing_outputs_kills_once_and_does_not_retry(self):
        f=self.f; directory=f.root/'timeout'; directory.mkdir(); output=directory/'codex_x_01.png'; output.write_bytes(b'partial')
        self.process.communicate.side_effect=[subprocess.TimeoutExpired('fake',900),None]; self.process.kill.side_effect=OSError('kill')
        self.assertEqual(self.api.run_codex_background_generation(f.source,directory,'x'),[output])
        self.popen.assert_called_once(); self.process.communicate.assert_called_once(); self.process.kill.assert_called_once()
        self.assertTrue(self.popen.call_args.kwargs['stdout'].closed); self.assertEqual(output.read_bytes(),b'partial')
    def test_process_generic_error_returns_empty_but_preserves_files_and_precall_errors_propagate(self):
        f=self.f; directory=f.root/'generic'; directory.mkdir(); output=directory/'codex_x_01.png'; output.write_bytes(b'partial')
        self.process.communicate.side_effect=[OSError('communicate'),None]
        self.assertEqual(self.api.run_codex_background_generation(f.source,directory,'x'),[]); self.popen.assert_called_once(); self.process.kill.assert_not_called()
        self.assertTrue(output.exists()); self.process.communicate.assert_called_once()
        self.popen.reset_mock(); self.which.side_effect=OSError('which')
        with self.assertRaisesRegex(OSError,'which'): self.api.run_codex_background_generation(f.source,directory,'x')
        self.popen.assert_not_called(); self.which.side_effect=None
        with patch.object(Path,'mkdir',side_effect=OSError('mkdir')):
            with self.assertRaisesRegex(OSError,'mkdir'): self.api.run_codex_background_generation(f.source,directory,'x')
        self.popen.assert_not_called()
    def test_process_log_open_and_spawn_failure_have_no_retry_or_signal(self):
        f=self.f; self.logs=f.root/'missing-log-dir'
        with patch.object(self.api,'IMAGE_WORKER_LOG_DIR',self.logs):
            self.assertEqual(self.api.run_codex_background_generation(f.source,f.root/'created','x'),[])
        self.assertTrue((f.root/'created').exists()); self.popen.assert_not_called(); self.assertFalse(self.logs.exists())
        self.popen.side_effect=[OSError('spawn'),self.process]
        self.assertEqual(self.api.run_codex_background_generation(f.source,f.root/'spawn','x'),[])
        self.popen.assert_called_once(); self.process.communicate.assert_not_called(); self.process.kill.assert_not_called()
    def test_start_codex_thread_exact_target_args_name_and_start_failure(self):
        f=self.f; self.api.start_codex_background_generation(f.source,f.sets,'raw id',3)
        f.factory.assert_called_once_with(target=self.api.run_codex_background_generation,args=(f.source,f.sets,'raw id',3),name='codex-background-worker-raw_id',daemon=True)
        f.thread.start.assert_called_once(); self.popen.assert_not_called()
        f.factory.reset_mock(); f.thread.start.reset_mock(); f.thread.start.side_effect=[OSError('start'),None]
        with self.assertRaisesRegex(OSError,'start'): self.api.start_codex_background_generation(f.source,f.sets,'raw id')
        f.factory.assert_called_once(); f.thread.start.assert_called_once()
    def test_runner_snapshot_binding_success_and_precise_state_order(self):
        f=self.f; original=copy.deepcopy(f.binding); f.resolver.version=99; f.clock.side_effect=[11,22,33,44,55]
        self.run_task()
        self.assertEqual([event[0] for event in f.events],['find','path','load','safe','update','meta','local','update','codex','images','meta','update'])
        f.find.assert_called_once_with('job'); f.path.assert_called_once_with('job'); f.load.assert_called_once_with(f.root/'job.json')
        self.assertEqual(f.resolver.scopes,[original['model_profiles']]); self.assertEqual(f.binding,original); self.assertEqual(f.resolver.records,[])
        self.assertTrue(all(event[2]==original['model_profiles'] for event in f.events[1:])); self.assertIsNone(f.resolver.current_snapshot())
        f.local.assert_called_once_with(f.source,f.sets/'safe-set',5); f.codex.assert_called_once_with(f.source,f.sets/'safe-set',' raw set ',5)
        self.assertEqual(f.task_updates,[{'status':'running','progress':8,'started_at':11,'note':'背景任务已启动，正在准备源图。'},
            {'status':'running','progress':42,'generated_image_count':6,'note':'本地背景变体已生成 5/5，正在等待 AI 背景生成。'},
            {'status':'completed','progress':100,'completed_at':55,'generated_image_count':11,'note':'背景集已生成完成，共 11 张。'}])
        self.assertEqual(f.meta_updates,[{'status':'generating','updated_at':22},
            {'status':'ready','generation_method':'queued_codexcli_imgworker_plus_local_same_environment_fallback','image_count':11,'completed_at':33,'updated_at':44}])
    def test_runner_missing_dependencies_and_load_failure_stay_outside_failure_settlement(self):
        f=self.f
        with patch.object(self.api,'model_profile_service',None):
            with self.assertRaisesRegex(RuntimeError,'Model profile resolver is not configured'): self.run_task()
        f.find.assert_not_called(); f.load.assert_not_called()
        f.find.side_effect=[OSError('find'),f.binding]
        with self.assertRaisesRegex(OSError,'find'): self.run_task()
        f.find.assert_called_once(); f.load.assert_not_called(); f.find.side_effect=lambda identity:f.binding
        f.load.side_effect=[OSError('load'),f.task]
        with self.assertRaisesRegex(OSError,'load'): self.run_task()
        f.load.assert_called_once(); f.update.assert_not_called(); f.meta.assert_not_called(); f.local.assert_not_called(); self.assertIsNone(f.resolver.current_snapshot())
    def test_runner_missing_task_and_pretry_path_failure(self):
        f=self.f; f.load.side_effect=lambda path:None; self.run_task(); f.safe.assert_not_called(); f.update.assert_not_called()
        f.load.side_effect=lambda path:f.task; f.safe.side_effect=[OSError('safe'), 'safe-set']
        with self.assertRaisesRegex(OSError,'safe'): self.run_task()
        f.safe.assert_called_once(); f.meta.assert_not_called(); f.update.assert_not_called(); f.local.assert_not_called()
    def test_runner_missing_source_and_insufficient_outputs_settle_failed_without_retry(self):
        f=self.f
        for stage in ['source','local','codex']:
            with self.subTest(stage=stage):
                f.task['source_path']=str(f.root/'missing') if stage=='source' else str(f.source)
                for mock in [f.local,f.codex,f.images,f.meta,f.update]: mock.reset_mock()
                f.local.side_effect=lambda *args:[Path('local')]* (4 if stage=='local' else 5)
                f.codex.side_effect=lambda *args:[Path('codex')]*4
                f.task_updates.clear(); f.meta_updates.clear(); self.run_task()
                expected={'source':'上传的背景源图不存在。','local':'本地背景变体生成不足：4/5。','codex':'AI 背景生成不足：4/5。'}[stage]
                self.assertEqual(f.task_updates[-1],{'status':'failed','progress':100,'completed_at':101,'error':expected,'note':'背景生成失败：'+expected})
                self.assertEqual(f.meta_updates[-1],{'status':'failed','error':expected,'updated_at':101}); f.images.assert_not_called()
                self.assertEqual(f.local.call_count,int(stage!='source')); self.assertEqual(f.codex.call_count,int(stage=='codex'))
    def test_runner_unknown_provider_error_is_not_retried_and_failure_writer_can_mask_it(self):
        f=self.f; error=OSError('unknown paid result'); f.codex.side_effect=[error,[Path('ok')]*5]
        self.run_task(); f.codex.assert_called_once(); f.images.assert_not_called()
        self.assertEqual(f.meta_updates[-1]['error'],'unknown paid result'); self.assertEqual(f.task_updates[-1]['status'],'failed')
        f.codex.reset_mock(); f.codex.side_effect=[error,[Path('ok')]*5]; f.meta.reset_mock(); f.update.reset_mock()
        original=f.meta.side_effect
        def fail_failed(identifier,**values):
            if values.get('status')=='failed': raise RuntimeError('settlement write')
            return original(identifier,**values)
        f.meta.side_effect=fail_failed
        with self.assertRaisesRegex(RuntimeError,'settlement write'): self.run_task()
        f.codex.assert_called_once(); self.assertEqual(f.meta.call_count,2)
        self.assertFalse(any(c.kwargs.get('status')=='failed' for c in f.update.call_args_list)); self.assertIsNone(f.resolver.current_snapshot())
    def test_submission_order_snapshot_freeze_and_restart_uses_original_version(self):
        f=self.f; f.clock.side_effect=[11,22]; result=self.api.enqueue_background_set_task(' raw_set ','',f.source)
        identifier='background_11_abcdef'; self.assertIs(result,f.saved[0])
        expected={'job_id':identifier,'task_id':identifier,'candidate_id':identifier,'candidate_name':' raw set ',
            'label':'添加背景： raw set ','queue_kind':'training','action':'generate_background_set','status':'queued','progress':0,
            'created_at':22,'background_set_id':' raw_set ','source_path':str(f.source),'sample_count':0,'estimated_minutes':10,
            'note':'背景生成任务已加入队列；完成前该背景集不会进入可选列表。','owner_user_id':'alice','owner_username':'Alice',
            'model_profiles':{'pipeline':{'version':1}}}
        self.assertEqual(result,expected); self.assertEqual([e[0] for e in f.events],['owner','save','thread','start','public'])
        f.factory.assert_called_once_with(target=self.api.run_background_set_task,args=(identifier,),daemon=True,name='background-set-task-'+identifier)
        self.assertIs(f.threads[identifier],f.thread); self.assertEqual(f.events[3][1],({identifier:f.thread},))
        f.clock.side_effect=None; f.resolver.version=99; f.events.clear()
        with patch.object(self.api,'run_codex_background_generation',f.codex): f.factory.call_args.kwargs['target'](*f.factory.call_args.kwargs['args'])
        self.assertEqual(f.resolver.scopes,[{'pipeline':{'version':1}}]); self.assertEqual(result,expected)
    def test_submission_owner_overrides_and_failed_public_keeps_saved_started_task(self):
        f=self.f; f.owner.side_effect=lambda:{'job_id':'owner-job','status':'owner-status','created_at':77}; f.public.side_effect=[OSError('public'),{'ok':True}]
        with self.assertRaisesRegex(OSError,'public'): self.api.enqueue_background_set_task('set','   ',f.source)
        self.assertEqual(len(f.saved),1); self.assertEqual((f.saved[0]['job_id'],f.saved[0]['status'],f.saved[0]['created_at']),('owner-job','owner-status',77))
        self.assertEqual(f.saved[0]['candidate_name'],'   '); self.assertEqual(f.saved[0]['label'],'添加背景：   ')
        self.assertEqual(list(f.threads),['background_101_abcdef']); f.factory.assert_called_once(); f.thread.start.assert_called_once(); f.public.assert_called_once()
    def test_submission_save_thread_and_start_failures_preserve_order_without_retry(self):
        f=self.f
        for stage in ['save','thread','start']:
            with self.subTest(stage=stage),ExitStack() as stack:
                f.events.clear(); f.saved.clear(); f.threads.clear()
                for mock in [f.save,f.factory,f.thread.start,f.public]: mock.reset_mock()
                target={'save':f.save,'thread':f.factory,'start':f.thread.start}[stage]; prior=target.side_effect
                count=0
                def fail_first(*args,**kwargs):
                    nonlocal count
                    count+=1
                    if count==1: raise OSError(stage)
                    return prior(*args,**kwargs)
                target.side_effect=fail_first; stack.callback(setattr,target,'side_effect',prior)
                with self.assertRaisesRegex(OSError,stage): self.api.enqueue_background_set_task('set','name',f.source)
                self.assertEqual(count,1); f.public.assert_not_called(); self.assertEqual(len(f.saved),int(stage!='save'))
                self.assertEqual(f.factory.call_count,int(stage!='save')); self.assertEqual(f.thread.start.call_count,int(stage=='start'))
                self.assertEqual(bool(f.threads),stage=='start')


    def test_process_name_reads_are_distinct_and_baseexceptions_are_not_swallowed(self):
        f=self.f; directory=f.root/'named'; self.name.side_effect=['log-name','first-name','second-name']
        self.api.run_codex_background_generation(f.source,directory,'raw',2)
        self.assertEqual(self.name.call_args_list,[call('raw')]*3)
        self.assertEqual(Path(self.popen.call_args.kwargs['stdout'].name),f.logs/'background_log-name_codexcli.log')
        prompt=self.process.communicate.call_args.args[0]
        self.assertTrue(prompt.endswith(str(directory/'codex_first-name_01.png')+'\n'+str(directory/'codex_second-name_02.png')+'\n'))
        self.name.side_effect=lambda value:value; self.process.communicate.side_effect=KeyboardInterrupt('cancel')
        with self.assertRaises(KeyboardInterrupt): self.api.run_codex_background_generation(f.source,directory,'x')
        self.process.kill.assert_not_called()
        self.process.communicate.side_effect=subprocess.TimeoutExpired('fake',900); self.process.kill.side_effect=KeyboardInterrupt('kill-cancel')
        with self.assertRaisesRegex(KeyboardInterrupt,'kill-cancel'): self.api.run_codex_background_generation(f.source,directory,'x')
        self.process.kill.assert_called_once()
    def test_thread_targets_and_registry_are_read_at_original_evaluation_points(self):
        f=self.f; original=self.api.run_codex_background_generation; replacement=Mock()
        def naming(value): self.api.run_codex_background_generation=replacement; return 'late-name'
        with patch.object(self.api,'run_codex_background_generation',original):
            self.name.side_effect=naming; self.api.start_codex_background_generation(f.source,f.sets,'raw')
        self.assertIs(f.factory.call_args.kwargs['target'],original); replacement.assert_not_called()
        f.factory.reset_mock(); f.thread.start.reset_mock(); original_save=f.save.side_effect
        target=Mock(); newer_target=Mock(); replacement_registry={}
        def save(task): original_save(task); self.api.run_background_set_task=target
        def factory(**kwargs): self.api._training_task_threads=replacement_registry; self.api.run_background_set_task=newer_target; return f.thread
        with patch.object(self.api,'run_background_set_task',self.api.run_background_set_task),patch.object(self.api,'_training_task_threads',f.threads):
            f.save.side_effect=save; f.factory.side_effect=factory
            self.api.enqueue_background_set_task('set','name',f.source)
        self.assertIs(f.factory.call_args.kwargs['target'],target); self.assertEqual(f.threads,{})
        self.assertEqual(replacement_registry,{'background_101_abcdef':f.thread}); f.thread.start.assert_called_once(); target.assert_not_called(); newer_target.assert_not_called()
    def test_runner_each_stage_error_preserves_settlement_order_without_retry(self):
        f=self.f
        stages=['start','generating','local','progress','codex','images','ready','completed']
        for stage in stages:
            with self.subTest(stage=stage),ExitStack() as stack:
                f.events.clear(); f.task_updates.clear(); f.meta_updates.clear()
                for mock in [f.update,f.meta,f.local,f.codex,f.images]: mock.reset_mock()
                target={'start':f.update,'generating':f.meta,'local':f.local,'progress':f.update,
                        'codex':f.codex,'images':f.images,'ready':f.meta,'completed':f.update}[stage]
                previous=target.side_effect; error=OSError(stage); hits=[]
                def fail_first(*args,**kwargs):
                    match={'start':kwargs.get('progress')==8,'generating':kwargs.get('status')=='generating',
                           'progress':kwargs.get('progress')==42,'ready':kwargs.get('status')=='ready',
                           'completed':kwargs.get('status')=='completed'}.get(stage,True)
                    result=previous(*args,**kwargs)
                    if match:
                        hits.append(stage)
                        if len(hits)==1: raise error
                    return result
                target.side_effect=fail_first; stack.callback(setattr,target,'side_effect',previous)
                self.run_task(); self.assertEqual(hits,[stage])
                self.assertEqual(f.events[-2][0],'meta'); self.assertEqual(f.events[-2][1][1]['status'],'failed')
                self.assertEqual(f.events[-1][0],'update'); self.assertEqual(f.events[-1][1][1]['status'],'failed')
                self.assertEqual(f.events[-1][1][1]['error'],stage)
                index=stages.index(stage); self.assertEqual(f.local.call_count,int(index>=2))
                self.assertEqual(f.codex.call_count,int(index>=4)); self.assertEqual(f.images.call_count,int(index>=5))
                self.assertEqual([v['status'] for v in f.meta_updates],
                    (['generating'] if index>=1 else [])+(['ready'] if index>=6 else [])+['failed'])
                self.assertIsNone(f.resolver.current_snapshot())
    def test_runner_old_snapshot_fallback_to_current_scope_or_one_fresh_snapshot(self):
        f=self.f; f.binding={}; f.resolver.version=23; self.run_task()
        self.assertEqual(f.resolver.records,[{}]); self.assertEqual(f.resolver.scopes,[{'pipeline':{'version':23}}])
        f.resolver.scopes.clear(); f.resolver.records.clear(); active={'pipeline':{'version':11}}
        with f.resolver.scope(active):
            self.run_task(); self.assertIs(f.resolver.current_snapshot(),active)
        self.assertEqual(f.resolver.records,[]); self.assertEqual(f.resolver.scopes,[active,active]); self.assertIsNone(f.resolver.current_snapshot())
    def test_submission_registry_write_failure_leaves_saved_task_and_unstarted_thread(self):
        f=self.f; error=OSError('registry'); writes=[]
        class BrokenRegistry(dict):
            def __setitem__(self,key,value):
                writes.append((key,value))
                if len(writes)==1: raise error
                return super().__setitem__(key,value)
        registry=BrokenRegistry()
        with patch.object(self.api,'_training_task_threads',registry):
            with self.assertRaises(OSError) as caught: self.api.enqueue_background_set_task('set','name',f.source)
        self.assertIs(caught.exception,error); self.assertEqual(writes,[('background_101_abcdef',f.thread)])
        self.assertEqual(len(f.saved),1); f.factory.assert_called_once(); f.thread.start.assert_not_called(); f.public.assert_not_called(); self.assertEqual(registry,{})


    def test_failed_task_settlement_error_propagates_once_after_failed_manifest_and_restores_scope(self):
        f=self.f; provider_error=OSError('unknown generation result'); error=OSError('failed-task write')
        f.codex.side_effect=[provider_error,[Path('would succeed')]*5]
        failed=[]; persisted={}; update=f.update.side_effect; meta=f.meta.side_effect
        def persist_meta(identifier,**values): persisted.update(values); return meta(identifier,**values)
        def fail_once(identifier,**values):
            result=update(identifier,**values)
            if values.get('status')=='failed':
                failed.append((identifier,copy.deepcopy(f.resolver.current_snapshot())))
                if len(failed)==1: raise error
            return result
        f.meta.side_effect=persist_meta; f.update.side_effect=fail_once
        outer={'pipeline':{'version':88}}
        with f.resolver.scope(outer):
            with self.assertRaises(OSError) as caught: self.run_task()
            self.assertIs(caught.exception,error); self.assertIs(f.resolver.current_snapshot(),outer)
        self.assertIsNone(f.resolver.current_snapshot()); self.assertEqual(failed,[('job',f.binding['model_profiles'])])
        self.assertEqual(f.resolver.scopes,[outer,f.binding['model_profiles']])
        self.assertEqual(persisted,{'status':'failed','error':'unknown generation result','updated_at':101})
        self.assertEqual([values['status'] for values in f.meta_updates],['generating','failed'])
        self.assertEqual([values['status'] for values in f.task_updates],['running','running','failed'])
        self.assertEqual([event[0] for event in f.events[-2:]],['meta','update'])
        f.local.assert_called_once(); f.codex.assert_called_once(); f.images.assert_not_called()
        self.assertEqual(f.meta.call_count,2); self.assertEqual(f.update.call_count,3)

    def test_independent_compositions_real_files_snapshots_and_no_constructor_reads(self):
        import cv2
        import json
        import numpy as np
        from contextvars import Context, ContextVar
        from uuid import UUID
        from local_inspection_service.training.background_codex import CodexBackgroundPaths, CodexBackgroundGeneration, CodexBackgroundThread
        from local_inspection_service.training.background_task_runner import BackgroundTaskRecords, BackgroundTaskGeneration, BackgroundTaskRunner
        from local_inspection_service.training.background_task_submission import BackgroundTaskSubmission
        from local_inspection_service.training.background_manifest import BackgroundManifest
        from local_inspection_service.training.background_catalog import BackgroundImageFiles, safe_background_set_id
        from local_inspection_service.training.background_writes import BackgroundWrites
        from local_inspection_service.training.background_variants import BackgroundVariants
        from local_inspection_service.training.submission import TrainingSubmissionRecords, TrainingSubmissionThreads
        identity=ContextVar('background-request-owner',default=None)
        def build(owner,stamp,version):
            root=self.f.root/owner; root.mkdir(); sets=root/'sets'; logs=root/'logs'; logs.mkdir()
            source=root/'source.png'; self.assertTrue(cv2.imwrite(str(source),np.full((31,47,3),version*10,dtype=np.uint8)))
            resolver=Resolver(); resolver.version=version; callbacks=[]; threads={}; observations=[]; processes=[]
            def port(fn): value=Mock(side_effect=fn); callbacks.append(value); return value
            def path(identifier): return root/(identifier+'.json')
            def read(target): return json.loads(target.read_text(encoding='utf-8'))
            def update(identifier,**values):
                task=read(path(identifier)); task.update(values); path(identifier).write_text(json.dumps(task),encoding='utf-8')
                observations.append((identity.get(),copy.deepcopy(resolver.current_snapshot())))
                return task
            def save(task): freeze_record(lambda:resolver,task); path(task['job_id']).write_text(json.dumps(task),encoding='utf-8')
            class FakeThread:
                def __init__(self,**kwargs): self.kwargs=kwargs; self.started=False
                def start(self): self.started=True
            class FakeProcess:
                def __init__(self,command,**kwargs): self.command=command; self.kwargs=kwargs; self.prompts=[]; processes.append(self)
                def communicate(self,prompt,*,timeout):
                    self.prompts.append((prompt,timeout,copy.deepcopy(resolver.current_snapshot()),identity.get()))
                    self_outer.assertFalse(self.kwargs['stdout'].closed)
                    for item in prompt.split('Save the final PNG files exactly here:\n',1)[1].splitlines():
                        output=Path(item); self_outer.assertTrue(output.resolve().is_relative_to(root.resolve())); output.write_bytes(owner.encode())
                    return None,None
                def kill(self): raise AssertionError('unexpected signal')
            self_outer=self
            clock=port(lambda:stamp); uuid=port(lambda:UUID('abcdef00-0000-0000-0000-000000000000'))
            manifest=BackgroundManifest(port(lambda:root),port(lambda:root/'manifest.json'))
            images=BackgroundImageFiles(port(lambda:{'.png'})); local=BackgroundVariants(clock)
            writes=BackgroundWrites(port(safe_background_set_id),port(manifest.load_background_sets_manifest),port(manifest.write_background_sets_manifest),port(lambda:sets),uuid,clock)
            codex=CodexBackgroundGeneration(port(lambda command:'fake-'+owner),CodexBackgroundPaths(port(lambda:logs),port(lambda:root)),port(lambda identifier:owner),port(lambda:FakeProcess))
            runner=BackgroundTaskRunner(BackgroundTaskRecords(port(lambda identifier:read(path(identifier))),port(path),port(lambda:read),port(lambda: update)),
                BackgroundTaskGeneration(port(lambda:sets),port(safe_background_set_id),port(lambda: writes.update_background_set_manifest),port(local.create_background_variants_from_source),port(codex.run_codex_background_generation),port(images.image_file_list)),clock,port(lambda:resolver))
            factory=port(FakeThread)
            starter=CodexBackgroundThread(port(lambda:factory),port(lambda:codex.run_codex_background_generation),port(lambda identifier:owner))
            submission=BackgroundTaskSubmission(TrainingSubmissionRecords(port(save),port(lambda task:task)),
                TrainingSubmissionThreads(port(lambda:runner.run_background_set_task),factory,port(lambda:threads)),
                port(lambda:{'owner_user_id':identity.get()}),clock,uuid)
            for callback in callbacks: callback.assert_not_called()
            self.assertFalse((root/'manifest.json').exists()); self.assertFalse(sets.exists())
            return SimpleNamespace(owner=owner,stamp=stamp,version=version,root=root,sets=sets,logs=logs,source=source,
                resolver=resolver,threads=threads,processes=processes,observations=observations,submission=submission,
                runner=runner,starter=starter,factory=factory,manifest=manifest,codex=codex)
        instances=[build('alice',101,7),build('bob',202,8)]
        for name in ['safe_name','find_training_task','training_task_path','load_training_task','update_training_task','save_training_task',
                     'public_training_task','current_owner_fields','create_background_variants_from_source','update_background_set_manifest',
                     'image_file_list','safe_background_set_id','run_codex_background_generation','run_background_set_task']:
            self.stack.enter_context(patch.object(self.api,name,side_effect=AssertionError('unexpected root dependency')))
        for index in [1,0]:
            item=instances[index]; token=identity.set(item.owner)
            try: result=item.submission.enqueue_background_set_task(item.owner,'',item.source)
            finally: identity.reset(token)
            item.identifier='background_%d_abcdef'%item.stamp; self.assertEqual(result['job_id'],item.identifier)
            self.assertEqual(result['owner_user_id'],item.owner); self.assertEqual(result['model_profiles'],{'pipeline':{'version':item.version}})
            self.assertEqual(list(item.threads),[item.identifier]); self.assertTrue(item.threads[item.identifier].started)
            self.assertEqual(item.processes,[]); item.resolver.version=99
        for index in [1,0,1,0]:
            item=instances[index]; thread=item.threads[item.identifier]
            Context().run(thread.kwargs['target'],*thread.kwargs['args'])
            task=json.loads((item.root/(item.identifier+'.json')).read_text(encoding='utf-8'))
            self.assertEqual((task['owner_user_id'],task['status'],task['generated_image_count']),(item.owner,'completed',10))
            self.assertEqual(item.resolver.scopes[-1],{'pipeline':{'version':item.version}}); self.assertIsNone(item.resolver.current_snapshot())
            self.assertTrue(all(owner is None and snapshot=={'pipeline':{'version':item.version}} for owner,snapshot in item.observations))
            self.assertEqual(list(item.manifest.load_background_sets_manifest()['sets']),[item.owner])
            self.assertEqual(item.manifest.load_background_sets_manifest()['sets'][item.owner]['status'],'ready')
            process=item.processes[-1]; self.assertEqual(process.kwargs['cwd'],str(item.root)); self.assertTrue(process.kwargs['stdout'].closed)
            self.assertEqual(process.command[5],str(item.root)); self.assertEqual(process.prompts[0][1:],(900,{'pipeline':{'version':item.version}},None))
            self.assertEqual(len(item.resolver.scopes),len(item.processes)); self.assertEqual(len(item.resolver.records),1)
            for path in (item.sets/item.owner).glob('codex_*.png'): self.assertEqual(path.read_bytes(),item.owner.encode())
        for item in instances:
            item.starter.start_codex_background_generation(item.source,item.sets,item.owner,2)
            started=item.factory.call_args.kwargs
            self.assertEqual(started['target'],item.codex.run_codex_background_generation)
            self.assertEqual(started['args'],(item.source,item.sets,item.owner,2)); self.assertEqual(started['name'],'codex-background-worker-'+item.owner)


    def test_runner_captures_each_writer_before_clock_and_length_arguments(self):
        for stage in ['task-start', 'manifest-start', 'manifest-end1', 'manifest-end2', 'task-end', 'length-count', 'length-note']:
            with self.subTest(stage=stage), ExitStack() as stack:
                f=BackgroundFixture(stack.enter_context(tempfile.TemporaryDirectory(prefix='background-capture-'))); f.bind(self.api,stack)
                task_next=Mock(side_effect=f.update_task); meta_next=Mock(side_effect=f.update_meta)
                times=[]; lengths=[]
                def clock():
                    times.append(len(times)+1)
                    if stage in {'task-start':1,'task-end':5} and len(times)=={'task-start':1,'task-end':5}[stage]: self.api.update_training_task=task_next
                    if stage in {'manifest-start':2,'manifest-end1':3,'manifest-end2':4} and len(times)=={'manifest-start':2,'manifest-end1':3,'manifest-end2':4}[stage]: self.api.update_background_set_manifest=meta_next
                    return times[-1]*11.9
                class Variants:
                    def __len__(inner):
                        lengths.append(len(lengths)+1)
                        if len(lengths)=={'length-count':2,'length-note':3}.get(stage): self.api.update_training_task=task_next
                        return 5
                f.clock.side_effect=clock; f.local.side_effect=lambda *args:Variants()
                with patch.object(self.api,'run_codex_background_generation',f.codex): self.api.run_background_set_task('job')
                self.assertEqual(times,[1,2,3,4,5]); self.assertEqual(lengths,[1,2,3])
                self.assertEqual(f.task_updates,[{'status':'running','progress':8,'started_at':11,'note':'背景任务已启动，正在准备源图。'},
                    {'status':'running','progress':42,'generated_image_count':6,'note':'本地背景变体已生成 5/5，正在等待 AI 背景生成。'},
                    {'status':'completed','progress':100,'completed_at':59,'generated_image_count':11,'note':'背景集已生成完成，共 11 张。'}])
                self.assertEqual(f.meta_updates,[{'status':'generating','updated_at':23},
                    {'status':'ready','generation_method':'queued_codexcli_imgworker_plus_local_same_environment_fallback','image_count':11,'completed_at':35,'updated_at':47}])
                self.assertEqual(f.update.call_count,1 if stage=='task-start' else 2 if stage.startswith('length') else 3)
                self.assertEqual(task_next.call_count,2 if stage=='task-start' else 1 if stage.startswith('length') else 0)
                self.assertEqual(f.meta.call_count,1 if stage=='manifest-start' else 2); self.assertEqual(meta_next.call_count,int(stage=='manifest-start'))
                self.assertIsNone(f.resolver.current_snapshot()); f.local.assert_called_once(); f.codex.assert_called_once()
                # A subsequent invocation must observe the replacement; no constructor/entry cache.
                self.api.update_training_task=task_next; self.api.update_background_set_manifest=meta_next
                task_next.reset_mock(); meta_next.reset_mock(); f.clock.side_effect=None; f.local.side_effect=lambda *args:[Path('local')]*5
                with patch.object(self.api,'run_codex_background_generation',f.codex): self.api.run_background_set_task('job')
                self.assertEqual(task_next.call_count,3); self.assertEqual(meta_next.call_count,2)

    def test_runner_captures_after_load_and_generation_before_each_write(self):
        f=self.f; second=Mock(side_effect=f.update_task); third=Mock(side_effect=f.update_task)
        meta_second=Mock(side_effect=f.update_meta); meta_third=Mock(side_effect=f.update_meta)
        def load(path): self.api.update_training_task=second; self.api.update_background_set_manifest=meta_second; return f.task
        def local(*args): self.api.update_training_task=third; return [Path('local')]*5
        def images(path): self.api.update_background_set_manifest=meta_third; return [Path('image')]*11
        f.load.side_effect=load; f.local.side_effect=local; f.images.side_effect=images; self.run_task()
        f.update.assert_not_called(); f.meta.assert_not_called(); self.assertEqual(second.call_count,1); self.assertEqual(third.call_count,2)
        meta_second.assert_called_once_with(' raw set ',status='generating',updated_at=101)
        meta_third.assert_called_once_with(' raw set ',status='ready',generation_method='queued_codexcli_imgworker_plus_local_same_environment_fallback',image_count=11,completed_at=101,updated_at=101)
        self.assertIsNone(f.resolver.current_snapshot())

    def test_runner_failed_writes_capture_before_three_error_reads_and_two_clocks(self):
        f=self.f; second_meta=Mock(side_effect=f.update_meta); second_task=Mock(side_effect=f.update_task); third_task=Mock(side_effect=f.update_task); reads=[]
        class Failure(RuntimeError):
            def __str__(inner):
                reads.append(len(reads)+1)
                if len(reads)==1: self.api.update_background_set_manifest=second_meta
                elif len(reads)==2: self.api.update_training_task=second_task
                else: self.api.update_training_task=third_task
                return 'error-'+str(len(reads))
        f.local.side_effect=Failure(); self.run_task()
        self.assertEqual(reads,[1,2,3]); self.assertEqual(f.clock.call_count,4)
        self.assertEqual(f.meta_updates,[{'status':'generating','updated_at':101},{'status':'failed','error':'error-1','updated_at':101}])
        self.assertEqual(f.task_updates[-1],{'status':'failed','progress':100,'completed_at':101,'error':'error-2','note':'背景生成失败：error-3'})
        self.assertEqual(f.meta.call_count,2); self.assertEqual(f.update.call_count,2)
        second_meta.assert_not_called(); second_task.assert_not_called(); third_task.assert_not_called(); f.codex.assert_not_called()
        self.assertIsNone(f.resolver.current_snapshot())
        for stage in ['manifest-clock','task-clock','manifest-string-error','task-error-error','task-note-error']:
            with self.subTest(stage=stage), ExitStack() as stack:
                f=BackgroundFixture(stack.enter_context(tempfile.TemporaryDirectory(prefix='background-failure-'))); f.bind(self.api,stack)
                late_meta=Mock(side_effect=f.update_meta); late_task=Mock(side_effect=f.update_task); strings=[]; clocks=[]
                class Failure(RuntimeError):
                    def __str__(inner):
                        strings.append(len(strings)+1)
                        if len(strings)=={'manifest-string-error':1,'task-error-error':2,'task-note-error':3}.get(stage): raise OSError('format failure')
                        return 'unknown result'
                def clock():
                    clocks.append(len(clocks)+1)
                    if len(clocks)==3 and stage=='manifest-clock': self.api.update_background_set_manifest=late_meta
                    if len(clocks)==4 and stage=='task-clock': self.api.update_training_task=late_task
                    return 101.9
                f.clock.side_effect=clock; f.local.side_effect=Failure()
                if stage.endswith('error'):
                    with self.assertRaisesRegex(OSError,'format failure'): self.api.run_background_set_task('job')
                    self.assertEqual(len(strings),{'manifest-string-error':1,'task-error-error':2,'task-note-error':3}[stage])
                    self.assertEqual(f.update.call_count,1); self.assertEqual(f.meta.call_count,1 if stage=='manifest-string-error' else 2)
                    self.assertEqual(len(clocks),2 if stage=='manifest-string-error' else 4)
                else:
                    self.api.run_background_set_task('job'); self.assertEqual(f.update.call_count,2); self.assertEqual(f.meta.call_count,2)
                late_meta.assert_not_called(); late_task.assert_not_called(); self.assertIsNone(f.resolver.current_snapshot()); f.local.assert_called_once()

    def test_runner_noncallable_target_still_evaluates_clock_then_settles_without_retry(self):
        f=self.f; self.api.update_training_task=None
        def clock(): self.api.update_training_task=f.update; return 101.9
        f.clock.side_effect=clock; self.run_task()
        self.assertEqual(f.clock.call_count,3); f.update.assert_called_once_with('job',status='failed',progress=100,completed_at=101,error="'NoneType' object is not callable",note="背景生成失败：'NoneType' object is not callable")
        f.meta.assert_called_once_with(' raw set ',status='failed',error="'NoneType' object is not callable",updated_at=101)
        f.local.assert_not_called(); f.codex.assert_not_called(); self.assertIsNone(f.resolver.current_snapshot())


    def test_provider_lookup_runner_errors_keep_catch_order_and_restore_model_scope(self):
        from local_inspection_service.training.background_task_runner import BackgroundTaskRunner, BackgroundTaskRecords, BackgroundTaskGeneration
        for stage in ['task-first','meta-first','failed-meta','failed-task','base-error']:
            with self.subTest(stage=stage), ExitStack() as stack:
                f=BackgroundFixture(stack.enter_context(tempfile.TemporaryDirectory(prefix='background-provider-')))
                error=KeyboardInterrupt('lookup') if stage=='base-error' else OSError('lookup')
                def task_provider():
                    if stage in ['task-first','base-error'] and tasks.call_count==1 or stage=='failed-task' and tasks.call_count==2: raise error
                    return f.update
                def meta_provider():
                    if stage=='meta-first' and metas.call_count==1 or stage=='failed-meta' and metas.call_count==2: raise error
                    return f.meta
                tasks=Mock(side_effect=task_provider); metas=Mock(side_effect=meta_provider)
                if stage.startswith('failed'): f.local.side_effect=RuntimeError('unknown generation')
                runner=BackgroundTaskRunner(BackgroundTaskRecords(f.find,f.path,lambda:f.load,tasks),
                    BackgroundTaskGeneration(lambda:f.sets,f.safe,metas,f.local,f.codex,f.images),f.clock,lambda:f.resolver)
                tasks.assert_not_called(); metas.assert_not_called(); f.find.assert_not_called(); f.clock.assert_not_called()
                if stage in ['failed-meta','failed-task','base-error']:
                    with self.assertRaises(type(error)) as caught: runner.run_background_set_task('job')
                    self.assertIs(caught.exception,error)
                else:
                    escaped=None
                    try: runner.run_background_set_task('job')
                    except BaseException as exc: escaped=exc
                    self.assertIsNone(escaped)
                self.assertEqual((tasks.call_count,metas.call_count,f.clock.call_count),{
                    'task-first':(2,1,2),'meta-first':(2,2,3),'failed-meta':(1,2,2),'failed-task':(2,2,3),'base-error':(1,0,0)}[stage])
                self.assertEqual([v['status'] for v in f.meta_updates],{
                    'task-first':['failed'],'meta-first':['failed'],'failed-meta':['generating'],'failed-task':['generating','failed'],'base-error':[]}[stage])
                self.assertEqual([v['status'] for v in f.task_updates],{
                    'task-first':['failed'],'meta-first':['running','failed'],'failed-meta':['running'],'failed-task':['running'],'base-error':[]}[stage])
                f.codex.assert_not_called(); self.assertEqual(f.local.call_count,int(stage.startswith('failed')))
                self.assertIsNone(f.resolver.current_snapshot()); self.assertEqual(f.resolver.scopes,[f.binding['model_profiles']])


    def test_runner_noncallable_manifest_evaluates_generating_ready_and_failed_arguments(self):
        for stage in ['generating','ready','failed']:
            with self.subTest(stage=stage), ExitStack() as stack:
                f=BackgroundFixture(stack.enter_context(tempfile.TemporaryDirectory(prefix='background-manifest-none-'))); f.bind(self.api,stack)
                clocks=[]; strings=[]
                def clock():
                    clocks.append(len(clocks)+1)
                    if len(clocks)==(2 if stage=='generating' else 3): self.api.update_background_set_manifest=f.meta
                    return len(clocks)*10.9
                def task_update(identifier,**values):
                    if stage=='generating' and values.get('progress')==8: self.api.update_background_set_manifest=None
                    return f.update_task(identifier,**values)
                def images(path): self.api.update_background_set_manifest=None; return [Path('image')]*11
                class Unknown(RuntimeError):
                    def __str__(inner):
                        strings.append('str'); self.api.update_background_set_manifest=f.meta; return 'unknown generation'
                def local(*args): self.api.update_background_set_manifest=None; raise Unknown()
                f.clock.side_effect=clock; f.update.side_effect=task_update
                if stage=='ready': f.images.side_effect=images
                if stage=='failed': f.local.side_effect=local
                with patch.object(self.api,'run_codex_background_generation',f.codex):
                    if stage=='failed':
                        with self.assertRaisesRegex(TypeError,"'NoneType' object is not callable"): self.api.run_background_set_task('job')
                    else:
                        escaped=None
                        try: self.api.run_background_set_task('job')
                        except BaseException as exc: escaped=exc
                        self.assertIsNone(escaped)
                self.assertEqual(clocks,list(range(1,{'generating':4,'ready':6,'failed':3}[stage]+1)))
                self.assertEqual(strings,['str'] if stage=='failed' else [])
                self.assertEqual(f.meta_updates,{'generating':[{'status':'failed','error':"'NoneType' object is not callable",'updated_at':32}],
                    'ready':[{'status':'generating','updated_at':21},{'status':'failed','error':"'NoneType' object is not callable",'updated_at':54}],
                    'failed':[{'status':'generating','updated_at':21}]}[stage])
                self.assertEqual([v['status'] for v in f.task_updates],{'generating':['running','failed'],'ready':['running','running','failed'],'failed':['running']}[stage])
                if stage!='failed':
                    self.assertEqual(f.task_updates[-1],{'status':'failed','progress':100,'completed_at':43 if stage=='generating' else 65,
                        'error':"'NoneType' object is not callable",'note':"背景生成失败：'NoneType' object is not callable"})
                self.assertEqual(f.local.call_count,int(stage!='generating')); self.assertEqual(f.codex.call_count,int(stage=='ready'))
                self.assertIsNone(f.resolver.current_snapshot())


    def test_new_callback_capture_precedes_path_cwd_and_thread_name_arguments(self):
        for stage in ['load', 'process', 'thread']:
            for noncallable in [False, True]:
                with self.subTest(stage=stage, noncallable=noncallable), ExitStack() as stack:
                    f=BackgroundFixture(stack.enter_context(tempfile.TemporaryDirectory(prefix='background-capture-',dir=self.f.root)))
                    f.bind(self.api,stack); calls=[]; newer=Mock()
                    if stage=='load':
                        selected=None if noncallable else Mock(return_value=None)
                        previous=Mock(return_value=None)
                        stack.enter_context(patch.object(self.api,'load_training_task',previous))
                        def find(identifier): self.api.load_training_task=selected; return f.binding
                        def path(identifier): calls.append('argument'); self.api.load_training_task=newer; return f.root/'job.json'
                        f.find.side_effect=find; f.path.side_effect=path
                        action=lambda:self.api.run_background_set_task('job')
                    elif stage=='process':
                        selected=None if noncallable else Mock(return_value=self.process)
                        previous=Mock(return_value=self.process)
                        stack.enter_context(patch.object(subprocess,'Popen',previous))
                        class Root:
                            def __str__(inner):
                                calls.append('argument'); subprocess.Popen=selected if len(calls)==1 else newer
                                return str(f.root)
                        stack.enter_context(patch.object(self.api,'ROOT',Root()))
                        action=lambda:self.api.run_codex_background_generation(f.source,f.sets,'x',0)
                    else:
                        selected=None if noncallable else Mock(return_value=f.thread)
                        stack.enter_context(patch.object(threading,'Thread',selected))
                        def name(identifier): calls.append('argument'); threading.Thread=newer; return 'x'
                        stack.enter_context(patch.object(self.api,'safe_name',name))
                        action=lambda:self.api.start_codex_background_generation(f.source,f.sets,'x')
                    if noncallable and stage!='process':
                        with self.assertRaises(TypeError): action()
                    else:
                        result=action()
                        if stage=='process': self.assertEqual(result,[])
                    self.assertEqual(calls,['argument']*(2 if stage=='process' else 1))
                    newer.assert_not_called()
                    if selected is not None: selected.assert_called_once()
                    if stage in ['load','process']: previous.assert_not_called()
                    if stage=='thread': self.assertEqual(f.thread.start.call_count,int(not noncallable))
                    if stage=='load': self.assertIsNone(f.resolver.current_snapshot()); f.update.assert_not_called()

    def test_new_getter_first_errors_preserve_existing_failure_boundaries(self):
        from local_inspection_service.training.background_codex import CodexBackgroundGeneration, CodexBackgroundPaths, CodexBackgroundThread
        from local_inspection_service.training.background_task_runner import BackgroundTaskRunner, BackgroundTaskRecords, BackgroundTaskGeneration
        for stage in ['load','process','thread']:
            with self.subTest(stage=stage):
                f=self.f; error=RuntimeError(stage); selected=Mock(); getter=Mock(side_effect=[error,selected])
                if stage=='load':
                    service=BackgroundTaskRunner(BackgroundTaskRecords(f.find,f.path,getter,lambda:f.update),
                        BackgroundTaskGeneration(lambda:f.sets,f.safe,lambda:f.meta,f.local,f.codex,f.images),f.clock,lambda:f.resolver)
                    action=lambda:service.run_background_set_task('job')
                elif stage=='process':
                    service=CodexBackgroundGeneration(self.which,CodexBackgroundPaths(lambda:f.logs,lambda:f.root),self.name,getter)
                    action=lambda:service.run_codex_background_generation(f.source,f.sets,'x',0)
                else:
                    service=CodexBackgroundThread(getter,lambda:self.api.run_codex_background_generation,self.name)
                    action=lambda:service.start_codex_background_generation(f.source,f.sets,'x')
                getter.assert_not_called()
                if stage=='process': self.assertEqual(action(),[])
                else:
                    with self.assertRaises(RuntimeError) as caught: action()
                    self.assertIs(caught.exception,error)
                getter.assert_called_once(); selected.assert_not_called(); self.popen.assert_not_called()
                f.factory.assert_not_called(); f.path.assert_not_called(); f.update.assert_not_called(); f.meta.assert_not_called()
                self.assertIsNone(f.resolver.current_snapshot())

    def test_codex_first_errors_do_not_repeat_filesystem_or_dependency_reads(self):
        from local_inspection_service.training.background_codex import CodexBackgroundGeneration, CodexBackgroundPaths, CodexBackgroundThread
        stages=['mkdir','logs','which','source-exists','root-first','root-cwd','open','outputs','timeout-outputs','name-log','name-output','name-thread','thread-create','target']
        for stage in stages:
            with self.subTest(stage=stage), ExitStack() as stack:
                f=BackgroundFixture(stack.enter_context(tempfile.TemporaryDirectory(prefix='background-first-',dir=self.f.root)))
                error=RuntimeError(stage); observed=[]
                index=2 if stage in ['root-cwd','name-output'] else 1
                def first(fn):
                    def invoke(*args,**kwargs):
                        observed.append(stage)
                        if len(observed)==index: raise error
                        return fn(*args,**kwargs)
                    return invoke
                which=lambda command:'fake'; logs=lambda:f.logs; root=lambda:f.root; name=lambda value:'x'
                factory=lambda **kwargs:f.thread; target=lambda:self.api.run_codex_background_generation
                process=Mock(); start=lambda:Mock(return_value=process)
                if stage=='logs': logs=first(logs)
                if stage=='which': which=first(which)
                if stage.startswith('root-'): root=first(root)
                if stage.startswith('name-'): name=first(name)
                if stage=='thread-create': factory=first(factory)
                if stage=='target': target=first(target)
                if stage=='mkdir':
                    original=Path.mkdir
                    stack.enter_context(patch.object(Path,'mkdir',autospec=True,side_effect=first(original)))
                if stage=='open':
                    original=Path.open
                    stack.enter_context(patch.object(Path,'open',autospec=True,side_effect=first(original)))
                if stage in ['source-exists','outputs','timeout-outputs']:
                    original=Path.exists; fail=first(original)
                    def exists(path):
                        matched=path==f.source if stage=='source-exists' else path.name.startswith('codex_')
                        return fail(path) if matched else original(path)
                    stack.enter_context(patch.object(Path,'exists',autospec=True,side_effect=exists))
                if stage=='timeout-outputs': process.communicate.side_effect=subprocess.TimeoutExpired('fake',900)
                generation=CodexBackgroundGeneration(which,CodexBackgroundPaths(logs,root),name,start)
                thread=CodexBackgroundThread(lambda:factory,target,name)
                action=(lambda:thread.start_codex_background_generation(f.source,f.sets,'x')) if stage in ['name-thread','thread-create','target'] else (lambda:generation.run_codex_background_generation(f.source,f.sets,'x',1))
                caught=None
                try: result=action()
                except BaseException as exc: caught=exc
                if stage in ['root-cwd','open']:
                    self.assertIsNone(caught); self.assertEqual(result,[])
                else: self.assertIs(caught,error)
                self.assertEqual(len(observed),index)
                if stage in ['name-thread','thread-create','target']: f.thread.start.assert_not_called()
                self.popen.assert_not_called()

    def test_runner_first_path_provider_and_clock_errors_do_not_retry(self):
        from local_inspection_service.training.background_task_runner import BackgroundTaskRunner, BackgroundTaskRecords, BackgroundTaskGeneration
        stages=['path','sets','exists','task-progress','meta-ready','task-completed',*[f'clock-{n}' for n in range(1,6)],'failure-clock-3','failure-clock-4']
        for stage in stages:
            with self.subTest(stage=stage), ExitStack() as stack:
                f=BackgroundFixture(stack.enter_context(tempfile.TemporaryDirectory(prefix='background-runner-first-',dir=self.f.root)))
                error=RuntimeError(stage); observed=[]
                index={'task-progress':2,'meta-ready':2,'task-completed':3}.get(stage,int(stage.rsplit('-',1)[1]) if 'clock-' in stage else 1)
                def first(fn):
                    def invoke(*args,**kwargs):
                        observed.append(stage)
                        if len(observed)==index: raise error
                        return fn(*args,**kwargs)
                    return invoke
                path=f.path; sets=lambda:f.sets; tasks=lambda:f.update; metas=lambda:f.meta; clock=f.clock
                if stage=='path': path=first(path)
                if stage=='sets': sets=first(sets)
                if stage.startswith('task-'): tasks=first(tasks)
                if stage=='meta-ready': metas=first(metas)
                if 'clock-' in stage: clock=first(clock)
                if stage.startswith('failure-'): f.local.side_effect=RuntimeError('generation')
                if stage=='exists':
                    original=Path.exists; fail=first(original)
                    stack.enter_context(patch.object(Path,'exists',autospec=True,side_effect=lambda value:fail(value) if value==f.source else original(value)))
                runner=BackgroundTaskRunner(BackgroundTaskRecords(f.find,path,lambda:f.load,tasks),
                    BackgroundTaskGeneration(sets,f.safe,metas,f.local,f.codex,f.images),clock,lambda:f.resolver)
                caught=None
                try: runner.run_background_set_task('job')
                except BaseException as exc: caught=exc
                propagate=stage in ['path','sets'] or stage.startswith('failure-')
                self.assertIs(caught,error if propagate else None)
                expected=index if propagate or stage=='exists' else index+(2 if stage.startswith('clock-') else 1)
                self.assertEqual(len(observed),expected)
                if not propagate: self.assertEqual(f.task_updates[-1]['status'],'failed')
                self.assertIsNone(f.resolver.current_snapshot())

    def test_submission_first_identity_registry_target_and_clock_errors_do_not_retry(self):
        from local_inspection_service.training.background_task_submission import BackgroundTaskSubmission
        from local_inspection_service.training.submission import TrainingSubmissionRecords, TrainingSubmissionThreads
        for stage in ['owner','registry','target','clock-first','clock-created','uuid']:
            with self.subTest(stage=stage), ExitStack() as stack:
                f=BackgroundFixture(stack.enter_context(tempfile.TemporaryDirectory(prefix='background-submit-first-',dir=self.f.root)))
                error=RuntimeError(stage); observed=[]; index=2 if stage=='clock-created' else 1
                def first(fn):
                    def invoke(*args,**kwargs):
                        observed.append(stage)
                        if len(observed)==index: raise error
                        return fn(*args,**kwargs)
                    return invoke
                owner=f.owner; registry=lambda:f.threads; target=lambda:self.api.run_background_set_task; clock=f.clock; uuid=f.uuid
                if stage=='owner': owner=first(owner)
                if stage=='registry': registry=first(registry)
                if stage=='target': target=first(target)
                if stage.startswith('clock-'): clock=first(clock)
                if stage=='uuid': uuid=first(uuid)
                service=BackgroundTaskSubmission(TrainingSubmissionRecords(f.save,f.public),TrainingSubmissionThreads(target,f.factory,registry),owner,clock,uuid)
                caught=None
                try: service.enqueue_background_set_task('x','name',f.source)
                except BaseException as exc: caught=exc
                self.assertIs(caught,error); self.assertEqual(len(observed),index)
                f.thread.start.assert_not_called(); f.public.assert_not_called()
                self.assertEqual(len(f.saved),int(stage in ['target','registry']))
                self.assertEqual(f.factory.call_count,int(stage=='registry'))

    def test_task_writer_none_still_evaluates_progress_completed_and_failed_arguments(self):
        for stage in ['progress','completed','failed']:
            with self.subTest(stage=stage), ExitStack() as stack:
                f=BackgroundFixture(stack.enter_context(tempfile.TemporaryDirectory(prefix='background-none-',dir=self.f.root)))
                f.bind(self.api,stack); lengths=[]; clocks=[]; strings=[]
                class Variants(list):
                    def __len__(inner):
                        lengths.append('len')
                        if len(lengths)==2: self.api.update_training_task=f.update
                        return 5
                class Failure(RuntimeError):
                    def __str__(inner): strings.append('str'); return 'unknown'
                def local(*args):
                    self.api.update_training_task=None
                    if stage=='failed': raise Failure()
                    return Variants()
                def images(path): self.api.update_training_task=None; return [Path('image')]*11
                def clock():
                    clocks.append('clock')
                    if len(clocks)==(5 if stage=='completed' else 4): self.api.update_training_task=f.update
                    return 101.9
                f.clock.side_effect=clock
                if stage in ['progress','failed']: f.local.side_effect=local
                else: f.images.side_effect=images
                caught=None
                with patch.object(self.api,'run_codex_background_generation',f.codex):
                    try: self.api.run_background_set_task('job')
                    except BaseException as exc: caught=exc
                if stage=='failed':
                    self.assertIsInstance(caught,TypeError); self.assertEqual(str(caught),"'NoneType' object is not callable")
                else: self.assertIsNone(caught)
                self.assertEqual(len(clocks),{'progress':4,'completed':7,'failed':4}[stage])
                self.assertEqual(len(lengths),3 if stage=='progress' else 0)
                self.assertEqual(len(strings),3 if stage=='failed' else 0)
                self.assertEqual([v['status'] for v in f.task_updates],{'progress':['running','failed'],'completed':['running','running','failed'],'failed':['running']}[stage])
                self.assertIsNone(f.resolver.current_snapshot())

    def test_process_factory_captured_after_real_log_enter_before_cwd_conversion(self):
        for noncallable in [False,True]:
            with self.subTest(noncallable=noncallable), ExitStack() as stack:
                f=BackgroundFixture(stack.enter_context(tempfile.TemporaryDirectory(prefix='background-open-capture-',dir=self.f.root)))
                f.bind(self.api,stack); events=[]; newer=Mock(); earlier=Mock(); selected=None if noncallable else Mock(return_value=self.process)
                stack.enter_context(patch.object(subprocess,'Popen',earlier))
                original=Path.open
                class Log:
                    def __init__(inner,handle): inner.handle=handle
                    def __enter__(inner):
                        result=inner.handle.__enter__(); events.append('enter'); subprocess.Popen=selected; return result
                    def __exit__(inner,*args): return inner.handle.__exit__(*args)
                def opening(path,*args,**kwargs): return Log(original(path,*args,**kwargs))
                stack.enter_context(patch.object(Path,'open',autospec=True,side_effect=opening))
                class Root:
                    def __str__(inner):
                        events.append('str')
                        if 'enter' in events: subprocess.Popen=newer
                        return str(f.root)
                stack.enter_context(patch.object(self.api,'ROOT',Root()))
                escaped=None
                try: result=self.api.run_codex_background_generation(f.source,f.sets,'x',0)
                except BaseException as exc: escaped=exc
                self.assertIsNone(escaped); self.assertEqual(result,[])
                self.assertEqual(events,['str','enter','str']); earlier.assert_not_called(); newer.assert_not_called()
                if selected is not None: selected.assert_called_once(); self.assertTrue(selected.call_args.kwargs['stdout'].closed)

if __name__=='__main__': unittest.main()
