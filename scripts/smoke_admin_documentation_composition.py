"""Admin documentation guard, cache and per-application route contracts."""
import ast
from pathlib import Path
import os
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.testclient import TestClient
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from local_inspection_service.auth.docs_api import DocumentationAccess, register_documentation_api

BASELINE = os.environ.get('VANTALINE_ADMIN_DOCS_BASELINE_SOURCE')
PATHS = ('/openapi.json', '/api/docs', '/redoc')
NAMES = ('openapi_schema', 'swagger_ui', 'redoc_ui')


def fixture(title='Example', state=None):
    app = FastAPI(title=title, docs_url=None, redoc_url=None, openapi_url=None)
    state = state if state is not None else {'user': {'id': title, 'admin': True}, 'exists': True}
    calls = []
    def authenticate(request):
        calls.append(('authenticate', request))
        return state['user'], state, None
    def users_exist(store):
        assert store is state
        calls.append(('users', store))
        return state['exists']
    def is_admin(user):
        calls.append(('admin', user))
        return user['admin']
    if BASELINE:
        tree = ast.parse(Path(BASELINE).read_text(encoding='utf-8'))
        selected = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in ('require_docs_admin', *NAMES)]
        assert len(selected) == 4
        scope = dict(app=app, authenticate_request=authenticate, users_exist=users_exist, user_is_admin=is_admin,
                     HTTPException=HTTPException, Request=Request, Response=Response,
                     get_openapi=get_openapi, get_swagger_ui_html=get_swagger_ui_html, get_redoc_html=get_redoc_html)
        module = ast.Module(body=[ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0), *selected], type_ignores=[])
        exec(compile(ast.fix_missing_locations(module), BASELINE, 'exec'), scope)
        guard = scope['require_docs_admin']
        endpoints = tuple(scope[name] for name in NAMES)
        owner = None
    else:
        owner = DocumentationAccess(authenticate, users_exist, is_admin)
        guard = owner.require_docs_admin
        endpoints = register_documentation_api(app, guard)
    return SimpleNamespace(**locals())


