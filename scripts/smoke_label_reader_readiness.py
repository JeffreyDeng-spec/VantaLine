"""Isolated PostgreSQL permissions, first-startup ordering and managed rollback."""
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import uuid
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import psycopg
from fastapi import FastAPI
from fastapi.testclient import TestClient
from smoke_label_summary_reads import Fixture, baseline_method
from local_inspection_service.label_inspection import worker_api
from local_inspection_service.label_inspection.dependencies import RepositoryLifecycle
from local_inspection_service.label_inspection.readiness import verify_summary_reads
from local_inspection_service.runtime.connections import ThreadRepositoryFactory
from local_inspection_service.runtime.label_identity import RuntimeUnavailable
from local_inspection_service.storage.postgres_runtime_repository import PostgresRuntimeRepository

SAFE_ERROR = "Label list database preflight failed"


def lifecycle(fixture, role, events):
    def create():
        # libpq effective role is deliberately different from the schema owner.
        connection = psycopg.connect(os.environ['VANTALINE_POSTGRES_DSN'], options=f'-c role={role}')
        events.append(('connect', connection))
        return SimpleNamespace(repository=PostgresRuntimeRepository(connection, '<synthetic>', fixture.schema))
    factory = ThreadRepositoryFactory(create, lambda: role)
    def clear():
        selected = getattr(factory._local, 'selection', None)
        if selected is not None:
            connection = selected.repository.connection
            events.append(('clear', int(connection.info.transaction_status)))
        factory.clear()
    return RepositoryLifecycle(lambda: factory.selection().repository, clear)


def expect_failure(call):
    try:
        call()
    except RuntimeUnavailable as error:
        assert str(error) == SAFE_ERROR and error.__suppress_context__
    else:
        raise AssertionError('unsafe reader became ready')


def app_fixture(repositories, events):
    app = FastAPI()
    app.on_event('startup')(lambda: events.append(('earlier_startup',)))
    control = SimpleNamespace(start=lambda: events.append(('control_ready',)),
                              close=lambda: events.append(('control_closed',)))
    identity = SimpleNamespace(mode='external')
    directory, models = lambda: Path('synthetic'), lambda: None
    with patch.object(worker_api, 'read_identity', return_value=identity), \
         patch.object(worker_api, 'create_control_factory', return_value=SimpleNamespace(clear=lambda: None)), \
         patch.object(worker_api, 'LabelRuntimeControl', return_value=control):
        first = worker_api.register(app, repositories, directory, models)
        assert worker_api.register(app, repositories, directory, models) is first
    assert [fn.__name__ for fn in app.router.on_startup] == ['verify_label_list_database', '<lambda>', 'start']
    @app.get('/ready')
    def ready():
        events.append(('http',))
        return {'ready': True}
    return app


def managed_rollback(fixture, repositories):
    # Real PG/controller/Unix sockets; candidate Web is the ASGI fixture above.
    # Systemd/units, candidate identity/control constructors and model work are substituted.
    from smoke_label_external_deployment import ExternalHarness
    from release_runtime_contract import WEB, LABEL
    class GuardedHarness(ExternalHarness):
        def run(self, command, *services, **options):
            if command == 'start' and services == (WEB,) and self.current.resolve() == self.new:
                self.events.append(('candidate_preflight',))
                with TestClient(app_fixture(repositories, self.events)):
                    raise AssertionError('restricted reader started')
            return super().run(command, *services, **options)
    with tempfile.TemporaryDirectory(prefix='reader-rollback-') as temporary:
        harness = GuardedHarness(Path(temporary), os.environ['VANTALINE_POSTGRES_DSN'], fixture.schema)
        try:
            transition = harness.transition
            transition.begin(harness.old, harness.new)
            harness.switch()
            expect_failure(transition.start)
            assert transition.data['phase'] == 'starting'
            assert harness.control is harness.child is None
            assert ('start', LABEL) not in harness.events
            assert ('earlier_startup',) not in harness.events and ('control_ready',) not in harness.events
            transition.rollback(harness.current)
            assert harness.current.resolve() == harness.old
            assert transition.data['phase'] == 'rolled_back'
            assert not transition.state(transition.data['old'], WEB).maintenance
            assert harness.child is None and harness.worker is not None
            assert transition.configurations().capture_pointer() is None
        finally:
            harness.close()


