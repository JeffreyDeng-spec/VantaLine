"""Detection task persistence contracts using synthetic records and local storage."""
from contextlib import ExitStack
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import uuid
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
PG_CHECK = '--postgres' in sys.argv
if PG_CHECK: sys.argv.remove('--postgres')


def task(identifier='task', **values):
    return dict(id=identifier, name=' Task ', required_accessory_counts={'a': 2},
                created_at=10, updated_at=20, owner_user_id='alice', **values)


class Fixture:
    def __init__(self, directory):
        self.directory = Path(directory)/'data'
        self.path = self.directory/'tasks.json'
        self.repo = None; self.cache = {}; self.events = []; self.choices = []
    def ensure(self):
        self.events.append('ensure'); self.directory.mkdir(parents=True, exist_ok=True)
    def repository(self):
        self.events.append(('repository', self.directory.exists()))
        value = self.choices.pop(0) if self.choices else self.repo
        if isinstance(value, Exception): raise value
        return value
    def get(self, key):
        self.events.append(('get', key)); return (key in self.cache, self.cache.get(key))
    def put(self, key, value): self.events.append(('put', key)); self.cache[key] = value
    def invalidate(self, key): self.events.append(('invalidate', key)); self.cache.pop(key, None)
    def background(self, value): return value.strip().lower().replace(' ', '_')
    def bind(self, api, stack):
        for name, value in {'DATA_DIR':self.directory, 'AI_DETECTION_TASKS_PATH':self.path,
                'runtime_postgres_repository_or_none':self.repository, 'ensure_dirs':self.ensure,
                'store_read_cache_get':self.get, 'store_read_cache_put':self.put,
                'store_read_cache_invalidate':self.invalidate, 'safe_background_set_id':self.background}.items():
            stack.enter_context(patch.object(api, name, value))
    def seed(self, value):
        self.directory.mkdir(parents=True, exist_ok=True); self.path.write_text(json.dumps(value), encoding='utf-8')


class TaskStoreContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix='detection-store-root-')
        root = Path(cls.temporary.name); (root/'local_inspection_service/static').mkdir(parents=True)
        os.environ.update(LOCAL_INSPECTION_ROOT=str(root), VANTALINE_DATA_STORE='json',
                          LOCAL_INSPECTION_AUTO_RESUME_WORKER='0', VANTALINE_LABEL_INSPECTION_ENABLED='false')
        from local_inspection_service import server
        cls.api = server
    @classmethod
    def tearDownClass(cls): cls.temporary.cleanup()
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='task-store-'); self.addCleanup(self.temporary.cleanup)
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        self.f = Fixture(self.temporary.name); self.f.bind(self.api, self.stack)
    def test_read_first_failures_keep_cache_and_storage_without_retry(self):
        api=self.api
        for mode in ('cache_get','ensure','repository','fetch','decode','normalize','cache_put','exists','read'):
            with self.subTest(mode=mode),ExitStack() as stack:
                f=Fixture(Path(self.temporary.name)/mode);f.bind(api,stack)
                raw=task('original',background_set_id='blue');f.seed({'tasks':[raw]})
                original_bytes=f.path.read_bytes();repo=Mock();repo.fetch_all.return_value=[{'raw_json':raw}]
                f.repo=None if mode in ('exists','read') else repo
                error=RuntimeError(mode)
                bindings={'cache_get':(api,'store_read_cache_get'),'ensure':(api,'ensure_dirs'),
                          'repository':(api,'runtime_postgres_repository_or_none'),'fetch':(repo,'fetch_all'),
                          'decode':(api,'row_raw_json_list'),'normalize':(api,'safe_background_set_id'),
                          'cache_put':(api,'store_read_cache_put'),'exists':(Path,'exists'),'read':(Path,'read_text')}
                owner,name=bindings[mode];operation=getattr(owner,name);attempts=[]
                def first_error(*args,**kwargs):
                    if mode=='exists' and args[0]!=f.path:return operation(*args,**kwargs)
                    attempts.append(1)
                    if len(attempts)==1:raise error
                    return operation(*args,**kwargs)
                target=stack.enter_context(patch.object(owner,name,autospec=owner is Path,side_effect=first_error))
                with self.assertRaises(RuntimeError) as caught:api.load_ai_detection_tasks()
                self.assertIs(caught.exception,error);self.assertEqual(attempts,[1])
                if mode=='exists':self.assertEqual(sum(call.args[0]==f.path for call in target.call_args_list),1)
                else:target.assert_called_once()
                self.assertEqual(f.cache,{})
                repo.replace_all.assert_not_called();repo.upsert_row.assert_not_called()
                if mode in ('cache_get','ensure','repository'):repo.fetch_all.assert_not_called()
                if mode!='read':self.assertEqual(f.path.read_bytes(),original_bytes)

    def test_write_first_failures_retain_invalidation_and_file_evidence(self):
        api=self.api
        for kind in ('batch','single'):
            for mode in ('invalidate','mkdir','repository','encode','database_write','write','replace'):
                with self.subTest(kind=kind,mode=mode),ExitStack() as stack:
                    f=Fixture(Path(self.temporary.name)/(kind+'_'+mode));f.bind(api,stack)
                    f.seed({'tasks':[task('old')]});before=f.path.read_bytes()
                    temporary=f.path.with_suffix('.json.tmp');temporary.write_bytes(b'temporary-before')
                    f.cache['ai_detection_tasks']=[task('cached')]
                    repo=Mock();f.repo=None if mode in ('write','replace') else repo
                    error=RuntimeError(kind+'_'+mode)
                    name='replace_all' if kind=='batch' else 'upsert_row'
                    bindings={'invalidate':(api,'store_read_cache_invalidate'),'mkdir':(Path,'mkdir'),
                              'repository':(api,'runtime_postgres_repository_or_none'),'encode':(api,'ai_detection_task_row'),
                              'database_write':(repo,name),'write':(Path,'write_text'),'replace':(Path,'replace')}
                    owner,attribute=bindings[mode];operation=getattr(owner,attribute)
                    def first_error(*args,**kwargs):
                        if target.call_count==1:raise error
                        return operation(*args,**kwargs)
                    target=stack.enter_context(patch.object(owner,attribute,autospec=owner is Path,side_effect=first_error))
                    value=task('new')
                    with self.assertRaises(RuntimeError) as caught:
                        if kind=='batch':api.save_ai_detection_tasks([value])
                        else:api.save_ai_detection_task(value,prepend=True)
                    self.assertIs(caught.exception,error);target.assert_called_once()
                    self.assertEqual(f.cache,{'ai_detection_tasks':[task('cached')]} if mode=='invalidate' else {})
                    self.assertEqual(f.path.read_bytes(),before)
                    if mode=='replace':
                        payload=json.loads(temporary.read_text(encoding='utf-8'))['tasks']
                        self.assertEqual(payload[0],value)
                        self.assertEqual(len(payload),1 if kind=='batch' else 2)
                    else:self.assertEqual(temporary.read_bytes(),b'temporary-before')
                    if mode!='database_write':repo.replace_all.assert_not_called();repo.upsert_row.assert_not_called()

    def test_background_first_failures_leave_workflow_state_unchanged(self):
        api=self.api
        for mode in ('find','record_normalize','current_normalize','resolver'):
            with self.subTest(mode=mode):
                raw=task('background',background_set_id='blue');error=RuntimeError(mode)
                state={'task_id':'background','background_set_id':'','untouched':['evidence']};before=json.loads(json.dumps(state))
                finder=Mock(return_value=raw);normalizer=Mock(return_value='');resolver=Mock(return_value=('blue',{'background_set_id':'blue'}))
                target=finder if mode=='find' else resolver if mode=='resolver' else normalizer
                success=raw if mode=='find' else ('blue',{'background_set_id':'blue'}) if mode=='resolver' else 'blue'
                def first_error(*args,**kwargs):
                    if target.call_count==1:raise error
                    return success
                target.side_effect=first_error
                with patch.multiple(api,find_ai_detection_task=finder,safe_background_set_id=normalizer):
                    if mode in ('find','record_normalize'):
                        with self.assertRaises(RuntimeError) as caught:api.ai_detection_task_background_record('background')
                    else:
                        with patch.object(api,'ai_detection_task_background_record',resolver):
                            with self.assertRaises(RuntimeError) as caught:api.hydrate_auto_optimize_background_from_ai_task(state)
                self.assertIs(caught.exception,error);target.assert_called_once();self.assertEqual(state,before)
                if mode=='find':normalizer.assert_not_called()
                if mode=='current_normalize':resolver.assert_not_called()


    def _capture_task_callback(self,mode,missing=False,prior=False):
        api=self.api;f=self.f;events=[]
        target_name='row_raw_json_list' if mode=='decode' else 'ai_detection_task_background_record' if mode=='hydrate_task' else 'safe_background_set_id'
        def value():return [] if mode=='decode' else ('',{}) if mode=='hydrate_task' else 'blue'
        def first(*args):events.append('B' if prior else 'A');return value()
        def replacement(*args):events.append('C' if prior else 'B');return value()
        def swap():events.append('arg');setattr(api,target_name,replacement)
        def advance():events.append('prior');setattr(api,target_name,first)
        class Text:
            def __str__(self):swap();return 'blue'
        raw=task('task',background_set_id=Text() if mode in ('load_background','background_record') else 'blue')
        def fetch(*args):
            if mode=='decode':swap()
            return [{'raw_json':raw}]
        repo=Mock();repo.fetch_all.side_effect=fetch;f.repo=repo;f.cache.clear()
        def repository():
            if prior and mode=='decode':advance()
            return repo
        def decode(rows):
            if prior and mode=='load_background':advance()
            return [raw]
        def find(identity):
            if prior and mode=='background_record':advance()
            return raw
        def normalizer(text):
            if prior and mode=='hydrate_task':advance()
            return ''
        callbacks={'runtime_postgres_repository_or_none':repository,'row_raw_json_list':decode,
                   'find_ai_detection_task':find,'safe_background_set_id':normalizer}
        callbacks[target_name]=Mock(side_effect=AssertionError('captured before preceding work')) if prior else (None if missing else first)
        with patch.multiple(api,**callbacks):
            def invoke():
                if mode in ('decode','load_background'):return api.load_ai_detection_tasks()
                if mode=='background_record':return api.ai_detection_task_background_record('task')
                if mode=='hydrate_current':return api.hydrate_auto_optimize_background_from_ai_task({'background_set_id':Text()})
                return api.hydrate_auto_optimize_background_from_ai_task({'task_id':Text()})
            if missing:
                with self.assertRaises(TypeError):invoke()
            else:invoke()
        self.assertEqual(events,(['prior'] if prior else [])+['arg']+([] if missing else ['B' if prior else 'A']))

    def test_callback_capture_before_argument_effects(self):
        for mode in ('decode','load_background','background_record','hydrate_current','hydrate_task'):
            with self.subTest(mode=mode):self._capture_task_callback(mode)

    def test_callback_capture_after_preceding_work(self):
        for mode in ('decode','load_background','background_record','hydrate_task'):
            with self.subTest(mode=mode):self._capture_task_callback(mode,prior=True)

    def test_missing_callback_preserves_argument_effects(self):
        for mode in ('decode','load_background','background_record','hydrate_current','hydrate_task'):
            with self.subTest(mode=mode):self._capture_task_callback(mode,missing=True)


    def test_identity_and_count_edge_cases(self):
        api=self.api
        self.assertEqual(api.sanitize_ai_detection_task_id(' __A 中文 B--___ '), 'a_b--')
        self.assertEqual(api.sanitize_ai_detection_task_id('A'*80), 'a'*72)
        self.assertEqual(api.sanitize_ai_detection_task_id(0), '')
        self.assertEqual(api.clean_ai_detection_task_name(' A\n B\t中 ', 'fallback'), 'A B 中')
        self.assertEqual(api.clean_ai_detection_task_name('', ''), 'AI 检测任务')
        self.assertEqual(api.clean_ai_detection_task_name('', 'f'*100), 'f'*96)
        self.assertEqual(api.normalize_ai_detection_task_counts({' a ':0, 'b':100, 'c':'bad', 'd':None, ' ':7, 0:9, 'e':2.9}),
                         {'a':1, 'b':99, 'c':1, 'd':1, 'e':2})
        with self.assertRaises(OverflowError): api.normalize_ai_detection_task_counts({'a':float('inf')})
        with self.assertRaises(AttributeError): api.normalize_ai_detection_task_counts([])
        with patch.object(api, 'AI_DETECTION_TASK_PREFIX', 'other:'):
            self.assertEqual(api.ai_detection_task_model_id(' A '), 'other: A ')
    def test_load_normalization_sort_cache_and_shallow_aliases(self):
        f=self.f; api=self.api; shared=['bob']; environment={'background_set_id':' Blue Room ', 'other':[1]}
        raw=task(' A! ', selected_accessory_ids=['a','x','a'], accessory_labels={'a':' Label ', 'x':'unused'},
                 shared_with_user_ids=shared, environment_background=environment)
        other=task('b'); other['updated_at']=20
        invalid=task(''); empty=task('empty'); empty['required_accessory_counts']={}
        repo=Mock(); repo.fetch_all.return_value=[{'raw_json':v} for v in (raw, other, invalid, empty)]; f.repo=repo
        values=api.load_ai_detection_tasks(); self.assertEqual([v['id'] for v in values], ['b','a'])
        got=values[1]; self.assertEqual(got['selected_accessory_ids'], ['a','a'])
        self.assertEqual(got['accessory_labels'], {'a':' Label '}); self.assertEqual(got['name'],'Task')
        self.assertEqual(got['background_set_id'],'blue_room'); self.assertIsNot(got['environment_background'],environment)
        self.assertIs(got['environment_background']['other'],environment['other']); self.assertIs(got['shared_with_user_ids'], shared)
        self.assertIsNot(values,f.cache['ai_detection_tasks']); self.assertIs(values[1],f.cache['ai_detection_tasks'][1])
        values.pop(); f.events=[]; again=api.load_ai_detection_tasks()
        self.assertEqual(len(again),2); self.assertEqual(f.events,[('get','ai_detection_tasks')])
        self.assertIs(api.find_ai_detection_task(' A! '),got)
        f.events=[]; self.assertIsNone(api.find_ai_detection_task('中文')); self.assertEqual(f.events,[])
        f.cache.clear(); f.repo=None; fallback=task('fallback'); fallback['selected_accessory_ids']=['not-present']
        fallback['background_set_id']='green_conveyor'; fallback['created_at']=0; fallback['updated_at']=0
        fallback['shared_with_user_ids']='not-list'; f.seed({'tasks':[fallback, 2]})
        with patch('time.time',return_value=123): value=api.load_ai_detection_tasks()[0]
        self.assertEqual(value['created_at'],123); self.assertEqual(value['updated_at'],123)
        self.assertEqual(value['selected_accessory_ids'],['a']); self.assertEqual(value['shared_with_user_ids'],[])
        self.assertNotIn('background_set_id',value); self.assertNotIn('environment_background',value)
    def test_json_read_failures_do_not_cache_or_hide_io_errors(self):
        f=self.f; api=self.api
        self.assertEqual(api.load_ai_detection_tasks(),[]); self.assertEqual(f.cache,{})
        for value in ('{bad','{}','null','123','{"tasks":{}}'):
            f.seed([]); f.path.write_text(value,encoding='utf-8')
            self.assertEqual(api.load_ai_detection_tasks(),[]); self.assertEqual(f.cache,{})
        f.path.write_bytes(b'\xff')
        with self.assertRaises(UnicodeDecodeError): api.load_ai_detection_tasks()
        with patch.object(Path,'read_text',side_effect=PermissionError('read')):
            with self.assertRaisesRegex(PermissionError,'read'): api.load_ai_detection_tasks()
        with patch.object(Path,'exists',side_effect=OSError('exists')):
            with self.assertRaisesRegex(OSError,'exists'): api.load_ai_detection_tasks()
        f.seed([]); self.assertEqual(api.load_ai_detection_tasks(),[]); self.assertEqual(f.cache,{'ai_detection_tasks':[]})
    def test_json_single_save_replaces_normalized_id_and_retains_raw_payload(self):
        f=self.f; api=self.api; a=task('A'); b=task('b'); b['updated_at']=30
        api.save_ai_detection_tasks([a,b]); self.assertEqual(json.loads(f.path.read_text())['tasks'],[a,b])
        replacement=task(' A! '); replacement['name']='中文 raw'; f.events=[]
        api.save_ai_detection_task(replacement,prepend=True)
        values=json.loads(f.path.read_text(encoding='utf-8'))['tasks']
        self.assertEqual(values[0]['id'],'b'); self.assertEqual(values[1],replacement)
        self.assertEqual([e[0] for e in f.events if isinstance(e,tuple)],
                         ['invalidate','repository','get','repository','put','invalidate','repository'])
        fresh=task('new'); api.save_ai_detection_task(fresh,prepend=True)
        self.assertEqual(json.loads(f.path.read_text())['tasks'][0],fresh)
        appended=task('last'); api.save_ai_detection_task(appended)
        self.assertEqual(json.loads(f.path.read_text())['tasks'][-1],appended)
        self.assertEqual(f.cache,{}); self.assertFalse(f.path.with_suffix('.json.tmp').exists())
    def test_save_errors_preserve_invalidation_directory_and_temp_residue(self):
        f=self.f; api=self.api; f.repo=RuntimeError('factory'); f.cache['ai_detection_tasks']=[task()]
        with self.assertRaisesRegex(RuntimeError,'factory'): api.save_ai_detection_tasks([])
        self.assertEqual(f.events,[('invalidate','ai_detection_tasks'),('repository',True)])
        self.assertEqual(f.cache,{}); self.assertTrue(f.directory.exists()); self.assertFalse(f.path.exists())
        f.repo=None; f.seed({'tasks':[task('old')]})
        with patch.object(Path,'replace',side_effect=PermissionError('replace')):
            with self.assertRaisesRegex(PermissionError,'replace'): api.save_ai_detection_tasks([task('new')])
        self.assertEqual(json.loads(f.path.read_text())['tasks'][0]['id'],'old')
        self.assertEqual(json.loads(f.path.with_suffix('.json.tmp').read_text())['tasks'][0]['id'],'new')
        with self.assertRaises(TypeError): api.save_ai_detection_tasks([{'bad':object()}])
        self.assertEqual(json.loads(f.path.with_suffix('.json.tmp').read_text())['tasks'][0]['id'],'new')
    def test_postgres_dispatch_late_selection_and_no_json_fallback(self):
        f=self.f; api=self.api; repo=Mock(); f.repo=repo
        api.save_ai_detection_tasks([task(),{},3]); repo.replace_all.assert_called_once()
        table,rows=repo.replace_all.call_args.args; self.assertEqual(table,'ai_detection_tasks'); self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['raw_json'],task()); self.assertFalse(f.path.exists())
        api.save_ai_detection_task({},prepend=True); repo.upsert_row.assert_not_called()
        api.save_ai_detection_task(task('single'),prepend=True); repo.upsert_row.assert_called_once()
        self.assertEqual(repo.upsert_row.call_args.args[1]['raw_json'],task('single'))
        f.cache.clear(); repo.fetch_all.side_effect=RuntimeError('database'); f.seed({'tasks':[task('json')]})
        with self.assertRaisesRegex(RuntimeError,'database'): api.load_ai_detection_tasks()
        self.assertEqual(f.cache,{})
        f.repo=None; f.events=[]; f.choices=[None, repo]; repo.fetch_all.side_effect=None
        repo.fetch_all.return_value=[{'raw_json':task('db')}]; f.choices.append(repo)
        api.save_ai_detection_task(task('new'))
        self.assertEqual([v['id'] for v in repo.replace_all.call_args.args[1]],['db','new'])
        self.assertEqual(json.loads(f.path.read_text())['tasks'][0]['id'],'json')
    def test_background_hydration_retains_existing_and_copies_environment(self):
        f=self.f; api=self.api; environment={'background_set_id':' Blue Room ', 'data':[1]}
        raw=task('a',environment_background=environment); f.cache['ai_detection_tasks']=[raw]
        key,value=api.ai_detection_task_background_record(' A ')
        self.assertEqual(key,'blue_room'); self.assertIsNot(value,environment); self.assertIs(value['data'],environment['data'])
        state={'task_id':'a','background_set_id':'green_conveyor'}
        self.assertTrue(api.hydrate_auto_optimize_background_from_ai_task(state))
        self.assertEqual(state['environment_background'],value); f.events=[]
        self.assertFalse(api.hydrate_auto_optimize_background_from_ai_task(state)); self.assertEqual(f.events,[])
        self.assertEqual(api.ai_detection_task_background_record(''),('',{})); self.assertEqual(f.events,[])
        raw['background_set_id']='green_conveyor'
        self.assertFalse(api.hydrate_auto_optimize_background_from_ai_task({'task_id':'a'}))
        self.assertEqual(api.ai_detection_task_background_record('missing'),('',{}))


    def test_composition_late_paths_rows_and_independent_service_instances(self):
        from local_inspection_service.detection import task_identity, task_backgrounds
        from local_inspection_service.detection.task_store import DetectionTaskStore, TaskStorePaths, TaskReadCache, TaskRows
        from local_inspection_service.storage.runtime_records import ai_detection_task_row, row_raw_json_list
        api=self.api; f=self.f
        self.assertIs(api.sanitize_ai_detection_task_id,task_identity.sanitize_ai_detection_task_id)
        def service(fixture):
            return DetectionTaskStore(fixture.repository,
                TaskStorePaths(lambda:fixture.directory, lambda:fixture.path, fixture.ensure),
                TaskReadCache(fixture.get,fixture.put,fixture.invalidate),
                TaskRows(ai_detection_task_row,lambda:row_raw_json_list),lambda:fixture.background)
        second=Fixture(Path(self.temporary.name)/'second'); first_store=service(f); second_store=service(second)
        first_store.save_ai_detection_task(task('first')); second_store.save_ai_detection_task(task('second'))
        self.assertEqual(first_store.load_ai_detection_tasks()[0]['id'],'first')
        self.assertEqual(second_store.load_ai_detection_tasks()[0]['id'],'second')
        self.assertIsNot(f.cache['ai_detection_tasks'],second.cache['ai_detection_tasks'])
        moved=f.directory/'moved.json'
        with patch.object(api,'AI_DETECTION_TASKS_PATH',moved): api.save_ai_detection_tasks([task('moved')])
        self.assertEqual(json.loads(moved.read_text())['tasks'][0]['id'],'moved')
        self.assertEqual(json.loads(f.path.read_text())['tasks'][0]['id'],'first')
        repo=Mock(); f.repo=repo; f.events=[]
        with patch.object(api,'ai_detection_task_row',side_effect=ValueError('row')):
            with self.assertRaisesRegex(ValueError,'row'): api.save_ai_detection_task(task())
        self.assertEqual(f.events,[('invalidate','ai_detection_tasks'),('repository',True)]); repo.upsert_row.assert_not_called()
        f.cache.clear(); repo.fetch_all.return_value=[]
        with patch.object(api,'row_raw_json_list',return_value=[task('decode')]):
            self.assertEqual(api.load_ai_detection_tasks()[0]['id'],'decode')
        environment={'background_set_id':'other'}
        with patch.object(api,'ai_detection_task_background_record',return_value=('other',environment)) as resolver:
            state={'task_id':'first'}; self.assertTrue(api.hydrate_auto_optimize_background_from_ai_task(state))
            self.assertIs(state['environment_background'],environment); resolver.assert_called_once_with('first')
        finder=Mock(return_value=task('first',background_set_id='blue'))
        self.assertEqual(task_backgrounds.ai_detection_task_background_record(' FIRST ',find_task=finder,
                         normalize_background=lambda:f.background)[0],'blue'); finder.assert_called_once_with('first')

    @unittest.skipUnless(PG_CHECK,'use --postgres with an isolated test DSN')
    def test_real_postgres_replace_upsert_invalid_rows_and_readback(self):
        import psycopg
        from psycopg import sql
        from local_inspection_service.storage.postgres_schema import postgres_ddl
        from local_inspection_service.storage.postgres_runtime_repository import PostgresRuntimeRepository
        dsn=os.environ['VANTALINE_POSTGRES_DSN']; schema='detection_task_store_'+uuid.uuid4().hex
        with psycopg.connect(dsn,autocommit=True) as control:
            control.execute(postgres_ddl(schema))
            try:
                with psycopg.connect(dsn) as connection:
                    self.f.repo=PostgresRuntimeRepository(connection,'test',schema); api=self.api
                    original=task(' A! ',shared_with_user_ids=['bob'],background_set_id='Blue Room')
                    api.save_ai_detection_tasks([original,{},False]); rows=self.f.repo.fetch_all('ai_detection_tasks')
                    self.assertEqual(len(rows),1); self.assertEqual(rows[0]['id'],'A!'); self.assertEqual(rows[0]['raw_json'],original)
                    loaded=api.load_ai_detection_tasks()[0]; self.assertEqual(loaded['id'],'a'); self.assertEqual(loaded['background_set_id'],'blue_room')
                    changed=task(' A! '); changed['name']='changed'
                    api.save_ai_detection_task(changed,prepend=True)
                    self.assertEqual(api.find_ai_detection_task('A!')['name'],'changed')
                    api.save_ai_detection_task({}); self.assertEqual(len(self.f.repo.fetch_all('ai_detection_tasks')),1)
                    api.save_ai_detection_task(task('second')); self.assertEqual(len(api.load_ai_detection_tasks()),2)
                    api.save_ai_detection_tasks([{},4]); self.assertEqual(api.load_ai_detection_tasks(),[])
                    self.assertFalse(self.f.path.exists())
            finally: control.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))


if __name__ == '__main__': unittest.main()
