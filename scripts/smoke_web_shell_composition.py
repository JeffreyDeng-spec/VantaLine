"""Public shell response and per-application routing contracts, without workers."""
import ast
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local_inspection_service.runtime.web_shell import WebShell, register_entry_routes, register_spa

BASELINE = os.environ.get("VANTALINE_WEB_SHELL_BASELINE_SOURCE")


class WebShellContract(unittest.TestCase):
    def setUp(self):
        self.state = dict(directory=Path('/fixture'), routes={'workspace', 'docs', 'login', 'tasks'},
                          blocked=('/api/', '/outputs/', '/static/', '/legacy'), enabled=True, exists=True)
        self.calls = []
        def get(key):
            self.calls.append(key)
            return self.state[key]
        def exists(path):
            self.calls.append(('exists', path))
            return self.state['exists']
        self.shell = WebShell(lambda: get('directory'), exists, lambda: get('routes'),
                              lambda: get('blocked'), lambda: get('enabled'))
        if BASELINE:
            nodes = [n for n in ast.parse(Path(BASELINE).read_text(encoding='utf-8')).body
                     if isinstance(n, ast.FunctionDef) and n.name in
                     ('index', 'legacy_index', 'react_preview', 'react_production_spa')]
            self.assertEqual(len(nodes), 4)
            replacements = {'REACT_PRODUCTION_DIST_DIR': "get('directory')",
                            'REACT_PRODUCTION_ROUTE_SEGMENTS': "get('routes')",
                            'REACT_PRODUCTION_BLOCKED_PREFIXES': "get('blocked')"}
            class Bind(ast.NodeTransformer):
                def visit_Name(self, node):
                    return ast.copy_location(ast.parse(replacements[node.id], mode='eval').body, node) if node.id in replacements else node
            for n in nodes:
                n.decorator_list = []
                Bind().visit(n)
            namespace = dict(FileResponse=FileResponse, RedirectResponse=RedirectResponse, Request=Request,
                             HTTPException=HTTPException, get=get,
                             react_production_spa_enabled=lambda: get('enabled'),
                             _business_files=SimpleNamespace(exists=exists))
            exec(compile(ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])), BASELINE, 'exec'), namespace)
            self.shell = SimpleNamespace(**{n.name: namespace[n.name] for n in nodes})

    def test_constructor_is_inert_and_index_headers_and_live_directory(self):
        self.assertEqual(self.calls, [])
        for directory in (Path('/a'), Path('/b')):
            self.state['directory'] = directory
            result = self.shell.index()
            self.assertEqual(result.path, directory/'index.html')
            self.assertEqual(result.headers['pragma'], 'no-cache')
            self.assertEqual(result.headers['cache-control'], 'no-store, no-cache, must-revalidate, max-age=0')

    def test_distinct_missing_index_errors(self):
        self.state['exists'] = False
        for invoke, message in ((self.shell.index, 'React production build is not available'),
                                (lambda: self.shell.react_production_spa('workspace'), 'Production React build is not available')):
            with self.assertRaises(HTTPException) as error: invoke()
            self.assertEqual((error.exception.status_code, error.exception.detail), (404, message))

    def test_disabled_short_circuits_path_and_files(self):
        self.state['enabled'] = False
        with self.assertRaises(HTTPException): self.shell.react_production_spa(object())
        self.assertEqual(self.calls, ['enabled'])

    def test_blocked_unknown_and_root_never_read_files(self):
        for path in ('', '/', 'api/private', 'outputs/picture.png', 'static/app.js', 'unknown'):
            self.calls.clear()
            with self.assertRaises(HTTPException): self.shell.react_production_spa(path)
            self.assertNotIn('directory', self.calls)
            self.assertFalse(any(isinstance(c, tuple) for c in self.calls))

    def test_live_allowlist_and_order(self):
        self.state['routes'] = {'new'}
        self.assertEqual(self.shell.react_production_spa('/new/x/').path, Path('/fixture/index.html'))
        self.assertEqual(self.calls, ['enabled', 'blocked', 'routes', 'directory', ('exists', Path('/fixture/index.html'))])

    def test_preview_query_preserved_and_known_routes_short_circuit(self):
        request = Request({'type':'http', 'scheme':'https', 'server':('example',443), 'path':'/',
                           'query_string':b'x=%2F&x=2', 'headers':[]})
        for path, target in (('', '/workspace'), ('/docs/a/', '/docs/a'), ('tasks/a', '/workspace/tasks/a')):
            result = self.shell.react_preview(request, path)
            self.assertEqual(result.status_code, 307)
            self.assertEqual(result.headers['location'], target+'?x=%2F&x=2')
        self.assertEqual(self.calls, ['routes'])
        with self.assertRaises(HTTPException): self.shell.react_preview(request, 'api/status')

    def test_legacy_always_unavailable_without_providers(self):
        with self.assertRaises(HTTPException) as error: self.shell.legacy_index('anything')
        self.assertEqual(error.exception.detail, 'Legacy frontend has been removed')
        self.assertEqual(self.calls, [])

    @unittest.skipIf(BASELINE, 'new registrar ownership')
    def test_two_real_route_sets_keep_api_precedence_and_separate_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            clients = []
            for name in ('first', 'second'):
                directory = Path(temporary)/name
                directory.mkdir()
                (directory/'index.html').write_text(name)
                shell = WebShell(lambda p=directory:p, Path.exists, lambda:{'workspace'}, lambda:('/api/',), lambda:True)
                app = FastAPI()
                register_entry_routes(app, shell)
                @app.get('/api/probe')
                def probe(): return {'ok':True}
                register_spa(app, shell)
                clients.append(TestClient(app))
            for name, client in zip(('first','second'), clients):
                self.assertEqual(client.get('/workspace').text, name)
                self.assertEqual(client.get('/api/probe').json(), {'ok':True})
                self.assertEqual(client.get('/api/missing').status_code, 404)
            self.assertEqual(clients[0].get('/').text, 'first')


if __name__ == '__main__':
    unittest.main()
