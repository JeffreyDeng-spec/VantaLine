"""Draft contracts against the original Agent pose execution functions."""
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

class AgentPoseExecutionContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.environment = patch.dict(os.environ)
        cls.environment.start()
        cls.root = tempfile.TemporaryDirectory(prefix='pose-execution-contract-')
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

    def orchestration(self):
        task = {'id': 'task'}
        config = {'accessories': []}
        state = {'tool_calls': [], 'pose_plan': {'accessories': [], 'pose_count': 0}}
        self.replace('ensure_agent_mcp_pose_plan', return_value=state)
        self.replace('agent_mcp_orchestration', return_value=state)
        self.photo = self.replace('pipeline_uses_photo_highlight_sprite_flow', return_value=False)
        self.stage = self.replace('set_agent_mcp_stage')
        self.pause = self.replace('pause_agent_mcp_task')
        self.lookup = self.replace('accessory_lookup_by_id', return_value={})
        self.tool = {'configured': True, 'model': 'bound', 'timeout_seconds': 42, 'provider': 'synthetic', 'provider_label': 'Synthetic', 'message': 'configure'}
        self.tool_config = self.replace('agent_mcp_gemini_image_config', return_value=self.tool)
        return task, config, state

    def execution(self):
        task, config, state = self.orchestration()
        self.settings_value = {'model': 'before'}
        self.settings_mock = self.replace('image_generation_settings', return_value=self.settings_value)
        self.provider = Mock()
        self.factory = self.replace('image_generation_provider_from_settings', return_value=self.provider)
        self.content = [{'synthetic': 'reference'}]
        self.assets = [{'path': 'synthetic'}]
        self.references = self.replace('agent_mcp_pose_reference_content', return_value=(self.content, self.assets))
        self.screen_value = {'label': 'green'}
        self.chroma = self.replace('choose_agent_mcp_chroma_screen', return_value=self.screen_value)
        self.prompt = self.replace('agent_mcp_pose_prompt', return_value='exact prompt')
        self.clock = self.replace('agent_mcp_now', return_value=123)
        self.artifact = {'output_path': 'out', 'output_url': '/out', 'metadata_path': 'meta', 'metadata_url': '/meta', 'sha256': None, 'latency_ms': 7, 'usage_metadata': {'count': 1}, 'generated_source_metadata': {'synthetic': True}, 'proxy': {'used': True, 'source_name': 'proxy', 'url': 'synthetic', 'auto_local': False}}
        self.writer = self.replace('write_agent_mcp_pose_artifact', return_value=self.artifact)
        self.error_type = type('SyntheticProviderError', (Exception,), {})
        self.replace('AiProviderError', new=self.error_type)
        call = {'tool': self.api.AGENT_MCP_TOOL_POSE_IMAGE, 'status': 'pending', 'accessory_id': 'part', 'pose_id': 'top'}
        state['tool_calls'] = [call]
        return task, config, state, call

    def preparation(self):
        task, config, state = self.orchestration()
        self.background = self.replace('ensure_pipeline_background_plate')
        self.photos = self.replace('prepare_photo_highlight_sprites_for_task', return_value=(False, False))
        self.save = self.replace('save_config')
        self.ensure = self.replace('ensure_agent_mcp_pose_tool_calls', return_value=state)
        self.execute = self.replace('execute_agent_mcp_pose_tool_calls', return_value=True)
        self.materialize = self.replace('materialize_agent_mcp_pose_assets', return_value=False)
        self.missing = self.replace('agent_mcp_missing_existing_asset_names', return_value=[])
        return task, config, state

    def test_registration_photo_flow_skips_configuration(self):
        task, config, state = self.orchestration()
        self.photo.return_value = True
        self.assertIs(self.api.ensure_agent_mcp_pose_tool_calls(task, config), state)
        self.tool_config.assert_not_called()
        self.lookup.assert_not_called()
        self.assertEqual(self.stage.call_args.args[1:4], ('pose_image_generation', 'skipped', 100))

    def test_registration_preserves_cache_and_active_call_identity(self):
        task, config, state = self.orchestration()
        cached = {'id': 'cached'}
        self.lookup.return_value = {'cached': cached}
        cache = self.replace('agent_mcp_accessory_pose_images_exist', return_value=True)
        self.replace('agent_mcp_tool_call_id', side_effect=lambda task, tool, part, pose: part + pose)
        existing = {'call_id': 'parttop', 'status': 'running'}
        request = {'original': []}
        state['tool_calls'] = [existing]
        state['pose_plan'] = {'pose_count': 3, 'accessories': [{'accessory_id': 'cached', 'poses': [{'pose_id': 'top'}]}, {'accessory_id': 'part', 'poses': [{'pose_id': 'top'}, {'pose_id': 'side', 'request': request}]}]}
        upsert = self.replace('upsert_agent_mcp_tool_call')
        self.assertIs(self.api.ensure_agent_mcp_pose_tool_calls(task, config), state)
        cache.assert_called_once_with(cached)
        self.assertEqual(upsert.call_count, 1)
        created = upsert.call_args.args[1]
        self.assertIs(created['request'], request)
        self.assertIs(state['tool_calls'][0], existing)
        self.assertEqual((created['call_id'], created['status'], created['provider']), ('partside', 'pending', 'synthetic'))

    def test_registration_missing_configuration_preserves_skip_precedence(self):
        task, config, state = self.orchestration()
        state['skip_pose_image_generation'] = True
        state['pose_plan'] = {'pose_count': 1, 'accessories': [{'accessory_id': 'part', 'poses': [{'pose_id': 'top'}]}]}
        self.tool['configured'] = False
        self.replace('agent_mcp_tool_call_id', return_value='call')
        upsert = self.replace('upsert_agent_mcp_tool_call')
        self.api.ensure_agent_mcp_pose_tool_calls(task, config)
        self.assertEqual((upsert.call_args.args[1]['status'], upsert.call_args.args[1]['error']), ('missing_configuration', 'configure'))
        self.assertEqual(self.stage.call_args.args[2:4], ('skipped', 100))
        self.tool['configured'] = True
        self.api.ensure_agent_mcp_pose_tool_calls(task, config)
        self.assertEqual(self.stage.call_args.args[2:4], ('pending', 100))

    def test_execution_photo_flow_returns_before_settings(self):
        task, config, state, call = self.execution()
        self.photo.return_value = True
        skipped = self.replace('mark_legacy_pose_flow_skipped_for_photo_highlight')
        self.assertTrue(self.api.execute_agent_mcp_pose_tool_calls(task, config))
        skipped.assert_called_once_with(task, config, state)
        self.tool_config.assert_not_called()
        self.factory.assert_not_called()
        self.assertEqual(call['status'], 'pending')

    def test_execution_missing_config_records_projection_without_provider(self):
        task, config, state, call = self.execution()
        self.tool['configured'] = False
        self.assertFalse(self.api.execute_agent_mcp_pose_tool_calls(task, config))
        self.assertIs(state['tool_config']['pose_image_generation'], self.tool)
        self.settings_mock.assert_not_called()
        self.provider.generate_image.assert_not_called()

    def test_execution_no_calls_still_constructs_bound_provider(self):
        task, config, state, call = self.execution()
        state['tool_calls'] = [{'tool': self.api.AGENT_MCP_TOOL_POSE_IMAGE, 'status': 'completed'}, {'tool': self.api.AGENT_MCP_TOOL_POSE_IMAGE, 'status': 'skipped'}]
        self.assertTrue(self.api.execute_agent_mcp_pose_tool_calls(task, config))
        self.factory.assert_called_once_with(self.settings_value)
        self.assertEqual(self.settings_value, {'model': 'bound', 'timeout_seconds': 42})
        self.provider.generate_image.assert_not_called()
        self.stage.assert_not_called()

    def test_execution_success_preserves_arguments_and_artifact_aliases(self):
        task, config, state, call = self.execution()
        self.assertTrue(self.api.execute_agent_mcp_pose_tool_calls(task, config))
        self.provider.generate_image.assert_called_once_with('exact prompt', self.content, model='bound')
        self.writer.assert_called_once_with(task, call, self.provider.generate_image.return_value, prompt='exact prompt', reference_assets=self.assets)
        self.assertIs(call['source_reference_assets'], self.assets)
        self.assertIs(call['usage_metadata'], self.artifact['usage_metadata'])
        self.assertIs(call['generated_source_metadata'], self.artifact['generated_source_metadata'])
        self.assertIs(call['chroma_screen'], self.screen_value)
        self.assertEqual((call['status'], call['sha256'], call['artifact_refs']), ('completed', None, ['/out', '/meta']))
        self.assertEqual((state['state'], state['active_stage'], state['pause']), ('pose_image_generation_completed', 'sample_generation', None))

    def test_execution_provider_error_pauses_once_without_retry(self):
        task, config, state, call = self.execution()
        self.provider.generate_image.side_effect = self.error_type('synthetic failure')
        self.assertFalse(self.api.execute_agent_mcp_pose_tool_calls(task, config))
        self.assertEqual(self.provider.generate_image.call_count, 1)
        self.writer.assert_not_called()
        self.assertEqual((call['status'], call['error']), ('failed', 'synthetic failure'))
        self.assertEqual(self.pause.call_args.kwargs['stage'], 'pose_image_generation')
        self.assertEqual(self.stage.call_args.args[2:4], ('failed', 5))

    def test_execution_unexpected_artifact_error_retains_running_state(self):
        task, config, state, call = self.execution()
        self.writer.side_effect = ValueError('metadata')
        with self.assertRaisesRegex(ValueError, 'metadata'):
            self.api.execute_agent_mcp_pose_tool_calls(task, config)
        self.assertEqual(call['status'], 'running')
        self.assertEqual(self.provider.generate_image.call_count, 1)
        self.pause.assert_not_called()
        self.assertNotIn('state', state)

    def test_execution_reference_error_is_outside_provider_catch(self):
        task, config, state, call = self.execution()
        self.references.side_effect = self.error_type('reference')
        with self.assertRaisesRegex(self.error_type, 'reference'):
            self.api.execute_agent_mcp_pose_tool_calls(task, config)
        self.assertEqual(call['status'], 'pending')
        self.provider.generate_image.assert_not_called()
        self.pause.assert_not_called()

    def test_preparation_background_failure_is_logged_then_photo_ready_saved(self):
        task, config, state = self.preparation()
        self.background.side_effect = ValueError('background')
        printer = self.stack.enter_context(patch.object(self.api.traceback, 'print_exc'))
        self.photos.return_value = (True, True)
        self.assertTrue(self.api.prepare_agent_mcp_before_sample_generation(task, config))
        printer.assert_called_once_with(file=self.api.sys.stderr)
        self.save.assert_called_once_with(config)
        self.ensure.assert_not_called()
        self.execute.assert_not_called()

    def test_preparation_existing_photo_pause_saves_only_changed(self):
        task, config, state = self.preparation()
        state['pause'] = {'stage': 'pose_image_generation'}
        self.photos.return_value = (False, True)
        self.assertFalse(self.api.prepare_agent_mcp_before_sample_generation(task, config))
        self.save.assert_called_once_with(config)
        self.ensure.assert_not_called()
        self.pause.assert_not_called()

    def test_preparation_photo_flow_never_falls_back_to_legacy(self):
        task, config, state = self.preparation()
        self.photo.return_value = True
        self.assertFalse(self.api.prepare_agent_mcp_before_sample_generation(task, config))
        self.assertEqual(self.pause.call_args.kwargs['suggested_actions'], ['retry_pose_image_generation', 'upload_more_reference_photos', 'cancel'])
        self.ensure.assert_not_called()
        self.execute.assert_not_called()
        self.save.assert_not_called()

    def test_preparation_skip_recovery_rechecks_after_single_execution(self):
        task, config, state = self.preparation()
        state['skip_pose_image_generation'] = True
        self.missing.side_effect = [['missing'], []]
        self.assertTrue(self.api.prepare_agent_mcp_before_sample_generation(task, config))
        self.assertFalse(state['skip_pose_image_generation'])
        self.assertEqual(self.materialize.call_count, 2)
        self.execute.assert_called_once_with(task, config)
        self.assertEqual(self.missing.call_count, 2)
        self.assertEqual((state['state'], state['active_stage'], state['pause']), ('sample_generation', 'sample_generation', None))
        self.stage.assert_not_called()
        self.save.assert_not_called()

    def test_preparation_skip_without_missing_keeps_skip_stage(self):
        task, config, state = self.preparation()
        state['skip_pose_image_generation'] = True
        self.assertTrue(self.api.prepare_agent_mcp_before_sample_generation(task, config))
        self.execute.assert_not_called()
        self.assertEqual(self.stage.call_args.args[2:4], ('skipped', 100))
        self.assertIsNone(state['pause'])

    def test_preparation_execution_success_materializes_without_extra_save(self):
        task, config, state = self.preparation()
        self.assertTrue(self.api.prepare_agent_mcp_before_sample_generation(task, config))
        self.execute.assert_called_once_with(task, config)
        self.materialize.assert_called_once_with(task, config)
        self.assertEqual(state['state'], 'sample_generation')
        self.save.assert_not_called()

    def test_preparation_failed_execution_uses_current_configuration_reason(self):
        task, config, state = self.preparation()
        self.execute.return_value = False
        self.assertFalse(self.api.prepare_agent_mcp_before_sample_generation(task, config))
        self.assertEqual(self.pause.call_args.kwargs['reason'], 'configure')
        self.assertEqual(self.pause.call_args.kwargs['suggested_actions'], ['configure_image_generation', 'continue_existing_assets', 'replan', 'cancel'])
        self.materialize.assert_not_called()
        self.assertEqual(self.execute.call_count, 1)

    def test_execution_reference_callee_selected_before_item_truth_test(self):
        task, config, state, call = self.execution()
        original = self.references
        replacement = Mock(return_value=([], []))
        api = self.api
        class Item(dict):
            def __bool__(self):
                api.agent_mcp_pose_reference_content = replacement
                return True
        item = Item(id='part')
        self.lookup.return_value = {'part': item}
        self.assertTrue(self.api.execute_agent_mcp_pose_tool_calls(task, config))
        original.assert_called_once_with(item, max_images=3)
        replacement.assert_not_called()
        self.assertIs(call['source_reference_assets'], self.assets)

    def test_execution_error_matcher_is_resolved_after_provider_failure(self):
        task, config, state, call = self.execution()
        changed = type('ChangedProviderError', (Exception,), {})
        def generate(*args, **kwargs):
            self.api.AiProviderError = changed
            raise changed('late matcher')
        self.provider.generate_image.side_effect = generate
        caught = None
        try:
            result = self.api.execute_agent_mcp_pose_tool_calls(task, config)
        except changed as exc:
            caught = exc
            result = None
        self.assertIsNone(caught)
        self.assertIs(result, False)
        self.assertEqual(call['status'], 'failed')
        self.assertEqual(self.provider.generate_image.call_count, 1)

    def test_registration_upsert_callee_selected_before_request_lookup(self):
        task, config, state = self.orchestration()
        self.replace('agent_mcp_tool_call_id', return_value='call')
        original = self.replace('upsert_agent_mcp_tool_call')
        replacement = Mock()
        api = self.api
        class Pose(dict):
            def get(self, key, default=None):
                if key == 'request':
                    api.upsert_agent_mcp_tool_call = replacement
                return super().get(key, default)
        state['pose_plan'] = {'accessories': [{'accessory_id': 'part', 'poses': [Pose(pose_id='top', request={'x': 1})]}]}
        self.api.ensure_agent_mcp_pose_tool_calls(task, config)
        self.assertEqual(original.call_count, 1)
        replacement.assert_not_called()
        self.assertEqual(original.call_args.args[1]['request'], {'x': 1})

    def test_preparation_materializer_is_resolved_after_execution(self):
        task, config, state = self.preparation()
        replacement = Mock(return_value=True)
        def execute(*args):
            self.api.materialize_agent_mcp_pose_assets = replacement
            return True
        self.execute.side_effect = execute
        self.assertTrue(self.api.prepare_agent_mcp_before_sample_generation(task, config))
        self.materialize.assert_not_called()
        replacement.assert_called_once_with(task, config)
        self.assertEqual(state['active_stage'], 'sample_generation')


    def test_workflow_constructors_do_not_read_capabilities(self):
        from dataclasses import fields
        from local_inspection_service.agent import pose_execution_ports as ports
        from local_inspection_service.agent.pose_call_registration import PoseCallRegistration
        from local_inspection_service.agent.pose_call_execution import PoseCallExecution
        from local_inspection_service.agent.pose_sample_preparation import PoseSamplePreparation
        getters = []
        def group(port_type):
            values = {f.name: Mock(return_value=None) for f in fields(port_type)}
            getters.extend(values.values())
            return port_type(**values)
        PoseCallRegistration(group(ports.PoseWorkflowState), group(ports.PoseWorkflowModels), group(ports.PoseCallRegistry))
        PoseCallExecution(group(ports.PoseWorkflowState), group(ports.PoseWorkflowModels), group(ports.PoseCallRegistry), group(ports.PoseCallContent), group(ports.PoseCallPresentation))
        PoseSamplePreparation(group(ports.PoseWorkflowState), group(ports.PoseWorkflowModels), group(ports.PoseSampleSteps), group(ports.PoseWorkflowDiagnostics))
        for getter in getters:
            getter.assert_not_called()

    def test_two_workflow_compositions_keep_state_and_callbacks_independent(self):
        from dataclasses import fields
        from local_inspection_service.agent import pose_execution_ports as ports
        from local_inspection_service.agent.pose_call_registration import PoseCallRegistration
        from local_inspection_service.agent.pose_call_execution import PoseCallExecution
        from local_inspection_service.agent.pose_sample_preparation import PoseSamplePreparation
        def group(port_type, **selected):
            return port_type(**{f.name: selected.get(f.name, lambda: None) for f in fields(port_type)})
        def make(name):
            state = {'pose_plan': {'accessories': [], 'pose_count': 0}}
            config = {'configured': False, 'message': name}
            records = []
            state_ports = group(ports.PoseWorkflowState, plan=lambda: lambda *args: state, current=lambda: lambda *args: state, photo_flow=lambda: lambda *args: False, stage=lambda: lambda *args, **kwargs: records.append(name))
            models = group(ports.PoseWorkflowModels, configuration=lambda: lambda: config)
            registry = group(ports.PoseCallRegistry, lookup=lambda: lambda value: {})
            steps = group(ports.PoseSampleSteps, background=lambda: lambda *args: None, photos=lambda: lambda *args: (True, False))
            registration = PoseCallRegistration(state_ports, models, registry)
            execution = PoseCallExecution(state_ports, models, registry, group(ports.PoseCallContent), group(ports.PoseCallPresentation))
            preparation = PoseSamplePreparation(state_ports, models, steps, group(ports.PoseWorkflowDiagnostics))
            return registration, execution, preparation, state, config, records
        instances = {name: make(name) for name in ('first', 'second')}
        with patch.object(self.api, 'ensure_agent_mcp_pose_plan', side_effect=AssertionError('root plan')), patch.object(self.api, 'agent_mcp_orchestration', side_effect=AssertionError('root state')), patch.object(self.api, 'agent_mcp_gemini_image_config', side_effect=AssertionError('root config')), patch.object(self.api, 'ensure_pipeline_background_plate', side_effect=AssertionError('root background')):
            for name in ('first', 'second', 'first'):
                registration, execution, preparation, state, config, records = instances[name]
                self.assertIs(registration.ensure_agent_mcp_pose_tool_calls({}, {}), state)
                self.assertFalse(execution.execute_agent_mcp_pose_tool_calls({}, {}))
                self.assertIs(state['tool_config']['pose_image_generation'], config)
                self.assertTrue(preparation.prepare_agent_mcp_before_sample_generation({}, {}))
                self.assertTrue(all(record == name for record in records))
            self.assertEqual(instances['first'][-1], ['first', 'first'])
            self.assertEqual(instances['second'][-1], ['second'])


if __name__ == '__main__':
    unittest.main()