def main():
    role = 'reader_preflight_' + uuid.uuid4().hex[:12]
    with Fixture() as f:
        f.insert('label_inspection_objects', [f.task('task'), f.run('run')])
        admin = f.writer.connection
        admin.execute(f'CREATE ROLE "{role}" NOLOGIN')
        admin.execute(f'GRANT USAGE ON SCHEMA "{f.schema}" TO "{role}"')
        admin.execute(f'GRANT SELECT ON {f.table} TO "{role}"')
        admin.commit()
        events = []
        repositories = lifecycle(f, role, events)
        try:
            from local_inspection_service.storage.label_inspection import LabelRepository
            old = baseline_method()(LabelRepository(repositories.repository()), 'alice', ['task'])
            assert old['task'][0]['id'] == 'run'
            repositories.clear(); events.clear()
            app = app_fixture(repositories, events)
            def start_app():
                with TestClient(app):
                    raise AssertionError('restricted reader started')
            expect_failure(start_app)
            assert [e[0] for e in events] == ['connect', 'clear']
            assert events[1][1] == 0 and events[0][1].closed
            managed_rollback(f, repositories)
            # Column grants are sufficient: do not impose a table-level privilege.
            admin.execute(f'GRANT SELECT (id,projection_version,raw_json) ON {f.cache} TO "{role}"')
            admin.commit(); events.clear()
            with TestClient(app) as client:
                assert client.get('/ready').json() == {'ready': True}
            assert [e[0] for e in events] == ['connect','clear','earlier_startup','control_ready','http','control_closed']
            assert events[0][1].closed and events[1][1] == 0
            for mutation in ('missing_table', 'missing_column', 'lock_timeout'):
                events.clear()
                if mutation == 'missing_table':
                    admin.execute(f'ALTER TABLE {f.cache} RENAME TO hidden_projection'); admin.commit()
                elif mutation == 'missing_column':
                    admin.execute(f'ALTER TABLE {f.cache} RENAME COLUMN projection_version TO hidden_version'); admin.commit()
                else:
                    admin.execute(f'LOCK TABLE {f.cache} IN ACCESS EXCLUSIVE MODE')
                try:
                    expect_failure(lambda: verify_summary_reads(repositories, required=True))
                    assert events[-1] == ('clear', 0) and events[0][1].closed
                finally:
                    admin.rollback()
                    if mutation == 'missing_table':
                        admin.execute(f'ALTER TABLE "{f.schema}".hidden_projection RENAME TO label_run_projection')
                    elif mutation == 'missing_column':
                        admin.execute(f'ALTER TABLE {f.cache} RENAME COLUMN hidden_version TO projection_version')
                    admin.commit()
            # A pre-existing caller transaction must never be committed by preflight.
            connection = repositories.repository().connection
            connection.execute('SELECT 1')
            expect_failure(lambda: verify_summary_reads(repositories, required=True))
            assert connection.closed
            repositories = RepositoryLifecycle(lambda: None, lambda: events.append(('clear_none',)))
            verify_summary_reads(repositories, required=False)
            expect_failure(lambda: verify_summary_reads(repositories, required=True))
            for fail_at in ('connect', 'clear'):
                def secret_error():
                    raise ValueError('synthetic-secret-dsn-never-log')
                broken = RepositoryLifecycle(secret_error if fail_at == 'connect' else lambda: None,
                                             secret_error if fail_at == 'clear' else lambda: None)
                expect_failure(lambda: verify_summary_reads(broken, required=True))
        finally:
            repositories.clear()
            admin.rollback()
            admin.execute(f'DROP OWNED BY "{role}"')
            admin.execute(f'DROP ROLE "{role}"')
            admin.commit()
    print('PASS reader actual-role permissions, column grants, missing schema, lock timeout, cleanup, first startup, control rejection and whole-release rollback')


if __name__ == '__main__':
    main()
