"""Actual per-application repository owners: isolation, invalidation and cleanup."""
import argparse
import asyncio
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from fastapi import FastAPI, HTTPException, Request
import httpx

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from local_inspection_service.runtime.repository_composition import RuntimeRepositories
from local_inspection_service.runtime.identity import RequestIdentity


class Connection:
    def __init__(self):
        self.closed=False
        self.created_by=threading.get_ident()
        self.closed_by=None
    def close(self):
        self.closed=True
        self.closed_by=threading.get_ident()


class Ownership(unittest.TestCase):
    def setUp(self):
        self.environment={'VANTALINE_DATA_STORE':' postgres ', 'DATABASE_URL':'fixture-first'}
        self.connections=[]
        self.calls=[]
        def connector(dsn):
            self.calls.append(dsn)
            connection=Connection();self.connections.append(connection)
            return connection
        self.owner=RuntimeRepositories(self.environment,connector=connector)
        self.addCleanup(self.owner.factory.clear)

    def test_inert_owned_factory_and_selection(self):
        self.assertEqual(self.calls,[])
        first=self.owner.access.runtime_repository_selection()
        self.assertIs(first,self.owner.access.runtime_repository_selection())
        self.assertIs(first.repository,self.owner.access.runtime_postgres_repository_or_none())
        self.assertEqual(self.calls,['fixture-first'])

    def test_live_environment_connector_and_broken_connection_rebuild(self):
        first=self.owner.access.runtime_postgres_repository_or_none().connection
        first.closed=True
        second=self.owner.access.runtime_postgres_repository_or_none().connection
        self.assertIsNot(first,second)
        self.environment['DATABASE_URL']='fixture-second'
        third=self.owner.access.runtime_postgres_repository_or_none().connection
        self.assertTrue(second.closed)
        self.assertEqual(self.calls[-1],'fixture-second')
        replacement=Connection()
        self.owner.connector=lambda dsn: replacement
        self.assertIs(self.owner.access.runtime_postgres_repository_or_none().connection,replacement)
        self.assertTrue(third.closed)
        self.owner.factory.clear()
        self.assertTrue(replacement.closed)

    def test_other_owner_reset_does_not_close_this_owner(self):
        other=RuntimeRepositories(self.environment,connector=self.owner.connector)
        try:
            first=self.owner.access.runtime_postgres_repository_or_none().connection
            second=other.access.runtime_postgres_repository_or_none().connection
            self.assertIsNot(first,second)
            self.owner.factory.reset()
            self.assertTrue(first.closed);self.assertFalse(second.closed)
            self.assertIs(other.access.runtime_postgres_repository_or_none().connection,second)
        finally:other.factory.clear()

    def test_cross_thread_reset_never_closes_active_other_thread_connection(self):
        entered,reset=threading.Event(),threading.Event()
        def work():
            with self.owner.factory.thread_scope():
                first=self.owner.access.runtime_postgres_repository_or_none().connection
                entered.set();self.assertTrue(reset.wait(5))
                self.assertFalse(first.closed)
                second=self.owner.access.runtime_postgres_repository_or_none().connection
                self.assertIsNot(first,second);self.assertTrue(first.closed)
        with ThreadPoolExecutor(1) as executor:
            future=executor.submit(work);self.assertTrue(entered.wait(5))
            self.owner.factory.reset();reset.set();future.result(5)
        self.assertTrue(all(c.closed and c.created_by==c.closed_by for c in self.connections))

    def test_actual_entry_graph_has_owned_internal_bindings(self):
        with tempfile.TemporaryDirectory(prefix='repository-entry-') as temporary:
            root=Path(temporary);(root/'local_inspection_service/static').mkdir(parents=True)
            with patch.dict(os.environ,{'LOCAL_INSPECTION_ROOT':str(root),'VANTALINE_DATA_STORE':'json',
                    'VANTALINE_LABEL_INSPECTION_ENABLED':'false','LOCAL_INSPECTION_AUTO_RESUME_WORKER':'0'}):
                from local_inspection_service import server
                owner=server._runtime_repository_owner
                self.assertIs(server._runtime_repositories,owner.factory)
                self.assertIs(server._runtime_repository_access,owner.access)
                self.assertIs(server.runtime_repository_cache_key.__self__,owner)
                self.assertIs(owner.access.factory(),owner.factory)
                self.assertIs(owner.access.selection().__self__,owner.access)
                def poisoned():raise AssertionError('entry rebinding reached owned factory')
                try:
                    with patch.object(server,'_runtime_repositories',SimpleNamespace(selection=poisoned)), \
                         patch.object(server,'runtime_repository_selection',poisoned):
                        self.assertIsNone(owner.access.runtime_postgres_repository_or_none())
                finally:owner.factory.clear()

    def test_existing_http_error_contract_and_json_selection(self):
        self.environment['VANTALINE_DATA_STORE']='json'
        self.assertIsNone(self.owner.access.runtime_postgres_repository_or_none())
        self.assertEqual(self.calls,[])
        self.environment['VANTALINE_DATA_STORE']='bad'
        with self.assertRaises(HTTPException) as caught:self.owner.access.runtime_repository_selection()
        self.assertEqual(caught.exception.status_code,503)
        self.assertEqual(caught.exception.detail['code'],'runtime_store_config_error')
        self.assertFalse(caught.exception.detail['json_fallback_used'])


