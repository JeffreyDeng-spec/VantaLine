"""Offline training lookup, pipeline link and trained model discovery contracts."""
from contextlib import ExitStack
import asyncio
import copy
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import uuid
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
PG_CHECK = '--postgres' in sys.argv
if PG_CHECK: sys.argv.remove('--postgres')


class Fixture:
    def __init__(self, root):
        self.root = root
        self.runs = root / 'runs'; self.runs.mkdir()
        self.output = root / 'output'
        self.config = {'accessories': [{'id': 'a', 'name': 'Current A'}, {'id': 'b', 'label': 'Current B'}]}
        self.tasks = {}; self.files = {}; self.pipeline = []; self.cache = {}; self.repo = None
        self.config_load = Mock(side_effect=lambda: self.config)
        self.repository = Mock(side_effect=lambda: self.repo)
        self.file_loader = Mock(side_effect=lambda path: self.tasks.get(path.stem))
        self.read = Mock(side_effect=lambda path: self.files.get(path))
        self.pipeline_load = Mock(side_effect=lambda: self.pipeline)
        self.profiles = Mock(side_effect=lambda items, labels: {'items': items, 'labels': labels})
        self.rules = Mock(side_effect=lambda spec, config: spec)
        self.visible = Mock(side_effect=lambda record, user: record['owner_user_id'] == user['id'])
        self.audit = Mock(side_effect=lambda record, path: {
            'created_at': record.get('created_at', 10), 'updated_at': record.get('updated_at', 20),
            'owner_user_id': record.get('owner_user_id', 'alice'), 'owner_username': 'fixture-owner'})
        self.get = Mock(side_effect=lambda key: (key in self.cache, self.cache.get(key)))
        self.put = Mock(side_effect=lambda key, value: self.cache.__setitem__(key, value))
        self.uses_ocr = Mock(side_effect=lambda item: bool(item.get('ocr')))
    def run(self, name='run', stamp=100, task=None, manifest=None, meta=None):
        directory = self.runs / name; directory.mkdir(exist_ok=True)
        os.utime(directory, (stamp, stamp))
        self.tasks[name] = {'action': 'train_model', 'task_id': 'task-'+name,
                            'selected_accessory_ids': ['a'], **(task or {})}
        self.files[self.output/'training_datasets'/name/'manifest.json'] = {'class_names': ['raw'], **(manifest or {})}
        self.files[directory/'library_metadata.json'] = meta or {}
        return directory
    def bind(self, api, stack):
        values = {'load_config': self.config_load, 'runtime_postgres_repository_or_none': self.repository,
            'load_training_task': self.file_loader, 'store_read_cache_get': self.get, 'store_read_cache_put': self.put,
            'training_run_roots': lambda: [self.runs], 'training_task_path': lambda name: self.root/(name+'.json'),
            'OUTPUT_DIR': self.output, 'load_json_file_mtime_cached': self.read,
            'resolve_service_path': lambda path: self.root/path, 'load_pipeline_tasks': self.pipeline_load,
            'accessory_uid': lambda item: 'generated', 'serialize_accessory': lambda item: dict(item),
            'record_audit_fields': self.audit, 'accessory_uses_ocr': self.uses_ocr,
            'build_ocr_accessory_profiles': self.profiles, 'apply_task_rule_override_to_spec': self.rules,
            'record_visible_to_user': self.visible, 'normalize_pipeline_detection_method': lambda method: method,
            'task_record_name': lambda task: task.get('name', '')}
        for name, value in values.items(): stack.enter_context(patch.object(api, name, value))


class TrainedCatalogContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.environment = patch.dict(os.environ)
        cls.environment.start()
        cls.runtime = tempfile.TemporaryDirectory(prefix='trained-root-')
        root = Path(cls.runtime.name); (root/'local_inspection_service/static').mkdir(parents=True)
        os.environ.update(LOCAL_INSPECTION_ROOT=str(root), VANTALINE_DATA_STORE='json',
                          LOCAL_INSPECTION_AUTO_RESUME_WORKER='0', VANTALINE_LABEL_INSPECTION_ENABLED='false')
        from local_inspection_service import server
        cls.api = server
    @classmethod
    def tearDownClass(cls):
        cls.runtime.cleanup(); cls.environment.stop()
    def setUp(self):
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        directory = self.stack.enter_context(tempfile.TemporaryDirectory(prefix='trained-case-'))
        self.f = Fixture(Path(directory)); self.f.bind(self.api, self.stack)
        token = self.api._request_user.set(None); self.addCleanup(self.api._request_user.reset, token)

    def test_finder_file_identity_selection_and_factory_errors(self):
        api = self.api; f = self.f
        self.assertIs(api.training_task_finder(), f.file_loader)
        f.repository.assert_called_once_with(); f.get.assert_not_called(); f.file_loader.assert_not_called()
        with patch.object(api, 'load_training_task', Mock()) as replacement:
            self.assertIs(api.training_task_finder(), replacement)
        f.repository.side_effect = RuntimeError('factory')
        with self.assertRaisesRegex(RuntimeError, 'factory'): api.training_task_finder()
        f.file_loader.assert_not_called()

    def test_finder_lazy_single_scan_shared_aliases_and_local_snapshot(self):
        api = self.api; f = self.f; repo = Mock(); f.repo = repo
        one = {'id': 'raw-id', 'task_id': 'task-alias', 'remote_training_job_id': 'remote'}
        row = {'id': 'row-id', 'job_id': 'row-job', 'raw_json': one}
        repo.fetch_all.return_value = [row, {'raw_json': {}}]
        finder = api.training_task_finder(); f.repository.assert_called_once_with(); repo.fetch_all.assert_not_called()
        f.repo = Mock(side_effect=AssertionError('must retain chosen repository'))
        found = finder(Path('task-alias.json')); self.assertEqual(found, one)
        for identity in ('raw-id', 'remote', 'row-id', 'row-job'):
            self.assertIs(finder(Path(identity+'.json')), found)
        self.assertIsNone(finder(Path('absent.json')))
        repo.fetch_all.assert_called_once_with('training_tasks'); f.get.assert_called_once_with('training_task_pairs')
        self.assertIs(f.cache['training_task_pairs'][0][0], found)
        f.cache['training_task_pairs'].append(({'id': 'added'}, {}))
        self.assertEqual(finder(Path('added.json')), {'id': 'added'})
        f.cache.clear(); self.assertIs(finder(Path('row-id.json')), found)
        repo.fetch_all.assert_called_once(); f.repository.assert_called_once()
        f.repo = repo; f.cache['training_task_pairs'] = [({'id': 'cached'}, {})]
        next_finder = api.training_task_finder()
        self.assertIs(next_finder(Path('cached.json')), f.cache['training_task_pairs'][0][0]); repo.fetch_all.assert_called_once()

    def test_finder_failure_boundaries_do_not_retry_or_fall_back(self):
        api = self.api; f = self.f; f.repo = Mock(); f.repo.fetch_all.side_effect = RuntimeError('fetch')
        finder = api.training_task_finder()
        with self.assertRaisesRegex(RuntimeError, 'fetch'): finder(Path('one.json'))
        self.assertIsNone(finder(Path('one.json'))); f.repo.fetch_all.assert_called_once(); f.put.assert_not_called()
        f.repo.fetch_all.side_effect = None; f.repo.fetch_all.return_value = [{'raw_json': {'id': 'one'}}, {'raw_json': {'id': 'two'}}]
        decoder = Mock(side_effect=[[{'id': 'one'}], ValueError('decode')])
        with patch.object(api, 'row_raw_json_list', decoder):
            finder = api.training_task_finder()
            with self.assertRaisesRegex(ValueError, 'decode'): finder(Path('two.json'))
            self.assertEqual(finder(Path('one.json')), {'id': 'one'}); self.assertIsNone(finder(Path('two.json')))
        self.assertEqual(decoder.call_count, 2); f.put.assert_not_called(); f.file_loader.assert_not_called()
        # A cache read failure precedes pairs assignment, so this one may be retried.
        f.get.side_effect = [RuntimeError('cache'), (True, [({'id': 'cached'}, {})])]
        finder = api.training_task_finder()
        with self.assertRaisesRegex(RuntimeError, 'cache'): finder(Path('cached.json'))
        self.assertEqual(finder(Path('cached.json')), {'id': 'cached'})

    def test_pipeline_links_sanitization_first_match_and_explicit_empty(self):
        api = self.api; f = self.f
        f.pipeline = [{'id': 7, 'model_run_id': 'my_run', 'name': 'first'},
                      {'id': 'second', 'training_task_id': 'my_run', 'name': 'second'}]
        self.assertEqual(api.pipeline_task_link_for_training_run('trained_my/run'), {'pipeline_task_id': '7', 'pipeline_task_name': 'first'})
        f.pipeline_load.assert_called_once_with(); f.pipeline_load.reset_mock()
        self.assertEqual(api.pipeline_task_link_for_training_run('my_run', []), {})
        self.assertEqual(api.pipeline_task_link_for_training_run('trained_'), {})
        f.pipeline_load.assert_not_called()
        self.assertEqual(api.pipeline_task_link_for_training_run('trained_trained_x', [{'id':'x','ai_model_id':'trained_trained_x'}])['pipeline_task_id'], 'x')
        with patch.object(api, 'task_record_name', side_effect=ValueError('name')):
            with self.assertRaisesRegex(ValueError, 'name'): api.pipeline_task_link_for_training_run('my_run')

    def test_finder_event_order_put_failure_and_original_loader_capture(self):
        api=self.api; f=self.f; loader=api.training_task_finder()
        with patch.object(api,'load_training_task',Mock()): self.assertIs(loader,f.file_loader)
        events=[]; first={'id':'first'}; second={'id':'second'}
        repo=Mock(); f.repo=repo
        repo.fetch_all.side_effect=lambda table: events.append('fetch') or [{'raw_json':first},{'raw_json':second}]
        f.get.side_effect=lambda key: events.append('get') or (False,None)
        f.put.side_effect=lambda key,value: (_ for _ in ()).throw(RuntimeError('put'))
        def decode(rows): events.append('decode'); return [rows[0]['raw_json']]
        def identify(path): events.append('identifier'); return ''
        match=Mock(side_effect=lambda task,requested,row: events.append('match') or True)
        with patch.object(api,'row_raw_json_list',side_effect=decode), patch.object(api,'file_stem_identifier',side_effect=identify), patch.object(api,'training_task_matches_identifier',match):
            finder=api.training_task_finder()
            with self.assertRaisesRegex(RuntimeError,'put'): finder(Path('empty.json'))
            self.assertEqual(events,['get','fetch','decode','decode'])
            self.assertIs(finder(Path('empty.json')),first)
            self.assertEqual(events,['get','fetch','decode','decode','identifier','match'])
            f.put.assert_called_once(); repo.fetch_all.assert_called_once(); match.assert_called_once_with(first,'',{'raw_json':first})

    def test_catalog_complete_payload_precedence_aliases_and_missing_weights(self):
        api = self.api; f = self.f
        f.config['accessories'].append({'id': 'a', 'name': 'Last A'})
        run = f.run(task={'required_accessory_counts': {'a': 140, 'b': -2}, 'ocr_accessory_ids': ['a'],
            'pipeline_task_id': 'task-pipe', 'pipeline_task_name': 'task-name', 'created_at': 31},
            manifest={'pipeline_task_id': 'manifest-pipe', 'created_at': 1}, meta={'display_name': 'Shown', 'note': 'note'})
        before = copy.deepcopy(f.tasks)
        values = api.list_trained_model_specs({}); f.config_load.assert_called_once_with()
        self.assertEqual([v['variant'] for v in values], ['yolo', 'yolo_ocr'])
        expected = {'id':'trained_run__yolo', 'run_id':'run', 'run_dir':str(run), 'task_id':'task-run',
            'pipeline_task_id':'task-pipe','pipeline_task_name':'task-name','variant':'yolo','label':'Shown',
            'description':'由训练库生成的任务模型。','note':'note','path':run/'weights/best.pt',
            'artifact_path':str(run/'weights/best.pt'),'metadata_path':str(f.output/'training_datasets/run/manifest.json'),
            'uses_ocr':False,'is_specialized':True,'selected_accessory_ids':['a'],'required_accessory_counts':{'a':140,'b':0},
            'accessory_class_map':{'0':'a'},'class_accessory_map':{'a':0},'ocr_accessory_ids':[],
            'ocr_model_class_ids':[],'ocr_accessory_profiles':{},'accessory_names':['Last A'],'accessory_labels':{'a':'Last A'},
            'model_class_names':{0:'Last A'},'model_to_business_class':{0:0},'model_to_accessory_id':{0:'a'},
            'rule_required_accessory_ids':['a','b'],'rule_required_classes':[0],'rule_min_counts':{'0':1},
            'rule_class_labels':{0:'Last A'},'created_at':31,'updated_at':20,'owner_user_id':'alice','owner_username':'fixture-owner'}
        self.assertEqual(values[0], expected); self.assertFalse(values[0]['path'].exists())
        expected_ocr = {**expected, 'id':'trained_run__yolo_ocr','variant':'yolo_ocr','uses_ocr':True,
            'ocr_accessory_ids':['a'],'ocr_model_class_ids':[0],
            'ocr_accessory_profiles':{'items':[{'id':'a','name':'Last A'}],'labels':{'a':'Last A'}}}
        self.assertEqual(values[1], expected_ocr)
        for key in ('selected_accessory_ids','required_accessory_counts','accessory_names','accessory_labels','model_class_names','model_to_accessory_id'):
            self.assertIs(values[0][key], values[1][key], key)
        self.assertIs(values[0]['rule_class_labels'], values[0]['model_class_names'])
        self.assertEqual(f.tasks, before); self.assertEqual(f.rules.call_count, 2); f.profiles.assert_called_once()
        f.audit.assert_called_once_with({**f.files[f.output/'training_datasets/run/manifest.json'], **f.tasks['run']}, run)

    def test_catalog_order_duplicates_skips_and_empty_setup(self):
        api = self.api; f = self.f
        self.assertEqual(api.list_trained_model_specs(f.config), [])
        f.repository.assert_called_once(); f.pipeline_load.assert_called_once(); f.read.assert_not_called()
        first = f.run('first', 100); second = f.run('second', 100); f.run('newest', 300)
        f.run('skip', 400, task={'action':'dataset'}); (f.runs/'file').write_text('not a run')
        # Tied mtimes preserve filesystem discovery order, including duplicate roots.
        ordered = [p.name for p in f.runs.iterdir() if p.is_dir() and p.name in {'first','second'}]
        with patch.object(api, 'training_run_roots', return_value=[f.runs, f.root/'absent', f.runs]):
            values = api.list_trained_model_specs(f.config)
        self.assertEqual([v['run_id'] for v in values], ['newest','newest',*ordered,*ordered])
        self.assertEqual(len(f.read.call_args_list), 12)
        f.read.assert_any_call(first/'library_metadata.json'); f.read.assert_any_call(second/'library_metadata.json')

    def test_catalog_manifest_fallback_class_maps_and_pipeline_ocr(self):
        api = self.api; f = self.f
        run = f.run(task={'task_id':'', 'selected_accessory_ids':[], 'manifest_path':'custom.json', 'model_variant':'invalid'},
            meta={'pipeline_task_id':'pipe', 'pipeline_task_name':'metadata name'})
        manifest = {'task_id':'manifest-task','selected_accessory_ids':['a','b'], 'class_names':['raw one'],
                    'accessory_class_map':{'-1':'b','0':'a','skip':'ignored'},'pipeline_task_name':'manifest name'}
        f.files[f.root/'custom.json'] = manifest
        f.pipeline = [{'id':'pipe','model_run_id':'run','detection_method':'yolo','name':'first'},
                      {'id':'pipe','model_run_id':'run','detection_method':'yolo_ocr','name':'last'}]
        values = api.list_trained_model_specs(f.config); plain, ocr = values
        self.assertEqual(plain['task_id'],'manifest-task'); self.assertEqual(plain['pipeline_task_name'],'manifest name')
        self.assertEqual(plain['pipeline_task_id'],'pipe'); self.assertEqual(plain['accessory_names'],['raw one'])
        self.assertEqual(plain['accessory_labels'],{'b':'b','a':'raw one'})
        self.assertEqual(plain['required_accessory_counts'],{'a':1,'b':1})
        self.assertEqual(ocr['ocr_accessory_ids'],['a']); self.assertEqual(ocr['ocr_model_class_ids'],[0])
        self.assertEqual(f.uses_ocr.call_count,4)
        f.tasks['run']['model_variant']='yolo_ocr'
        self.assertEqual([v['variant'] for v in api.list_trained_model_specs(f.config)],['yolo_ocr','yolo'])
        f.tasks['run']['selected_accessory_ids']=['missing']; f.tasks['run']['ocr_accessory_ids']=['missing','a','missing']
        self.assertEqual(api.list_trained_model_specs(f.config)[0]['ocr_accessory_ids'],['a','missing'])
        f.files[f.root/'custom.json']=[]; f.files[run/'library_metadata.json']=[]; f.tasks['run']={'action':'train_model'}
        f.files[f.output/'training_datasets/run/manifest.json']=None; f.pipeline=[]
        value=api.list_trained_model_specs(f.config)[0]
        self.assertEqual(value['task_id'],'run'); self.assertEqual(value['model_class_names'],{0:'accessory'})
        self.assertEqual(value['label'],'run · YOLO'); self.assertEqual(value['pipeline_task_id'],'')

    def test_catalog_rule_replacement_and_error_propagation_order(self):
        api=self.api; f=self.f; run=f.run()
        replacement={'owner_user_id':'alice','replacement':True}; f.rules.return_value=None
        f.rules.side_effect=lambda spec,config: replacement
        self.assertIs(api.list_trained_model_specs(f.config)[0],replacement)
        f.tasks['run']['required_accessory_counts']={'a':'bad'}; f.rules.reset_mock()
        api._request_user.set({'id':'unrelated-user'})
        with self.assertRaises(ValueError): api.list_trained_model_specs(f.config)
        f.rules.assert_not_called(); f.visible.assert_not_called()
        f.tasks['run']['required_accessory_counts']={}; f.tasks['run']['accessory_class_map']={'--1':'a'}
        with self.assertRaises(ValueError): api.list_trained_model_specs(f.config)
        with patch.object(Path,'stat',side_effect=OSError('stat')):
            with self.assertRaisesRegex(OSError,'stat'): api.list_trained_model_specs(f.config)
        original_stat=Path.stat; run_stats=[]
        def sort_failure(path,*args,**kwargs):
            if path==run:
                run_stats.append(path)
                if len(run_stats)==2: raise OSError('sort-phase')
            return original_stat(path,*args,**kwargs)
        f.repository.reset_mock(); f.pipeline_load.reset_mock(); f.read.reset_mock()
        with patch.object(Path,'stat',sort_failure):
            with self.assertRaisesRegex(OSError,'sort-phase'): api.list_trained_model_specs(f.config)
        self.assertEqual(len(run_stats),2)
        f.repository.assert_called_once_with(); f.pipeline_load.assert_called_once_with(); f.read.assert_not_called()
        f.tasks['run']['accessory_class_map']={}; f.read.side_effect=PermissionError('read')
        with self.assertRaisesRegex(PermissionError,'read'): api.list_trained_model_specs(f.config)

    def test_catalog_identity_is_late_and_async_thread_context_is_isolated(self):
        api=self.api; f=self.f; f.run('alice',task={'owner_user_id':'alice'}); f.run('bob',task={'owner_user_id':'bob'})
        api._request_user.set({'id':'alice'})
        def switch(spec,config):
            api._request_user.set({'id':'bob'}); return spec
        f.rules.side_effect=switch
        self.assertEqual([v['run_id'] for v in api.list_trained_model_specs(f.config)],['bob'])
        self.assertEqual(f.rules.call_count,2); self.assertEqual(f.visible.call_count,2)
        f.rules.side_effect=lambda spec,config:spec
        barrier=threading.Barrier(2)
        def visible(record,user):
            barrier.wait(timeout=10); return record['owner_user_id']==user['id']
        f.visible.side_effect=visible
        async def worker(name):
            token=api._request_user.set({'id':name})
            try:
                await asyncio.sleep(0)
                result=await asyncio.to_thread(api.list_trained_model_specs,f.config)
                self.assertEqual(api._request_user.get(),{'id':name})
                return [v['run_id'] for v in result]
            finally: api._request_user.reset(token)
        async def check(): return await asyncio.gather(worker('alice'),worker('bob'))
        self.assertEqual(asyncio.run(check()),[['alice'],['bob']])
        self.assertEqual(api._request_user.get(),{'id':'bob'})

    def test_independent_services_are_lazy_and_do_not_capture_identity(self):
        from contextvars import ContextVar
        from local_inspection_service.training.task_lookup import TrainingTaskLookup, LookupCache, LookupRows
        from local_inspection_service.training.model_catalog import (
            TrainedModelCatalog, TrainingFiles, TrainingAccessories, TrainingPipeline, TrainingAccess)
        from local_inspection_service.pipeline.training_links import TrainingLinks
        from local_inspection_service.storage.runtime_records import row_raw_json_list, file_stem_identifier
        other_root=self.f.root/'other'; other_root.mkdir(); other=Fixture(other_root)
        def compose(f):
            user=ContextVar('fixture-user',default=None)
            lookup=TrainingTaskLookup(f.repository,lambda:f.file_loader,LookupCache(f.get,f.put),
                LookupRows(row_raw_json_list,file_stem_identifier,lambda task,value,row:task.get('id')==value))
            links=TrainingLinks(f.pipeline_load,lambda task:task.get('name',''))
            catalog=TrainedModelCatalog(f.config_load,
                TrainingFiles(lambda:[f.runs],lookup.training_task_finder,lambda:(lambda name:f.root/(name+'.json')),
                    f.read,lambda:f.output,lambda:(lambda path:f.root/path)),
                TrainingAccessories(lambda item:'generated',dict,lambda:f.uses_ocr,lambda:f.profiles),
                TrainingPipeline(f.pipeline_load,lambda:links.pipeline_task_link_for_training_run,lambda:(lambda method:method)),
                TrainingAccess(user.get,f.visible,lambda:f.audit),f.rules)
            f.repository.assert_not_called(); f.config_load.assert_not_called(); f.pipeline_load.assert_not_called()
            return catalog,lookup,user
        first,first_lookup,first_user=compose(self.f); second,second_lookup,second_user=compose(other)
        self.f.run('first',task={'owner_user_id':'alice'}); other.run('second',task={'owner_user_id':'bob'})
        first_user.set({'id':'alice'}); second_user.set({'id':'bob'})
        self.assertEqual([v['run_id'] for v in first.list_trained_model_specs()],['first'])
        self.assertEqual([v['run_id'] for v in second.list_trained_model_specs()],['second'])
        first_user.set({'id':'bob'})
        self.assertEqual(first.list_trained_model_specs(),[])
        self.assertEqual([v['run_id'] for v in second.list_trained_model_specs()],['second'])
        self.assertIs(first_lookup.training_task_finder(),self.f.file_loader)
        self.assertIs(second_lookup.training_task_finder(),other.file_loader)
        # Composition adapters resolve root replacements at invocation time.
        with patch.object(self.api,'pipeline_task_link_for_training_run',return_value={'pipeline_task_id':'late'}) as link:
            self.assertEqual(self.api.list_trained_model_specs(self.f.config)[0]['pipeline_task_id'],'late')
            link.assert_called_once_with('first',[])

    @unittest.skipUnless(PG_CHECK, 'use --postgres with an isolated test DSN')
    def test_real_postgres_finder_aliases_one_scan_and_snapshot(self):
        import psycopg
        from psycopg import sql
        from local_inspection_service.storage.postgres_schema import postgres_ddl
        from local_inspection_service.storage.postgres_runtime_repository import PostgresRuntimeRepository
        from local_inspection_service.storage.runtime_records import training_task_row
        schema='training_finder_'+uuid.uuid4().hex; dsn=os.environ['VANTALINE_POSTGRES_DSN']
        with psycopg.connect(dsn,autocommit=True) as control:
            control.execute(postgres_ddl(schema))
            try:
                with psycopg.connect(dsn) as connection:
                    repository=PostgresRuntimeRepository(connection,'test',schema)
                    repository.upsert_row('training_tasks',training_task_row({'id':'one','task_id':'alias','action':'train_model'}))
                    self.f.repo=Mock(wraps=repository); finder=self.api.training_task_finder()
                    self.f.repo.fetch_all.assert_not_called(); found=finder(Path('alias.json'))
                    self.assertEqual(found['id'],'one'); self.assertIs(finder(Path('one.json')),found)
                    repository.upsert_row('training_tasks',training_task_row({'id':'two','action':'train_model'}))
                    self.f.cache.clear(); self.assertIsNone(finder(Path('two.json')))
                    self.f.repo.fetch_all.assert_called_once_with('training_tasks')
                    self.assertEqual(self.api.training_task_finder()(Path('two.json'))['id'],'two')
                    self.assertEqual(self.f.repo.fetch_all.call_count,2); self.f.file_loader.assert_not_called()
            finally: control.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))


    def test_catalog_callback_first_failures_preserve_original_exception(self):
        api = self.api; f = self.f
        f.run(task={'model_variant': 'yolo_ocr', 'manifest_path': 'custom-manifest.json',
                    'pipeline_task_id': 'p', 'owner_user_id': 'alice'})
        f.config['accessories'].append({'id': '', 'name': 'Generated'})
        f.pipeline = [{'id': 'p', 'model_run_id': 'run', 'detection_method': 'yolo_ocr'}]
        api._request_user.set({'id': 'alice'})
        names = ('load_config', 'training_run_roots', 'training_task_finder', 'load_pipeline_tasks',
            'training_task_path', 'load_training_task', 'load_json_file_mtime_cached', 'resolve_service_path',
            'record_audit_fields', 'pipeline_task_link_for_training_run', 'accessory_uid',
            'serialize_accessory', 'accessory_uses_ocr', 'build_ocr_accessory_profiles',
            'normalize_pipeline_detection_method', 'apply_task_rule_override_to_spec', 'record_visible_to_user')
        originals = {name: getattr(api, name) for name in names}
        for target in names:
            with self.subTest(target=target), ExitStack() as stack:
                error = RuntimeError('first catalog callback'); events = []; attempts = []
                for name, original in originals.items():
                    def invoke(*args, _name=name, _original=original, **kwargs):
                        events.append(_name)
                        if _name == target:
                            attempts.append(args)
                            if len(attempts) == 1: raise error
                        return _original(*args, **kwargs)
                    stack.enter_context(patch.object(api, name, invoke))
                with self.assertRaises(RuntimeError) as raised:
                    api.list_trained_model_specs(None)
                self.assertIs(raised.exception, error)
                self.assertEqual(len(attempts), 1); self.assertEqual(events[-1], target)

    def test_finder_first_failures_are_not_automatically_retried(self):
        api = self.api; f = self.f
        for target in ('repository', 'get', 'fetch_all', 'row_raw_json_list', 'put',
                       'file_stem_identifier', 'training_task_matches_identifier'):
            with self.subTest(target=target), ExitStack() as stack:
                error = RuntimeError('first finder callback'); events = []; attempts = []
                f.cache.clear(); repo = Mock(); f.repo = repo
                repo.fetch_all.return_value = [{'raw_json': {'id': 'one'}}]
                bindings = [(api, 'runtime_postgres_repository_or_none', 'repository'),
                    (api, 'store_read_cache_get', 'get'), (repo, 'fetch_all', 'fetch_all'),
                    (api, 'row_raw_json_list', 'row_raw_json_list'), (api, 'store_read_cache_put', 'put'),
                    (api, 'file_stem_identifier', 'file_stem_identifier'),
                    (api, 'training_task_matches_identifier', 'training_task_matches_identifier')]
                for owner, name, label in bindings:
                    original = getattr(owner, name)
                    def invoke(*args, _label=label, _original=original, **kwargs):
                        events.append(_label)
                        if _label == target:
                            attempts.append(args)
                            if len(attempts) == 1: raise error
                        return _original(*args, **kwargs)
                    stack.enter_context(patch.object(owner, name, invoke))
                with self.assertRaises(RuntimeError) as raised:
                    finder = api.training_task_finder()
                    finder(Path('one.json'))
                self.assertIs(raised.exception, error)
                self.assertEqual(len(attempts), 1); self.assertEqual(events[-1], target)
                f.file_loader.assert_not_called()
                if target in ('repository', 'get', 'fetch_all', 'row_raw_json_list', 'put'):
                    self.assertNotIn('training_task_pairs', f.cache)
                else:
                    self.assertEqual(f.cache['training_task_pairs'][0][0], {'id': 'one'})


    def test_catalog_filesystem_failures_are_not_retried(self):
        api = self.api; f = self.f; run = f.run()
        for name in ('exists', 'iterdir', 'is_dir', 'stat'):
            with self.subTest(boundary=name):
                original = getattr(Path, name); error = OSError('first filesystem boundary')
                hits = []; run_stats = []
                def fail_once(path, *args, **kwargs):
                    target = path == (f.runs if name in ('exists', 'iterdir') else run)
                    if name == 'stat' and path == run:
                        run_stats.append(path)
                        # The first run stat belongs to is_dir; the second is sorting.
                        target = len(run_stats) == 2
                    if target:
                        hits.append(path)
                        if len(hits) == 1: raise error
                    return original(path, *args, **kwargs)
                with patch.object(Path, name, fail_once):
                    with self.assertRaises(OSError) as raised:
                        api.list_trained_model_specs(f.config)
                self.assertIs(raised.exception, error); self.assertEqual(len(hits), 1)
                if name == 'stat': self.assertEqual(len(run_stats), 2)
                f.read.assert_not_called(); f.rules.assert_not_called()


    def test_catalog_callbacks_capture_before_arguments_and_after_pipeline_load(self):
        api = self.api
        targets = {'resolve': 'resolve_service_path', 'audit': 'record_audit_fields',
            'uses': 'accessory_uses_ocr', 'uses_second': 'accessory_uses_ocr', 'method_first': 'normalize_pipeline_detection_method',
            'method_second': 'normalize_pipeline_detection_method', 'profiles': 'build_ocr_accessory_profiles',
            'task_path': 'training_task_path', 'link': 'pipeline_task_link_for_training_run'}
        for mode, target in targets.items():
            for variant in ('ordinary', 'prior', 'missing'):
                with self.subTest(mode=mode, variant=variant), ExitStack() as stack:
                    directory = stack.enter_context(tempfile.TemporaryDirectory(prefix='catalog-capture-'))
                    f = Fixture(Path(directory)); f.bind(api, stack); f.run()
                    events = []; swapped = False; armed = False
                    def value(*args):
                        if mode == 'resolve': return f.root/'custom.json'
                        if mode == 'audit': return dict(created_at=1, updated_at=2, owner_user_id='alice', owner_username='Alice')
                        if mode.startswith('uses'): return False
                        if mode.startswith('method'): return 'yolo_ocr'
                        if mode in ('profiles', 'link'): return {}
                        return f.root/(args[0]+'.json')
                    def callback(label, *args):
                        first = not events
                        events.append(label)
                        if mode == 'uses_second' and first and variant != 'ordinary':
                            events.append('prior')
                            setattr(api, target, None if variant == 'missing' else lambda *args: callback('B', *args))
                        return value(*args)
                    def swap():
                        nonlocal swapped
                        if not swapped:
                            swapped = True; events.append('arg')
                            setattr(api, target, lambda *args: callback('C', *args))
                    def preceding():
                        if variant != 'ordinary' and mode != 'uses_second':
                            events.append('prior')
                            setattr(api, target, None if variant == 'missing' else lambda *args: callback('B', *args))
                        return f.pipeline
                    f.pipeline_load.side_effect = preceding
                    stack.enter_context(patch.object(api, target, lambda *args: callback('A', *args)))
                    class Task(dict):
                        def __iter__(self): return super().__iter__()
                        def keys(self):
                            if mode == 'audit': swap()
                            return super().keys()
                        def __getitem__(self, key):
                            if mode == 'resolve' and key == 'manifest_path': swap()
                            return super().__getitem__(key)
                    task = Task(f.tasks['run']); f.tasks['run'] = task
                    if mode == 'resolve':
                        task['manifest_path'] = 'custom.json'; f.files[f.root/'custom.json'] = {'class_names': ['raw']}
                    if mode.startswith('uses'):
                        class Identifier:
                            count = 0
                            def __str__(self):
                                self.count += 1
                                if self.count == (5 if mode == 'uses_second' else 4): swap()
                                return 'a'
                        task['selected_accessory_ids'] = [Identifier()]
                        if mode == 'uses_second':
                            task['pipeline_task_id'] = 'p'
                            f.pipeline = [{'id': 'p', 'detection_method': 'yolo_ocr'}]
                    if mode.startswith('method'):
                        class Pipeline(dict):
                            def get(self, key, *args):
                                if key == 'detection_method': swap()
                                return super().get(key, *args)
                        task['pipeline_task_id'] = 'p'; f.pipeline = [Pipeline(id='p', detection_method='yolo_ocr')]
                        if mode == 'method_second': task['ocr_accessory_ids'] = ['a']
                    if mode == 'profiles':
                        class Identifier(str):
                            def __str__(self):
                                if armed: swap()
                                return self
                        class Meta(dict):
                            def get(self, key, *args):
                                nonlocal armed
                                if key == 'note': armed = True
                                return super().get(key, *args)
                        task['ocr_accessory_ids'] = [Identifier('a')]
                        f.files[f.runs/'run/library_metadata.json'] = Meta(note='fixture')
                    if mode in ('task_path', 'link'):
                        class Run(type(Path())):
                            @property
                            def name(path):
                                path.reads = getattr(path, 'reads', 0) + 1
                                if path.reads == (1 if mode == 'task_path' else 3): swap()
                                return super().name
                        run = Run(f.runs/'run')
                        class Root:
                            def exists(self): return True
                            def iterdir(self): return [run]
                        stack.enter_context(patch.object(api, 'training_run_roots', lambda: [Root()]))
                    if variant == 'missing':
                        with self.assertRaises(TypeError): api.list_trained_model_specs(f.config)
                        expected = ['prior', 'arg']
                    else:
                        api.list_trained_model_specs(f.config)
                        expected = ['arg', 'A'] if variant == 'ordinary' else ['prior', 'arg', 'B']
                        if mode == 'method_first': expected.append('C')
                    if mode == 'uses_second':
                        expected = ['A', 'arg', 'A'] if variant == 'ordinary' else (['A', 'prior', 'arg'] if variant == 'missing' else ['A', 'prior', 'arg', 'B'])
                    self.assertEqual(events, expected)


    def test_direct_pipeline_link_failures_are_not_retried(self):
        api = self.api; f = self.f
        f.pipeline = [{'id': 'pipe', 'model_run_id': 'run', 'name': 'Name'}]
        for target in ('load_pipeline_tasks', 'task_record_name'):
            with self.subTest(target=target):
                error = RuntimeError('first link boundary'); calls = []
                original = getattr(api, target)
                def fail_once(*args):
                    calls.append(args)
                    if len(calls) == 1: raise error
                    return original(*args)
                with patch.object(api, target, fail_once):
                    with self.assertRaises(RuntimeError) as raised:
                        api.pipeline_task_link_for_training_run('run')
                self.assertIs(raised.exception, error); self.assertEqual(len(calls), 1)

    def test_second_catalog_reads_and_ocr_calls_are_not_retried(self):
        api = self.api; f = self.f
        f.run(task={'pipeline_task_id': 'p'})
        f.pipeline = [{'id': 'p', 'detection_method': 'yolo_ocr'}]
        for target in ('load_json_file_mtime_cached', 'accessory_uses_ocr', 'normalize_pipeline_detection_method'):
            with self.subTest(target=target):
                error = RuntimeError('second catalog boundary'); calls = []
                original = getattr(api, target)
                def fail_second(*args):
                    calls.append(args)
                    if len(calls) == 2: raise error
                    return original(*args)
                with patch.object(api, target, fail_second):
                    with self.assertRaises(RuntimeError) as raised:
                        api.list_trained_model_specs(f.config)
                self.assertIs(raised.exception, error); self.assertEqual(len(calls), 2)

    def test_new_catalog_and_loader_getters_fail_once(self):
        from dataclasses import replace
        api = self.api; catalog = api._trained_model_catalog
        cases = [('files', 'task_path'), ('files', 'resolve'), ('files', 'output'),
                 ('access', 'audit'), ('access', 'current_user'), ('accessories', 'uses_ocr'),
                 ('accessories', 'profiles'), ('pipeline', 'method'), ('pipeline', 'link'),
                 ('lookup', 'file_loader')]
        for owner, field in cases:
            with self.subTest(owner=owner, field=field), ExitStack() as stack:
                directory = stack.enter_context(tempfile.TemporaryDirectory(prefix='catalog-getter-'))
                f = Fixture(Path(directory)); f.bind(api, stack)
                f.run(task={'manifest_path': 'custom.json', 'pipeline_task_id': 'p'})
                f.pipeline = [{'id': 'p', 'detection_method': 'yolo_ocr'}]
                error = RuntimeError('first getter failure'); calls = []
                original = getattr(api._training_task_lookup, field) if owner == 'lookup' else getattr(getattr(catalog, owner), field)
                def fail_once():
                    calls.append(field)
                    if len(calls) == 1: raise error
                    return original()
                if owner == 'lookup': stack.enter_context(patch.object(api._training_task_lookup, field, fail_once))
                else: stack.enter_context(patch.object(catalog, owner, replace(getattr(catalog, owner), **{field: fail_once})))
                with self.assertRaises(RuntimeError) as raised:
                    if owner == 'lookup': api.training_task_finder()
                    else: api.list_trained_model_specs(f.config)
                self.assertIs(raised.exception, error); self.assertEqual(calls, [field])


if __name__ == '__main__': unittest.main()
