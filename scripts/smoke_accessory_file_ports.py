"""Accessory upload and provenance ownership using isolated synthetic object stores."""
import asyncio
import ast
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import hashlib
import inspect
import io
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import cv2
import numpy as np
from fastapi import HTTPException, UploadFile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from canonical_application_source_contract import read_checked_application_source
import smoke_detection_artifact_ports as fixtures
from local_inspection_service.storage.artifacts.files import BusinessFiles
from local_inspection_service.storage.artifacts.images import ImageFiles
from local_inspection_service.storage.artifacts.types import ArtifactUnavailable
from local_inspection_service.training.dataset_archives import file_sha256
from local_inspection_service.accessories import creation, image_job_metadata, sprite_render_metadata
from local_inspection_service.accessories.creation import AccessoryCreation
from local_inspection_service.accessories.image_job_metadata import ImageJobMetadata, ProvenanceDependencies
from local_inspection_service.accessories.sprite_render_metadata import SpriteRenderMetadata
from local_inspection_service.accessories.sprite_metadata_ports import SpriteRenderOperations, SpriteImageReads
from local_inspection_service.accessories.mask_geometry import alpha_bbox


class AccessoryFilePortsTests(unittest.TestCase):
    def setUp(self):
        fixtures.DetectionArtifactPortsTests.setUp(self)
        self.default = Mock(side_effect=AssertionError('implicit accessory files'))
        for module in (creation, image_job_metadata, sprite_render_metadata):
            p = patch.object(module, 'BusinessFiles', self.default, create=True); p.start(); self.addCleanup(p.stop)

    def creation_graph(self, index):
        files = BusinessFiles(lambda: self.runtimes[index]); access, store, media, profiles, candidates = [Mock() for _ in range(5)]
        access.current_user.return_value = {'id': str(index)}; access.new_owner_id.return_value = str(index)
        media.upload_directory.return_value = self.root / 'uploads'; media.safe_name.side_effect = str
        media.size_reference.return_value = ''; media.physical_size.return_value = {}
        candidates.create.side_effect = lambda name, material, role, sources, *args: {'id': 'same', 'source_files': sources}
        service = AccessoryCreation(access, store, media, profiles, candidates, Mock(), Mock(), files=files)
        return files, service, profiles, candidates

    def preview(self, service, bodies):
        args = {key: '' for key in inspect.signature(service.preview_accessory).parameters}
        args.update(name='synthetic', material_type='object', material_alpha_policy='opaque',
                    files=[UploadFile(file=io.BytesIO(body), filename=str(i) + '.png') for i, body in enumerate(bodies)])
        return asyncio.run(service.preview_accessory(**args))

    def test_two_uploads_at_identical_paths_remain_owned_by_their_selected_store(self):
        def run(index):
            files, service, profiles, candidates = self.creation_graph(index); body = ('fixture-' + str(index)).encode()
            result = self.preview(service, [body]); path = Path(result['candidate']['source_files'][0])
            self.assertEqual(files.read_bytes(path), body); self.assertFalse(path.exists()); profiles.start_worker.assert_not_called()
            return path
        with patch.object(creation, 'uuid', SimpleNamespace(uuid4=lambda: SimpleNamespace(hex='same'))), ThreadPoolExecutor(max_workers=2) as pool:
            paths = list(pool.map(run, range(2)))
        self.assertEqual(*paths); self.default.assert_not_called()

    def test_second_upload_failure_retains_first_without_candidate_or_worker(self):
        files, service, profiles, candidates = self.creation_graph(0)
        original = self.runtimes[0].store.put_stream; failure = ArtifactUnavailable('synthetic upload failure')
        def put(key, body, **kwargs):
            if key.endswith('/1.png'): raise failure
            return original(key, body, **kwargs)
        with patch.object(creation, 'uuid', SimpleNamespace(uuid4=lambda: SimpleNamespace(hex='same'))), patch.object(self.runtimes[0].store, 'put_stream', side_effect=put) as puts:
            with self.assertRaises(ArtifactUnavailable) as caught: self.preview(service, [b'first', b'second'])
            self.assertIs(caught.exception, failure); self.assertEqual(puts.call_count, 2)
        self.assertEqual(files.read_bytes(self.root / 'uploads/accessory_candidates/src_same/0.png'), b'first')
        candidates.create.assert_not_called(); profiles.start_worker.assert_not_called()

    def test_identity_failure_precedes_any_upload_side_effect(self):
        files, service, profiles, candidates = self.creation_graph(0)
        service.access.current_user.side_effect = HTTPException(401, 'required')
        with patch.object(files, 'copy_stream', wraps=files.copy_stream) as writes:
            with self.assertRaises(HTTPException) as caught: self.preview(service, [b'synthetic'])
            self.assertEqual(caught.exception.status_code, 401); writes.assert_not_called()
        candidates.create.assert_not_called()

    def test_guide_hashes_and_anchor_legacy_order_come_from_the_selected_store(self):
        jobs = []
        for index in range(2):
            files = BusinessFiles(lambda index=index: self.runtimes[index]); anchor = self.root / 'anchor_pose_guides/same.png'; output = self.root / 'outputs/same.png'
            if index == 0: files.write_bytes(output, b'older')
            body = ('anchor-' + str(index)).encode(); files.write_bytes(anchor, body)
            if index == 1: files.write_bytes(output, b'newer')
            rows = self.stores[index].locations.rows
            for path, stamp in ((anchor, 2000000000), (output, 1000000000 if index == 0 else 3000000000)):
                key = self.runtimes[index].key(path); rows[key] = replace(rows[key], mtime_ns=stamp)
            self.assertEqual(files.stat(output).st_mtime < files.stat(anchor).st_mtime, index == 0)
            service = ImageJobMetadata(ProvenanceDependencies(lambda path: file_sha256(path, files=files), lambda: 'policy', lambda: {'lying': [anchor]}, lambda: 8), None, files=files)
            job = {'generation_step': 'anchor_replacement', 'anchor_image_path': str(anchor), 'output_path': str(output), 'pose_family': 'lying'}
            self.assertTrue(service.ensure_anchor_image_provenance(job)); self.assertTrue(service.ensure_image_job_target_guides(job))
            self.assertEqual(job['target_guide_sha256'], {'same.png': hashlib.sha256(body).hexdigest()}); jobs.append(job)
        self.assertEqual(jobs[0]['anchor_provenance'], 'legacy_path_only'); self.assertIsNone(jobs[0]['anchor_image_sha256'])
        self.assertEqual(jobs[1]['anchor_provenance'], 'sha256'); self.assertEqual(jobs[1]['anchor_image_sha256'], hashlib.sha256(b'anchor-1').hexdigest())

    def test_sprite_existence_selects_own_image_or_retains_original_size_fallback(self):
        path = self.root / 'normalized_assets/same.png'; shapes = []
        for index in range(2):
            files = BusinessFiles(lambda index=index: self.runtimes[index]); images = ImageFiles(lambda: cv2, files=files)
            if index == 1: images.imwrite(str(path), np.full((5, 7, 4), 255, np.uint8))
            decode = Mock(side_effect=images.imread)
            ops = SpriteRenderOperations(lambda: alpha_bbox, Mock(), Mock(), Mock(), Mock(), Mock())
            service = SpriteRenderMetadata(ops, SpriteImageReads(lambda: Path, lambda: decode, lambda: cv2.IMREAD_UNCHANGED), files=files)
            shapes.append(service.asset_visible_shape_px({'path': str(path), 'source_object_size_px': [11, 13]}))
            self.assertEqual(decode.call_count, index)
        self.assertEqual(shapes, [(11, 13), (7, 5)])

    def test_missing_none_falsey_dependencies_and_root_bindings(self):
        class Falsey:
            def __bool__(self): raise AssertionError('truthiness checked')
        for cls in (AccessoryCreation, ImageJobMetadata, SpriteRenderMetadata):
            args = {k: Mock() for k in inspect.signature(cls).parameters if k != 'files'}
            with self.assertRaises(TypeError): cls(**args)
            with self.assertRaises(TypeError): cls(**args, files=None)
            port = Falsey(); self.assertIs(cls(**args, files=port).files, port)
        root = Path(__file__).resolve().parents[1]; tree = ast.parse(read_checked_application_source(root / 'local_inspection_service/server.py', encoding='utf-8')); found = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {'AccessoryCreation', 'ImageJobMetadata', '_SpriteRenderMetadata'}:
                if node.func.id == 'ImageJobMetadata' and not node.args:
                    self.assertNotIn('files', [kw.arg for kw in node.keywords]); continue
                values = [kw.value for kw in node.keywords if kw.arg == 'files']; self.assertEqual(len(values), 1)
                self.assertEqual(ast.dump(values[0]), ast.dump(ast.parse('_business_files', mode='eval').body)); found.append(node.func.id)
        self.assertCountEqual(found, ['AccessoryCreation', '_SpriteRenderMetadata'])
        from application_integration_source_contract import verify_actual_compositions
        verify_actual_compositions()
        owner=ast.parse((root/'local_inspection_service/accessories/image_composition.py').read_text())
        calls=[node for node in ast.walk(owner) if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=='ImageJobMetadata']
        self.assertEqual(len(calls),1)
        self.assertEqual(ast.dump(next(kw.value for kw in calls[0].keywords if kw.arg=='files')),ast.dump(ast.parse('files',mode='eval').body))
        assignments={target.id:node.value for node in tree.body if isinstance(node,ast.Assign) for target in node.targets if isinstance(target,ast.Name)}
        self.assertEqual(ast.dump(assignments['_image_job_metadata']),ast.dump(ast.parse('_image_jobs.metadata',mode='eval').body))
        self.assertEqual(ast.dump(next(kw.value for kw in assignments['_image_jobs'].keywords if kw.arg=='files')),ast.dump(ast.parse('_business_files',mode='eval').body))


if __name__ == '__main__': unittest.main()
