"""Text media runtime isolation and retained failure semantics, synthetic stores only."""
import ast
import hashlib
from dataclasses import replace
import inspect
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from canonical_application_source_contract import read_checked_application_source
import smoke_detection_artifact_ports as fixtures
from fastapi import HTTPException
from local_inspection_service.text_inspection.media import TextMedia, TextMediaRecords
from local_inspection_service.storage.artifacts.types import ArtifactUnavailable

def digest(data):return hashlib.sha256(data).hexdigest()

class TextMediaRuntimeTests(unittest.TestCase):
    def setUp(self):fixtures.DetectionArtifactPortsTests.setUp(self)
    def media(self,index):
        return TextMedia(lambda:self.root/'text_inspection_v2',digest,TextMediaRecords(Mock(),Mock()),runtime_provider=lambda:self.runtimes[index])
    def test_same_paths_are_owned_by_independent_stores(self):
        a,b=self.media(0),self.media(1);path=a.media_path('alice','standard','source.bin')
        for owner,data in [(a,b'first'),(b,b'second'),(a,b'updated')]:owner.write(path,data)
        self.assertEqual(a.read_verified(str(path),'alice','standard',expected_sha256=digest(b'updated')),b'updated')
        self.assertEqual(b.read_verified(str(path),'alice','standard'),b'second')
        self.assertFalse(path.exists())
        for media in (a,b):
            with self.assertRaises(HTTPException) as caught:media.read_verified(str(path),'bob','standard')
            self.assertEqual(caught.exception.status_code,404)
    def test_local_hybrid_and_cos_missing_boundaries(self):
        local=TextMedia(lambda:self.root/'text_inspection_v2',digest,TextMediaRecords(Mock(),Mock()),runtime_provider=lambda:None)
        path=local.media_path('alice','standard','source.bin');local.write(path,b'local')
        media=self.media(0)
        with self.assertRaises(HTTPException) as caught:media.read_verified(str(path),'alice','standard')
        self.assertEqual(caught.exception.status_code,404)
        with patch.object(media,'runtime_provider',return_value=replace(self.runtimes[0],mode='hybrid')):
            self.assertEqual(media.read_verified(str(path),'alice','standard'),b'local')
        media.write(path,b'remote')
        with patch.object(media,'runtime_provider',return_value=replace(self.runtimes[0],mode='hybrid')):
            self.assertEqual(media.read_verified(str(path),'alice','standard'),b'remote')
        self.assertEqual(path.read_bytes(),b'local')
    def test_runtime_failure_and_remote_read_failure_never_use_local_bytes(self):
        media=self.media(0);path=media.media_path('alice','standard','source.bin');media.write(path,b'remote')
        path.parent.mkdir(parents=True);path.write_bytes(b'local')
        failure=ArtifactUnavailable('synthetic unavailable')
        with patch.object(self.runtimes[0].store,'read_bytes',side_effect=failure) as read:
            with self.assertRaises(ArtifactUnavailable) as caught:media.read_verified(str(path),'alice','standard')
        self.assertIs(caught.exception,failure);read.assert_called_once()
        media.runtime_provider=Mock(side_effect=failure)
        for call in (lambda:media.write(path,b'new'),lambda:media.read_verified(str(path),'alice','standard')):
            with self.assertRaises(ArtifactUnavailable) as caught:call()
            self.assertIs(caught.exception,failure)
        self.assertEqual(path.read_bytes(),b'local')
    def test_remote_size_digest_and_cached_asset_skip_source(self):
        media=self.media(0);path=media.media_path('alice','standard','source.bin');media.write(path,b'bytes')
        for kwargs in ({'max_bytes':4},{'expected_sha256':'bad'}):
            with self.assertRaises(HTTPException) as caught:media.read_verified(str(path),'alice','standard',**kwargs)
            self.assertEqual(caught.exception.status_code,409)
        asset=dict(media_path=str(path),standard_id='standard',sha256=digest(b'bytes'),asset_kind='manual_page')
        self.assertEqual(media.asset_bytes(asset,'alice'),b'bytes');media.records.owned.assert_not_called();media.records.save.assert_not_called()
    def test_required_provider_and_composition(self):
        class Falsey:
            def __bool__(self):raise AssertionError('provider truthiness')
            def __call__(self):return None
        args=(Mock(),Mock(),TextMediaRecords(Mock(),Mock()))
        with self.assertRaises(TypeError):TextMedia(*args)
        with self.assertRaises(TypeError):TextMedia(*args,runtime_provider=None)
        provider=Falsey();self.assertIs(TextMedia(*args,runtime_provider=provider).runtime_provider,provider)
        tree=ast.parse(read_checked_application_source(Path(__file__).resolve().parents[1] / 'local_inspection_service/server.py', encoding='utf-8'))
        assign=next(n for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='_text_media' for t in n.targets))
        from application_integration_source_contract import verify_actual_compositions
        verify_actual_compositions()
        self.assertEqual(ast.dump(assign.value),ast.dump(ast.parse('_text_standards.media',mode='eval').body))
        standards=next(n.value for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='_text_standards' for t in n.targets))
        media=next(k.value for k in standards.keywords if k.arg=='media')
        self.assertEqual(ast.unparse(media.func),'StandardMediaStorage')
        value=next(k.value for k in media.keywords if k.arg=='runtime_provider')
        self.assertEqual(ast.dump(value),ast.dump(ast.parse('_business_files.runtime_provider',mode='eval').body))
        owner=ast.parse((Path(__file__).resolve().parents[1]/'local_inspection_service/text_inspection/standard_composition.py').read_text())
        calls=[n for n in ast.walk(owner) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='TextMedia']
        self.assertEqual(len(calls),1)
        self.assertEqual(ast.dump(next(k.value for k in calls[0].keywords if k.arg=='runtime_provider')),ast.dump(ast.parse('media.runtime_provider',mode='eval').body))

if __name__=='__main__':unittest.main()