async def asgi_owners(dsn=None):
    connections=[]
    def connector(value):
        if dsn:
            import psycopg
            connection=psycopg.connect(value)
        else:connection=Connection()
        connections.append(connection)
        return connection
    owners=[RuntimeRepositories({'VANTALINE_DATA_STORE':'postgres','DATABASE_URL':dsn or 'fixture'},connector=connector) for _ in range(2)]
    identities=[RequestIdentity(),RequestIdentity()]
    barrier=threading.Barrier(2)
    def application(owner,identity,index):
        app=FastAPI()
        @app.middleware('http')
        async def bind(request:Request,call_next):
            with identity.bind({'id':request.headers['x-owner']}):
                return await call_next(request)
        @app.get('/probe')
        def probe(fail:bool=False):
            with owner.factory.thread_scope():
                connection=owner.access.runtime_postgres_repository_or_none().connection
                assert owner.access.runtime_postgres_repository_or_none().connection is connection
                assert identities[1-index].get() is None
                if fail:raise ValueError('synthetic-failure')
                barrier.wait(5)
                result=connection.execute('SELECT pg_backend_pid()').fetchone()[0] if dsn else id(connection)
                return {'user':identity.get()['id'],'connection':result}
        return app
    apps=[application(owner,identity,index) for index,(owner,identity) in enumerate(zip(owners,identities))]
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=apps[0],raise_app_exceptions=False),base_url='https://fixture.invalid') as a, \
               httpx.AsyncClient(transport=httpx.ASGITransport(app=apps[1],raise_app_exceptions=False),base_url='https://fixture.invalid') as b:
        left,right=await asyncio.gather(a.get('/probe',headers={'x-owner':'alice'}),b.get('/probe',headers={'x-owner':'bob'}))
        assert left.status_code==right.status_code==200
        assert left.json()['user']=='alice' and right.json()['user']=='bob'
        assert left.json()['connection']!=right.json()['connection']
        assert all(c.closed for c in connections)
        error=await a.get('/probe?fail=true',headers={'x-owner':'error'})
        assert error.status_code==500 and all(c.closed for c in connections)
    assert all(i.get() is None for i in identities)
    if not dsn:assert all(c.created_by==c.closed_by for c in connections)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--postgres',action='store_true');args=parser.parse_args()
    result=unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromTestCase(Ownership))
    if not result.wasSuccessful():raise SystemExit(1)
    asyncio.run(asgi_owners(os.environ['VANTALINE_POSTGRES_DSN'] if args.postgres else None))
    print('PASS explicit repository owners, actual ASGI thread scopes and connection failure cleanup; fixtures are not the full production factory')
