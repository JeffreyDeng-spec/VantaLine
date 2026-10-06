"""Compare the real HTTP shell against its frozen pre-extraction constructor."""
import asyncio
import hashlib
import os
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from starlette.middleware.gzip import GZipMiddleware
from httpx import ASGITransport, AsyncClient
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local_inspection_service.runtime.http_application import create_http_application

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / 'tests/backend_contract/http_application_baseline.py'
BASELINE_SHA = 'eb7d464414cee11ffc76c9b7a1f339b71d2aa760ae995b5a8d28800442ec39a3'


def original(environment):
    body = BASELINE.read_bytes()
    if hashlib.sha256(body).hexdigest() != BASELINE_SHA:
        raise AssertionError('HTTP constructor baseline changed')
    namespace = {'__package__': 'local_inspection_service',
                 'os': SimpleNamespace(environ=environment), 'FastAPI': FastAPI,
                 'CORSMiddleware': CORSMiddleware, 'GZipMiddleware': GZipMiddleware}
    exec(compile(body, str(BASELINE), 'exec'), namespace)
    return SimpleNamespace(app=namespace['app'], cors_origins=namespace['CORS_ORIGINS'],
                           cors_origin_regex=namespace['CORS_ORIGIN_REGEX'])


def middleware(app):
    return [(item.cls, item.args, item.kwargs) for item in app.user_middleware]


async def responses(shell, origin):
    shell.app.add_api_route('/probe', lambda: PlainTextResponse('x' * 2048), methods=['GET'])
    async with AsyncClient(transport=ASGITransport(app=shell.app), base_url='http://fixture') as client:
        results = []
        for method, path, headers in [
            ('GET', '/probe', {'Origin': origin, 'Accept-Encoding': 'gzip'}),
            ('OPTIONS', '/probe', {'Origin': origin, 'Access-Control-Request-Method': 'POST',
                                    'Access-Control-Request-Headers': 'X-Test'}),
            ('OPTIONS', '/probe', {'Origin': origin, 'Access-Control-Request-Method': 'TRACE'}),
            ('GET', '/docs', {'Origin': origin}),
            ('GET', '/openapi.json', {'Origin': origin}),
        ]:
            response = await client.request(method, path, headers=headers)
            selected = {k:v for k,v in response.headers.items() if k.startswith('access-control-') or k in ('vary', 'content-encoding', 'content-type')}
            results.append((response.status_code, response.content, selected))
        return results


class HttpConstructionTests(unittest.TestCase):
    def test_original_settings_and_middleware_order(self):
        cases = [{}, {'VANTALINE_FILE_STORE':'local'}, {'VANTALINE_FILE_STORE':'cos'},
                 {'VANTALINE_FILE_STORE':''}, {'INSPECTION_ENABLE_LAN_CORS':'1'},
                 {'INSPECTION_ENABLE_LAN_CORS':'true'}, {'INSPECTION_CORS_ORIGIN_REGEX':''},
                 {'INSPECTION_CORS_ORIGINS':' , https://a.example,https://a.example, http://b.example ,'},
                 {'INSPECTION_ENABLE_LAN_CORS':'1', 'INSPECTION_CORS_ORIGIN_REGEX':'['}]
        for env in cases:
            with self.subTest(env=env):
                before, after = original(env), create_http_application(env)
                self.assertEqual(before.cors_origins, after.cors_origins)
                self.assertEqual(before.cors_origin_regex, after.cors_origin_regex)
                self.assertEqual(middleware(before.app), middleware(after.app))
                self.assertEqual(after.app.routes, [])
                self.assertEqual(after.app.title, before.app.title)
                self.assertEqual(after.app.router.on_startup, [])
                self.assertEqual(after.app.router.on_shutdown, [])

    def test_actual_cors_compression_and_documentation_responses(self):
        for env, origin in [({}, 'http://localhost:8123'), ({}, 'https://blocked.example'),
                ({'INSPECTION_ENABLE_LAN_CORS':'1'}, 'http://192.168.1.2:8123'),
                ({'INSPECTION_CORS_ORIGINS':'https://allowed.example'}, 'https://allowed.example'),
                ({'INSPECTION_CORS_ORIGIN_REGEX':''}, 'http://localhost')]:
            with self.subTest(env=env,origin=origin):
                self.assertEqual(asyncio.run(responses(original(env), origin)),
                                 asyncio.run(responses(create_http_application(env), origin)))

    def test_invalid_regex_is_deferred_to_asgi_construction(self):
        for build in (original, create_http_application):
            shell = build({'INSPECTION_CORS_ORIGIN_REGEX':'['})
            import re
            with self.assertRaises(re.error):
                asyncio.run(responses(shell, 'http://localhost'))

    def test_repeated_construction_owns_fresh_routes_and_settings(self):
        env = {'INSPECTION_CORS_ORIGINS':'https://first.example'}
        a, b = create_http_application(env), create_http_application(env)
        self.assertIsNot(a.app, b.app)
        self.assertIsNot(a.app.router, b.app.router)
        self.assertIsNot(a.cors_origins, b.cors_origins)
        a.app.add_api_route('/only-a', lambda: None)
        a.app.state.marker = 'a'
        a.cors_origins.append('https://a.example')
        env['INSPECTION_CORS_ORIGINS'] = 'https://changed.example'
        self.assertEqual(b.app.routes, [])
        self.assertFalse(hasattr(b.app.state, 'marker'))
        self.assertEqual(b.cors_origins, ['https://first.example'])
        self.assertEqual(create_http_application(env).cors_origins, ['https://changed.example'])
        self.assertEqual(len(a.app.user_middleware), 2)
        self.assertEqual(len(b.app.user_middleware), 2)

    def test_no_resource_or_worker_creation(self):
        poison = Mock(side_effect=AssertionError('HTTP factory started resource'))
        with patch.object(Path,'mkdir',poison), patch.object(threading.Thread,'start',poison):
            create_http_application({})
            create_http_application({'VANTALINE_FILE_STORE':'cos'})
        poison.assert_not_called()

    def test_environment_read_order_and_failure(self):
        class Environment(dict):
            def __init__(self):
                super().__init__(); self.reads=[]
            def get(self,key,default=None):
                self.reads.append(key)
                if key == 'INSPECTION_CORS_ORIGINS':
                    raise LookupError('synthetic configuration failure')
                return super().get(key,default)
        reads=[]
        for build in (original,create_http_application):
            env=Environment()
            with self.assertRaisesRegex(LookupError,'synthetic configuration failure'):
                build(env)
            reads.append(env.reads)
        self.assertEqual(*reads)
        self.assertEqual(reads[0], ['VANTALINE_FILE_STORE','INSPECTION_ENABLE_LAN_CORS',
                                   'INSPECTION_CORS_ORIGIN_REGEX','INSPECTION_CORS_ORIGINS'])


if __name__ == '__main__':
    unittest.main()
