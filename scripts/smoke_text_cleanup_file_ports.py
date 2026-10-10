"""Text cleanup ownership, conflict retention and partial failure with synthetic stores."""
import ast
import asyncio
import copy
import hashlib
import inspect
import io
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import Mock, patch
from PIL import Image
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from canonical_application_source_contract import read_checked_application_source
import smoke_detection_artifact_ports as fixtures
from smoke_text_standards import Fixture, StandardMedia
from local_inspection_service.storage.artifacts.files import BusinessFiles
from local_inspection_service.storage.artifacts.types import ArtifactUnavailable
from local_inspection_service.text_inspection import extraction_api
from local_inspection_service.text_inspection.extraction_ports import ExtractionAccess, ExtractionRecords, ExtractionMedia, ExtractionModels
from local_inspection_service.text_inspection.standard_edits import StandardEdits


class TextCleanupFilePortsTests(unittest.TestCase):
    def setUp(self): fixtures.DetectionArtifactPortsTests.setUp(self)

    def graph(self, index, *, expired=True, lose=False):
        files = BusinessFiles(lambda: self.runtimes[index]); root = self.root/'text_inspection_v2'
        source = root/'alice/root/source.png'; buffer = io.BytesIO(); Image.new('RGB', (300, 200), (40+index*80, 60, 100)).save(buffer, 'PNG'); data = buffer.getvalue()
        files.write_bytes(source, data); records = {('extractions', 'root'): {'id': 'root', 'root_id': 'root', 'kind': 'task', 'owner_user_id': 'alice', 'version': 0, 'status': 'needs_adjustment', 'created_at': int(time.time())-(8*86400 if expired else 0), 'source_path': str(source), 'source_sha256': hashlib.sha256(data).hexdigest(), 'diagnostics': {}}}
        def load(kind): return [copy.deepcopy(value) for (key, _), value in records.items() if key == kind]
        def owned(kind, key, owner):
            value = records.get((kind, key)); return copy.deepcopy(value) if value and value['owner_user_id'] == owner else None
        def save(kind, value, **kwargs):
            if lose and value['kind'] == 'revision': return False
            records[kind, value['id']] = copy.deepcopy(value); return True
        media = ExtractionMedia(lambda owner, identifier, name: root/owner/identifier/name, files.write_bytes, lambda path, *args, **kwargs: files.read_bytes(Path(path)), lambda contents: hashlib.sha256(contents).hexdigest(), Mock())
        models = ExtractionModels(lambda: {}, lambda purpose: {}, Mock(), Mock(), lambda value: value, lambda: False)
        app = FastAPI(); extraction_api.register(app, ExtractionAccess(lambda *a, **kw: None, lambda: ('alice','synthetic')), ExtractionRecords(lambda: None, owned, load, save), media, models, Mock(), files=files)
        client = TestClient(app, raise_server_exceptions=False); self.addCleanup(client.close)
        return files, source, records, client, data

    def test_expiry_deletes_only_the_selected_store_and_lowercase_png(self):
        first, second = self.graph(0), self.graph(1)
        files, source, records, client, data = first
        keep = source.with_name('keep.txt'); upper = source.with_name('keep.PNG')
        files.write_bytes(keep, b'synthetic'); files.write_bytes(upper, data)
        self.assertEqual(client.get('/api/text-inspection/extraction-capabilities').status_code, 200)
        self.assertFalse(files.exists(source)); self.assertTrue(files.exists(keep)); self.assertTrue(files.exists(upper))
        self.assertTrue(second[0].exists(second[1])); self.assertNotIn(('extractions','root_v1'), second[2])
        self.assertEqual(records['extractions','root_v1']['status'], 'expired')

    def test_delete_failure_retains_expired_tombstone_and_source(self):
        files, source, records, client, data = self.graph(0); failure = ArtifactUnavailable('synthetic expiry delete')
        with patch.object(self.runtimes[0].store, 'remove', side_effect=failure):
            self.assertEqual(client.get('/api/text-inspection/extraction-capabilities').status_code, 500)
        self.assertEqual(records['extractions','root_v1']['status'], 'expired'); self.assertTrue(files.exists(source))

    def test_losing_remote_revision_retains_new_bytes_without_overwriting_root(self):
        files, source, records, client, data = self.graph(0, expired=False, lose=True)
        response = client.post('/api/text-inspection/extractions/root/revise', json={'version':0,'polygon':[[.1,.1],[.9,.1],[.9,.9],[.1,.9]]})
        self.assertEqual(response.status_code, 409)
        paths = list(files.glob(source.parent, '*.png')); self.assertEqual(len(paths), 2)
        self.assertEqual(files.read_bytes(source), data); self.assertNotIn(('extractions','root_v1'), records)
        self.assertTrue(all(not path.exists() for path in paths))

    def test_standard_failure_retains_remote_bytes_and_cleanup_failure_propagates(self):
        for index, original in enumerate((HTTPException(418, 'synthetic conflict'), RuntimeError('synthetic edit failure'))):
            files = BusinessFiles(lambda index=index: self.runtimes[index]); f = Fixture(self.root/'text_inspection_v2'); f.seed()
            path = self.root/'text_inspection_v2/alice/std/new.png'; f.edits.files = files
            f.edits.media = StandardMedia(lambda *args: path, lambda: files.write_bytes, lambda data: hashlib.sha256(data).hexdigest())
            f.repo = Mock(); f.repo.add_text_inspection_standard_asset.side_effect = original
            with self.assertRaises(HTTPException) as caught: f.add()
            self.assertEqual(caught.exception.status_code, 418 if index == 0 else 409); self.assertEqual(files.read_bytes(path), b'image')
            cleanup = ArtifactUnavailable('synthetic cleanup runtime')
            with patch.object(files, 'runtime', side_effect=cleanup):
                # Use an independent successful media writer to reach the cleanup decision.
                f.edits.media = StandardMedia(lambda *args: path, lambda: lambda *args: None, lambda data: 'synthetic')
                with self.assertRaises(ArtifactUnavailable) as caught: f.add()
                self.assertIs(caught.exception, cleanup)

    def test_required_ports_fail_before_routes_and_accept_falsey_owners(self):
        class Falsey:
            def __bool__(self): raise AssertionError('truthiness checked')
        app = FastAPI(); before = len(app.routes); args = [app] + [Mock() for _ in range(5)]
        with self.assertRaises(TypeError): extraction_api.register(*args)
        with self.assertRaises(TypeError): extraction_api.register(*args, files=None)
        self.assertEqual(len(app.routes), before)
        files = Falsey(); extraction_api.register(*args, files=files); self.assertGreater(len(app.routes), before)
        kwargs = {name: Mock() for name in inspect.signature(StandardEdits).parameters if name != 'files'}
        with self.assertRaises(TypeError): StandardEdits(**kwargs)
        with self.assertRaises(TypeError): StandardEdits(**kwargs, files=None)
        self.assertIs(StandardEdits(**kwargs, files=files).files, files)
        root = Path(__file__).resolve().parents[1]/'local_inspection_service'
        def keyword(tree, name, field):
            calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id==name]
            self.assertEqual(len(calls),1,name)
            return next(k.value for k in calls[0].keywords if k.arg==field)
        tree=ast.parse(read_checked_application_source(root / 'server.py', encoding='utf-8'))
        media=keyword(tree,'TextStandardWorkflows','media')
        self.assertEqual(ast.dump(next(k.value for k in media.keywords if k.arg=='files')),ast.dump(ast.parse('_business_files',mode='eval').body))
        self.assertEqual(ast.dump(keyword(tree,'TextComparisonWorkflows','files')),ast.dump(ast.parse('_business_files',mode='eval').body))
        standard=ast.parse((root/'text_inspection/standard_composition.py').read_text(encoding='utf-8'))
        comparison=ast.parse((root/'text_inspection/comparison_composition.py').read_text(encoding='utf-8'))
        self.assertEqual(ast.dump(keyword(standard,'StandardEdits','files')),ast.dump(ast.parse('media.files',mode='eval').body))
        self.assertEqual(ast.dump(keyword(comparison,'register_extraction','files')),ast.dump(ast.parse('self.files',mode='eval').body))
        assignment=[n for n in ast.walk(comparison) if isinstance(n,ast.Assign) and any(ast.dump(t)==ast.dump(ast.parse('self.files = files').body[0].targets[0]) for t in n.targets)]
        self.assertEqual(len(assignment),1)
        self.assertEqual(ast.dump(assignment[0].value),ast.dump(ast.parse('files',mode='eval').body))


if __name__ == '__main__': unittest.main()
