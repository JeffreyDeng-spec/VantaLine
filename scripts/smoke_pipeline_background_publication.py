"""Offline original contracts for pipeline background publication; synthetic media only."""
import hashlib
import os
from pathlib import Path
import sys
import tempfile
import unittest
import cv2
from contextlib import ExitStack
from unittest.mock import Mock, patch, call
sys.path.insert(0, str(Path.cwd()))

class PipelineBackgroundPublicationContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lifetime = ExitStack()
        cls.lifetime.enter_context(patch.dict(os.environ))
        cls.root = Path(cls.lifetime.enter_context(tempfile.TemporaryDirectory(prefix='pipeline-background-publication-')))
        (cls.root / 'local_inspection_service/static').mkdir(parents=True)
        for key in ('DATABASE_URL', 'VANTALINE_POSTGRES_DSN', 'PGDSN'):
            os.environ.pop(key, None)
        os.environ.update(LOCAL_INSPECTION_ROOT=str(cls.root), VANTALINE_DATA_STORE='json', LOCAL_INSPECTION_AUTO_RESUME_WORKER='0', VANTALINE_LABEL_INSPECTION_ENABLED='false', YOLO_AUTOINSTALL='false')
        for name in ('requests.sessions.Session.request', 'urllib.request.urlopen', 'subprocess.Popen', 'os.kill'):
            cls.lifetime.enter_context(patch(name, side_effect=AssertionError('External operation forbidden')))
        from types import SimpleNamespace
        cls.import_factory = Mock(side_effect=AssertionError('Eager model load forbidden'))
        cls.import_remove = Mock(side_effect=AssertionError('Eager inference forbidden'))
        cls.lifetime.enter_context(patch.dict(sys.modules, {'rembg': SimpleNamespace(new_session=cls.import_factory, remove=cls.import_remove)}))
        from local_inspection_service import server
        cls.import_factory.assert_not_called()
        cls.import_remove.assert_not_called()
        cls.api = server

    @classmethod
    def tearDownClass(cls):
        cls.lifetime.close()

    def replace(self, name, **kwargs):
        return self.stack.enter_context(patch.object(self.api, name, **kwargs))

    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.directory = Path(self.stack.enter_context(tempfile.TemporaryDirectory(dir=self.root)))
        self.backgrounds = self.directory / 'backgrounds'
        self.outputs = self.directory / 'outputs'
        self.task = {'id': 't', 'name': 'Task', 'owner_user_id': 'owner', 'owner_username': 'User', 'accessory_ids': ['part', 'second']}
        self.config = {'synthetic': True}
        self.state = {}
        self.item = {'id': 'part', 'name': 'Part'}
        self.state_fn = self.replace('agent_mcp_orchestration', return_value=self.state)
        self.ids = self.replace('canonical_pipeline_accessory_ids', return_value=['part', 'second'])
        self.lookup = self.replace('accessory_lookup_by_id', return_value={'part': self.item})
        self.output = self.replace('output_write_dir_for_owner', return_value=self.outputs)
        self.safe_record = self.replace('safe_record_id', side_effect=lambda value: value)
        self.safe_set = self.replace('safe_background_set_id', side_effect=lambda value: value)
        self.replace('BACKGROUND_SETS_DIR', new=self.backgrounds)
        self.replace('LEGACY_OWNER_ID', new='legacy')
        self.original_prompt = self.api.pipeline_background_plate_prompt
        self.prompt = self.replace('pipeline_background_plate_prompt', return_value='unchanged synthetic prompt')
        self.match = self.replace('match_background_library_plate', return_value=None)
        self.resolve = self.replace('resolve_service_path', side_effect=lambda value: Path(value))
        self.tool_value = {'configured': False, 'model': 'bound-model', 'timeout_seconds': 42, 'provider_name': 'gemini'}
        self.tool = self.replace('agent_mcp_gemini_image_config', return_value=self.tool_value)
        self.content = [{'synthetic': True}]
        self.references = self.replace('agent_mcp_pose_reference_content', return_value=(self.content, ['unused']))
        self.settings_value = {'model': 'previous', 'untouched': 1}
        self.settings = self.replace('image_generation_settings', return_value=self.settings_value)
        self.provider = Mock()
        self.provider.generate_image.return_value = {'bytes': b'synthetic payload', 'mime_type': 'image/png'}
        self.factory = self.replace('image_generation_provider_from_settings', return_value=self.provider)
        self.error_type = type('SyntheticProviderError', (Exception,), {})
        self.replace('AiProviderError', new=self.error_type)
        self.bounded = self.replace('bounded_text', side_effect=lambda value, limit: value[:limit])
        self.derive = self.replace('derive_background_plate_from_accessory', side_effect=self.write_local)
        self.handle = Mock()
        self.handle.__enter__ = Mock(return_value=self.handle)
        self.handle.__exit__ = Mock(return_value=False)
        self.handle.convert.return_value.save.side_effect=self.save_synthetic
        self.open = self.stack.enter_context(patch.object(self.api.Image, 'open', return_value=self.handle))
        self.variants = self.replace('create_background_variants_from_source')
        self.images = self.replace('image_file_list', side_effect=lambda directory: sorted(directory.glob('*.png')))
        self.manifest = {'sets': {'previous': {'id': 'previous'}}, 'other': True}
        self.load = self.replace('load_background_sets_manifest', return_value=self.manifest)
        self.write = self.replace('write_background_sets_manifest')
        self.url = self.replace('public_output_url_for_existing', return_value='/synthetic/plate')
        self.hash = self.replace('file_sha256', wraps=self.api.file_sha256)
        self.now = self.replace('agent_mcp_now', return_value='synthetic-now')
        self.stack.enter_context(patch.object(self.api.time, 'time', return_value=123.9))

    @staticmethod
    def save_synthetic(path, **kwargs):
        path.write_bytes(b'synthetic converted image')

    @staticmethod
    def write_local(item, path):
        path.write_bytes(b'synthetic derived image')
        return path

    def invoke(self):
        return self.api.ensure_pipeline_background_plate(self.task, self.config)

    def test_prompt_exact_text_and_name_fallback(self):
        prompt = self.original_prompt
        expected = '\n'.join([
            'Generate ONE empty work-surface background plate for VantaLine training-sample synthesis.',
            "Reference context: the original capture environment of accessory 'Part'.",
            'Reproduce the SAME visible background surface / environment shown in the reference photo, but completely EMPTY — remove every product, paper sheet, cable, strap, shadow of the product, hand, text, label, ruler, or tool so only the bare target surface remains.',
            'Do not invent a green conveyor or chroma background unless the reference background itself is green.',
            "Camera: STRICTLY vertical top-down (bird's-eye) at 90 degrees, optical axis perpendicular to the surface. No tilt, no perspective, no oblique angle.",
            'The surface must fill the entire frame edge to edge. Match the reference material, colour, texture scale, lighting, and camera height as closely as possible. Even, diffuse lighting; no glare, no objects, no people, no text, no rulers, no grid.',
        ])
        self.assertEqual(prompt(self.item), expected)
        self.assertIn("accessory 'identifier'", prompt({'id': 'identifier', 'name': ''}))
        self.assertIn("accessory 'the item'", prompt({}))

    def test_existing_plate_short_circuits_all_generation(self):
        self.state['background_plate'] = {'background_set_id': 'existing'}
        self.images.side_effect = None
        self.images.return_value = [self.backgrounds/'existing/a.png']
        self.assertEqual(self.invoke(), 'existing')
        self.assertEqual(self.task['background_set_id'], 'existing')
        self.ids.assert_not_called()
        self.tool.assert_not_called()
        self.write.assert_not_called()

    def test_missing_accessory_ids_and_lookup_stop(self):
        self.ids.return_value = []
        self.assertIsNone(self.invoke())
        self.lookup.assert_not_called()
        self.ids.return_value = ['absent']
        self.assertIsNone(self.invoke())
        self.output.assert_not_called()
        self.references.assert_not_called()

    def test_library_match_reads_tool_and_references_but_skips_provider(self):
        source = self.directory/'library.png'
        source.write_bytes(b'synthetic source')
        matched = {'image_path': str(source), 'background_set_id': 'library', 'distance': .1}
        self.match.return_value = matched
        self.tool_value['configured'] = True
        self.assertEqual(self.invoke(), 'task_plate_t')
        self.tool.assert_called_once_with()
        self.references.assert_called_once_with(self.item, max_images=2)
        self.factory.assert_not_called()
        self.derive.assert_not_called()
        self.assertIs(self.state['background_plate']['background_match'], matched)
        self.assertIs(self.manifest['sets']['task_plate_t']['background_match'], matched)
        self.assertEqual(self.state['background_plate']['method'], 'background_library_match')

    def test_library_copy_oserror_falls_through_and_clears_match(self):
        source = self.directory/'library.png'
        source.write_bytes(b'synthetic source')
        self.match.return_value = {'image_path': str(source)}
        self.open.side_effect = [OSError('synthetic copy failure'), self.handle]
        self.assertEqual(self.invoke(), 'task_plate_t')
        self.derive.assert_called_once()
        self.assertEqual(self.state['background_plate']['background_match'], {})
        self.assertEqual(self.state['background_plate_error'], '')

    def test_configured_provider_constructed_even_without_reference_content(self):
        self.tool_value['configured'] = True
        self.references.return_value = ([], [])
        self.assertEqual(self.invoke(), 'task_plate_t')
        self.factory.assert_called_once_with(self.settings_value)
        self.assertEqual(self.settings_value, {'model': 'bound-model', 'timeout_seconds': 42, 'untouched': 1})
        self.provider.generate_image.assert_not_called()
        self.derive.assert_called_once()

    def test_provider_jpeg_and_gemini_call_count(self):
        self.tool_value['configured'] = True
        self.provider.generate_image.return_value = {'bytes': b'synthetic jpeg', 'mime_type': 'IMAGE/JPEG'}
        self.assertEqual(self.invoke(), 'task_plate_t')
        self.provider.generate_image.assert_called_once_with('unchanged synthetic prompt', self.content, model='bound-model')
        record = self.state['background_plate']
        self.assertTrue(record['plate_path'].endswith('plate.jpg'))
        self.assertEqual(record['api_calls'], 1)
        self.assertEqual(record['sha256'], hashlib.sha256(b'synthetic jpeg').hexdigest())
        self.derive.assert_not_called()

    def test_other_provider_preserves_existing_zero_call_projection(self):
        self.tool_value.update(configured=True, provider_name='synthetic')
        self.assertEqual(self.invoke(), 'task_plate_t')
        self.assertEqual(self.state['background_plate']['method'], 'agent_synthetic_empty_surface')
        self.assertEqual(self.state['background_plate']['api_calls'], 0)
        self.assertEqual(self.provider.generate_image.call_count, 1)

    def test_provider_error_bounded_then_local_success_clears_error(self):
        self.tool_value['configured'] = True
        self.provider.generate_image.side_effect = self.error_type('x'*250)
        self.assertEqual(self.invoke(), 'task_plate_t')
        self.bounded.assert_called_once_with('x'*250, 240)
        self.assertEqual(self.state['background_plate_error'], '')
        self.assertEqual(self.state['background_plate']['method'], 'accessory_photo_surface_local_fallback')

    def test_provider_error_retained_when_local_missing(self):
        self.tool_value['configured'] = True
        self.provider.generate_image.side_effect = self.error_type('specific failure')
        self.derive.side_effect = None
        self.derive.return_value = None
        self.assertIsNone(self.invoke())
        self.assertEqual(self.state['background_plate_error'], 'specific failure')
        self.write.assert_not_called()

    def test_unavailable_and_missing_derived_path_report_default_error(self):
        self.derive.side_effect = None
        self.derive.return_value = None
        self.assertIsNone(self.invoke())
        self.assertEqual(self.state['background_plate_error'], '无法从首个配件环境生成背景底板。')
        self.derive.return_value = self.directory/'does-not-exist.png'
        self.assertIsNone(self.invoke())
        self.write.assert_not_called()
        self.assertNotIn('background_set_id', self.task)

    def test_unexpected_provider_exception_propagates_without_local_retry(self):
        self.tool_value['configured'] = True
        failure = RuntimeError('synthetic unknown result')
        self.provider.generate_image.side_effect = failure
        with self.assertRaises(RuntimeError) as caught:
            self.invoke()
        self.assertIs(caught.exception, failure)
        self.derive.assert_not_called()
        self.write.assert_not_called()
        self.assertEqual(self.provider.generate_image.call_count, 1)

    def test_task_directory_replaced_then_variants_even_when_copy_fails(self):
        target=self.backgrounds/'task_plate_t'
        target.mkdir(parents=True)
        (target/'stale.txt').write_text('synthetic stale')
        self.open.side_effect = ValueError('synthetic publication copy failure')
        self.variants.side_effect = lambda source, directory, count: (directory/'variant.png').write_bytes(b'synthetic variant')
        self.assertEqual(self.invoke(), 'task_plate_t')
        self.assertFalse((target/'stale.txt').exists())
        self.variants.assert_called_once_with(self.outputs/'t/plate.png', target, count=6)
        self.assertTrue((target/'variant.png').exists())

    def test_empty_variant_set_stops_before_manifest(self):
        self.open.side_effect = ValueError('synthetic copy failure')
        self.assertIsNone(self.invoke())
        self.variants.assert_called_once()
        self.load.assert_not_called()
        self.assertNotIn('background_plate', self.state)

    def test_manifest_payload_and_owner_fallback_identity(self):
        self.task['owner_user_id'] = ''
        prior_sets = self.manifest['sets']
        self.assertEqual(self.invoke(), 'task_plate_t')
        self.assertIs(self.manifest['sets'], prior_sets)
        self.write.assert_called_once_with(self.manifest)
        record = prior_sets['task_plate_t']
        self.assertEqual((record['owner_user_id'], record['created_at'], record['shared_with_user_ids']), ('legacy', 123, []))
        self.assertEqual(record['name'], '流水线背景 · Task')
        self.assertEqual(self.state['background_plate']['accessory_id'], 'part')
        self.assertEqual(self.state['background_plate']['created_at'], 'synthetic-now')

    def test_manifest_write_failure_preserves_existing_partial_mutations(self):
        failure = OSError('synthetic manifest failure')
        self.write.side_effect = failure
        with self.assertRaises(OSError) as caught:
            self.invoke()
        self.assertIs(caught.exception, failure)
        self.assertIn('task_plate_t', self.manifest['sets'])
        self.assertNotIn('background_plate', self.state)
        self.assertNotIn('background_set_id', self.task)
        self.url.assert_not_called()

    def test_strict_hash_error_after_manifest_before_state_assignment(self):
        failure = OSError('synthetic hash failure')
        self.hash.side_effect = failure
        with self.assertRaises(OSError) as caught:
            self.invoke()
        self.assertIs(caught.exception, failure)
        self.write.assert_called_once()
        self.url.assert_called_once()
        self.now.assert_not_called()
        self.assertNotIn('background_plate', self.state)
        self.assertNotIn('background_set_id', self.task)

    def test_url_callback_rebinds_hash_at_original_late_read(self):
        replacement = Mock(return_value='late-hash')
        def url(path):
            self.api.file_sha256 = replacement
            return '/late/url'
        self.url.side_effect = url
        self.assertEqual(self.invoke(), 'task_plate_t')
        self.hash.assert_not_called()
        replacement.assert_called_once_with(self.outputs/'t/plate.png')
        self.assertEqual(self.state['background_plate']['sha256'], 'late-hash')
        self.assertEqual(self.state['background_plate']['plate_url'], '/late/url')

    def test_stale_existing_set_continues_to_publication(self):
        self.state['background_plate'] = {'background_set_id': 'missing-old-set'}
        self.assertEqual(self.invoke(), 'task_plate_t')
        self.ids.assert_called_once_with(self.config, ['part', 'second'])
        self.assertEqual(self.images.call_args_list, [call(self.backgrounds/'missing-old-set'), call(self.backgrounds/'task_plate_t')])
        self.assertEqual(self.state['background_plate']['background_set_id'], 'task_plate_t')

    def test_set_id_callee_selected_before_record_id_rebinding(self):
        replacement = Mock(return_value='unexpected-set')
        calls = []
        def record_id(value):
            calls.append(value)
            if len(calls) == 2:
                self.api.safe_background_set_id = replacement
            return value
        self.safe_record.side_effect = record_id
        self.assertEqual(self.invoke(), 'task_plate_t')
        self.safe_set.assert_called_once_with('task_plate_t')
        replacement.assert_not_called()
        self.assertEqual(calls, ['t', 't'])

    def test_exception_type_is_read_after_provider_raises(self):
        self.tool_value['configured'] = True
        later = type('LateSyntheticProviderError', (Exception,), {})
        def generate(*args, **kwargs):
            self.api.AiProviderError = later
            raise later('late provider exception')
        self.provider.generate_image.side_effect = generate
        self.assertEqual(self.invoke(), 'task_plate_t')
        self.bounded.assert_called_once_with('late provider exception', 240)
        self.derive.assert_called_once()
        self.assertEqual(self.state['background_plate_error'], '')

    def test_callback_selection_and_eager_config_reference_rebinding(self):
        later_ids = Mock(return_value=['unexpected'])
        api = self.api
        class EffectfulId:
            def __str__(self):
                api.canonical_pipeline_accessory_ids = later_ids
                return 'converted'
        self.task['accessory_ids'] = [EffectfulId()]
        self.assertEqual(self.invoke(), 'task_plate_t')
        self.ids.assert_called_once_with(self.config, ['converted'])
        later_ids.assert_not_called()
        self.api.canonical_pipeline_accessory_ids = self.ids
        self.state.clear()
        self.task['id'] = 'second-task'
        self.task['accessory_ids'] = ['part']
        self.references.reset_mock()
        events = []
        later_factory = Mock(return_value=self.provider)
        def settings():
            events.append('settings')
            self.api.image_generation_provider_from_settings = later_factory
            return self.settings_value
        later_settings = Mock(side_effect=settings)
        def references(item, **kwargs):
            events.append('references')
            self.api.image_generation_settings = later_settings
            return self.content, []
        later_references = Mock(side_effect=references)
        def config():
            events.append('config')
            self.api.agent_mcp_pose_reference_content = later_references
            self.tool_value['configured'] = True
            return self.tool_value
        self.tool.side_effect = config
        self.assertEqual(self.invoke(), 'task_plate_second-task')
        self.assertEqual(events, ['config', 'references', 'settings'])
        later_references.assert_called_once_with(self.item, max_images=2)
        later_settings.assert_called_once_with()
        later_factory.assert_called_once_with(self.settings_value)
        self.references.assert_not_called()
        self.settings.assert_not_called()
        self.factory.assert_not_called()

    def test_provider_payload_partial_write_failure_is_not_retried(self):
        self.tool_value['configured'] = True
        failure = OSError('synthetic partial payload write')
        target = self.outputs/'t/plate.png'
        original_write = Path.write_bytes
        def write(path, data):
            if path == target:
                original_write(path, b'synthetic partial payload')
                raise failure
            return original_write(path, data)
        with patch.object(Path, 'write_bytes', new=write):
            with self.assertRaises(OSError) as caught:
                self.invoke()
        self.assertIs(caught.exception, failure)
        self.assertEqual(self.provider.generate_image.call_count, 1)
        self.assertEqual(target.read_bytes(), b'synthetic partial payload')
        self.derive.assert_not_called()
        self.variants.assert_not_called()
        self.write.assert_not_called()
        self.assertNotIn('background_plate', self.state)
        self.assertNotIn('background_set_id', self.task)

    def test_intermediate_failure_preserves_copy_and_directory_side_effects(self):
        source = self.directory/'library.png'
        source.write_bytes(b'synthetic library')
        self.match.return_value = {'image_path': str(source), 'background_set_id': 'library'}
        failure = RuntimeError('synthetic eager reference failure')
        self.state['background_plate_error'] = 'old error'
        self.references.side_effect = failure
        with self.assertRaises(RuntimeError) as caught:
            self.invoke()
        self.assertIs(caught.exception, failure)
        self.assertEqual((self.outputs/'t/plate.png').read_bytes(), b'synthetic converted image')
        self.assertEqual(self.state['background_plate_error'], '')
        self.factory.assert_not_called()
        self.derive.assert_not_called()
        self.variants.assert_not_called()
        self.write.assert_not_called()
        self.assertNotIn('background_plate', self.state)
        self.assertNotIn('background_set_id', self.task)
        self.references.side_effect = None
        self.match.return_value = None
        target = self.backgrounds/'task_plate_t'
        target.mkdir(parents=True)
        old = target/'old.txt'
        old.write_text('synthetic stale data')
        failure = RuntimeError('synthetic variants failure')
        self.variants.side_effect = failure
        with self.assertRaises(RuntimeError) as caught:
            self.invoke()
        self.assertIs(caught.exception, failure)
        self.assertFalse(old.exists())
        self.assertEqual((target/'plate.png').read_bytes(), b'synthetic converted image')
        self.load.assert_not_called()
        self.write.assert_not_called()
        self.assertNotIn('background_plate', self.state)
        self.assertNotIn('background_set_id', self.task)

    def test_independent_publication_instances_keep_capabilities_isolated(self):
        from local_inspection_service.agent.pipeline_background_publication import PipelineBackgroundPublication
        from local_inspection_service.agent.pipeline_background_publication_ports import BackgroundPublicationTasks, BackgroundPublicationPaths, BackgroundPublicationSelection, BackgroundPublicationProviders, BackgroundPublicationCatalog, BackgroundPublicationProjection
        names=('agent_mcp_orchestration','canonical_pipeline_accessory_ids','accessory_lookup_by_id','output_write_dir_for_owner','safe_record_id','safe_background_set_id','resolve_service_path','BACKGROUND_SETS_DIR','pipeline_background_plate_prompt','match_background_library_plate','derive_background_plate_from_accessory','agent_mcp_gemini_image_config','agent_mcp_pose_reference_content','image_generation_settings','image_generation_provider_from_settings','AiProviderError','image_file_list','create_background_variants_from_source','load_background_sets_manifest','write_background_sets_manifest','bounded_text','public_output_url_for_existing','file_sha256','agent_mcp_now','LEGACY_OWNER_ID')
        poison=Mock(side_effect=AssertionError('root dependency escape'))
        for name in names:
            self.replace(name,new=poison)
        all_events=[]
        def make(label):
            directory=self.directory/label
            directory.mkdir()
            source=directory/'source.png'
            source.write_bytes(b'synthetic independent source')
            holder={'library':True,'sets':{}}
            error_type=type('Synthetic'+label+'Error',(Exception,),{})
            provider=Mock()
            provider.generate_image.side_effect=error_type('synthetic '+label+' failure')
            values={
                'state':lambda task:task['state'], 'ids':lambda config,ids:['part'], 'lookup':lambda config:{'part':{'id':'part','name':label}},
                'output':lambda kind,owner:directory/'output', 'record_id':str, 'set_id':str, 'resolve':Path, 'sets_directory':directory/'sets',
                'prompt':lambda item:'prompt-'+label, 'match':lambda item,owner:({'image_path':str(source),'background_set_id':label} if holder['library'] else None), 'derive':self.write_local,
                'config':lambda:{'configured':True,'model':label,'timeout_seconds':12,'provider_name':'synthetic'}, 'references':lambda item,**kw:([{'label':label}],[]), 'settings':lambda:{}, 'create':lambda settings:provider, 'error_type':error_type,
                'images':lambda directory:sorted(directory.glob('*.png')), 'variants':lambda source,directory,**kw:[], 'manifest':lambda:holder, 'publish':lambda manifest:None,
                'bounded':lambda value,limit:value[:limit], 'url':lambda path:'/synthetic/'+label, 'digest':lambda path:hashlib.sha256(path.read_bytes()).hexdigest(), 'now':lambda:7, 'legacy_owner':label,
            }
            def getter(key):
                def get():
                    all_events.append((label,key))
                    return values[key]
                return get
            groups=[(BackgroundPublicationTasks,('state','ids','lookup')),(BackgroundPublicationPaths,('output','record_id','set_id','resolve','sets_directory')),(BackgroundPublicationSelection,('prompt','match','derive')),(BackgroundPublicationProviders,('config','references','settings','create','error_type')),(BackgroundPublicationCatalog,('images','variants','manifest','publish')),(BackgroundPublicationProjection,('bounded','url','digest','now','legacy_owner'))]
            service=PipelineBackgroundPublication(*(kind(**{key:getter(key) for key in keys}) for kind,keys in groups))
            return service,holder,set(values)
        a=make('A');b=make('B')
        self.assertEqual(all_events,[])
        results=[]
        for serial,(label,(service,holder,keys)) in enumerate((('A',a),('B',b),('A',a))):
            start=len(all_events)
            for library in (True,False):
                holder['library']=library
                task={'id':str(serial)+'-'+str(library),'owner_user_id':'','accessory_ids':['part'],'state':{}}
                result=service.ensure_pipeline_background_plate(task,{})
                self.assertEqual(result,'task_plate_'+task['id'])
                self.assertEqual(holder['sets'][result]['owner_user_id'],label)
                self.assertEqual(task['state']['background_plate']['method'],'background_library_match' if library else 'accessory_photo_surface_local_fallback')
                self.assertEqual(task['state']['background_plate_error'],'')
                results.append(task['state']['background_plate']['plate_url'])
            self.assertEqual({who for who,key in all_events[start:]},{label})
            self.assertEqual({key for who,key in all_events[start:]},keys)
        self.assertEqual(results,['/synthetic/A','/synthetic/A','/synthetic/B','/synthetic/B','/synthetic/A','/synthetic/A'])
        self.assertIsNot(a[0],b[0])
        poison.assert_not_called()

if __name__ == '__main__':
    unittest.main()
