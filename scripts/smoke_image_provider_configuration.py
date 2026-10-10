"""Image endpoint configuration and protocol parity, with all network calls replaced."""
import ast
import base64
from dataclasses import fields
import os
from pathlib import Path
import requests
import shutil
import sys
from types import SimpleNamespace
from typing import Any
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from canonical_application_source_contract import read_checked_application_source
BASELINE = os.environ.get('VANTALINE_IMAGE_PROVIDER_CONFIGURATION_BASELINE_SOURCE')
NAMES = ('image_job_prompt', 'cursor_image_model_score', 'inspect_cursor_image_models', 'cursor_image2_settings', 'public_cursor_image2_status', 'cursor_image2_payload', 'cursor_image2_response_candidates', 'extract_cursor_image2_bytes')


def create(bindings):
    if BASELINE:
        nodes = [n for n in ast.parse(Path(BASELINE).read_text(encoding='utf-8-sig')).body if isinstance(n, ast.FunctionDef) and n.name in NAMES]
        assert len(nodes) == 8
        bindings.update(Any=Any, Path=Path, os=os, requests=requests, shutil=shutil)
        exec(compile(ast.Module(body=nodes, type_ignores=[]), BASELINE, 'exec'), bindings)
        return SimpleNamespace(**{name: bindings[name] for name in NAMES})
    from local_inspection_service.model_providers.image_provider_configuration import ImageProviderConfiguration
    from local_inspection_service.model_providers.image_provider_configuration_ports import ImageProviderSelection, ImageProviderSettings, ImageProviderPayload
    def ports(cls):
        return cls(**{f.name: lambda name=f.name: bindings[name] for f in fields(cls)})
    service = ImageProviderConfiguration(ports(ImageProviderSelection), ports(ImageProviderSettings), ports(ImageProviderPayload))
    bindings.update({name: getattr(service, name) for name in NAMES})
    return service