class Documentation(unittest.TestCase):
    def test_no_construction_io_and_route_metadata(self):
        f = fixture()
        self.assertEqual(f.calls, [])
        self.assertEqual([route.path for route in f.app.routes], list(PATHS))
        self.assertEqual([route.name for route in f.app.routes], list(NAMES))
        self.assertEqual([route.endpoint for route in f.app.routes], list(f.endpoints))
        self.assertTrue(all(not route.include_in_schema for route in f.app.routes))
        self.assertTrue(all(route.methods == {'GET'} for route in f.app.routes))

    def test_guard_order_short_circuit_and_identity(self):
        for exists, user, names in ((False, {'admin': True}, ['authenticate','users']),
                                   (True, None, ['authenticate','users']),
                                   (True, {}, ['authenticate','users']),
                                   (True, {'admin':False}, ['authenticate','users','admin']),
                                   (True, {'admin':True}, ['authenticate','users','admin'])):
            f = fixture(state={'exists':exists,'user':user})
            request = object()
            if exists and user and user['admin']:
                self.assertIs(f.guard(request), user)
            else:
                with self.assertRaises(HTTPException) as raised:
                    f.guard(request)
                self.assertEqual((raised.exception.status_code,raised.exception.detail), (404,'Not found'))
            self.assertEqual([name for name,_ in f.calls], names)
            self.assertIs(f.calls[0][1], request)

    def test_truthy_cached_schema_never_bypasses_current_identity(self):
        f = fixture()
        sentinel = {'private':'cached'}
        f.app.openapi_schema = sentinel
        self.assertIs(f.endpoints[0](object()), sentinel)
        for endpoint in f.endpoints:
            f.state['user'] = None
            with self.assertRaises(HTTPException) as raised:
                endpoint(object())
            self.assertEqual(raised.exception.status_code,404)
            self.assertIs(f.app.openapi_schema,sentinel)
        f.state['user'] = {'admin':True}
        self.assertIs(f.endpoints[0](object()), sentinel)

    def test_two_apps_own_titles_routes_and_cache_identity(self):
        a,b = fixture('Alpha'),fixture('Beta')
        a.app.get('/alpha')(lambda: {'a':1})
        b.app.get('/beta')(lambda: {'b':2})
        for f,path in ((a,'/alpha'),(b,'/beta')):
            f.app.openapi_schema = {}  # Falsey cache must be regenerated.
            schema = f.endpoints[0](object())
            self.assertIs(schema, f.app.openapi_schema)
            self.assertEqual(schema['info'], {'title':f.title,'description':'Admin-only OpenAPI schema','version':'1.0.0'})
            self.assertEqual(set(schema['paths']),{path})
            self.assertIs(f.endpoints[0](object()),schema)
            f.app.get('/added-later')(lambda: None)
            self.assertIs(f.endpoints[0](object()),schema)
            self.assertNotIn('/added-later',schema['paths'])
        self.assertIsNot(a.app.openapi_schema,b.app.openapi_schema)
        self.assertIsNot(a.endpoints[0],b.endpoints[0])

    def test_html_and_http_errors(self):
        f = fixture('Admin & Docs')
        for endpoint,expected in ((f.endpoints[1],get_swagger_ui_html(openapi_url='/openapi.json',title='Admin & Docs Docs')),
                                  (f.endpoints[2],get_redoc_html(openapi_url='/openapi.json',title='Admin & Docs ReDoc'))):
            actual=endpoint(object())
            self.assertEqual((actual.body,actual.status_code,dict(actual.headers)),(expected.body,expected.status_code,dict(expected.headers)))
        with TestClient(f.app) as client:
            for path in PATHS:
                self.assertEqual(client.get(path).status_code,200)
            f.state['user'] = None
            for path in PATHS:
                response=client.get(path)
                self.assertEqual((response.status_code,response.json()),(404,{'detail':'Not found'}))

    def test_dependency_and_cache_failure_identity(self):
        failure=RuntimeError('synthetic auth failure')
        class BadState(dict):
            def __getitem__(self,key):
                raise failure
        f=fixture(state=BadState())
        f.app.openapi_schema={'secret':'cached'}
        with self.assertRaises(RuntimeError) as raised:
            f.endpoints[0](object())
        self.assertIs(raised.exception,failure)
        self.assertEqual([name for name,_ in f.calls],['authenticate'])
        class BadTruth(dict):
            def __bool__(self):
                raise failure
        f=fixture()
        f.app.openapi_schema=BadTruth()
        with self.assertRaises(RuntimeError) as raised:
            f.endpoints[0](object())
        self.assertIs(raised.exception,failure)
        self.assertEqual([name for name,_ in f.calls],['authenticate','users','admin'])

    @unittest.skipIf(BASELINE,'candidate domain composition only')
    def test_duplicate_preflight_and_partial_registration_failure(self):
        fail=Mock(side_effect=AssertionError('construction I/O'))
        default_app=FastAPI()
        before=list(default_app.routes)
        with self.assertRaises(ValueError):
            register_documentation_api(default_app,fail)
        self.assertEqual(default_app.routes,before)
        for path in PATHS:
            app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None)
            app.get(path)(lambda: None)
            before=list(app.routes)
            with self.assertRaises(ValueError):
                register_documentation_api(app,fail)
            self.assertEqual(app.routes,before)
        app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None)
        app.post(PATHS[0])(lambda: None)
        original=app.router.add_api_route
        failure=RuntimeError('second registration fails')
        count=0
        def add(*args,**kwargs):
            nonlocal count
            count+=1
            if count==2:
                raise failure
            return original(*args,**kwargs)
        with patch.object(app.router,'add_api_route',add):
            with self.assertRaises(RuntimeError) as raised:
                register_documentation_api(app,fail)
        self.assertIs(raised.exception,failure)
        self.assertEqual([r.path for r in app.routes],[PATHS[0],PATHS[0]])
        self.assertFalse(fail.called)

    @unittest.skipIf(BASELINE,'candidate full app assembly only')
    def test_actual_app_middleware_and_direct_binding(self):
        from scripts import verify_backend_contract as contract
        original=contract.capture_http_errors
        def check(app):
            result=original(app)
            clients=[TestClient(app,base_url='https://testserver') for _ in range(3)]
            try:
                for client,user in zip(clients[1:],('contract-reader','contract-admin')):
                    self.assertEqual(client.post('/api/auth/login',json={'username':user,'password':'contract-fixture-password-only'}).status_code,200)
                self.assertTrue(app.openapi_schema)
                expected=((404,401,404),(404,403,404),(200,200,200))
                for client,statuses in zip(clients,expected):
                    self.assertEqual(tuple(client.get(path).status_code for path in PATHS),statuses)
            finally:
                for client in clients:
                    client.close()
            return result
        with patch.object(contract,'capture_http_errors',check):
            snapshot=contract.capture()
        self.assertEqual(contract.encoded(snapshot),contract.BASELINE.read_text(encoding='utf-8'))
        from local_inspection_service import server
        self.assertIs(server.require_docs_admin.__self__,server._documentation_access)
        self.assertEqual(server._documentation_access.authenticate,server._authentication.sessions.authenticate_request)
        self.assertEqual(server._documentation_access.users_exist,server._authentication.accounts.users_exist)
        self.assertIs(server._documentation_access.is_admin,server.user_is_admin)
        for path,name in zip(PATHS,NAMES):
            self.assertEqual([r.endpoint for r in server.app.routes if getattr(r,'path',None)==path],[getattr(server,name)])
        selected=server._documentation_access.authenticate
        with patch.object(server,'authenticate_request',Mock(side_effect=AssertionError('rebound root'))):
            self.assertIs(server._documentation_access.authenticate,selected)


if __name__=='__main__':
    unittest.main()
