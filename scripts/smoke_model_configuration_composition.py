"""Actual independent profile owners and HTTP registrars, without external calls."""
import ast
from dataclasses import fields, replace
import hashlib
import json
import os
import re
import tempfile
import time
from typing import get_type_hints
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from local_inspection_service.model_profiles.composition import ModelConfiguration
from local_inspection_service.model_profiles.dependencies import ProfileDependencies, ProfileApiDependencies
from local_inspection_service.model_profiles.legacy import LegacyConfiguration, sources
from local_inspection_service.model_providers.configuration_composition import ProviderConfiguration


def provider_inputs():
    forbidden = Mock(side_effect=AssertionError('unexpected configuration capability call'))
    ports = {name: kind(**{field.name: forbidden for field in fields(kind)})
             for name, kind in get_type_hints(ProviderConfiguration.__init__).items()
             if name != 'return'}
    return ports, forbidden


class MemoryCursor:
    """Read-only runtime protocol substitute; Service and Repository are real."""
    def __init__(self, runtime):
        self.runtime = runtime
        self.value = None

    def execute(self, query, parameters=()):
        self.runtime.events.append(('execute', query, parameters))
        if self.runtime.fail_reads:
            raise RuntimeError('synthetic repository failure')
        if query.startswith('INSERT INTO'):
            if self.runtime.fail_writes:
                raise RuntimeError('synthetic repository write failure')
            self.runtime.records[parameters[0]] = json.loads(parameters[3])
            self.value = None
            return self
        self.value = self.runtime.records.get(parameters[0]) if parameters else None
        return self

    def fetchone(self):
        return None if self.value is None else {'raw_json': self.value}

    def close(self):
        self.runtime.events.append(('close',))


class MemoryRuntime:
    def __init__(self, marker):
        self.marker = marker
        self.events = []
        self.fail_reads = False
        self.fail_writes = False
        self.connection = self
        self.records = {
            'same:1': dict(id='same', version=1, name=marker, provider='qwen',
                           model='model-' + marker, base_url='https://example.invalid',
                           timeout_seconds=30, enabled=True, capabilities=['vision'],
                           pending=False, secret_ref='SAME_REF', masked_key='redacted'),
            'state': dict(revision=1, heads={'same': 1}, bindings={'pipeline': 'same'},
                          migrated_at=0, initial_snapshot={}),
        }

    def _qualified_table(self, name):
        return self.marker + '.' + name

    def _cursor(self):
        return MemoryCursor(self)

    def _row_to_dict(self, cursor, row):
        return row

    def commit(self):
        self.events.append(('commit',))

    def rollback(self):
        self.events.append(('rollback',))


def configured_owner(marker):
    runtime = MemoryRuntime(marker)
    reads = []
    forbidden = Mock(side_effect=AssertionError('unexpected mutation or migration'))
    dependencies = ProfileDependencies(lambda: runtime, forbidden,
        lambda reference: reads.append(reference) or 'synthetic-' + marker,
        forbidden, forbidden, forbidden, forbidden)
    return ModelConfiguration(dependencies, agent_defaults=lambda: {}), runtime, reads


def owner(defaults=None):
    forbidden = Mock(side_effect=AssertionError('construction or scoped-unbound read performed external I/O'))
    dependencies = ProfileDependencies(*([forbidden] * 7))
    return ModelConfiguration(dependencies, agent_defaults=defaults or (lambda: {'model': 'default', 'enabled': True})), forbidden


