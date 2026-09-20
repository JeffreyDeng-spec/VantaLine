"""Draft contracts against the original Agent pose rendering functions."""
import base64
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from contextlib import ExitStack
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path.cwd()))

class AgentPoseRenderContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.environment = patch.dict(os.environ)
        cls.environment.start()
        cls.root = tempfile.TemporaryDirectory(prefix='pose-render-contract-')
        (Path(cls.root.name) / 'local_inspection_service/static').mkdir(parents=True)
        os.environ.update(LOCAL_INSPECTION_ROOT=cls.root.name, VANTALINE_DATA_STORE='json', LOCAL_INSPECTION_AUTO_RESUME_WORKER='0', VANTALINE_LABEL_INSPECTION_ENABLED='false')
        from local_inspection_service import server
        cls.api = server

    @classmethod
    def tearDownClass(cls):
        cls.root.cleanup()
        cls.environment.stop()

    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.directory = Path(self.stack.enter_context(tempfile.TemporaryDirectory(dir=self.root.name)))
        for name in ('requests.sessions.Session.request', 'urllib.request.urlopen', 'subprocess.Popen', 'os.kill'):
            self.stack.enter_context(patch(name, side_effect=AssertionError('External operation forbidden')))

    def replace(self, name, **kwargs):
        return self.stack.enter_context(patch.object(self.api, name, **kwargs))

    def settings(self, value):
        self.replace('image_generation_settings', return_value=value)
        self.replace('image_generation_provider_key', side_effect=lambda value: 'key:' + value)
        self.replace('image_generation_provider_label', side_effect=lambda value: 'label:' + value)
        self.replace('default_image_generation_base_url', return_value='https://example.invalid/image')
        self.replace('default_image_generation_api_key_env', return_value='SYNTHETIC_KEY')

    def screen(self):
        return self.replace('normalize_chroma_screen', return_value={'rgb': [0, 255, 0], 'hex': '#00FF00', 'label': 'green'})

    def prompt_inputs(self):
        return ({'name': 'Task'}, {'accessory_name': 'Part', 'accessory_id': 'part', 'object_kind': 'gear'}, {'pose_id': 'top', 'label': 'Top', 'stable_contact': 'base', 'generation_prompt': 'exact top pose', 'negative_prompt': 'extra props', 'request': {'background': 'solid', 'output_contract': 'single'}})

    def artifact(self):
        output = self.directory / 'part.png'
        self.replace('agent_mcp_pose_output_path', return_value=output)
        self.replace('file_sha256', return_value='digest')
        self.replace('public_output_url', side_effect=lambda path: '/synthetic/' + path.name)
        self.replace('agent_mcp_now', return_value=123)
        self.screen()
        return output

    def test_settings_projection_keeps_fields_and_excludes_raw_credentials(self):
        settings = {'provider': ' GEMINI ', 'model': ' explicit ', 'configured': True, 'timeout_seconds': 400, 'api_key_present': True, 'api_key': 'synthetic-secret', 'proxy_url_raw': 'synthetic-hidden', 'proxy_configured': True}
        self.settings(settings)
        default = self.replace('default_image_generation_model', return_value='default')
        result = self.api.agent_mcp_gemini_image_config()
        self.assertEqual((result['provider_name'], result['provider'], result['model'], result['timeout_seconds']), ('gemini', 'key:gemini', 'explicit', 300.0))
        self.assertEqual((result['status'], result['configured'], result['missing']), ('ready', True, []))
        self.assertEqual(result['api_key_env'], 'SYNTHETIC_KEY')
        self.assertNotIn('synthetic-secret', str(result))
        self.assertNotIn('synthetic-hidden', str(result))
        default.assert_called_once_with('gemini')
        self.assertEqual(settings['model'], ' explicit ')

    def test_settings_retains_two_distinct_default_model_evaluations(self):
        self.settings({'provider': 'gemini', 'model': '', 'configured': True, 'api_key_present': True})
        default = self.replace('default_image_generation_model', side_effect=['chosen', 'advertised'])
        result = self.api.agent_mcp_gemini_image_config()
        self.assertEqual((result['model'], result['default_model']), ('chosen', 'advertised'))
        self.assertEqual(default.call_count, 2)

    def test_settings_missing_configuration_and_timeout_error(self):
        self.settings({'provider': 'gemini', 'model': ' ', 'configured': True, 'timeout_seconds': 1})
        self.replace('default_image_generation_model', return_value='default')
        result = self.api.agent_mcp_gemini_image_config()
        self.assertFalse(result['configured'])
        self.assertEqual(result['timeout_seconds'], 10.0)
        self.assertEqual(result['missing'], [self.api.IMAGE_GENERATION_API_KEY_ENV, self.api.IMAGE_GENERATION_MODEL_ENV])
        self.assertEqual(result['status'], 'missing_configuration')
        self.replace('image_generation_settings', return_value={'timeout_seconds': 'not-a-number'})
        with self.assertRaises(ValueError):
            self.api.agent_mcp_gemini_image_config()

    def test_reference_order_filter_mime_hash_and_limit_forwarding(self):
        first = self.directory / 'first.png'; first.write_bytes(b'first')
        second = self.directory / 'second.jpg'; second.write_bytes(b'second')
        records = [None, {'source_path': str(self.directory / 'missing')}, {'source_path': str(first), 'sha256': 'provided', 'mime_type': 'image/custom', 'ordinal': 7}, {'source_path': str(second), 'width': 20, 'height': 10}]
        contexts = self.replace('accessory_reference_image_contexts', return_value=records)
        self.replace('resolve_service_path', side_effect=Path)
        self.replace('public_output_url_for_existing', side_effect=lambda path: '/synthetic/' + path.name)
        digest = self.replace('file_sha256', return_value='computed')
        item = {}; content, refs = self.api.agent_mcp_pose_reference_content(item, max_images=2)
        contexts.assert_called_once_with(item, max_images=2)
        self.assertEqual([r['source_path'] for r in refs], [str(first), str(second)])
        self.assertEqual([r['sha256'] for r in refs], ['provided', 'computed'])
        self.assertEqual([r['mime_type'] for r in refs], ['image/custom', 'image/jpeg'])
        self.assertEqual(content[0]['image_url']['url'], 'data:image/custom;base64,' + base64.b64encode(b'first').decode())
        self.assertEqual((refs[0]['ordinal'], refs[1]['width'], refs[1]['height']), (7, 20, 10))
        digest.assert_called_once_with(second)

    def test_reference_read_failure_escapes_without_hash_or_retry(self):
        source = self.directory / 'image.png'; source.write_bytes(b'image')
        self.replace('accessory_reference_image_contexts', return_value=[{'source_path': str(source)}])
        self.replace('resolve_service_path', return_value=source)
        digest = self.replace('file_sha256')
        error = OSError('synthetic read error')
        with patch.object(Path, 'read_bytes', side_effect=error) as reader:
            with self.assertRaises(OSError) as caught:
                self.api.agent_mcp_pose_reference_content({})
        self.assertIs(caught.exception, error)
        reader.assert_called_once_with()
        digest.assert_not_called()

    def test_exact_planned_render_prompt(self):
        self.screen()
        result = self.api.agent_mcp_pose_prompt(*self.prompt_inputs())
        self.assertEqual(hashlib.sha256(result.encode()).hexdigest(), 'dc1eef5b26930909618608f93b9ec2f813b387c43b6ee647a896fd0b0b513465')

    def test_exact_fallback_render_prompt(self):
        self.screen(); task, plan, _ = self.prompt_inputs()
        pose = {'pose_id': 'top', 'label': 'Top', 'stable_contact': 'base', 'gravity_basis': 'flat', 'conveyor_view': 'overhead'}
        result = self.api.agent_mcp_pose_prompt(task, plan, pose)
        self.assertEqual(hashlib.sha256(result.encode()).hexdigest(), 'ebaf91d7e27ee9a436365ace1f9ac7e0d5a8c571d36e090e68f8d7a466585acc')

    def test_prompt_retains_repeated_request_lookup(self):
        self.screen(); task, plan, _ = self.prompt_inputs()
        class ChangingPose(dict):
            calls = 0
            def get(self, key, default=None):
                if key == 'request':
                    self.calls += 1
                    return {'background': 'first' if self.calls == 1 else 'second'}
                return super().get(key, default)
        pose = ChangingPose(pose_id='top')
        prompt = self.api.agent_mcp_pose_prompt(task, plan, pose)
        self.assertEqual(pose.calls, 2)
        self.assertIn('Background style: second.', prompt)
        self.assertNotIn('Background style: first.', prompt)

    def test_output_path_owner_sanitation_and_extension(self):
        owner = self.replace('output_write_dir_for_owner', return_value=self.directory)
        sanitizer = self.replace('safe_record_id', side_effect=lambda value: 'safe-' + value)
        result = self.api.agent_mcp_pose_output_path({'id': 'task', 'owner_user_id': 'owner'}, 'part', 'pose', 'IMAGE/JPEG')
        self.assertEqual(result, self.directory / 'safe-task' / 'safe-part__safe-pose.jpg')
        owner.assert_called_once_with('agent_mcp_pose_images', 'owner')
        self.assertTrue(result.parent.is_dir())
        self.assertEqual([c.args[0] for c in sanitizer.call_args_list], ['task', 'part', 'pose'])
        self.assertEqual(self.api.agent_mcp_pose_output_path({}, 'a', 'b', '').suffix, '.png')

    def test_output_path_retains_created_directory_when_filename_sanitization_fails(self):
        self.replace('output_write_dir_for_owner', return_value=self.directory)
        self.replace('safe_record_id', side_effect=['task', ValueError('synthetic invalid part')])
        with self.assertRaises(ValueError):
            self.api.agent_mcp_pose_output_path({'id': 'task'}, 'bad', 'pose', 'image/png')
        self.assertTrue((self.directory / 'task').is_dir())

    def test_artifact_bytes_metadata_aliases_and_provider_fields(self):
        output = self.artifact(); references = [{'sha256': 'ref'}]; usage = {'tokens': 1}
        value = self.api.write_agent_mcp_pose_artifact({'id': 'task'}, {'call_id': 'call', 'accessory_id': 'part', 'pose_id': 'top', 'provider': 'agnes_image_generation'}, {'bytes': b'image', 'usage_metadata': usage, 'latency_ms': '9', 'model': 'synthetic', 'proxy_used': True, 'proxy_url': 'https://example.invalid'}, prompt='synthetic prompt', reference_assets=references)
        self.assertTrue(output.exists())
        self.assertEqual(output.read_bytes(), b'image')
        self.assertIs(value['source_reference_assets'], references)
        self.assertIs(value['usage_metadata'], usage)
        self.assertEqual((value['created_at'], value['latency_ms'], value['sha256']), (123, 9, 'digest'))
        self.assertEqual(value['generated_source_metadata'], {'native_provider': 'agnes', 'generated_by': 'Agnes Image', 'synthid_watermark_expected': False})
        self.assertEqual(json.loads(Path(value['metadata_path']).read_text())['prompt'], 'synthetic prompt')
        self.assertEqual(value['metadata_url'], '/synthetic/part.png.metadata.json')

    def test_artifact_hash_failure_leaves_image_without_metadata(self):
        output = self.artifact(); digest = self.replace('file_sha256', side_effect=OSError('synthetic hash error'))
        with self.assertRaises(OSError):
            self.api.write_agent_mcp_pose_artifact({}, {}, {'bytes': b'image'}, prompt='prompt', reference_assets=[])
        self.assertTrue(output.exists())
        self.assertEqual(output.read_bytes(), b'image')
        self.assertFalse(output.with_suffix('.png.metadata.json').exists())
        digest.assert_called_once_with(output)

    def test_artifact_serialization_failure_leaves_image_without_metadata(self):
        output = self.artifact()
        with patch.object(self.api.json, 'dumps', side_effect=TypeError('synthetic json error')) as serializer:
            with self.assertRaises(TypeError):
                self.api.write_agent_mcp_pose_artifact({}, {}, {'bytes': b'image'}, prompt='prompt', reference_assets=[])
        self.assertTrue(output.exists())
        self.assertEqual(output.read_bytes(), b'image')
        self.assertFalse(output.with_suffix('.png.metadata.json').exists())
        self.assertEqual(serializer.call_count, 1)

    def test_artifact_final_metadata_url_failure_keeps_both_written_files(self):
        output = self.artifact()
        self.replace('public_output_url', side_effect=['/synthetic/image', ValueError('synthetic metadata URL error')])
        with self.assertRaises(ValueError):
            self.api.write_agent_mcp_pose_artifact({}, {}, {'bytes': b'image'}, prompt='prompt', reference_assets=[])
        self.assertTrue(output.exists())
        self.assertEqual(output.read_bytes(), b'image')
        self.assertEqual(json.loads(output.with_suffix('.png.metadata.json').read_text())['output_url'], '/synthetic/image')

    def test_artifact_default_provider_usage_and_text_bound(self):
        self.artifact()
        value = self.api.write_agent_mcp_pose_artifact({}, {}, {'bytes': b'image', 'usage_metadata': [], 'text': 'x' * 800}, prompt='prompt', reference_assets=[])
        self.assertEqual(value['provider'], 'gemini_native_image_generation')
        self.assertEqual(value['usage_metadata'], {})
        self.assertTrue(value['generated_source_metadata']['synthid_watermark_expected'])
        self.assertLessEqual(len(value['provider_text']), 600)

    def test_reference_resolver_selected_before_effectful_record_lookup(self):
        source = self.directory / 'reference.png'; source.write_bytes(b'reference')
        api = self.api
        later = Mock(return_value=self.directory / 'missing')
        class ChangingReference(dict):
            def get(self, key, default=None):
                if key == 'source_path':
                    api.resolve_service_path = later
                    return 'synthetic-reference'
                return super().get(key, default)
        self.replace('accessory_reference_image_contexts', return_value=[ChangingReference(sha256='provided')])
        first = self.replace('resolve_service_path', return_value=source)
        self.replace('public_output_url_for_existing', return_value='/reference')
        content, refs = api.agent_mcp_pose_reference_content({})
        self.assertEqual(len(content), 1)
        self.assertEqual(refs[0]['source_path'], str(source))
        first.assert_called_once_with('synthetic-reference')
        later.assert_not_called()

    def test_artifact_output_resolver_selected_before_effectful_call_lookup(self):
        output = self.artifact(); api = self.api
        later = Mock(return_value=self.directory / 'unexpected.png')
        first = api.agent_mcp_pose_output_path
        class ChangingCall(dict):
            def get(self, key, default=None):
                if key == 'accessory_id':
                    api.agent_mcp_pose_output_path = later
                    return 'part'
                return super().get(key, default)
        api.write_agent_mcp_pose_artifact({}, ChangingCall(pose_id='top'), {'bytes': b'image'}, prompt='prompt', reference_assets=[])
        self.assertTrue(output.exists())
        first.assert_called_once_with({}, 'part', 'top', 'image/png')
        later.assert_not_called()

    def test_path_sanitizer_captured_for_task_then_refreshed_for_filename(self):
        api = self.api
        self.replace('output_write_dir_for_owner', return_value=self.directory)
        first = self.replace('safe_record_id', side_effect=lambda value: 'old-' + value)
        later = Mock(side_effect=lambda value: 'new-' + value)
        class ChangingTask(dict):
            def get(self, key, default=None):
                if key == 'id':
                    api.safe_record_id = later
                    return 'task'
                return super().get(key, default)
        value = api.agent_mcp_pose_output_path(ChangingTask(), 'part', 'pose', 'image/png')
        self.assertEqual(value, self.directory / 'old-task' / 'new-part__new-pose.png')
        first.assert_called_once_with('task')
        self.assertEqual([call.args[0] for call in later.call_args_list], ['part', 'pose'])

    def test_metadata_bound_write_selected_before_serializer_side_effect(self):
        output = self.artifact(); original_dumps = json.dumps; original_write = Path.write_text
        later = Mock(side_effect=AssertionError('late write selection'))
        def serialize(*args, **kwargs):
            Path.write_text = later
            return original_dumps(*args, **kwargs)
        with patch.object(Path, 'write_text', new=original_write), patch.object(self.api.json, 'dumps', side_effect=serialize):
            value = self.api.write_agent_mcp_pose_artifact({}, {}, {'bytes': b'image'}, prompt='prompt', reference_assets=[])
        self.assertTrue(output.exists())
        self.assertTrue(Path(value['metadata_path']).exists())
        later.assert_not_called()


    def test_render_constructors_do_not_read_capabilities(self):
        from dataclasses import fields
        from local_inspection_service.agent import pose_render_ports as ports
        from local_inspection_service.agent.pose_render_configuration import PoseRenderConfiguration
        from local_inspection_service.agent.pose_render_content import PoseRenderContent
        from local_inspection_service.agent.pose_artifact_store import PoseArtifactStore
        getters = []
        def group(port_type):
            values = {field.name: Mock(return_value=None) for field in fields(port_type)}
            getters.extend(values.values())
            return port_type(**values)
        PoseRenderConfiguration(group(ports.PoseRenderConfigurationSources), group(ports.PoseRenderConfigurationDefaults))
        PoseRenderContent(group(ports.PoseRenderReferences), group(ports.PoseRenderPresentation))
        PoseArtifactStore(group(ports.PoseRenderPaths), group(ports.PoseRenderArtifacts), group(ports.PoseRenderPresentation))
        for getter in getters:
            getter.assert_not_called()

    def test_two_live_render_compositions_remain_independent(self):
        from dataclasses import fields
        from local_inspection_service.agent import pose_render_ports as ports
        from local_inspection_service.agent.pose_render_configuration import PoseRenderConfiguration
        from local_inspection_service.agent.pose_render_content import PoseRenderContent
        from local_inspection_service.agent.pose_artifact_store import PoseArtifactStore
        def group(port_type, **selected):
            return port_type(**{field.name: selected.get(field.name, lambda: None) for field in fields(port_type)})
        def make(name):
            sources = group(ports.PoseRenderConfigurationSources,
                settings=lambda: lambda: {'provider': name, 'model': name, 'configured': True, 'api_key_present': True},
                provider_key=lambda: lambda value: name,
                provider_label=lambda: lambda value: name,
                model=lambda: lambda value: name,
                base_url=lambda: lambda value: name,
                key_environment=lambda: lambda value: name)
            defaults = ports.PoseRenderConfigurationDefaults(**{field.name: (lambda: 60.0) if field.name == 'timeout' else (lambda: name) for field in fields(ports.PoseRenderConfigurationDefaults)})
            presentation = group(ports.PoseRenderPresentation, screen=lambda: lambda value: {'rgb': [0, 255, 0], 'hex': '#00FF00', 'label': name})
            content = PoseRenderContent(group(ports.PoseRenderReferences), presentation)
            owner = self.directory / name
            paths = group(ports.PoseRenderPaths, owner_root=lambda: lambda *args: owner, sanitize=lambda: lambda value: value)
            holder = {}
            artifacts = group(ports.PoseRenderArtifacts,
                output=lambda: holder['store'].agent_mcp_pose_output_path,
                digest=lambda: lambda path: name,
                public_url=lambda: lambda path: '/' + name,
                bounded=lambda: lambda value, limit: str(value)[:limit],
                now=lambda: lambda: len(name),
                dumps=lambda: json.dumps)
            holder['store'] = PoseArtifactStore(paths, artifacts, presentation)
            return PoseRenderConfiguration(sources, defaults), content, holder['store'], owner
        instances = {name: make(name) for name in ('first', 'second')}
        with patch.object(self.api, 'image_generation_settings', side_effect=AssertionError('root settings')), patch.object(self.api, 'normalize_chroma_screen', side_effect=AssertionError('root screen')), patch.object(self.api, 'output_write_dir_for_owner', side_effect=AssertionError('root paths')), patch.object(self.api, 'file_sha256', side_effect=AssertionError('root hash')):
            for name in ('first', 'second', 'first'):
                configuration, content, store, owner = instances[name]
                self.assertEqual(configuration.agent_mcp_gemini_image_config()['model'], name)
                self.assertIn('exact ' + name + ' RGB', content.agent_mcp_pose_prompt({}, {}, {}))
                value = store.write_agent_mcp_pose_artifact({'id': 'task'}, {'accessory_id': 'part', 'pose_id': 'pose'}, {'bytes': name.encode()}, prompt=name, reference_assets=[])
                self.assertEqual(value['sha256'], name)
                self.assertEqual(Path(value['output_path']), owner / 'task' / 'part__pose.png')
                self.assertEqual(Path(value['output_path']).read_bytes(), name.encode())
                self.assertEqual(value['created_at'], len(name))


if __name__ == '__main__':
    unittest.main()
