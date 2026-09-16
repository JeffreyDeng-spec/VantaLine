"""Native ASGI/thread-pool identity and connection lifecycle contracts."""
import argparse
import asyncio
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import sys
import threading
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi import FastAPI, Request
import httpx
from local_inspection_service.runtime.connections import ThreadRepositoryFactory
from local_inspection_service.runtime.identity import RequestIdentity


class Connection:
    def __init__(self):
        self.closed = False
        self.created_by = threading.get_ident()
        self.closed_by = None

    def close(self):
        self.closed = True
        self.closed_by = threading.get_ident()


def connection_contract():
    connections = []
    key = ['first']
    def create():
        connection = Connection()
        connections.append(connection)
        return SimpleNamespace(repository=SimpleNamespace(connection=connection))
    factory = ThreadRepositoryFactory(create, lambda:key[0])
    first = factory.selection()
    assert factory.selection() is first
    first.repository.connection.closed = True
    second = factory.selection()
    assert second is not first and first.repository.connection.closed_by is not None
    key[0] = 'second'
    third = factory.selection()
    assert third is not second and second.repository.connection.closed
    factory.reset()
    assert third.repository.connection.closed
    try:
        with factory.thread_scope():
            fourth = factory.selection()
            with factory.thread_scope():
                assert factory.selection() is fourth
            assert not fourth.repository.connection.closed
            raise ValueError('synthetic failure')
    except ValueError:
        pass
    assert fourth.repository.connection.closed
    # Invalidation while connecting closes the stale result and retries once.
    stale = []
    def racing_create():
        result = create()
        stale.append(result)
        if len(stale) == 1:
            race.reset()
        return result
    race = ThreadRepositoryFactory(racing_create, lambda: 'stable')
    with race.thread_scope():
        assert race.selection() is stale[1]
    assert all(item.repository.connection.closed for item in stale)
    assert all(c.created_by == c.closed_by for c in connections)

    # A reset in a different thread cannot close an in-use connection there.
    entered, reset = threading.Event(), threading.Event()
    def worker():
        with factory.thread_scope():
            before = factory.selection()
            entered.set()
            assert reset.wait(5)
            assert not before.repository.connection.closed
            after = factory.selection()
            assert after is not before and before.repository.connection.closed
    with ThreadPoolExecutor(1) as pool:
        future = pool.submit(worker)
        assert entered.wait(5)
        factory.reset()
        reset.set()
        future.result(timeout=5)
    assert all(c.closed and c.created_by == c.closed_by for c in connections)


async def http_contract(dsn=None):
    identity, other_identity = RequestIdentity(), RequestIdentity()
    connections = []
    def create():
        if dsn:
            import psycopg
            connection = psycopg.connect(dsn)
        else:
            connection = Connection()
        connections.append(connection)
        return SimpleNamespace(repository=SimpleNamespace(connection=connection))
    factory = ThreadRepositoryFactory(create, lambda:'asgi-contract')
    app = FastAPI()
    barrier = threading.Barrier(2)
    @app.middleware('http')
    async def user(request: Request, call_next):
        with identity.bind({'id': request.headers['x-test-owner']}):
            return await call_next(request)
    @app.get('/work')
    def work(fail: bool = False):
        with factory.thread_scope():
            owner = identity.get()['id']
            assert other_identity.get() is None
            connection = factory.selection().repository.connection
            assert factory.selection().repository.connection is connection
            if fail:
                raise ValueError('synthetic request failure')
            barrier.wait(timeout=5)
            assert identity.get()['id'] == owner
            identifier = connection.execute('SELECT pg_backend_pid()').fetchone()[0] if dsn else id(connection)
            return {'owner': owner, 'connection': identifier}
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url='https://fixture.invalid') as client:
        first, second = await asyncio.gather(
            client.get('/work', headers={'x-test-owner':'alice'}),
            client.get('/work', headers={'x-test-owner':'bob'}),
        )
        assert first.status_code == second.status_code == 200, (first.text, second.text)
        assert first.json()['owner'] == 'alice' and second.json()['owner'] == 'bob'
        assert first.json()['connection'] != second.json()['connection']
        assert all(c.closed for c in connections)
        response = await client.get('/work?fail=true', headers={'x-test-owner':'error'})
        assert response.status_code == 500
        assert all(c.closed for c in connections)
    assert identity.get() is other_identity.get() is None
    if not dsn:
        assert all(c.created_by == c.closed_by for c in connections)


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--postgres', action='store_true')
    args = parser.parse_args()
    connection_contract()
    asyncio.run(http_contract(os.environ['VANTALINE_POSTGRES_DSN'] if args.postgres else None))
    print('PASS runtime identity, native thread-pool isolation, connection rebuild/reset and same-thread exception cleanup')


if __name__ == '__main__':
    main()
