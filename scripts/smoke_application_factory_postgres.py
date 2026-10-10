"""Real PostgreSQL ownership across two actual applications; no native startup.

Requires an isolated test database. Creates only two uniquely named schemas,
then removes those schemas. No model, PLC, task or worker is invoked.
"""
import asyncio
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import uuid

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from smoke_application_factory import environment
from local_inspection_service.runtime.application import create_application


class PostgresApplicationContracts(unittest.TestCase):
    def setUp(self):
        dsn = os.environ.get('APPLICATION_FACTORY_TEST_DATABASE_URL')
        if not dsn:
            raise RuntimeError('APPLICATION_FACTORY_TEST_DATABASE_URL must name an isolated test database')
        self.admin = psycopg.connect(dsn, autocommit=True)
        self.addCleanup(self.admin.close)
        temporary = tempfile.TemporaryDirectory(prefix='actual-app-pg-')
        self.addCleanup(temporary.cleanup)
        self.apps = []
        self.schemas = []
        self.addCleanup(self.clean_schemas)
        for marker in ('a', 'b'):
            schema = 'actual_factory_' + uuid.uuid4().hex
            self.admin.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
            self.schemas.append(schema)
            self.admin.execute(sql.SQL('CREATE TABLE {}.ownership (marker TEXT NOT NULL)').format(sql.Identifier(schema)))
            self.admin.execute(sql.SQL('INSERT INTO {}.ownership VALUES (%s)').format(sql.Identifier(schema)), (marker,))
            env = environment(Path(temporary.name) / marker)
            app = create_application(env)
            self.addCleanup(lambda app=app: self.assertTrue(app.lifetime.close(10)))
            env.update(VANTALINE_DATA_STORE='postgres', DATABASE_URL=make_conninfo(
                dsn, options='-c search_path=' + schema, connect_timeout=5))
            self.apps.append(app)

    def clean_schemas(self):
        for schema in self.schemas:
            self.admin.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))

    def test_accounts_async_threads_and_database_scopes_are_independent(self):
        barrier = threading.Barrier(2)
        closed = []
        async def account(app, marker):
            identity = app.infrastructure._request_user
            token = identity.set({'id': marker})
            def query():
                factory = app.infrastructure._runtime_repositories
                with factory.thread_scope():
                    selected = factory.selection()
                    self.assertIs(factory.selection(), selected)
                    connection = selected.repository.connection
                    access = app.infrastructure._runtime_repository_access.runtime_postgres_repository_or_none()
                    rows = app.infrastructure._app_configuration.store.rows.runtime_postgres_repository_or_none()()
                    self.assertIs(access, selected.repository)
                    self.assertIs(rows, selected.repository)
                    row = rows.connection.execute('SELECT marker, pg_backend_pid() FROM ownership').fetchone()
                    barrier.wait(5)
                    self.assertEqual(identity.get()['id'], marker)
                    closed.append(connection)
                    return row
            try:
                return await asyncio.to_thread(query)
            finally:
                identity.reset(token)
        async def concurrent():
            return await asyncio.gather(account(self.apps[0], 'a'), account(self.apps[1], 'b'))
        rows = asyncio.run(concurrent())
        self.assertEqual([row[0] for row in rows], ['a', 'b'])
        self.assertNotEqual(rows[0][1], rows[1][1])
        self.assertTrue(all(connection.closed for connection in closed))
        self.assertTrue(all(app.infrastructure._request_user.get() is None for app in self.apps))

    def test_closed_connection_rebuild_error_release_and_neighbor_close(self):
        a, b = self.apps
        factory = a.infrastructure._runtime_repositories
        first = factory.selection().repository.connection
        first.close()
        second = factory.selection().repository.connection
        self.assertIsNot(first, second)
        self.assertEqual(second.execute('SELECT marker FROM ownership').fetchone(), ('a',))
        neighbor = b.infrastructure._runtime_repositories.selection().repository.connection
        with self.assertRaises(psycopg.errors.DivisionByZero):
            with factory.thread_scope():
                self.assertIs(factory.selection().repository.connection, second)
                second.execute('SELECT 1 / 0')
        self.assertTrue(second.closed)
        rebuilt = factory.selection().repository.connection
        self.assertIsNot(rebuilt, second)
        self.assertEqual(rebuilt.execute('SELECT marker FROM ownership').fetchone(), ('a',))
        self.assertTrue(a.lifetime.close(10))
        self.assertTrue(rebuilt.closed)
        self.assertFalse(neighbor.closed)
        self.assertEqual(neighbor.execute('SELECT marker FROM ownership').fetchone(), ('b',))


if __name__ == '__main__':
    unittest.main()
