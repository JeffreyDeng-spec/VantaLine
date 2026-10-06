"""Isolated PostgreSQL, independent OS process and pinned model-resolution checks."""
from dataclasses import replace
import json
import multiprocessing
import os
from pathlib import Path
import signal
import sys
import tempfile
import time
from types import SimpleNamespace
from unittest.mock import patch
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local_inspection_service.storage.artifacts.runtime import get_runtime
from release_runtime_client import request
from release_runtime_contract import WEB, LABEL
from local_inspection_service.runtime.configuration import ConfigurationSnapshot
from local_inspection_service.runtime.connections import ThreadRepositoryFactory
from local_inspection_service.runtime.label_identity import LabelRuntimeIdentity, RuntimeUnavailable
from local_inspection_service.label_inspection.runtime import LabelProcess
from local_inspection_service.label_inspection.runtime_models import create_models
from local_inspection_service.label_inspection.runtime_control import LabelRuntimeControl
from local_inspection_service.label_inspection.dependencies import RepositoryLifecycle
from local_inspection_service.label_inspection import worker_api
from local_inspection_service.model_profiles.repository import Repository
from local_inspection_service.model_profiles.service import Service
from local_inspection_service.model_profiles.dependencies import ProfileDependencies
from local_inspection_service.storage.postgres_runtime_repository import PostgresRuntimeRepository
from local_inspection_service.storage.postgres_schema import postgres_ddl
from local_inspection_service.storage.runtime_selector import default_postgres_connector


def repositories(dsn, schema):
    factory = ThreadRepositoryFactory(lambda: SimpleNamespace(repository=PostgresRuntimeRepository(
        default_postgres_connector(dsn), '<synthetic>', schema_name=schema)), lambda: schema)
    return RepositoryLifecycle(lambda: factory.selection().repository, factory.clear)


def child(dsn, schema, root, configuration, identity):
    root = Path(root)
    process = LabelProcess(identity, configuration, root, repositories(dsn, schema), repositories(dsn, schema),
                           control_directory=root/'control', allowed_uid=os.getuid(), runtime_provider=get_runtime)
    signal.signal(signal.SIGTERM, process.request_stop)
    signal.signal(signal.SIGINT, process.request_stop)
    process.run()


