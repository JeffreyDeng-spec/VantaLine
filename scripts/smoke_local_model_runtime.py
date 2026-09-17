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
        first=LocalModels(selection.selected_model_spec,factory,legacy,trained)
        second=LocalModels(selection.selected_model_spec,factory,legacy,trained)
        for provider in (specialized,trained,registry,default,removed,factory,legacy):provider.assert_not_called()
        self.assertIs(self.api._models,self.api._local_models.models)
        self.assertIs(self.api._model_paths,self.api._local_models.paths)
        self.assertIsNot(first.models,second.models);self.assertIsNot(first.paths,second.paths)
        one=first.model();two=second.model();self.assertIsNot(one,two);self.assertEqual(factory.call_count,2)
        first.models.pop('default');self.assertIs(second.model(),two);self.assertNotIn('default',first.models)
        self.assertEqual(first.paths['default'],self.path.resolve())


if __name__=='__main__':unittest.main()
