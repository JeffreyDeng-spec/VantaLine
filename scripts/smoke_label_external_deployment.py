"""Actual controller and separate consumer process against an isolated PostgreSQL schema."""
import json
import multiprocessing
import os
from pathlib import Path
import signal
import sys
import tempfile
import time
import uuid

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from local_inspection_service.storage.artifacts.runtime import get_runtime
from release_runtime_configuration import ConfigurationFiles
from release_runtime_contract import ContractError, WEB, LABEL
from smoke_label_runtime_deployment import RuntimeHarness
from smoke_label_process import repositories
from local_inspection_service.runtime.configuration import ConfigurationSnapshot
from local_inspection_service.runtime.label_identity import read_identity
from local_inspection_service.label_inspection.runtime import LabelProcess
from local_inspection_service.label_inspection.runtime_control import LabelRuntimeControl
from local_inspection_service.label_inspection.worker import LabelWorker
from local_inspection_service.model_profiles.repository import Repository
from local_inspection_service.storage.postgres_schema import postgres_ddl
from local_inspection_service.storage.runtime_selector import default_postgres_connector


def consumer(dsn, schema, root):
    root=Path(root)
    snapshot=ConfigurationSnapshot.read_worker(root/'configuration/current/config.json',
        credentials_directory=None,owner=os.getuid())
    directory=snapshot.apply_worker_environment(os.environ)
    identity=read_identity((root/'current').resolve(),current=root/'current',configuration_revision=lambda:snapshot.revision)
    process=LabelProcess(identity,snapshot,directory,repositories(dsn,schema),repositories(dsn,schema),
        control_directory=root/'control',allowed_uid=os.getuid(), runtime_provider=get_runtime)
    signal.signal(signal.SIGTERM,process.request_stop)
    signal.signal(signal.SIGINT,process.request_stop)
    process.run()


class ExternalHarness(RuntimeHarness):
    def __init__(self,root,dsn,schema):
        self.snapshot=ConfigurationSnapshot.capture({'VANTALINE_DATA_STORE':'postgres','DATABASE_URL':dsn},root)
        self.dsn,self.schema=dsn,schema
        self.child=None
        self.fail_worker=False
        super().__init__(root,repositories(dsn,schema))
        manifest=json.loads((self.new/'RUNTIME_TOPOLOGY.json').read_text())
        manifest.update(worker_mode='external',services=[WEB,LABEL])
        (self.new/'RUNTIME_TOPOLOGY.json').write_text(json.dumps(manifest))
        self.transition.configuration_files=ConfigurationFiles(root/'configuration',uid=os.getuid(),gid=os.getgid())

    def property(self,service,name,**options):
        if service==LABEL:
            live=self.child is not None and self.child.is_alive()
            if name=='MainPID': return str(self.child.pid) if live else '0'
            if name=='ActiveState': return 'active' if live else 'inactive'
            if name=='LoadState': return 'loaded'
        return super().property(service,name,**options)

    def run(self,command,*services,**options):
        self.events.append((command,*services))
        if command=='disable': return
        assert command=='start'
        if services==(LABEL,):
            if self.fail_worker: raise ContractError('Synthetic worker startup rejection')
            if self.child is None or not self.child.is_alive():
                self.child=multiprocessing.get_context('spawn').Process(target=consumer,args=(self.dsn,self.schema,str(self.root)))
                self.child.start()
            return
        assert services==(WEB,)
        if self.control is not None: return
        identity=read_identity(self.current.resolve(),current=self.current,configuration_revision=lambda:self.snapshot.revision)
        self.worker=LabelWorker(self.repositories,lambda:self.root,lambda:None, runtime_provider=get_runtime) if identity.mode=='embedded' else None
        if self.worker is not None: self.worker._iteration=lambda:False
        self.control=LabelRuntimeControl(identity,self.repositories,self.worker,directory=self.directory,
            allowed_uid=os.getuid(),configuration=self.snapshot)
        self.control.start()

    def install(self,topology,**options):
        self.events.append(('install',topology.mode))
        assert options['configuration']==self.snapshot.export()['configuration']

    def stop_all(self,services,*,deadline):
        self.events.append(('stop',*services))
        if LABEL in services and self.child is not None:
            if self.child.is_alive(): os.kill(self.child.pid,signal.SIGTERM)
            self.child.join(max(0,deadline-time.monotonic()))
            assert not self.child.is_alive() and self.child.exitcode==0
            self.child=None
        if WEB in services: super().close()

    def close(self):
        self.stop_all((WEB,LABEL),deadline=time.monotonic()+5)


def main():
    dsn=os.environ['VANTALINE_POSTGRES_DSN']
    schema='label_external_'+uuid.uuid4().hex[:12]
    setup=default_postgres_connector(dsn)
    lifecycle=repositories(dsn,schema)
    harness=None
    try:
        with setup.cursor() as cursor: cursor.execute(postgres_ddl(schema))
        setup.commit()
        repo=Repository(lifecycle.repository())
        with repo.transaction() as cursor:
            repo.put(cursor,'state','state',dict(revision=1,heads={},bindings={'label':''},migrated_at=1,initial_snapshot={'label':None}))
        lifecycle.clear()
        for case in ('accept','rollback','worker_failure'):
            # Each case has a distinct synthetic data directory/config revision.
            # Reset only this disposable schema control record between cases.
            with setup.cursor() as cursor:
                cursor.execute(f'DELETE FROM "{schema}".label_runtime_state')
            setup.commit()
            with tempfile.TemporaryDirectory(prefix='label-external-') as temporary:
                harness=ExternalHarness(Path(temporary),dsn,schema)
                transition=harness.transition
                transition.begin(harness.old,harness.new)
                assert harness.control is None and harness.worker is None and harness.child is None
                harness.switch()
                harness.fail_worker=case=='worker_failure'
                if harness.fail_worker:
                    try: transition.start()
                    except ContractError: pass
                    else: raise AssertionError('missing worker accepted')
                else:
                    transition.start()
                    assert harness.worker is None and harness.child.is_alive()
                    states=[transition.state(transition.data['new'],role) for role in (WEB,LABEL)]
                    assert states[0].pid!=states[1].pid
                    assert all(s.config_revision==harness.snapshot.revision and s.maintenance for s in states)
                    assert states[1].state=='drained'
                if case=='accept':
                    transition.accept()
                    assert transition.state(transition.data['new'],LABEL).state=='ready'
                    assert not transition.state(transition.data['new'],WEB).maintenance
                else:
                    transition.rollback(harness.current)
                    assert harness.child is None and harness.worker is not None
                    assert harness.current.resolve()==harness.old
                    assert not transition.state(transition.data['old'],WEB).maintenance
                    assert transition.configurations().capture_pointer() is None
                harness.close(); harness=None
        assert 'local_inspection_service.server' not in sys.modules
        print('label external deployment: real separate process + PG + sockets + config publication, accept, rollback and startup failure passed')
    finally:
        if harness is not None: harness.close()
        lifecycle.clear()
        with setup.cursor() as cursor: cursor.execute(f'DROP SCHEMA "{schema}" CASCADE')
        setup.commit();setup.close()


if __name__=='__main__': main()