class ConfigurationContract(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.no_network = patch.object(requests, 'get', side_effect=AssertionError('Unmocked network forbidden'))
        self.no_network.start()
        self.addCleanup(self.no_network.stop)

    def fixture(self):
        config = {'provider': 'cursor', 'base_url': 'https://example.invalid/v1/', 'api_key': 'synthetic-key', 'connected': True}
        b = dict(CURSOR_IMAGE_MODEL_PRIORITY=('gpt-image', 'image2'), CURSOR_IMAGE_MODEL_KEYWORDS=('image',),
                 normalize_agent_model_options=lambda value: value or [], normalize_agent_provider=lambda provider, url: provider,
                 AGENT_PROVIDER_CURSOR='cursor', agent_connected=lambda c: c.get('connected', False),
                 load_agent_config=lambda: config, CURSOR_IMAGE2_BASE_URL_ENV='TEST_BASE', AGENT_CURSOR_DEFAULT_BASE_URL='https://default.invalid',
                 CURSOR_IMAGE2_ENDPOINT_ENV='TEST_ENDPOINT', CURSOR_IMAGE2_API_KEY_ENV='TEST_KEY', CURSOR_IMAGE2_MODEL_ENV='TEST_MODEL',
                 CURSOR_IMAGE2_DEFAULT_MODEL='default-model', masked_url_for_status=lambda value: 'redacted-endpoint' if value else '',
                 LOCAL_CODEX_IMAGE_PROVIDER='local', CURSOR_IMAGE2_PROVIDER='cursor-image', MAX_IMAGE_WORKER_INPUTS=2,
                 image_file_payload=lambda path: {'path': str(path)}, decode_b64_image=lambda value: base64.b64decode(value) if value else b'')
        return create(b), b, config

    def test_exact_prompt_and_pose_variants(self):
        s, _, _ = self.fixture()
        job = {'output_path': '/out.png', 'prompt': 'CORE', 'pose_family': 'upright', 'generation_step': 'anchor_replacement', 'input_files': ['a', 'b'], 'video_reference_frames': ['v']}
        expected = '''You are the ImageWorker for the local assembly-line inspection service.

Use all 2 attached images. 1 may be frames extracted from a user video.
The first attached image is a hidden backend anchor image. Use it only for layout, pose, scale, camera, and table/background.

Core prompt:
CORE

- Generate a realistic PNG with AI image generation; do not satisfy this with local drawing or script-only image editing.
- Final image must contain exactly nine replacement objects matched to the nine anchor bars.
- Save the final PNG exactly here:
  /out.png'''
        self.assertEqual(s.image_job_prompt(job), expected)
        self.assertIn('exactly nine horizontal', s.image_job_prompt({'pose_family': 'lying'}))
        self.assertIn('requested pose collection', s.image_job_prompt({}))
        self.assertIn('Follow the core prompt exactly.', s.image_job_prompt({}))

    def test_priority_model_selection_and_stable_ties(self):
        s, _, config = self.fixture()
        self.assertEqual(s.cursor_image_model_score('GPT-IMAGE-X'), (100, 11))
        self.assertEqual(s.cursor_image_model_score('image2'), (99, 6))
        self.assertEqual(s.cursor_image_model_score('image'), (10, 5))
        self.assertEqual(s.cursor_image_model_score(None), (0, 0))
        config['model_options'] = [{'id': 'text'}, {'id': 'image2'}, {'id': 'gpt-image-a'}, {'id': 'gpt-image-b'}]
        result = s.inspect_cursor_image_models(config)
        self.assertEqual(result['recommended_model'], 'gpt-image-a')
        self.assertEqual(result['image_model_count'], 3)
        self.assertEqual([item['id'] for item in result['image_models']], ['gpt-image-a', 'gpt-image-b', 'image2'])

    def test_model_list_statuses_and_projection_limit(self):
        s, _, config = self.fixture()
        self.assertEqual(s.inspect_cursor_image_models(config)['status'], 'no_model_list')
        config['model_options'] = [{'id': 'text'}]
        self.assertEqual(s.inspect_cursor_image_models(config)['status'], 'no_image_model')
        config['connected'] = False
        self.assertEqual(s.inspect_cursor_image_models(config)['status'], 'not_connected')
        config['model_options'] = [{'id': f'image-{i}'} for i in range(20)]
        result = s.inspect_cursor_image_models(config)
        self.assertEqual(result['status'], 'image_model_available')
        self.assertFalse(result['connected'])
        self.assertEqual((result['image_model_count'], len(result['image_models'])), (20, 12))

    def test_explicit_endpoint_and_environment_precedence(self):
        s, _, config = self.fixture()
        result = s.cursor_image2_settings()
        self.assertFalse(result['configured'])
        self.assertEqual(result['missing'], ['TEST_ENDPOINT'])
        self.assertEqual(result['api_key'], 'synthetic-key')
        self.assertEqual(result['base_url'], 'https://example.invalid/v1')
        config['model_options'] = [{'id': 'image2'}]
        with patch.dict(os.environ, {'TEST_BASE': ' https://override.invalid/ ', 'TEST_ENDPOINT': ' https://relay.invalid/ ', 'TEST_KEY': ' private-fixture ', 'TEST_MODEL': ' explicit '}):
            result = s.cursor_image2_settings()
        self.assertTrue(result['configured'])
        self.assertEqual((result['base_url'], result['endpoint'], result['api_key'], result['model']), ('https://override.invalid', 'https://relay.invalid', 'private-fixture', 'explicit'))
        self.assertEqual(result['endpoint_public'], 'redacted-endpoint')

    def test_other_provider_no_key_reuse_and_timeout_bounds(self):
        s, _, config = self.fixture()
        config['provider'] = 'other'
        result = s.cursor_image2_settings()
        self.assertEqual(result['api_key'], '')
        self.assertEqual(result['base_url'], 'https://default.invalid')
        self.assertEqual(result['missing'], ['TEST_ENDPOINT', 'TEST_KEY'])
        for value, expected in [(-4, 10), (9000, 900), (0, 120), ('33.5', 33.5)]:
            config['timeout_seconds'] = value
            self.assertEqual(s.cursor_image2_settings()['timeout_seconds'], expected)
        config['timeout_seconds'] = 'invalid'
        with self.assertRaises(ValueError):
            s.cursor_image2_settings()

    def test_public_status_redaction_and_local_fallback(self):
        s, _, _ = self.fixture()
        with patch.dict(os.environ, {'TEST_ENDPOINT': 'https://relay.invalid/private-fixture'}), patch.object(shutil, 'which', return_value='/fake/codex'):
            result = s.public_cursor_image2_status()
        self.assertNotIn('api_key', result)
        self.assertEqual(result['endpoint'], 'redacted-endpoint')
        self.assertNotIn('synthetic-key', repr(result))
        self.assertNotIn('private-fixture', repr(result))
        self.assertTrue(result['fallback']['configured'])
        with patch.object(shutil, 'which', return_value=None):
            self.assertEqual(s.public_cursor_image2_status()['fallback']['status'], 'missing_config')

    def test_payload_cap_and_file_failure_before_transport(self):
        s, b, _ = self.fixture()
        with patch.dict(os.environ, {'INSPECTION_CURSOR_IMAGE2_SIZE': ' 512x512 '}):
            payload = s.cursor_image2_payload({'prompt': 'CORE'}, ['a', 'b', 'c'], {'model': 'm'})
        self.assertEqual(payload['input_images'], [{'path': 'a'}, {'path': 'b'}])
        self.assertEqual((payload['size'], payload['n'], payload['response_format']), ('512x512', 1, 'b64_json'))
        b['image_file_payload'] = Mock(side_effect=OSError('missing input'))
        with self.assertRaisesRegex(OSError, 'missing input'):
            s.cursor_image2_payload({}, ['missing'], {'model': 'm'})

    def test_response_candidate_order_and_identity(self):
        s, _, _ = self.fixture()
        a, b, c = {'id': 1}, {'id': 2}, {'id': 3}
        payload = {'data': [a, 0], 'images': b, 'output': [c], 'result': {}, 'url': 'fixture'}
        candidates = s.cursor_image2_response_candidates(payload)
        self.assertEqual(candidates, [a, b, c, {}, payload])
        self.assertIs(candidates[0], a)
        self.assertIs(candidates[-1], payload)
        self.assertEqual(s.cursor_image2_response_candidates([a, None]), [a])
        self.assertEqual(s.cursor_image2_response_candidates(None), [])

    def test_response_bytes_precedence_url_and_failures(self):
        s, _, _ = self.fixture()
        self.assertEqual(s.extract_cursor_image2_bytes({'data': [{'b64_json': base64.b64encode(b'PNG').decode(), 'url': 'https://never.invalid'}]}, {'timeout_seconds': 12}), b'PNG')
        requests.get.assert_not_called()
        response = Mock(content=b'URL')
        with patch.object(requests, 'get', return_value=response) as get:
            self.assertEqual(s.extract_cursor_image2_bytes({'url': ' https://fixture.invalid '}, {'timeout_seconds': '12'}), b'URL')
            get.assert_called_once_with('https://fixture.invalid', timeout=12.0)
            response.raise_for_status.assert_called_once()
        failure = RuntimeError('bad response')
        response.raise_for_status.side_effect = failure
        with patch.object(requests, 'get', return_value=response), self.assertRaises(RuntimeError) as raised:
            s.extract_cursor_image2_bytes({'url': 'https://fixture.invalid'}, {'timeout_seconds': 12})
        self.assertIs(raised.exception, failure)
        with self.assertRaisesRegex(RuntimeError, 'TEST_ENDPOINT'):
            s.extract_cursor_image2_bytes({}, {'timeout_seconds': 12})

    @unittest.skipIf(BASELINE, 'candidate composition only')
    def test_assembly_and_instance_isolation(self):
        from local_inspection_service.model_providers.image_provider_configuration_ports import ImageProviderSelection, ImageProviderSettings, ImageProviderPayload
        tree = ast.parse(read_checked_application_source(ROOT / 'local_inspection_service/server.py', encoding='utf-8'))
        assignment = next(n for n in tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == '_image_provider_configuration' for t in n.targets))
        from application_integration_source_contract import verify_actual_compositions
        verify_actual_compositions()
        self.assertEqual(len(assignment.value.keywords), 3)
        for group, cls in zip(assignment.value.keywords, (ImageProviderSelection, ImageProviderSettings, ImageProviderPayload)):
            self.assertEqual({k.arg for k in group.value.keywords}, {f.name for f in fields(cls)})
            for getter in group.value.keywords:
                self.assertIsInstance(getter.value, ast.Lambda)
                expected = '_provider_configuration.'+getter.arg if getter.arg in {'masked_url_for_status','normalize_agent_model_options','normalize_agent_provider'} else getter.arg
                self.assertEqual(ast.dump(getter.value.body), ast.dump(ast.parse(expected, mode='eval').body))
                self.assertFalse(getter.value.args.args)
        a, ab, _ = self.fixture()
        b, bb, _ = self.fixture()
        ab['CURSOR_IMAGE_MODEL_PRIORITY'] = ('alpha',)
        bb['CURSOR_IMAGE_MODEL_PRIORITY'] = ('beta',)
        self.assertEqual([s.cursor_image_model_score('alpha')[0] for s in (a, b, a)], [100, 0, 100])


if __name__ == '__main__':
    unittest.main(verbosity=2)
