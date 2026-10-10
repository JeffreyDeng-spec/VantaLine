"""Explicit storage for accessory edits, retaining partial failure semantics."""
import ast
import asyncio
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
import sys
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
from local_inspection_service.accessories.files import AccessoryFiles


class AccessoryEditPortsTests(unittest.TestCase):
    def setUp(self):
        fixtures.DetectionArtifactPortsTests.setUp(self)

    def graph(self, index):
        files = BusinessFiles(lambda: self.runtimes[index]); images = ImageFiles(lambda: cv2, files=files)
        source = self.root / 'uploads/accessories/same/source.png'; pixels = np.full((30, 40, 3), 40 + index * 100, np.uint8)
        images.imwrite(str(source), pixels)
        item = {'id': 'same', 'material_type': 'text', 'source_files': [str(source)]}; config = {'accessories': [item]}
        events = []
        access, store, media, profiles, projection = [Mock() for _ in range(5)]
        access.current_user.return_value = {'id': str(index)}; access.require_access.side_effect = lambda *a, **k: events.append('access')
        store.load_config.return_value = config; store.scope_config.side_effect = lambda cfg, user: cfg; store.save_item.side_effect = lambda *a: events.append('save')
        media.upload_directory.return_value = self.root / 'uploads'; media.data_directory.return_value = self.root
        media.safe_name.side_effect = lambda name: name; media.image_suffixes.return_value = {'.png'}; media.text_source_count.return_value = 1
        media.existing_source_paths.side_effect = lambda value: [Path(p) for p in value['source_files']]
        media.is_rectified.return_value = False; media.crop_stem.return_value = 'source'
        media.detail.side_effect = lambda value: {'gallery': [{'source_path': p} for p in value['source_files']]}
        media.image_jobs.return_value = []; media.clean_sprites.return_value = []
        profiles.refresh.side_effect = lambda *a, **k: events.append('refresh'); profiles.save_cache.side_effect = lambda *a: events.append('cache'); profiles.fallback.return_value = {'synthetic': True}
        projection.serialize_accessory_summary.side_effect = lambda value: dict(value); projection.serialize_accessory_items.side_effect = lambda value: value
        service = AccessoryFiles(access, store, media, profiles, projection, files=files, images=images)
        return service, files, images, source, item, events

    def test_upload_and_crop_use_only_their_storage_owner(self):
        graphs = [self.graph(i) for i in range(2)]
        corners = [{'x': 0, 'y': 0}, {'x': 100, 'y': 0}, {'x': 100, 'y': 100}, {'x': 0, 'y': 100}]
        outputs = []
        for index, (service, files, images, source, item, events) in enumerate(graphs):
            uploaded = UploadFile(filename='added.png', file=BytesIO(('owner-' + str(index)).encode()))
            try: asyncio.run(service.add_accessory_files('same', [uploaded]))
            finally: uploaded.file.close()
            self.assertEqual(files.read_bytes(source.parent / 'added.png'), ('owner-' + str(index)).encode())
            result = service.crop_accessory_text_image('same', SimpleNamespace(source_path=str(source), corners=corners))
            output = Path(result['source_path']); outputs.append(output)
            cropped = images.imread(str(output), cv2.IMREAD_COLOR)
            self.assertEqual(cropped.shape, (30, 40, 3))
            np.testing.assert_array_equal(cropped[2:-2, 2:-2], np.full((26, 36, 3), 40 + index * 100, np.uint8))
            self.assertEqual(events, ['access', 'refresh', 'cache', 'save'] * 2)
            self.assertFalse(output.exists())
        self.assertEqual(*outputs)
        again = graphs[0][0].crop_accessory_text_image('same', SimpleNamespace(source_path=str(graphs[0][3]), corners=corners))
        self.assertTrue(again['source_path'].endswith('_1.png'))
        self.assertFalse(graphs[1][1].exists(Path(again['source_path'])))

    def test_reference_selection_and_delete_are_owner_specific(self):
        graphs = [self.graph(i) for i in range(2)]; service, files, images, source, item, events = graphs[0]
        service.set_accessory_ai_reference('same', SimpleNamespace(source_path=str(source)))
        self.assertEqual(item['ai_profile_reference_files'], [str(source)]); self.assertNotIn('ai_profile_reference_files', graphs[1][4])
        service.delete_accessory_file('same', SimpleNamespace(source_path=str(source)))
        self.assertFalse(files.exists(source)); self.assertTrue(graphs[1][1].exists(source)); self.assertEqual(item['source_files'], [])
        self.assertEqual(graphs[1][4]['source_files'], [str(source)])

    def test_second_upload_failure_keeps_first_file_before_record_mutation(self):
        service, files, images, source, item, events = self.graph(0)
        original = self.runtimes[0].store.put_stream; calls = []; failure = ArtifactUnavailable('synthetic second upload')
        def put(*args, **kwargs):
            calls.append(1)
            if len(calls) == 2: raise failure
            return original(*args, **kwargs)
        uploads = [UploadFile(filename=name, file=BytesIO(name.encode())) for name in ('first.png', 'second.png')]
        try:
            with patch.object(self.runtimes[0].store, 'put_stream', side_effect=put):
                with self.assertRaises(ArtifactUnavailable) as caught: asyncio.run(service.add_accessory_files('same', uploads))
                self.assertIs(caught.exception, failure)
        finally:
            for upload in uploads: upload.file.close()
        self.assertEqual(files.read_bytes(source.parent / 'first.png'), b'first.png'); self.assertFalse(files.exists(source.parent / 'second.png'))
        self.assertEqual(item['source_files'], [str(source)]); self.assertEqual(events, ['access'])

    def test_unlink_failure_preserves_preceding_record_mutation(self):
        service, files, images, source, item, events = self.graph(0)
        failure = ArtifactUnavailable('synthetic unlink failure')
        with patch.object(files, 'unlink', side_effect=failure):
            with self.assertRaises(ArtifactUnavailable) as caught: service.delete_accessory_file('same', SimpleNamespace(source_path=str(source)))
            self.assertIs(caught.exception, failure)
        self.assertEqual(item['source_files'], []); self.assertTrue(files.exists(source)); self.assertEqual(events, ['access'])

    def test_required_falsey_ports_and_root_binding(self):
        class Falsey:
            def __bool__(self): raise AssertionError('truthiness checked')
        args = [Mock() for _ in range(5)]
        with self.assertRaises(TypeError): AccessoryFiles(*args)
        files, images = Falsey(), Falsey()
        for ports in ({'files': None, 'images': images}, {'files': files, 'images': None}):
            with self.assertRaises(TypeError): AccessoryFiles(*args, **ports)
        service = AccessoryFiles(*args, files=files, images=images); self.assertIs(service.files, files); self.assertIs(service.images, images)
        tree = ast.parse(read_checked_application_source(Path(__file__).resolve().parents[1] / 'local_inspection_service/server.py', encoding='utf-8'))
        calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == 'AccessoryFiles']; self.assertEqual(len(calls), 1)
        for field, name in [('files', '_business_files'), ('images', '_accessory_image_io')]:
            values = [kw.value for kw in calls[0].keywords if kw.arg == field]; self.assertEqual(len(values), 1)
            self.assertEqual(ast.dump(values[0]), ast.dump(ast.parse(name, mode='eval').body))


if __name__ == '__main__': unittest.main()
