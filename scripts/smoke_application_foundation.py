"""Two real foundational graphs with synthetic connections and ASGI dispatch."""
import asyncio
import os
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import Mock, patch
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local_inspection_service.runtime.application_foundation import FoundationInputs, build_foundation
from local_inspection_service.auth.composition import AuthenticationSettings
from local_inspection_service.auth.sessions import SessionSettings
from local_inspection_service.auth.login_limits import LoginLimitSettings
from smoke_repository_composition import Connection


def inputs(name, connector=None):
    return FoundationInputs(
        {'VANTALINE_DATA_STORE': 'postgres', 'DATABASE_URL': name},
        Path('unused') / name, Path('unused') / name / 'auth.json',
        AuthenticationSettings(lambda: 120000, lambda: SessionSettings(name, 500, 30),
            lambda: LoginLimitSettings(60, 10, 120), lambda: 'legacy'),
        'legacy', 'system', connector,
    )


class FoundationContract(unittest.TestCase):
    def test_constructs_fresh_owners_without_io_or_workers(self):
        poison = Mock(side_effect=AssertionError('construction performed I/O'))
        value = inputs('inert', poison)
        with patch.object(Path, 'mkdir', poison), patch.object(threading.Thread, 'start', poison):
            first, second = build_foundation(value), build_foundation(value)
        poison.assert_not_called()
        for owner in ('repositories', 'authentication', 'records'):
            self.assertIsNot(getattr(first, owner), getattr(second, owner))
        self.assertIsNot(first.authentication.identity, second.authentication.identity)
        for field in ('write_lock', 'limits', 'repository'):
            self.assertIsNot(getattr(first.authentication.services, field), getattr(second.authentication.services, field))
        self.assertIs(first.records.access.identity, first.authentication.identity)
        self.assertIs(second.records.access.identity, second.authentication.identity)

    def test_interleaved_identity_connection_and_independent_reset(self):
        first, second = [build_foundation(inputs(name, lambda _: Connection())) for name in ('a', 'b')]
        with first.authentication.identity.bind({'id': 'a', 'role': 'user'}), second.authentication.identity.bind({'id': 'b', 'role': 'user'}):
            self.assertEqual(first.records.access.current_owner_fields()['owner_user_id'], 'a')
            self.assertEqual(second.records.access.current_owner_fields()['owner_user_id'], 'b')
            with first.repositories.factory.thread_scope(), second.repositories.factory.thread_scope():
                ca = first.repositories.access.runtime_postgres_repository_or_none().connection
                cb = second.repositories.access.runtime_postgres_repository_or_none().connection
                self.assertIsNot(ca, cb)
                first.repositories.factory.reset()
                self.assertTrue(ca.closed)
                self.assertFalse(cb.closed)
                self.assertIs(second.repositories.access.runtime_postgres_repository_or_none().connection, cb)
        self.assertTrue(cb.closed)
        self.assertIsNone(first.authentication.identity.get())
        self.assertIsNone(second.authentication.identity.get())

    def test_environment_and_connector_updates_are_instance_local(self):
        calls = []
        first_inputs = inputs('a', lambda dsn: (calls.append(dsn), Connection())[1])
        second_inputs = inputs('b', first_inputs.connector)
        first, second = build_foundation(first_inputs), build_foundation(second_inputs)
        with first.repositories.factory.thread_scope(), second.repositories.factory.thread_scope():
            ca = first.repositories.access.runtime_postgres_repository_or_none().connection
            cb = second.repositories.access.runtime_postgres_repository_or_none().connection
            first_inputs.environment['DATABASE_URL'] = 'new-a'
            changed = first.repositories.access.runtime_postgres_repository_or_none().connection
            self.assertTrue(ca.closed)
            self.assertEqual(calls, ['a', 'b', 'new-a'])
            replacement = Connection()
            first.repositories.connector = lambda _: replacement
            self.assertIs(first.repositories.access.runtime_postgres_repository_or_none().connection, replacement)
            self.assertTrue(changed.closed)
            self.assertIs(second.repositories.access.runtime_postgres_repository_or_none().connection, cb)
            self.assertFalse(cb.closed)
        self.assertTrue(replacement.closed and cb.closed)

    def test_concurrent_asgi_threads_and_exception_cleanup(self):
        async def run():
            connections = []
            def connector(_):
                value = Connection();connections.append(value);return value
            graphs = [build_foundation(inputs(name, connector)) for name in ('a', 'b')]
            barrier = threading.Barrier(2)
            def application(graph):
                app = FastAPI()
                @app.middleware('http')
                async def bind(request: Request, call_next):
                    with graph.authentication.identity.bind({'id': request.headers['x-owner'], 'role': 'user'}):
                        return await call_next(request)
                @app.get('/probe')
                def probe(fail: bool = False):
                    with graph.repositories.factory.thread_scope():
                        conn = graph.repositories.access.runtime_postgres_repository_or_none().connection
                        barrier.wait(3)
                        if fail:
                            raise RuntimeError('synthetic probe failure')
                        return {'owner': graph.records.access.current_owner_fields()['owner_user_id'], 'thread': conn.created_by}
                return app
            clients = [AsyncClient(transport=ASGITransport(app=application(g), raise_app_exceptions=False), base_url='http://fixture') for g in graphs]
            try:
                responses = await asyncio.gather(clients[0].get('/probe', headers={'x-owner': 'a'}), clients[1].get('/probe?fail=true', headers={'x-owner': 'b'}))
                self.assertEqual([v.status_code for v in responses], [200, 500])
                self.assertEqual(responses[0].json()['owner'], 'a')
            finally:
                for client in clients:
                    await client.aclose()
            self.assertEqual(len(connections), 2)
            self.assertNotEqual(connections[0].created_by, connections[1].created_by)
            self.assertTrue(all(c.closed and c.created_by == c.closed_by for c in connections))
            self.assertTrue(all(g.authentication.identity.get() is None for g in graphs))
        asyncio.run(run())

    @unittest.skipUnless(os.getenv('VANTALINE_POSTGRES_DSN'), 'isolated PostgreSQL not configured')
    def test_real_postgres_connections_belong_to_each_foundation(self):
        import psycopg
        configs = [inputs(name, psycopg.connect) for name in ('a', 'b')]
        for config in configs:
            config.environment['DATABASE_URL'] = os.environ['VANTALINE_POSTGRES_DSN']
        first, second = [build_foundation(config) for config in configs]
        with first.repositories.factory.thread_scope(), second.repositories.factory.thread_scope():
            ca = first.repositories.access.runtime_postgres_repository_or_none().connection
            cb = second.repositories.access.runtime_postgres_repository_or_none().connection
            self.assertNotEqual(ca.execute('SELECT pg_backend_pid()').fetchone()[0], cb.execute('SELECT pg_backend_pid()').fetchone()[0])
            first.repositories.factory.reset()
            self.assertTrue(ca.closed)
            self.assertEqual(cb.execute('SELECT 1').fetchone()[0], 1)
        self.assertTrue(cb.closed)

    def test_entry_uses_the_same_three_owners(self):
        from scripts.verify_backend_contract import capture
        capture()
        from local_inspection_service import server
        foundation = server._foundation
        self.assertIs(server._runtime_repository_owner, foundation.repositories)
        self.assertIs(server._authentication_domain, foundation.authentication)
        self.assertIs(server._record_services, foundation.records)
        self.assertIs(foundation.records.access.identity, foundation.authentication.identity)


if __name__ == '__main__':
    unittest.main()
