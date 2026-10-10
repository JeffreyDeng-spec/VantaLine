"""Actual independent infrastructure graphs; synthetic IO, no model or cloud calls."""
import asyncio
from dataclasses import replace
import json
import os
from pathlib import Path
from types import SimpleNamespace
import re
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from canonical_application_source_contract import read_checked_application_source
from smoke_application_foundation import inputs as foundation_inputs
from smoke_repository_composition import Connection
from smoke_model_configuration_composition import provider_inputs
from local_inspection_service.runtime.infrastructure import (
    ConfigurationRowCodecs, InfrastructureInputs, build_infrastructure)
from local_inspection_service.runtime.path_configuration_composition import PathConfigurationLocations
from local_inspection_service.runtime.service_path_ports import ServicePathSettings, PathProjectionPolicy
from local_inspection_service.model_providers.configuration_inputs import ProviderConfigurationInputs


class InfrastructureContracts(unittest.TestCase):
    def inputs(self, marker):
        temporary = tempfile.TemporaryDirectory(prefix='vl-infrastructure-')
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        data = root/'data'
        foundation = foundation_inputs(marker)
        foundation.environment.update(VANTALINE_DATA_STORE='json')
        foundation = replace(foundation, data_directory=data, auth_path=data/'auth.json')
        ports, poison = provider_inputs()
        ports['secret_paths'] = replace(ports['secret_paths'], directory=lambda: data, file=lambda: data/'secrets.env')
        ports['secret_environment'] = replace(ports['secret_environment'], values=lambda: foundation.environment)
        ports['secret_policy'] = replace(ports['secret_policy'], fullmatch=lambda: re.fullmatch)
        ports['secret_codec'] = replace(ports['secret_codec'], loads=lambda: json.loads,
            dumps=lambda: json.dumps, decode_error=lambda: json.JSONDecodeError)
        ports['secret_file_operations'] = replace(ports['secret_file_operations'], chmod=lambda: os.chmod, replace=lambda: os.replace)
        ports['validation_capabilities'] = replace(ports['validation_capabilities'], fullmatch=lambda: re.fullmatch)
        ports['proxy_transports'] = replace(ports['proxy_transports'], os=lambda: SimpleNamespace(environ=foundation.environment))
        ports['legacy_settings_i_o'] = replace(ports['legacy_settings_i_o'], environment=lambda: foundation.environment)
        value = InfrastructureInputs(
            foundation=foundation, cv2=poison, pil=poison,
            locations=PathConfigurationLocations(lambda: (data, root/'outputs'),
                lambda: data/'config.json', lambda: data/'backup.json', lambda: data, lambda: (data,)),
            paths=ServicePathSettings(lambda: root, lambda: root/'app', lambda: root/'outputs'),
            path_policy=PathProjectionPolicy(lambda: ('/old/vantaline',), lambda: set(), lambda: 'legacy', lambda: 'system'),
            rows=ConfigurationRowCodecs(poison, poison, poison),
            defaults=lambda: {'accessories': [], 'marker': marker}, protected_keys=lambda: ('plc',),
            provider=ProviderConfigurationInputs(**ports), legacy_label=poison, agent_defaults=poison,
            cache_ttl=lambda: 5.0, clock=lambda: 100.0, artifact_builder=poison)
        return value, root, poison

    def test_inert_fresh_owners_and_late_failure_publish_no_resources(self):
        value, root, poison = self.inputs('inert')
        inert_ports, _ = provider_inputs()
        from dataclasses import fields
        class InertEnvironment(dict):
            def get(self, *args):
                raise AssertionError('construction read environment')
        inert = replace(value,
            foundation=replace(value.foundation, environment=InertEnvironment(), connector=poison,
                authentication=type(value.foundation.authentication)(**{
                    field.name: poison for field in fields(value.foundation.authentication)})),
            locations=PathConfigurationLocations(*([poison]*5)), paths=ServicePathSettings(*([poison]*3)),
            path_policy=PathProjectionPolicy(*([poison]*4)), provider=ProviderConfigurationInputs(**inert_ports),
            defaults=poison, protected_keys=poison, cache_ttl=poison, clock=poison)
        with patch.object(Path, 'mkdir', poison), patch.object(threading.Thread, 'start', poison):
            a, b = build_infrastructure(inert), build_infrastructure(inert)
            error = RuntimeError('synthetic late construction failure')
            with patch('local_inspection_service.model_profiles.composition.ModelConfiguration', side_effect=error):
                with self.assertRaises(RuntimeError) as caught:
                    build_infrastructure(inert)
            self.assertIs(caught.exception, error)
        poison.assert_not_called()
        self.assertFalse((root/'data').exists())
        for name in ('foundation', 'artifacts', 'paths', 'provider', 'models', 'caches'):
            self.assertIsNot(getattr(a, name), getattr(b, name))
        self.assertIsNot(a.foundation.authentication.identity, b.foundation.authentication.identity)
        self.assertIsNot(a.models.service._scope, b.models.service._scope)

    def test_identical_media_and_json_names_use_selected_actual_artifact_store(self):
        from smoke_detection_artifact_ports import DetectionArtifactPortsTests
        from smoke_artifact_runtime_provider import configuration
        DetectionArtifactPortsTests.setUp(self)
        graphs=[]
        for index in range(2):
            value, _, _ = self.inputs(str(index))
            value.foundation.environment.update(configuration())
            graphs.append(build_infrastructure(replace(value,
                artifact_builder=Mock(return_value=self.runtimes[index]))))
        path=self.root/'outputs/same.json'
        for index, graph in enumerate(graphs):
            graph.artifacts.files.write_text(path,json.dumps({'owner':index}),encoding='utf-8')
        self.assertFalse(path.exists())
        self.assertEqual([graph.caches.json.load(path) for graph in graphs],[{'owner':0},{'owner':1}])
        graphs[0].artifacts.files.unlink(path)
        self.assertIsNone(graphs[0].caches.json.load(path))
        self.assertEqual(graphs[1].caches.json.load(path),{'owner':1})

    def test_owned_capabilities_configuration_identity_and_caches(self):
        ia, ra, _ = self.inputs('a'); ib, rb, _ = self.inputs('b')
        a, b = build_infrastructure(ia), build_infrastructure(ib)
        for graph in (a, b):
            self.assertIs(graph.paths.paths.identity._request_user(), graph.foundation.authentication.identity)
            self.assertIs(graph.paths.configuration.store.rows.runtime_postgres_repository_or_none().__self__, graph.foundation.repositories.access)
            self.assertIs(graph.provider.local.files._business_files(), graph.artifacts.files)
            self.assertIs(graph.provider.local.files.ensure_dirs().__self__, graph.paths)
            self.assertIs(graph.caches.json.files(), graph.artifacts.files)
        self.assertEqual(a.paths.configuration.load_config()['marker'], 'a')
        self.assertFalse((rb/'data').exists()); self.assertFalse(b.paths.migration.done)
        a.paths.save_config({'marker': 'changed-a', 'accessories': []})
        self.assertEqual(b.paths.configuration.load_config()['marker'], 'b')
        for graph, root, name in ((a, ra, 'alice'), (b, rb, 'bob')):
            with graph.foundation.authentication.identity.bind({'id': name, 'role': 'user'}):
                self.assertEqual(graph.paths.paths.output_write_dir('preview'), root/'outputs/users'/name/'preview')
        with a.caches.request.scope():
            a.caches.request.current.get()['same'] = 'a'
            with b.caches.request.scope():
                self.assertEqual(b.caches.request.current.get(), {})
                b.caches.request.current.get()['same'] = 'b'
                self.assertEqual(a.caches.request.current.get()['same'], 'a')
        self.assertIsNone(a.caches.request.current.get()); self.assertIsNone(b.caches.request.current.get())
        a.caches.store.put('same', 'a'); b.caches.store.put('same', 'b')
        a.caches.store.invalidate('same')
        self.assertEqual(a.caches.store.get('same'), (False, None))
        self.assertEqual(b.caches.store.get('same'), (True, 'b'))
        path_a=ra/'data/cache.json'; path_b=rb/'data/cache.json'
        a.artifacts.files.write_text(path_a, '{"marker":"a"}', encoding='utf-8')
        b.artifacts.files.write_text(path_b, '{"marker":"b"}', encoding='utf-8')
        self.assertEqual(a.caches.json.load(path_a), {'marker':'a'})
        self.assertEqual(b.caches.json.load(path_b), {'marker':'b'})

    def test_real_secret_store_and_profile_snapshot_scope_are_owned(self):
        ia, _, _ = self.inputs('a'); ib, _, _ = self.inputs('b')
        a, b = build_infrastructure(ia), build_infrastructure(ib)
        a.models.service.dependencies.write_secret('SAME_REF', 'synthetic-a')
        b.models.service.dependencies.write_secret('SAME_REF', 'synthetic-b')
        self.assertEqual(a.models.service.dependencies.read_secret('SAME_REF'), 'synthetic-a')
        self.assertEqual(b.models.service.dependencies.read_secret('SAME_REF'), 'synthetic-b')
        self.assertEqual(ia.foundation.environment['SAME_REF'], 'synthetic-a')
        self.assertEqual(ib.foundation.environment['SAME_REF'], 'synthetic-b')
        ia.foundation.environment['FLAG']='true'; ib.foundation.environment['FLAG']='false'
        self.assertTrue(a.provider.env_flag_enabled('FLAG'))
        self.assertFalse(b.provider.env_flag_enabled('FLAG'))
        self.assertIs(a.provider.legacy_json._io.environment(),ia.foundation.environment)
        self.assertIs(b.provider.legacy_json._io.environment(),ib.foundation.environment)
        with a.models.service.scope({'marker':'a'}):
            with b.models.service.scope({'marker':'b'}):
                self.assertEqual(a.models.service.current_snapshot(), {'marker':'a'})
                self.assertEqual(b.models.service.current_snapshot(), {'marker':'b'})
        self.assertIsNone(a.models.service.current_snapshot()); self.assertIsNone(b.models.service.current_snapshot())

    def test_path_and_model_repository_access_select_the_same_current_owner(self):
        from local_inspection_service.runtime.repository_composition import RuntimeRepositories
        value, _, _ = self.inputs('selection')
        graph=build_infrastructure(value)
        a=Mock(return_value='a'); b=Mock(return_value='b')
        original=graph.foundation.repositories.access
        original.runtime_postgres_repository_or_none=a
        self.assertEqual(graph.models.service.dependencies.runtime_repository(),'a')
        replacement=RuntimeRepositories({}).access
        replacement.runtime_postgres_repository_or_none=b
        graph.foundation.repositories.access=replacement
        self.assertEqual(graph.paths.configuration.store.rows.runtime_postgres_repository_or_none()(),'b')
        self.assertEqual(graph.models.service.dependencies.runtime_repository(),'b')
        a.assert_called_once(); self.assertEqual(b.call_count,2)

    def test_explicit_preallocated_artifact_is_preserved_without_selection(self):
        from local_inspection_service.storage.artifacts.composition import create_artifact_composition
        value, _, poison = self.inputs('preallocated')
        artifact=create_artifact_composition(poison,poison,poison,builder=poison)
        graph=build_infrastructure(value,artifacts=artifact)
        self.assertIs(graph.artifacts,artifact)
        self.assertIs(graph.provider.local.files._business_files(),artifact.files)
        self.assertIs(graph.caches.json.files(),artifact.files)
        poison.assert_not_called()

    def test_actual_default_entry_uses_the_same_complete_infrastructure(self):
        from scripts.verify_backend_contract import capture
        capture()
        from local_inspection_service import server
        graph=server._infrastructure
        for name, owner in (
            ('_foundation',graph.foundation), ('_artifact_composition',graph.artifacts),
            ('_path_configuration',graph.paths), ('_provider_configuration',graph.provider),
            ('_model_profile_configuration',graph.models), ('_request_read_cache',graph.caches.request),
            ('_store_cache',graph.caches.store), ('_json_cache',graph.caches.json)):
            self.assertIs(getattr(server,name),owner)
        self.assertIs(server.ensure_dirs.__self__,graph.paths.directories)
        self.assertIs(server.migrate_persisted_local_paths_once.__self__,graph.paths.migration)
        self.assertIs(server.model_profile_service,graph.models.service)

    def test_actual_default_source_is_current_and_all_callable_nodes_are_preserved(self):
        import ast
        import application_integration_source_contract as contract
        source=read_checked_application_source(contract.ROOT / 'local_inspection_service/server.py')
        current=ast.parse(contract.restore_training_persistence_graph_root(source))
        self.assertEqual(contract.digest(current),contract.INFRASTRUCTURE['integrated_ast_sha256'])
        parent=ast.parse(contract.restore_infrastructure_root(source))
        functions=lambda tree:[(node.name,contract.canonical(node)) for node in tree.body
            if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef))]
        self.assertEqual(functions(current),functions(parent))
        self.assertEqual(len(functions(current)),983)

    def test_async_to_native_thread_identity_rebuild_and_exception_release(self):
        values = [self.inputs(name)[0] for name in ('a', 'b')]
        connections=[]
        def connect(_):
            connection=Connection(); connections.append(connection); return connection
        graphs=[]
        for value in values:
            value.foundation.environment['VANTALINE_DATA_STORE']='postgres'
            graphs.append(build_infrastructure(replace(value, foundation=replace(value.foundation, connector=connect))))
        barrier=threading.Barrier(2)
        def run(graph, name, fail):
            with graph.foundation.repositories.factory.thread_scope():
                first=graph.models.service.dependencies.runtime_repository().connection
                barrier.wait(3)
                first.close()
                rebuilt=graph.models.service.dependencies.runtime_repository().connection
                self.assertIsNot(first, rebuilt)
                self.assertEqual(graph.foundation.records.access.current_owner_fields()['owner_user_id'],name)
                if fail: raise RuntimeError('synthetic thread failure')
                return rebuilt
        async def execute():
            async def selected(graph,name,fail):
                with graph.foundation.authentication.identity.bind({'id':name,'role':'user'}):
                    return await asyncio.to_thread(run,graph,name,fail)
            results=await asyncio.gather(selected(graphs[0],'a',False), selected(graphs[1],'b',True), return_exceptions=True)
            self.assertTrue(results[0].closed)
            self.assertIsInstance(results[1],RuntimeError)
        asyncio.run(execute())
        self.assertEqual(len(connections),4)
        self.assertTrue(all(connection.closed for connection in connections))
        self.assertTrue(all(graph.foundation.authentication.identity.get() is None for graph in graphs))


if __name__ == '__main__': unittest.main()
