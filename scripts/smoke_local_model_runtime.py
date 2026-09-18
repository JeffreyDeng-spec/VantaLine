"""Model selection and process-local cache contracts; no real model is loaded."""
from contextlib import ExitStack
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch, call
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


class LocalModelContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='local-model-root-')
        root=Path(cls.temp.name);(root/'local_inspection_service/static').mkdir(parents=True)
        os.environ.update(LOCAL_INSPECTION_ROOT=str(root),VANTALINE_DATA_STORE='json',
                          LOCAL_INSPECTION_AUTO_RESUME_WORKER='0',VANTALINE_LABEL_INSPECTION_ENABLED='false')
        from local_inspection_service import server
        cls.api=server
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.directory=tempfile.TemporaryDirectory(prefix='local-model-files-');self.addCleanup(self.directory.cleanup)
        self.path=Path(self.directory.name)/'fixture.pt';self.path.write_bytes(b'synthetic-not-a-model')
        self.registry={'default':{'id':'default','path':self.path}}
        self.specialized=Mock(return_value=[]);self.trained=Mock(return_value=[]);self.legacy=Mock(return_value=[])
        self.factory=Mock(side_effect=lambda path:object())
        for name,value in {'DEFAULT_MODEL_ID':'default','MODEL_REGISTRY':self.registry,
                'list_ai_detection_specialized_model_specs':self.specialized,'list_trained_model_specs':self.trained,
                'legacy_model_specs':self.legacy,'YOLO':self.factory}.items():
            self.stack.enter_context(patch.object(self.api,name,value))
        # Mutate the documented compatibility objects, not root assignment hooks.
        self.models=self.api._models;self.paths=self.api._model_paths
        old_models=dict(self.models);old_paths=dict(self.paths);self.models.clear();self.paths.clear()
        def restore():self.models.clear();self.models.update(old_models);self.paths.clear();self.paths.update(old_paths)
        self.addCleanup(restore)
    def test_selection_precedence_identity_and_typeerror_compatibility(self):
        api=self.api;config={'active_model_id':'chosen'};first={'id':'chosen','origin':'first'};second={'id':'chosen','origin':'second'}
        self.specialized.return_value=[first,second]
        self.assertIs(api.selected_model_spec(None,config),first);self.specialized.assert_called_once_with(config);self.trained.assert_not_called()
        self.specialized.return_value=[];self.trained.return_value=[second,first]
        self.assertIs(api.selected_model_spec('chosen',config),second);self.trained.assert_called_once_with(config)
        self.trained.reset_mock();self.trained.side_effect=[TypeError('inside provider'),[first]]
        self.assertIs(api.selected_model_spec('chosen',config),first)
        self.assertEqual(self.trained.call_args_list,[call(config),call()])
        self.trained.side_effect=None;self.trained.return_value=[]
        self.assertIs(api.selected_model_spec('',{}),self.registry['default'])
        with self.assertRaises(api.HTTPException) as error:api.selected_model_spec('absent',{})
        self.assertEqual(error.exception.status_code,400);self.assertEqual(error.exception.detail,'Unknown model_id: absent')
        self.specialized.side_effect=TypeError('specialized');self.trained.reset_mock()
        with self.assertRaisesRegex(TypeError,'specialized'):api.selected_model_spec('default',config)
        self.trained.assert_not_called()
    def test_removed_feature_explicit_and_configured_fallback(self):
        api=self.api
        with patch.object(api,'removed_phase1_feature',side_effect=api.HTTPException(410,'removed')) as removed:
            with self.assertRaises(api.HTTPException) as error:api.selected_model_spec('label_sheet_local_match',{})
            self.assertEqual(error.exception.status_code,410);removed.assert_called_once_with('Label Sheet')
            removed.reset_mock();self.assertIs(api.selected_model_spec(None,{'active_model_id':'label_sheet_local_match'}),self.registry['default'])
            removed.assert_not_called()
        with patch.object(api,'removed_phase1_feature',return_value=None):
            self.assertIs(api.selected_model_spec('label_sheet_local_match',{}),self.registry['default'])
    def test_remote_model_guards_and_cached_spec_validation(self):
        api=self.api
        for flags,message in [({'is_ai_detection':True,'is_label_sheet_match':True},'AI Detection does not use a local YOLO model'),
                              ({'is_label_sheet_match':True},'Label sheet matching does not use a local YOLO model')]:
            with patch.object(api,'selected_model_spec',return_value=flags):
                with self.assertRaises(RuntimeError) as error:api.model()
                self.assertEqual(str(error.exception),message)
        self.factory.assert_not_called();self.assertEqual(self.models,{})
        self.models['cached']=object()
        with patch.object(api,'selected_model_spec',return_value={'id':'cached','path':None}):
            with self.assertRaises(TypeError):api.model('cached')
        with patch.object(api,'selected_model_spec',return_value={'id':'cached','path':self.path.parent/'missing.pt'}):
            self.assertIs(api.model('cached'),self.models['cached'])
        self.factory.assert_not_called()
    def test_model_cache_by_id_and_resolved_path_preserves_precedence(self):
        api=self.api;first=api.model();self.factory.assert_called_once_with(str(self.path))
        self.assertIs(self.models['default'],first);self.assertEqual(self.paths['default'],self.path.resolve())
        alternate=self.path.parent/'alternate.pt';alternate.write_bytes(b'other')
        self.registry['default']['path']=alternate
        self.assertIs(api.model(),first);self.assertEqual(self.paths['default'],self.path.resolve());self.assertEqual(self.factory.call_count,1)
        self.registry['alias']={'id':'alias','path':self.path.parent/'.'/self.path.name}
        self.assertIs(api.model('alias'),first);self.assertEqual(self.paths['alias'],self.path.resolve());self.assertEqual(self.factory.call_count,1)
        # A stale cache path without its instance cannot be reused.
        self.models.clear();self.paths.clear();self.paths['stale']=self.path.resolve()
        second=api.model('alias');self.assertIsNot(second,first);self.assertEqual(self.factory.call_count,2)
        self.assertNotIn('stale',self.models)
    def test_missing_files_and_factory_errors_do_not_poison_cache(self):
        api=self.api;missing=self.path.parent/'missing.pt';self.paths['cached']=missing.resolve();self.models['cached']=object()
        self.registry['missing']={'id':'missing','path':missing}
        with self.assertRaisesRegex(RuntimeError,'Model file not found'):api.model('missing')
        self.assertNotIn('missing',self.models);self.factory.assert_not_called()
        self.factory.side_effect=RuntimeError('factory')
        with self.assertRaisesRegex(RuntimeError,'factory'):api.model()
        self.assertNotIn('default',self.models);self.assertNotIn('default',self.paths)
        self.factory.side_effect=None;instance=object();self.factory.return_value=instance
        self.assertIs(api.model(),instance);self.assertEqual(self.factory.call_count,2)
    def test_loaded_ids_empty_paths_and_alias_discovery(self):
        api=self.api;self.models.update({'':object(),'z':object()})
        self.assertEqual(api.yolo_loaded_model_ids({}),['','z']);self.legacy.assert_not_called();self.trained.assert_not_called()
        self.paths['z']=self.path.resolve();self.legacy.return_value=[{'id':'legacy','path':self.path},
            {'id':'ai','path':self.path,'is_ai_detection':True},{'id':'sheet','path':self.path,'is_label_sheet_match':True},
            {'id':'bad','path':123},{'id':'other','path':self.path.parent/'other'}]
        self.trained.return_value=[{'id':'trained','path':self.path},{'id':'','path':self.path}]
        config={'fixture':True};self.assertEqual(api.yolo_loaded_model_ids(config),['legacy','trained','z'])
        self.legacy.assert_called_once_with();self.trained.assert_called_once_with(config)
        self.assertTrue(api.yolo_model_ready('trained',config));self.assertFalse(api.yolo_model_ready('',config))
        self.factory.assert_not_called()
    def test_loaded_ids_error_boundaries_and_registry_reads_remain_lazy(self):
        api=self.api;self.paths['cached']=self.path.resolve();self.legacy.side_effect=RuntimeError('legacy')
        with self.assertRaisesRegex(RuntimeError,'legacy'):api.yolo_loaded_model_ids({})
        self.trained.assert_not_called();self.legacy.side_effect=None
        self.legacy.return_value=[{'id':'file','path':self.path}]
        with patch.object(Path,'resolve',side_effect=OSError('resolve')):self.assertEqual(api.yolo_loaded_model_ids({}),[])
        with patch.object(Path,'resolve',side_effect=ValueError('resolve')):
            with self.assertRaisesRegex(ValueError,'resolve'):api.yolo_loaded_model_ids({})
        self.legacy.return_value=[];self.paths.clear();self.registry['other']={'id':'other','path':self.path}
        with patch.object(api,'DEFAULT_MODEL_ID','other'):
            self.assertIs(api.selected_model_spec(None),self.registry['other'])

    def test_popped_aliases_stale_ready_and_original_factory_path(self):
        api=self.api;self.models['']=object()
        self.assertTrue(api.yolo_model_ready('',{}));self.models.clear()
        nested=self.path.parent/'nested';nested.mkdir()
        raw=nested/'..'/self.path.name;self.registry['default']['path']=raw
        first=api.model();self.factory.assert_called_once_with(str(raw))
        self.registry['alias']={'id':'alias','path':self.path};self.assertIs(api.model('alias'),first)
        self.models.pop('default');self.assertIs(api.model(),first);self.assertEqual(self.factory.call_count,1)
        self.models.clear();self.trained.return_value=[{'id':'still-ready','path':self.path}]
        self.assertTrue(api.yolo_model_ready('still-ready',{}));self.assertEqual(self.models,{})
        self.trained.return_value=[]
        before=dict(self.paths)
        for method in ('exists','resolve'):
            with patch.object(Path,method,side_effect=OSError(method)):
                with self.assertRaisesRegex(OSError,method):api.model()
            self.assertEqual(self.models,{});self.assertEqual(self.paths,before)
        self.assertIsNot(api.model(),first);self.assertEqual(self.factory.call_count,2)


    def test_construction_is_lazy_and_instance_state_is_independent(self):
        from local_inspection_service.detection.model_selection import ModelSelection
        from local_inspection_service.detection.local_models import LocalModels
        specialized=Mock(return_value=[]);trained=Mock(return_value=[])
        registry=Mock(return_value=self.registry);default=Mock(return_value='default');removed=Mock()
        selection=ModelSelection(specialized,trained,registry,default,removed)
        factory=Mock(side_effect=lambda path:object());legacy=Mock(return_value=[])
        first=LocalModels(selection.selected_model_spec,lambda:factory,legacy,trained)
        second=LocalModels(selection.selected_model_spec,lambda:factory,legacy,trained)
        for provider in (specialized,trained,registry,default,removed,factory,legacy):provider.assert_not_called()
        self.assertIs(self.api._models,self.api._local_models.models)
        self.assertIs(self.api._model_paths,self.api._local_models.paths)
        self.assertIsNot(first.models,second.models);self.assertIsNot(first.paths,second.paths)
        one=first.model();two=second.model();self.assertIsNot(one,two);self.assertEqual(factory.call_count,2)
        first.models.pop('default');self.assertIs(second.model(),two);self.assertNotIn('default',first.models)
        self.assertEqual(first.paths['default'],self.path.resolve())


    def test_existing_model_callbacks_preserve_first_failure_and_cache(self):
        api = self.api
        names = ('list_ai_detection_specialized_model_specs', 'list_trained_model_specs',
            'removed_phase1_feature', 'selected_model_spec', 'YOLO', 'legacy_model_specs')
        cases = [
            ('list_ai_detection_specialized_model_specs', lambda: api.selected_model_spec('default', {}), []),
            ('list_trained_model_specs', lambda: api.selected_model_spec('default', {}), []),
            ('removed_phase1_feature', lambda: api.selected_model_spec('label_sheet_local_match', {}), None),
            ('selected_model_spec', lambda: api.model('default', {}), self.registry['default']),
            ('YOLO', lambda: api.model('default', {}), object()),
            ('legacy_model_specs', lambda: api.yolo_loaded_model_ids({}), []),
            ('legacy_model_specs', lambda: api.yolo_model_ready('default', {}), []),
            ('list_trained_model_specs', lambda: api.yolo_loaded_model_ids({}), []),
        ]
        for target, operation, valid in cases:
            with self.subTest(target=target, operation=operation):
                self.models.clear(); self.paths.clear()
                self.paths['known'] = self.path.resolve()
                before_models = dict(self.models); before_paths = dict(self.paths)
                events = []; attempts = []; error = RuntimeError('first model boundary')
                with ExitStack() as stack:
                    for name in names:
                        original = getattr(api, name)
                        def invoke(*args, _name=name, _original=original, **kwargs):
                            events.append(_name)
                            if _name == target:
                                attempts.append(args)
                                if len(attempts) == 1:
                                    raise error
                                return valid
                            return _original(*args, **kwargs)
                        stack.enter_context(patch.object(api, name, invoke))
                    with self.assertRaises(RuntimeError) as raised:
                        operation()
                self.assertIs(raised.exception, error)
                self.assertEqual(len(attempts), 1)
                self.assertEqual(events[-1], target)
                self.assertEqual(self.models, before_models)
                self.assertEqual(self.paths, before_paths)

    def test_trained_typeerror_fallback_stops_after_second_failure(self):
        api = self.api; config = {'fixture': True}
        for second_error in (TypeError('second typeerror'), RuntimeError('second runtimeerror')):
            with self.subTest(second=type(second_error).__name__):
                self.trained.reset_mock()
                self.trained.side_effect = [TypeError('original compatibility trigger'), second_error,
                                           [self.registry['default']]]
                with self.assertRaises(type(second_error)) as raised:
                    api.selected_model_spec('default', config)
                self.assertIs(raised.exception, second_error)
                self.assertEqual(self.trained.call_args_list, [call(config), call()])
                self.factory.assert_not_called()
                self.assertEqual(self.models, {}); self.assertEqual(self.paths, {})
        self.trained.reset_mock(); error = RuntimeError('no compatibility fallback')
        self.trained.side_effect = [error, [self.registry['default']]]
        with self.assertRaises(RuntimeError) as raised:
            api.selected_model_spec('default', config)
        self.assertIs(raised.exception, error)
        self.trained.assert_called_once_with(config)

    def test_filesystem_failures_stop_before_cache_publication(self):
        api = self.api
        for method in ('exists', 'resolve'):
            with self.subTest(method=method):
                error = OSError('first path failure'); attempts = []
                original = getattr(Path, method)
                def fail_once(path, *args, **kwargs):
                    attempts.append(path)
                    if len(attempts) == 1:
                        raise error
                    return original(path, *args, **kwargs)
                with patch.object(Path, method, fail_once):
                    with self.assertRaises(OSError) as raised:
                        api.model('default', {})
                self.assertIs(raised.exception, error)
                self.assertEqual(attempts, [self.path])
                self.assertEqual(self.models, {}); self.assertEqual(self.paths, {})
                self.factory.assert_not_called()

    def test_new_registry_default_ports_preserve_reads_and_first_failure(self):
        selection = self.api._model_selection
        for field, fail_at, requested in [('registry', 1, 'default'), ('registry', 2, 'default'),
                                          ('default_id', 1, None)]:
            with self.subTest(field=field, fail_at=fail_at):
                events = []; calls = []; error = RuntimeError('new model policy port')
                original = getattr(selection, field)
                def fail_once(*args, **kwargs):
                    calls.append(args); events.append('port')
                    if len(calls) == fail_at:
                        raise error
                    return original(*args, **kwargs)
                with ExitStack() as stack:
                    stack.enter_context(patch.object(selection, field, fail_once))
                    for name in ('specialized', 'trained'):
                        original_callback = getattr(selection, name)
                        def observe(*args, _name=name, _original=original_callback, **kwargs):
                            events.append(_name)
                            return _original(*args, **kwargs)
                        stack.enter_context(patch.object(selection, name, observe))
                    with self.assertRaises(RuntimeError) as raised:
                        self.api.selected_model_spec(requested, {})
                self.assertIs(raised.exception, error)
                self.assertEqual(len(calls), fail_at)
                self.assertEqual(events[-1], 'port')
                self.factory.assert_not_called()


    def test_factory_capture_before_path_string_and_after_resolution(self):
        api = self.api
        for mode in ('ordinary', 'prior-replacement', 'missing'):
            with self.subTest(mode=mode):
                self.models.clear(); self.paths.clear()
                events = []; armed = False; instances = {name: object() for name in ('A', 'B', 'C')}
                factories = {name: (lambda value, name=name: (events.append(name), instances[name])[1])
                             for name in instances}
                original_resolve = Path.resolve; original_string = Path.__str__
                def resolve(path, *args, **kwargs):
                    nonlocal armed
                    result = original_resolve(path, *args, **kwargs)
                    if mode == 'prior-replacement':
                        events.append('prior'); api.YOLO = factories['B']
                    elif mode == 'missing':
                        events.append('prior'); api.YOLO = None
                    armed = True
                    return result
                def stringify(path):
                    nonlocal armed
                    if armed:
                        armed = False; events.append('str'); api.YOLO = factories['C']
                    return original_string(path)
                with patch.object(api, 'YOLO', factories['A']), patch.object(Path, 'resolve', resolve), \
                        patch.object(Path, '__str__', stringify):
                    if mode == 'missing':
                        with self.assertRaises(TypeError):
                            api.model('default', {})
                    else:
                        result = api.model('default', {})
                expected = ['str', 'A'] if mode == 'ordinary' else ['prior', 'str', 'B']
                if mode == 'missing':
                    self.assertEqual(events, ['prior', 'str'])
                    self.assertEqual(self.models, {}); self.assertEqual(self.paths, {})
                else:
                    self.assertEqual(events, expected)
                    self.assertIs(result, instances[expected[-1]])
                    self.assertIs(self.models['default'], result)
                    self.assertEqual(self.paths['default'], self.path.resolve())


    def test_cache_publication_failure_preserves_original_partial_state(self):
        api = self.api
        for failing in ('models', 'paths'):
            with self.subTest(failing=failing):
                error = RuntimeError('first cache write'); events = []; instance = object()
                class Cache(dict):
                    def __init__(self, name):
                        super().__init__(); self.name = name; self.writes = 0
                    def __setitem__(self, key, value):
                        self.writes += 1; events.append(self.name)
                        if self.name == failing and self.writes == 1:
                            raise error
                        return super().__setitem__(key, value)
                models, paths = Cache('models'), Cache('paths')
                with ExitStack() as stack:
                    stack.enter_context(patch.object(api, '_models', models))
                    stack.enter_context(patch.object(api, '_model_paths', paths))
                    # Bind the actual state owner after migration; old function bodies
                    # consume the same temporary dictionaries through root aliases.
                    owner = getattr(api, '_local_models', None)
                    if owner is not None:
                        stack.enter_context(patch.object(owner, 'models', models))
                        stack.enter_context(patch.object(owner, 'paths', paths))
                    factory = stack.enter_context(patch.object(api, 'YOLO', return_value=instance))
                    with self.assertRaises(RuntimeError) as raised:
                        api.model('default', {})
                self.assertIs(raised.exception, error)
                self.assertEqual(events, ['models'] if failing == 'models' else ['models', 'paths'])
                self.assertEqual(models, {} if failing == 'models' else {'default': instance})
                self.assertEqual(paths, {})
                factory.assert_called_once_with(str(self.path))


    def test_loaded_path_errors_skip_once_or_propagate_without_retry(self):
        api = self.api; self.models['cached'] = object(); self.paths['cached'] = self.path.resolve()
        self.legacy.return_value = [{'id': 'alias', 'path': self.path}]
        for kind in (OSError, TypeError, ValueError):
            with self.subTest(error=kind.__name__):
                error = kind('first loaded path failure'); calls = []
                original = Path.resolve
                def fail_once(path, *args, **kwargs):
                    calls.append(path)
                    if len(calls) == 1:
                        raise error
                    return original(path, *args, **kwargs)
                with patch.object(Path, 'resolve', fail_once):
                    if kind is ValueError:
                        with self.assertRaises(ValueError) as raised:
                            api.yolo_loaded_model_ids({})
                        self.assertIs(raised.exception, error)
                    else:
                        self.assertEqual(api.yolo_loaded_model_ids({}), ['cached'])
                self.assertEqual(calls, [self.path])
                self.assertEqual(set(self.models), {'cached'}); self.assertEqual(set(self.paths), {'cached'})
                self.factory.assert_not_called()

    def test_falsey_cached_instances_are_retained_by_id_and_path(self):
        api = self.api
        class FalseyModel:
            def __bool__(self): return False
        for cached in (None, FalseyModel()):
            with self.subTest(cached=cached):
                self.models.clear(); self.paths.clear(); self.models['default'] = cached
                self.assertIs(api.model('default', {}), cached)
                self.assertEqual(self.paths, {})
                self.paths['default'] = self.path.resolve()
                self.registry['alias'] = {'id': 'alias', 'path': self.path}
                self.assertIs(api.model('alias', {}), cached)
                self.assertIs(self.models['alias'], cached)
                self.assertEqual(self.paths['alias'], self.path.resolve())
                self.factory.assert_not_called()


if __name__=='__main__':unittest.main()
