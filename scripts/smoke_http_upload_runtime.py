"""Exercise injected multipart admission with real ASGI calls and no external storage."""
import asyncio
from contextlib import contextmanager
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
from fastapi import Request
from fastapi.responses import PlainTextResponse
from httpx import ASGITransport, AsyncClient
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local_inspection_service.runtime.http_application import create_http_application
from local_inspection_service.storage.artifacts.types import DiskCapacityError

HEADERS = {'Content-Type': 'multipart/form-data; boundary=synthetic'}


class Budget:
    preallocated = False
    def __init__(self):
        self.limits = {'upload': 8}
        self.used = 0
        self.entries = 0
        self.exits = 0

    @contextmanager
    def reserve(self, kind, size):
        assert kind == 'upload'
        if self.used + size > 4:
            raise DiskCapacityError('synthetic full budget')
        self.used += size
        self.entries += 1
        try:
            yield
        finally:
            self.used -= size
            self.exits += 1


def runtime(budget):
    return SimpleNamespace(store=SimpleNamespace(budget=budget))


def shell(provider, mode='cos'):
    app = create_http_application({'VANTALINE_FILE_STORE': mode}, upload_runtime_provider=provider).app
    async def echo(request: Request):
        return PlainTextResponse(await request.body())
    app.add_api_route('/body', echo, methods=['POST'])
    return app


def client(app):
    return AsyncClient(transport=ASGITransport(app=app), base_url='http://synthetic')


class HttpUploadRuntimeTests(unittest.TestCase):
    def test_lazy_provider_is_not_used_for_local_or_nonmultipart_requests(self):
        async def run():
            poison = Mock(side_effect=AssertionError('unexpected provider use'))
            local, remote = shell(poison, 'local'), shell(poison)
            poison.assert_not_called()
            async with client(local) as a, client(remote) as b:
                self.assertEqual((await a.post('/body', content=b'test', headers=HEADERS)).content, b'test')
                self.assertEqual((await b.post('/body', content=b'test')).content, b'test')
            poison.assert_not_called()
        asyncio.run(run())

    def test_simultaneous_apps_keep_reservations_separate_and_cleanup(self):
        async def run():
            entered, release = asyncio.Event(), asyncio.Event()
            a_budget, b_budget = Budget(), Budget()
            a, b = shell(lambda: runtime(a_budget)), shell(lambda: runtime(b_budget))
            async def hold(request: Request):
                body = await request.body()
                entered.set()
                await release.wait()
                return PlainTextResponse(body)
            a.add_api_route('/hold', hold, methods=['POST'])
            async with client(a) as ca, client(b) as cb:
                pending = asyncio.create_task(ca.post('/hold', content=b'test', headers=HEADERS))
                try:
                    await asyncio.wait_for(entered.wait(), 2)
                    self.assertEqual(a_budget.used, 4)
                    refused = await ca.post('/body', content=b'test', headers=HEADERS)
                    self.assertEqual(refused.status_code, 503)
                    self.assertEqual(refused.json(), {'detail': 'Upload staging is busy'})
                    accepted = await cb.post('/body', content=b'test', headers=HEADERS)
                    self.assertEqual((accepted.status_code, accepted.content), (200, b'test'))
                    self.assertEqual((a_budget.used, b_budget.used), (4, 0))
                finally:
                    release.set()
                    response = await asyncio.wait_for(pending, 2)
                self.assertEqual((response.status_code, response.content), (200, b'test'))
            self.assertEqual((a_budget.used, b_budget.used), (0, 0))
            self.assertEqual((a_budget.entries, a_budget.exits, b_budget.entries, b_budget.exits), (1, 1, 1, 1))
        asyncio.run(run())

    def test_provider_result_is_resolved_for_each_multipart_request(self):
        async def run():
            current = [None]
            provider = Mock(side_effect=lambda: current[0])
            app = shell(provider)
            async with client(app) as c:
                self.assertEqual((await c.post('/body', content=b'test', headers=HEADERS)).status_code, 200)
                budget = Budget(); budget.limits['upload'] = 2
                current[0] = runtime(budget)
                refused = await c.post('/body', content=b'test', headers=HEADERS)
                self.assertEqual(refused.status_code, 413)
                self.assertEqual(refused.json(), {'detail': 'Upload exceeds staging capacity'})
                self.assertEqual(budget.entries, 0)
            self.assertEqual(provider.call_count, 2)
        asyncio.run(run())

    def test_provider_failure_propagates_without_fallback_or_route_execution(self):
        async def run():
            failure = RuntimeError('synthetic provider failure')
            provider = Mock(side_effect=failure)
            app = shell(provider); reached = []
            async def route():
                reached.append(True)
                return PlainTextResponse('unexpected')
            app.add_api_route('/never', route, methods=['POST'])
            async with client(app) as c:
                with self.assertRaises(RuntimeError) as caught:
                    await c.post('/never', content=b'test', headers=HEADERS)
                self.assertIs(caught.exception, failure)
            provider.assert_called_once_with()
            self.assertEqual(reached, [])
        asyncio.run(run())

    def test_route_failure_releases_only_its_injected_budget(self):
        async def run():
            budget = Budget(); app = shell(lambda: runtime(budget))
            failure = RuntimeError('synthetic route failure')
            async def route(request: Request):
                self.assertEqual(await request.body(), b'test')
                raise failure
            app.add_api_route('/fail', route, methods=['POST'])
            async with client(app) as c:
                with self.assertRaises(RuntimeError) as caught:
                    await c.post('/fail', content=b'test', headers=HEADERS)
                self.assertIs(caught.exception, failure)
                self.assertEqual(budget.used, 0)
                self.assertEqual((await c.post('/body', content=b'test', headers=HEADERS)).status_code, 200)
            self.assertEqual((budget.used, budget.entries, budget.exits), (0, 2, 2))
        asyncio.run(run())


if __name__ == '__main__':
    unittest.main()