class Contracts(unittest.TestCase):
    def test_empty_profile_migration_uses_owned_legacy_readers_and_secret_store(self):
        # Source readers and key enumeration are substituted; migration, profile
        # creation, secret persistence and Repository are real. No PostgreSQL.
        with tempfile.TemporaryDirectory(prefix='configuration-migration-') as directory:
            completed = []
            for marker in ('B', 'A'):
                ports, poison = provider_inputs()
                location = Path(directory) / marker
                environment = {}
                ports['secret_paths'] = replace(ports['secret_paths'],
                    directory=lambda location=location: location, file=lambda location=location: location / 'secrets.env')
                ports['secret_environment'] = replace(ports['secret_environment'], values=lambda environment=environment: environment)
                ports['secret_policy'] = replace(ports['secret_policy'], fullmatch=lambda: re.fullmatch)
                ports['secret_codec'] = replace(ports['secret_codec'],
                    loads=lambda: json.loads, dumps=lambda: json.dumps, decode_error=lambda: json.JSONDecodeError)
                ports['secret_file_operations'] = replace(ports['secret_file_operations'],
                    chmod=lambda: os.chmod, replace=lambda: os.replace)
                ports['validation_capabilities'] = replace(ports['validation_capabilities'],
                    fullmatch=lambda: re.fullmatch)
                provider = ProviderConfiguration(**ports)
                runtime = MemoryRuntime(marker)
                runtime.records = {}
                vision = dict(provider='qwen', model='qwen3-vl-flash',
                    base_url='https://example.invalid', timeout_seconds=30,
                    api_key='vision-' + marker, enabled=True)
                image = {**vision, 'provider': 'qwen_image', 'model': 'qwen-image-2.0-pro',
                         'api_key': 'image-' + marker}
                agent = {**vision, 'provider': 'openai_compatible', 'model': 'assistant-' + marker,
                         'api_key': 'agent-' + marker}
                events = []
                def read(kind, value):
                    return lambda: events.append(kind) or dict(value)
                with patch.object(provider.legacy_json, '_legacy_ai_detection_settings', read('ai', vision)), \
                     patch.object(provider.legacy_image, '_legacy_image_generation_settings', read('image', image)), \
                     patch.object(provider.legacy_agent, '_legacy_load_agent_config', read('agent', agent)), \
                     patch.object(provider, 'load_ai_local_config', read('local', {})), \
                     patch.object(provider.keys, 'normalize_ai_key_items', return_value=[]), \
                     patch.object(provider.keys, 'normalize_image_key_items', return_value=[]), \
                     patch.object(provider.keys, 'normalize_agent_key_items', return_value=[]), \
                     patch.object(provider, 'load_agent_config', create=True,
                                  side_effect=AssertionError('migration recursed into modern settings')):
                    value = provider.create_model_configuration(runtime_repository=lambda runtime=runtime: runtime,
                        legacy_label=read('label', {'key': 'label-' + marker}), agent_defaults=poison)
                    self.assertEqual(events, [])
                    if marker == 'A':
                        runtime.fail_writes = True
                        with self.assertRaisesRegex(RuntimeError, 'repository write failure'):
                            value.service.initialize()
                        self.assertEqual(runtime.records, {})
                        self.assertIn(('rollback',), runtime.events)
                        self.assertEqual(runtime.events[-1], ('close',))
                        self.assertEqual(set(provider.load_local_secret_env().values()), {'vision-A'})
                        self.assertEqual(completed[0][1].ai_detection_settings()['api_key'], 'vision-B')
                        runtime.fail_writes = False
                        events.clear()
                    value.service.initialize()
                    self.assertEqual(events, ['ai', 'image', 'agent', 'local', 'label'])
                    self.assertEqual(value.ai_detection_settings()['api_key'], 'vision-' + marker)
                    self.assertEqual(value.image_generation_settings()['api_key'], 'image-' + marker)
                    self.assertEqual(value.service.resolve('training_assistant')['api_key'], 'agent-' + marker)
                    self.assertEqual(value.service.resolve('label')['api_key'], 'label-' + marker)
                    saved = provider.load_local_secret_env()
                    self.assertEqual(set(saved.values()), {'vision-' + marker, 'image-' + marker,
                                                          'agent-' + marker, 'label-' + marker})
                    self.assertEqual(environment, saved)
                    initial_events = list(events)
                    value.service.initialize()
                    self.assertEqual(events, initial_events)
                    completed.append((marker, value))
                poison.assert_not_called()
            for marker, value in completed:
                self.assertEqual(value.ai_detection_settings()['api_key'], 'vision-' + marker)

    def test_profile_factory_closes_over_provider_and_preserves_pinned_versions(self):
        for marker in ('A', 'B'):
            ports, poison = provider_inputs()
            environment = {'SAME_REF': 'synthetic-' + marker}
            ports['secret_environment'] = replace(ports['secret_environment'], values=lambda environment=environment: environment)
            ports['secret_policy'] = replace(ports['secret_policy'], fullmatch=lambda: re.fullmatch)
            provider = ProviderConfiguration(**ports)
            runtime = MemoryRuntime(marker)
            label = Mock(side_effect=AssertionError('existing profile read migrated legacy sources'))
            value = provider.create_model_configuration(runtime_repository=lambda runtime=runtime: runtime,
                legacy_label=label, agent_defaults=poison)
            self.assertEqual(runtime.events, [])
            with value.service.scope({'pipeline': {'id': 'same', 'version': 1}}):
                runtime.records['same:2'] = {**runtime.records['same:1'],
                                             'version': 2, 'model': 'changed-' + marker}
                runtime.records['state']['heads']['same'] = 2
                result = value.ai_detection_settings()
                self.assertEqual((result['model'], result['api_key']),
                                 ('model-' + marker, 'synthetic-' + marker))
            self.assertIsNone(value.service.current_snapshot())
            self.assertEqual(value.ai_detection_settings()['model'], 'changed-' + marker)
            label.assert_not_called()
            poison.assert_not_called()

    def test_complete_provider_domain_construction_is_inert_and_independent(self):
        ports, poison = provider_inputs()
        first = ProviderConfiguration(**ports)
        second = ProviderConfiguration(**ports)
        for name in ('defaults', 'validation', 'public_urls', 'identity', 'secrets',
                     'keys', 'proxy', 'local', 'legacy_json', 'legacy_image',
                     'agent_policy', 'legacy_agent'):
            self.assertIsNot(getattr(first, name), getattr(second, name))
        poison.assert_not_called()

    def test_owned_key_registry_resolves_each_supplied_environment(self):
        for marker in ('A', 'B'):
            ports, poison = provider_inputs()
            environment = {'SHARED_KEY': 'synthetic-' + marker}
            ports['secret_environment'] = replace(ports['secret_environment'], values=lambda environment=environment: environment)
            ports['secret_policy'] = replace(ports['secret_policy'], fullmatch=lambda: re.fullmatch)
            ports['json_key_policy'] = replace(ports['json_key_policy'],
                default_provider=lambda: 'qwen', supported=lambda: {'qwen'})
            ports['json_defaults'] = replace(ports['json_defaults'], labels=lambda: {'qwen': 'Qwen'})
            ports['key_presentation'] = replace(ports['key_presentation'],
                text=lambda: lambda value, limit: str(value)[:limit])
            ports['key_identity_runtime'] = replace(ports['key_identity_runtime'],
                sha256=lambda: hashlib.sha256, time_ns=lambda: time.time_ns,
                substitute=lambda: re.sub, fullmatch=lambda: re.fullmatch)
            value = ProviderConfiguration(**ports)
            result = value.normalize_ai_key_items({'api_keys': [
                {'id': 'same', 'provider': 'qwen', 'env': 'SHARED_KEY'}]}, 'qwen')
            self.assertEqual(result[0]['key'], 'synthetic-' + marker)
            self.assertEqual(value.local_secret_env_value('SHARED_KEY'), 'synthetic-' + marker)
            self.assertEqual(environment, {'SHARED_KEY': 'synthetic-' + marker})
            poison.assert_not_called()

    def test_configured_models_and_secrets_are_local_with_identical_references(self):
        first, runtime_a, reads_a = configured_owner('A')
        second, runtime_b, reads_b = configured_owner('B')
        self.assertEqual(runtime_a.events, [])
        self.assertEqual(runtime_b.events, [])
        snapshot = {'pipeline': {'id': 'same', 'version': 1}}
        with first.service.scope(snapshot), second.service.scope(snapshot):
            a = first.ai_detection_settings()
            b = second.ai_detection_settings()
            self.assertEqual((a['model'], a['api_key']), ('model-A', 'synthetic-A'))
            self.assertEqual((b['model'], b['api_key']), ('model-B', 'synthetic-B'))
            runtime_a.fail_reads = True
            with self.assertRaisesRegex(RuntimeError, 'repository failure'):
                first.ai_detection_settings()
            self.assertEqual(second.ai_detection_settings()['model'], 'model-B')
        self.assertIsNone(first.service.current_snapshot())
        self.assertIsNone(second.service.current_snapshot())
        self.assertEqual(reads_a, ['SAME_REF'])
        self.assertEqual(reads_b, ['SAME_REF', 'SAME_REF'])
        self.assertIn(('rollback',), runtime_a.events)
        self.assertEqual(runtime_a.events[-1], ('close',))

    def test_successful_http_uses_each_actual_repository_without_secret_disclosure(self):
        for marker in ('A', 'B'):
            value, _, reads = configured_owner(marker)
            app = FastAPI()
            other = Mock(side_effect=AssertionError('unexpected provider call'))
            value.register(app, ProfileApiDependencies(lambda: {'id': 'synthetic-admin'},
                                                       other, other, other, other))
            client = TestClient(app)
            try:
                response = client.get('/api/admin/model-profiles')
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()['profiles'][0]['model'], 'model-' + marker)
                self.assertNotIn('secret_ref', response.text)
                self.assertNotIn('synthetic-', response.text)
                self.assertEqual(reads, [])
            finally:
                client.close()

    def test_legacy_label_capability_is_explicit_and_preserves_callback_order(self):
        for marker in ('A', 'B'):
            events = []
            def read(name, result):
                return lambda *args: events.append(name) or dict(result)
            def keys(name):
                return lambda *args: events.append(name) or []
            config = LegacyConfiguration(
                ai=read('ai', {'provider': 'qwen', 'api_key': ''}),
                image=read('image', {'provider': 'qwen_image'}),
                agent=read('agent', {}), local=read('local', {}),
                ai_keys=keys('ai_keys'), image_keys=keys('image_keys'),
                agent_keys=keys('agent_keys'), label=read('label', {'key': 'synthetic-' + marker}))
            with patch('local_inspection_service.label_inspection.model.legacy_settings',
                       side_effect=AssertionError('implicit global label configuration')):
                result = sources(config)
            self.assertEqual(events, ['ai', 'image', 'agent', 'local', 'ai_keys',
                                      'image_keys', 'agent_keys', 'label'])
            self.assertEqual(result[3][1]['api_key'], 'synthetic-' + marker)
            self.assertEqual(result[3][2], ['label'])

    def test_inert_construction_has_distinct_actual_services_and_scopes(self):
        first, poison_a = owner()
        second, poison_b = owner()
        self.assertIsNot(first.service, second.service)
        self.assertIsNot(first.service._scope, second.service._scope)
        self.assertIs(first.resolve_model_profiles(), first.service)
        poison_a.assert_not_called()
        poison_b.assert_not_called()

    def test_two_interleaved_scopes_keep_settings_and_failures_local(self):
        first, poison_a = owner()
        second, poison_b = owner()
        with first.service.scope({'marker': 'A'}):
            with second.service.scope({'marker': 'B'}):
                self.assertEqual(first.service.current_snapshot(), {'marker': 'A'})
                self.assertEqual(second.service.current_snapshot(), {'marker': 'B'})
                self.assertEqual(first.ai_detection_settings()['profile_purpose'], 'pipeline')
                self.assertEqual(second.image_generation_settings()['profile_purpose'], 'image')
                with self.assertRaisesRegex(RuntimeError, 'synthetic'):
                    with first.service.scope({'marker': 'nested'}):
                        raise RuntimeError('synthetic')
                self.assertEqual(first.service.current_snapshot(), {'marker': 'A'})
                self.assertEqual(second.service.current_snapshot(), {'marker': 'B'})
        self.assertIsNone(first.service.current_snapshot())
        self.assertIsNone(second.service.current_snapshot())
        poison_a.assert_not_called()
        poison_b.assert_not_called()

    def test_scope_context_does_not_leak_across_execution_threads(self):
        first, _ = owner()
        second, _ = owner()
        def scoped(value, marker):
            with value.service.scope({'marker': marker}):
                selected = value.service.current_snapshot()
                result = value.ai_detection_settings('document')
            self.assertIsNone(value.service.current_snapshot())
            return selected, result['profile_purpose']
        with ThreadPoolExecutor(max_workers=2) as pool:
            a = pool.submit(scoped, first, 'A')
            b = pool.submit(scoped, second, 'B')
            self.assertEqual(a.result(), ({'marker': 'A'}, 'document'))
            self.assertEqual(b.result(), ({'marker': 'B'}, 'document'))

    def test_agent_projection_resolves_before_defaults_and_preserves_merge(self):
        events = []
        value, poison = owner(lambda: events.append('defaults') or {'model': 'legacy', 'extra': 'kept', 'enabled': True})
        original = value.service.resolve
        def resolve(purpose):
            events.append(purpose)
            return original(purpose)
        with value.service.scope({}), patch.object(value.service, 'resolve', resolve):
            result = value.load_agent_config()
        self.assertEqual(events, ['training_assistant', 'defaults'])
        self.assertEqual(result['model'], '')
        self.assertEqual(result['extra'], 'kept')
        self.assertFalse(result['enabled'])
        poison.assert_not_called()

    def test_missing_resolver_explicitly_fails_every_settings_boundary(self):
        value, poison = owner()
        value.service = None
        for method in (value.resolve_model_profiles, value.ai_detection_settings,
                       value.image_generation_settings, value.load_agent_config):
            with self.subTest(method=method.__name__), self.assertRaisesRegex(RuntimeError, 'not configured'):
                method()
        poison.assert_not_called()

    def test_two_http_registrars_keep_admin_gate_and_routes_local(self):
        applications = []
        events = []
        for marker, status in (('A', 401), ('B', 403)):
            value, poison = owner()
            def denied(marker=marker, status=status):
                events.append(marker)
                raise HTTPException(status, 'Synthetic admin gate')
            other = Mock(side_effect=AssertionError('denied request reached profile capability'))
            app = FastAPI()
            value.register(app, ProfileApiDependencies(denied, other, other, other, other))
            applications.append((app, status, poison))
        self.assertEqual([(r.path, r.methods) for r in applications[0][0].routes],
                         [(r.path, r.methods) for r in applications[1][0].routes])
        for app, status, poison in applications:
            client = TestClient(app)
            try:
                response = client.get('/api/admin/model-profiles')
                self.assertEqual(response.status_code, status)
                self.assertEqual(response.json(), {'detail': 'Synthetic admin gate'})
            finally:
                client.close()
            poison.assert_not_called()
        self.assertEqual(events, ['A', 'B'])


if __name__ == '__main__':
    unittest.main()