def main():
    assert 'local_inspection_service.server' not in sys.modules
    dsn = os.environ['VANTALINE_POSTGRES_DSN']
    schema = 'label_process_' + uuid.uuid4().hex[:12]
    setup = default_postgres_connector(dsn)
    connections = repositories(dsn, schema)
    process = web = None
    try:
        with setup.cursor() as cursor: cursor.execute(postgres_ddl(schema))
        setup.commit()
        with tempfile.TemporaryDirectory(prefix='label-process-') as temporary:
            root = Path(temporary)
            models = create_models(connections, root, {})
            try: models.initialize()
            except RuntimeUnavailable: pass
            else: raise AssertionError('worker initialized a missing registry')
            repo = Repository(connections.repository())
            with repo.read_tx() as cursor:
                assert repo.state(cursor) is None
            values = {}
            def write(key, value):
                values[key] = value
                (root/'runtime_secrets.local.env').write_text(''.join(k+'='+json.dumps(v)+'\n' for k,v in values.items()))
            service = Service(ProfileDependencies(connections.repository, write, lambda k: values.get(k,''),
                lambda: [], lambda v: None, lambda v: None, lambda v: 'masked'))
            service.initialize()
            first = service.save_profile(dict(name='synthetic',provider='doubao',model='doubao-seed-synthetic',
                base_url='https://synthetic.invalid/v1',api_key='synthetic-first'), 'fixture')
            service.save_bindings(2, {'label':first['id']}, 'fixture')
            snapshot = service.snapshot()['label']
            service.save_profile(dict(id=first['id'],version=1,name='synthetic',provider='doubao',model='doubao-seed-synthetic-new',
                base_url='https://synthetic.invalid/v1',api_key='synthetic-second'), 'fixture', first['id'])
            for reader in (models, create_models(connections, root, {})):
                reader.initialize()
                assert reader.resolve('label', snapshot)['api_key'] == 'synthetic-first'
                assert reader.resolve('label', snapshot)['profile_version'] == 1
                assert reader.snapshot()['label']['version'] == 2
                assert reader.snapshot_for_record({'created_at':1})['label'] is None
            configuration = ConfigurationSnapshot.capture({'VANTALINE_DATA_STORE':'postgres', 'DATABASE_URL':'fixture'}, root)
            identity = LabelRuntimeIdentity('a'*40, 'v2026.10.1', 'external', configuration.revision)
            web = LabelRuntimeControl(identity, repositories(dsn,schema), None, directory=root/'control',
                allowed_uid=os.getuid(), configuration=configuration)
            web.start()
            assert web.command({'schema':1,'command':'status','revision':'b'*32})['state'] == 'ready'
            process = multiprocessing.get_context('spawn').Process(target=child,
                args=(dsn,schema,str(root),configuration,identity))
            process.start()
            deadline = time.monotonic()+10
            while True:
                try:
                    state = request(LABEL,'status','b'*32,uid=os.getuid(),pid=process.pid,directory=root/'control')
                    break
                except Exception:
                    assert process.is_alive() and time.monotonic() < deadline
                    time.sleep(.05)
            assert state['state']=='drained' and state['pid']==process.pid and state['pid']!=os.getpid()
            assert state['git_commit']==identity.commit and state['config_revision']==configuration.revision
            resumed=request(LABEL,'resume','b'*32,uid=os.getuid(),pid=process.pid,directory=root/'control')
            assert resumed['state']=='ready'
            duplicate = LabelProcess(identity, configuration, root, repositories(dsn,schema), repositories(dsn,schema),
                control_directory=root/'control',allowed_uid=os.getuid(), runtime_provider=get_runtime)
            try: duplicate.start()
            except RuntimeUnavailable: pass
            else: raise AssertionError('duplicate consumer role was accepted')
            finally: duplicate.close()
            os.kill(process.pid, signal.SIGTERM)
            process.join(5)
            assert process.exitcode == 0, 'worker did not finish signal drain'
            assert not (root/'control/label-control.sock').exists()
            web.close(); web=None
            from fastapi import FastAPI
            app=FastAPI()
            factory=SimpleNamespace(selection=lambda:SimpleNamespace(repository=connections.repository()),clear=connections.clear)
            def identity_from_config(*args, **kwargs):
                return replace(identity, config_revision=kwargs['configuration_revision']())
            def build_control(build, lifecycle, worker, **options):
                assert worker is None
                return LabelRuntimeControl(build,lifecycle,None,directory=root/'control',allowed_uid=os.getuid(),**options)
            with patch.object(worker_api,'read_identity',side_effect=identity_from_config), \
                    patch.object(worker_api.ConfigurationSnapshot,'capture',return_value=configuration), \
                    patch.object(worker_api,'create_control_factory',return_value=factory), \
                    patch.object(worker_api,'LabelWorker',side_effect=AssertionError('Web constructed external consumer')), \
                    patch.object(worker_api,'LabelRuntimeControl',side_effect=build_control):
                directory=lambda:root
                provider=lambda:models
                handle=worker_api.register(app,connections,directory,provider, runtime_provider=get_runtime)
                assert worker_api.register(app,connections,directory,provider, runtime_provider=get_runtime) is handle
                for hook in app.router.on_startup: hook()
                assert handle.runtime_control.worker is None
                for hook in app.router.on_shutdown: hook()
            assert 'local_inspection_service.server' not in sys.modules
            print('label process: missing registry, pinned profiles/restart, real child PID, duplicate role, SIGTERM drain and Web without consumer passed')
    finally:
        if process is not None and process.is_alive():
            process.terminate(); process.join(5)
        if web is not None: web.close()
        connections.clear()
        with setup.cursor() as cursor: cursor.execute(f'DROP SCHEMA "{schema}" CASCADE')
        setup.commit(); setup.close()


if __name__=='__main__': main()
