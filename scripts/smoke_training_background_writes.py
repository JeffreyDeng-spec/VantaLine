"""Synthetic background generation and write contracts; all deletion is confined to owned temporary roots."""
from contextlib import ExitStack
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, call, patch
import cv2
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class TracedRNG:
    def __init__(self, rng): self.rng = rng; self.calls = []
    def __getattr__(self, name):
        def invoke(*args, **kwargs):
            self.calls.append([name, args, kwargs])
            return getattr(self.rng, name)(*args, **kwargs)
        return invoke


class TrainingBackgroundWriteContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.environment = patch.dict(os.environ); cls.environment.start()
        cls.runtime = tempfile.TemporaryDirectory(prefix='background-writes-root-')
        root = Path(cls.runtime.name); (root / 'local_inspection_service/static').mkdir(parents=True)
        os.environ.update(LOCAL_INSPECTION_ROOT=str(root), VANTALINE_DATA_STORE='json',
                          LOCAL_INSPECTION_AUTO_RESUME_WORKER='0', VANTALINE_LABEL_INSPECTION_ENABLED='false')
        from local_inspection_service import server
        cls.api = server
    @classmethod
    def tearDownClass(cls): cls.runtime.cleanup(); cls.environment.stop()
    def setUp(self):
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory(prefix='background-writes-'))).resolve()
        self.sets = self.root / 'sets'; self.source = self.root / 'source.gif'; self.source.write_bytes(b'raw source bytes')
        self.manifest = {'sets': {}}; self.saved = []; self.events = []
        self.clock = Mock(return_value=101.001)
        self.load = Mock(side_effect=lambda: self.events.append('load') or self.manifest)
        self.write = Mock(side_effect=lambda value: self.events.append('write') or self.saved.append(value))
        self.sanitize = Mock(return_value='fixture'); self.fallback = Mock(return_value='fallback')
        self.payload = Mock(side_effect=lambda identifier, meta: {'projected': identifier, 'meta': meta})
        for name, value in {'BACKGROUND_SETS_DIR': self.sets, 'LEGACY_OWNER_ID': 'legacy-fixture',
                            'load_background_sets_manifest': self.load, 'write_background_sets_manifest': self.write,
                            'sanitize_ai_detection_task_id': self.sanitize, 'safe_record_id': self.fallback,
                            'background_set_payload': self.payload, 'IMAGE_REFERENCE_SUFFIXES': {'.png', '.jpg'}}.items():
            self.stack.enter_context(patch.object(self.api, name, value))
        self.stack.enter_context(patch('time.time', self.clock))
        for target in ['requests.request', 'subprocess.Popen', 'os.kill']:
            self.stack.enter_context(patch(target, side_effect=AssertionError('unexpected external operation')))
        original_rmtree = shutil.rmtree
        def contained_rmtree(path, *args, **kwargs):
            resolved = Path(path).resolve()
            if not resolved.is_relative_to(self.root): raise AssertionError('delete outside owned fixture: ' + str(resolved))
            self.events.append('remove'); return original_rmtree(path, *args, **kwargs)
        self.stack.enter_context(patch.object(shutil, 'rmtree', side_effect=contained_rmtree))
    def input_image(self):
        y, x = np.indices((31, 47)); image = np.stack([(x * 7 + y * 3) % 256, (x * 11 + y * 5) % 256, (x * 3 + y * 13) % 256], axis=-1).astype(np.uint8)
        path = self.root / 'fixture.png'; self.assertTrue(cv2.imwrite(str(path), image)); return path, image
    def render_signature(self):
        source, _ = self.input_image(); generators = []; original = np.random.default_rng
        def factory(seed): value = TracedRNG(original(seed)); generators.append(value); return value
        with patch.object(np.random, 'default_rng', side_effect=factory) as random:
            paths = self.api.create_background_variants_from_source(source, self.root / 'variants', 3)
        self.assertEqual(random.call_args, call(int(101.001 * 1000) % (2**32 - 1)))
        self.assertEqual(len(generators), 1)
        return {'names': [path.name for path in paths],
                'pixels': [hashlib.sha256(cv2.imread(str(path)).tobytes()).hexdigest() for path in paths],
                'rng_calls': json.loads(json.dumps(generators[0].calls)),
                'rng_state': generators[0].rng.bit_generator.state}
    def test_variants_original_pixel_and_rng_golden(self):
        expected = json.loads((Path(__file__).resolve().parents[1] / 'tests/backend_contract/training_background_variants.json').read_text(encoding='utf-8'))
        self.assertEqual(self.render_signature(), expected['signature'])
    def test_variants_missing_image_and_nonpositive_count_side_effect_order(self):
        with patch.object(cv2, 'imread', return_value=None), patch.object(np.random, 'default_rng') as random:
            self.assertEqual(self.api.create_background_variants_from_source(self.source, self.root / 'missing'), [])
            self.assertFalse((self.root / 'missing').exists()); self.clock.assert_not_called(); random.assert_not_called()
        source, _ = self.input_image()
        for count in [0, -2]:
            directory = self.root / ('count-' + str(count)); self.clock.reset_mock()
            with patch.object(np.random, 'default_rng', wraps=np.random.default_rng) as random:
                self.assertEqual(self.api.create_background_variants_from_source(source, directory, count), [])
                self.assertTrue(directory.is_dir()); self.clock.assert_called_once(); random.assert_called_once()
    def test_variants_strict_noise_boundary_and_rng_call_counts(self):
        source, image = self.input_image()
        for chance in [0.7999, 0.8]:
            rng = Mock(); rng.random.return_value = chance
            rng.uniform.side_effect = lambda low, high: 1.0 if low in (0.94, 1.0) else (0.03 if low == 0.025 else 0.0)
            rng.normal.side_effect = lambda mean, scale, **kwargs: np.zeros(kwargs['size']) if 'size' in kwargs else 0.0
            rng.integers.side_effect = lambda low, high: 5 if low == 5 else (100 if low == 45 else 0)
            with patch.object(np.random, 'default_rng', return_value=rng), patch.object(cv2, 'resize', wraps=cv2.resize) as resize:
                result = self.api.create_background_variants_from_source(source, self.root / str(chance), 1)
                self.assertEqual(len(result), 1); self.assertEqual(resize.call_args.args[1], (47, 31)); self.assertEqual(resize.call_args.kwargs, {'interpolation': cv2.INTER_AREA})
            self.assertEqual(rng.uniform.call_count, 5 if chance < 0.8 else 4)
            self.assertEqual(rng.normal.call_count, 11 if chance < 0.8 else 10); self.assertEqual(rng.integers.call_count, 18)
            self.assertEqual(sum('size' in c.kwargs for c in rng.normal.call_args_list), int(chance < 0.8))
            self.assertTrue(np.array_equal(cv2.imread(str(source)), image))
    def test_variants_false_writes_still_return_paths_and_partial_error_never_retries(self):
        source, _ = self.input_image(); directory = self.root / 'false'
        with patch.object(cv2, 'imwrite', return_value=False) as write:
            result = self.api.create_background_variants_from_source(source, directory, 2)
            self.assertEqual(result, [directory / 'fixture_variant_01.png', directory / 'fixture_variant_02.png']); self.assertEqual(write.call_count, 2)
            self.assertEqual(list(directory.iterdir()), [])
        original = cv2.imwrite; error = OSError('second write'); directory = self.root / 'partial'
        def partial(*args, **kwargs):
            result = original(*args, **kwargs)
            if write.call_count == 2: raise error
            return result
        with patch.object(cv2, 'imwrite', side_effect=partial) as write:
            with self.assertRaises(OSError) as caught: self.api.create_background_variants_from_source(source, directory, 3)
            self.assertIs(caught.exception, error); self.assertEqual(write.call_count, 2)
        self.assertEqual(sorted(path.name for path in directory.iterdir()), ['fixture_variant_01.png', 'fixture_variant_02.png'])
    def test_minimum_short_circuits_uses_first_file_and_does_not_recount(self):
        for images, minimum, expected in [([], 6, None), ([Path('z')], 1, None), ([Path('z'), Path('a')], 6, 4)]:
            with patch.object(self.api, 'image_file_list', return_value=images) as files, patch.object(self.api, 'create_background_variants_from_source', return_value=[]) as create:
                self.assertIsNone(self.api.ensure_background_set_minimum_images(' raw set ', minimum))
                files.assert_called_once_with(self.sets / 'raw_set')
                if expected is None: create.assert_not_called()
                else: create.assert_called_once_with(images[0], self.sets / 'raw_set', expected)
    def test_unique_manifest_collision_short_circuit_and_fifty_candidate_fallback(self):
        self.manifest = {'sets': {}}
        with patch('uuid.uuid4') as uuid:
            self.assertEqual(self.api.unique_background_set_id(' raw name '), 'raw_name'); uuid.assert_not_called(); self.clock.assert_not_called()
        self.manifest = {'sets': {'raw_name': {}, 'raw_name_abcdef': {}}}
        with patch('uuid.uuid4', return_value=SimpleNamespace(hex='abcdef1234')) as uuid, patch.object(Path, 'exists', side_effect=AssertionError('manifest collision should short circuit')):
            self.assertEqual(self.api.unique_background_set_id(' raw name '), 'raw_name_101')
            self.assertEqual(uuid.call_count, 50); self.clock.assert_called_once_with()
        self.clock.reset_mock(); self.sets.mkdir(); (self.sets / 'fresh').mkdir(); self.manifest = {'sets': []}
        with patch('uuid.uuid4', return_value=SimpleNamespace(hex='aabbcc1234')) as uuid:
            self.assertEqual(self.api.unique_background_set_id('fresh'), 'fresh_aabbcc'); uuid.assert_called_once(); self.clock.assert_not_called()
    def test_update_manifest_raw_key_empty_record_id_override_and_aliases(self):
        current = {}; self.manifest = {'sets': {' raw/key ': current}, 'default_set_id': None}; shared = []
        with patch.object(self.api, 'safe_background_set_id', side_effect=AssertionError('must not sanitize update key')):
            result = self.api.update_background_set_manifest(' raw/key ', id='override', shared=shared)
        self.assertIs(result, current); self.assertIs(result['shared'], shared); self.assertNotIn('name', result)
        self.assertIs(self.manifest['sets'][' raw/key '], current); self.assertIsNone(self.manifest['default_set_id']); self.write.assert_called_once_with(self.manifest)
        self.manifest = {'sets': []}; result = self.api.update_background_set_manifest('raw_key', note='value')
        self.assertEqual(result, {'id': 'raw_key', 'name': 'raw key', 'note': 'value'}); self.assertEqual(self.manifest['default_set_id'], 'green_conveyor')
    def test_update_manifest_failure_keeps_mutation_and_invalid_current_is_not_repaired(self):
        current = {'id': 'x'}; self.manifest = {'sets': {'x': current}}; error = OSError('manifest write')
        self.write.side_effect = [error, None]
        with self.assertRaises(OSError) as caught: self.api.update_background_set_manifest('x', status='new')
        self.assertIs(caught.exception, error); self.write.assert_called_once(); self.assertEqual(current, {'id': 'x', 'status': 'new'})
        self.assertEqual(self.manifest['default_set_id'], 'green_conveyor')
        self.manifest = {'sets': {'x': None}}; self.write.reset_mock()
        with self.assertRaises(AttributeError): self.api.update_background_set_manifest('x', status='new')
        self.write.assert_not_called()
    def test_environment_replacement_exact_metadata_two_clocks_and_unknown_suffix_bytes(self):
        directory = self.sets / 'task_env_fixture'; self.assertTrue(directory.resolve().is_relative_to(self.root))
        directory.mkdir(parents=True); (directory / 'old.png').write_bytes(b'old')
        self.clock.side_effect = [11.9, 22.9]
        def variants(source, target, *, count):
            self.events.append('variants'); self.assertEqual(source.read_bytes(), b'raw source bytes')
            self.assertFalse((target / 'old.png').exists()); (target / 'variant.png').write_bytes(b'variant'); return []
        with patch.object(self.api, 'create_background_variants_from_source', side_effect=variants) as create:
            result = self.api.save_task_environment_background_set(' raw task ', self.source, {'id': 123, 'username': '', 'name': 'fallback name'}, '   ')
            create.assert_called_once_with(directory / 'source.jpg', directory, count=5)
        self.assertEqual((directory / 'source.jpg').read_bytes(), b'raw source bytes'); self.sanitize.assert_called_once_with(' raw task '); self.fallback.assert_not_called()
        meta = self.manifest['sets']['task_env_fixture']
        self.assertEqual(meta, {'id': 'task_env_fixture', 'name': '   ', 'description': '用户首次检测前通过摄像头采集的空白生产环境背景',
            'source': str(directory / 'source.jpg'), 'created_at': 11, 'updated_at': 22, 'status': 'ready', 'image_count': 2,
            'generation_method': 'camera_empty_environment_local_variants', 'owner_user_id': '123', 'owner_username': 'fallback name', 'shared_with_user_ids': []})
        self.assertEqual(self.events, ['remove', 'variants', 'load', 'write']); self.assertIs(result['meta'], meta)
        self.payload.assert_called_once_with('task_env_fixture', meta)
    def test_environment_fallback_id_empty_count_legacy_owner_and_preserved_png_suffix(self):
        self.sanitize.return_value = ''; source = self.root / 'image.PNG'; source.write_bytes(b'unchanged PNG bytes')
        with patch.object(self.api, 'create_background_variants_from_source', return_value=[]) as create, patch.object(self.api, 'image_file_list', return_value=[]) as files:
            result = self.api.save_task_environment_background_set('raw', source, {})
            directory = self.sets / 'task_env_fallback'; create.assert_called_once_with(directory / 'source.png', directory, count=5); files.assert_called_once_with(directory)
        self.fallback.assert_called_once_with('raw'); meta = result['meta']
        self.assertEqual((meta['name'], meta['owner_user_id'], meta['owner_username'], meta['status'], meta['image_count']), ('任务空场景背景 · fallback', 'legacy-fixture', '', 'empty', 0))
        self.assertEqual((directory / 'source.png').read_bytes(), b'unchanged PNG bytes')
    def test_environment_source_inside_replaced_directory_is_deleted_before_copy_failure(self):
        directory = self.sets / 'task_env_fixture'; self.assertTrue(directory.resolve().is_relative_to(self.root))
        directory.mkdir(parents=True); source = directory / 'source.png'; source.write_bytes(b'old source')
        with patch.object(self.api, 'create_background_variants_from_source') as create:
            with self.assertRaises(FileNotFoundError): self.api.save_task_environment_background_set('raw', source, {})
            create.assert_not_called()
        self.assertTrue(directory.is_dir()); self.assertEqual(list(directory.iterdir()), []); self.assertEqual(self.events, ['remove'])
        self.clock.assert_not_called(); self.load.assert_not_called(); self.write.assert_not_called(); self.payload.assert_not_called()
    def test_environment_second_clock_failure_keeps_files_without_metadata_or_retry(self):
        error = OSError('second clock'); self.clock.side_effect = [11.9, error, 99]
        with patch.object(self.api, 'create_background_variants_from_source', return_value=[]) as create:
            with self.assertRaises(OSError) as caught: self.api.save_task_environment_background_set('raw', self.source, {})
            self.assertIs(caught.exception, error); create.assert_called_once(); self.assertEqual(self.clock.call_count, 2)
        self.assertEqual((self.sets / 'task_env_fixture/source.jpg').read_bytes(), b'raw source bytes')
        self.load.assert_not_called(); self.write.assert_not_called(); self.payload.assert_not_called()
    def test_environment_variant_metadata_and_payload_errors_do_not_repeat_file_replacement(self):
        for stage in ['variant', 'metadata', 'payload']:
            with self.subTest(stage=stage), ExitStack() as stack:
                directory = self.root / stage / 'sets'; stack.enter_context(patch.object(self.api, 'BACKGROUND_SETS_DIR', directory))
                target = directory / 'task_env_fixture'; self.assertTrue(target.resolve().is_relative_to(self.root)); target.mkdir(parents=True); (target / 'old').write_bytes(b'old')
                self.events.clear(); error = OSError(stage)
                create = Mock(return_value=[]); update = Mock(return_value={'id': 'task_env_fixture'}); payload = Mock(return_value={'ok': True})
                if stage == 'variant':
                    def partial(source, folder, **kwargs):
                        (folder / 'partial.png').write_bytes(b'partial')
                        if create.call_count == 1: raise error
                        return []
                    create.side_effect = partial
                elif stage == 'metadata': update.side_effect = [error, {'id': 'task_env_fixture'}]
                else: payload.side_effect = [error, {'ok': True}]
                stack.enter_context(patch.object(self.api, 'create_background_variants_from_source', create))
                stack.enter_context(patch.object(self.api, 'update_background_set_manifest', update))
                stack.enter_context(patch.object(self.api, 'background_set_payload', payload))
                with self.assertRaises(OSError) as caught: self.api.save_task_environment_background_set('raw', self.source, {})
                self.assertIs(caught.exception, error); self.assertEqual(self.events, ['remove']); create.assert_called_once()
                self.assertEqual(update.call_count, int(stage != 'variant')); self.assertEqual(payload.call_count, int(stage == 'payload'))
                self.assertEqual((target / 'source.jpg').read_bytes(), b'raw source bytes'); self.assertFalse((target / 'old').exists())
                if stage == 'variant': self.assertEqual((target / 'partial.png').read_bytes(), b'partial')


    def test_environment_partial_copy_error_is_not_retried_and_retains_exact_bytes(self):
        directory = self.sets / 'task_env_fixture'; self.assertTrue(directory.resolve().is_relative_to(self.root))
        directory.mkdir(parents=True); (directory / 'old.png').write_bytes(b'old')
        target = directory / 'source.jpg'; error = OSError('partial source copy'); original = shutil.copy2
        def fail_first(source, destination):
            if copied.call_count == 1:
                Path(destination).write_bytes(b'partial copy'); raise error
            return original(source, destination)
        with patch.object(shutil, 'copy2', side_effect=fail_first) as copied, \
             patch.object(self.api, 'create_background_variants_from_source') as create, \
             patch.object(self.api, 'image_file_list') as images:
            with self.assertRaises(OSError) as caught: self.api.save_task_environment_background_set('raw', self.source, {})
            self.assertIs(caught.exception, error); copied.assert_called_once_with(self.source, target)
            create.assert_not_called(); images.assert_not_called()
        self.assertEqual(target.read_bytes(), b'partial copy'); self.assertEqual(self.source.read_bytes(), b'raw source bytes')
        self.assertEqual(list(directory.iterdir()), [target]); self.assertEqual(self.events, ['remove'])
        self.clock.assert_not_called(); self.load.assert_not_called(); self.write.assert_not_called(); self.payload.assert_not_called()
    def test_environment_ignored_remove_failure_continues_copy_and_counts_remaining_files(self):
        directory = self.sets / 'task_env_fixture'; self.assertTrue(directory.resolve().is_relative_to(self.root))
        directory.mkdir(parents=True); old = directory / 'old.png'; old.write_bytes(b'remaining file')
        with patch.object(shutil, 'rmtree', return_value=None) as remove, \
             patch.object(self.api, 'create_background_variants_from_source', return_value=[]) as create:
            result = self.api.save_task_environment_background_set('raw', self.source, {})
            remove.assert_called_once_with(directory, ignore_errors=True)
            create.assert_called_once_with(directory / 'source.jpg', directory, count=5)
        self.assertEqual(old.read_bytes(), b'remaining file'); self.assertEqual((directory / 'source.jpg').read_bytes(), b'raw source bytes')
        self.assertEqual(result['meta']['image_count'], 2); self.assertEqual(result['meta']['status'], 'ready')
        self.write.assert_called_once(); self.payload.assert_called_once()

    def test_independent_compositions_with_real_variants_manifests_and_no_constructor_reads(self):
        from uuid import UUID
        from local_inspection_service.training.background_manifest import BackgroundManifest
        from local_inspection_service.training.background_catalog import BackgroundImageFiles, safe_background_set_id
        from local_inspection_service.training.background_variants import BackgroundVariants, BackgroundMinimumImages
        from local_inspection_service.training.background_writes import BackgroundWrites
        from local_inspection_service.training.task_background_store import (TaskBackgroundIdentity, TaskBackgroundPaths,
            TaskBackgroundRecords, TaskBackgroundStore)
        def build(owner, shade, stamp):
            directory = self.root / owner; sets = directory / 'sets'; source = self.root / (owner + '.png')
            image = np.full((31, 47, 3), shade, dtype=np.uint8); self.assertTrue(cv2.imwrite(str(source), image))
            callbacks = []
            def port(fn): value = Mock(side_effect=fn); callbacks.append(value); return value
            manifest = BackgroundManifest(port(lambda: directory), port(lambda: directory / 'manifest.json'))
            images = BackgroundImageFiles(port(lambda: {'.png'})); clock = port(lambda: stamp)
            variants = BackgroundVariants(clock)
            writes = BackgroundWrites(port(safe_background_set_id), port(manifest.load_background_sets_manifest),
                port(manifest.write_background_sets_manifest), port(lambda: sets),
                port(lambda: UUID('abcdef00-0000-0000-0000-000000000000')), clock)
            minimum = BackgroundMinimumImages(port(safe_background_set_id), port(lambda: sets),
                port(images.image_file_list), port(lambda: variants.create_background_variants_from_source))
            store = TaskBackgroundStore(
                TaskBackgroundIdentity(port(lambda identifier: owner), port(lambda identifier: 'fallback-' + owner),
                                       port(lambda: safe_background_set_id), port(lambda: 'legacy-' + owner)),
                TaskBackgroundPaths(port(lambda: sets), port(lambda: {'.png'})),
                TaskBackgroundRecords(port(lambda: writes.update_background_set_manifest),
                                      port(lambda identifier, meta: {'id': identifier, 'meta': meta, 'paths': images.image_file_list(sets / identifier)})),
                port(variants.create_background_variants_from_source), port(images.image_file_list), clock)
            for callback in callbacks: callback.assert_not_called()
            self.assertFalse(directory.exists())
            return owner, shade, stamp, sets, source, manifest, writes, minimum, store, clock
        instances = [build('alice', 40, 101.001), build('bob', 170, 202.002)]
        for name in ['safe_background_set_id', 'sanitize_ai_detection_task_id', 'safe_record_id', 'image_file_list',
                     'load_background_sets_manifest', 'write_background_sets_manifest', 'create_background_variants_from_source',
                     'ensure_background_set_minimum_images', 'unique_background_set_id', 'update_background_set_manifest',
                     'save_task_environment_background_set', 'background_set_payload']:
            self.stack.enter_context(patch.object(self.api, name, side_effect=AssertionError('unexpected root dependency')))
        for index in [1, 0, 1, 0]:
            owner, shade, stamp, sets, source, manifest, writes, minimum, store, clock = instances[index]
            identifier = 'task_env_' + owner; directory = sets / identifier; clock.reset_mock()
            result = store.save_task_environment_background_set('ignored', source, {'id': owner, 'username': owner})
            self.assertEqual(clock.call_count, 3); self.assertEqual(result['id'], identifier)
            expected_paths = [directory / 'source.png'] + [directory / ('source_variant_%02d.png' % n) for n in range(1, 6)]
            self.assertEqual(result['paths'], expected_paths); self.assertEqual(result['meta']['source'], str(directory / 'source.png'))
            self.assertEqual(result['meta']['owner_user_id'], owner); self.assertEqual(result['meta']['image_count'], 6)
            self.assertEqual((result['meta']['created_at'], result['meta']['updated_at']), (int(stamp), int(stamp)))
            self.assertEqual((directory / 'source.png').read_bytes(), source.read_bytes()); self.assertFalse((directory / 'old.marker').exists())
            for path in expected_paths: self.assertLess(abs(float(cv2.imread(str(path)).mean()) - shade), 25)
            self.assertEqual(writes.unique_background_set_id(identifier), identifier + '_abcdef')
            self.assertEqual(list(manifest.load_background_sets_manifest()['sets']), [identifier])
            # Original minimum behavior overwrites numbered variants instead of recounting or allocating fresh names.
            clock.reset_mock(); minimum.ensure_background_set_minimum_images(identifier, 8)
            clock.assert_called_once(); self.assertEqual(sorted(directory.iterdir()), expected_paths)
            (directory / 'old.marker').write_bytes(b'replaced on next call')


    def _capture_callback_window(self, site, mode):
        import types
        ns = self.api.__dict__
        events = []
        stop = RuntimeError('stop after safe')
        field = {'create': 'create_background_variants_from_source', 'safe': 'safe_background_set_id', 'update': 'update_background_set_manifest'}[site]

        def called(label):

            def callback(*args, **kwargs):
                events.append(label)
                return kwargs if site == 'update' else 'set' if site == 'safe' else []
            return callback
        a, b, c = (called('A'), called('B'), called('C'))

        def prior():
            events.append('prior')
            ns[field] = a if mode == 'ordinary' else b if mode == 'prior' else None

        def argument():
            events.append('argument')
            ns[field] = c
        with tempfile.TemporaryDirectory(prefix='background-capture-', dir=self.root) as directory:
            root = Path(directory)
            source = root / 'source.png'
            source.write_bytes(b'synthetic')
            ns.update(BACKGROUND_SETS_DIR=root / 'sets', safe_background_set_id=lambda value: 'set', sanitize_ai_detection_task_id=lambda value: 'task', safe_record_id=lambda value: 'fallback', IMAGE_REFERENCE_SUFFIXES={'.png'}, LEGACY_OWNER_ID='legacy', time=types.SimpleNamespace(time=lambda: 101), background_set_payload=lambda key, meta: meta)
            if site == 'create':
                ns[field] = a

                class Images(list):

                    def __bool__(self):
                        prior()
                        return True

                    def __getitem__(self, key):
                        argument()
                        return super().__getitem__(key)
                ns['image_file_list'] = lambda path: Images([source])
                invoke = lambda: ns['ensure_background_set_minimum_images']('set', 3)
            elif site == 'safe':
                ns[field] = a

                class Clean(str):

                    def __bool__(self):
                        prior()
                        return True

                    def __format__(self, format_spec):
                        argument()
                        return str.__format__(self, format_spec)

                class StopDirectory:

                    def __truediv__(self, value):
                        raise stop
                ns['sanitize_ai_detection_task_id'] = lambda value: Clean('task')
                ns['BACKGROUND_SETS_DIR'] = StopDirectory()
                invoke = lambda: ns['save_task_environment_background_set']('raw', source, {'id': 'owner'})
            else:
                ns[field] = a

                class Images(list):

                    def __len__(self):
                        prior()
                        return 1

                class Display:

                    def __bool__(self):
                        argument()
                        return True
                ns['create_background_variants_from_source'] = lambda *args, **kwargs: []
                ns['image_file_list'] = lambda path: Images([source])
                invoke = lambda: ns['save_task_environment_background_set']('raw', source, {'id': 'owner'}, Display())
            caught = None
            try:
                invoke()
            except BaseException as error:
                caught = error
            assert 'argument' in events, events
            index = events.index('argument')
            assert events[index - 1] == 'prior', events
            if mode == 'missing':
                assert type(caught) is TypeError, (type(caught), events)
                assert events[index:] == ['argument'], events
            else:
                assert caught is (stop if site == 'safe' else None), (caught, events)
                assert events[index + 1:] == ['A' if mode == 'ordinary' else 'B'], events
            return events

    def test_callbacks_capture_at_nearest_prework_before_arguments(self):
        for site in ['create', 'safe', 'update']:
            for mode in ['ordinary', 'prior', 'missing']:
                with self.subTest(site=site, mode=mode), patch.dict(self.api.__dict__):
                    self._capture_callback_window(site, mode)

    def write_failure_fixture(self, scope, mode):
        from uuid import UUID
        f, operation, ports = self.failure_fixture(scope, 'unique' if mode.startswith('unique') else mode)
        if mode == 'unique-initial':
            operation = lambda: self.api.unique_background_set_id('fresh')
        elif mode in ['unique-candidate', 'unique-exhausted']:
            import uuid
            scope.enter_context(patch.object(uuid, 'uuid4', return_value=UUID('abcdef00-0000-0000-0000-000000000000')))
            if mode == 'unique-exhausted': (f.sets / 'existing_abcdef').mkdir()
        return f, operation, ports

    def test_direct_write_filesystem_first_errors_never_retry(self):
        cases = [('variants', cv2, 'imread', None), ('variants', Path, 'mkdir', 'variants'),
                 ('unique-initial', Path, 'exists', 'fresh'), ('unique-candidate', Path, 'exists', 'existing_abcdef'),
                 ('environment', Path, 'exists', 'task_env_fixture'), ('environment', Path, 'mkdir', 'task_env_fixture'),
                 ('environment', shutil, 'rmtree', 'task_env_fixture')]
        for mode, owner, field, leaf in cases:
            with self.subTest(mode=mode, field=field), ExitStack() as scope:
                f, operation, _ = self.write_failure_fixture(scope, mode)
                target = f.sets / leaf if leaf else None
                if field == 'rmtree': target.mkdir(); (target / 'old.marker').write_bytes(b'old')
                original = getattr(owner, field); calls = []; failure = RuntimeError('direct-write-first')
                def fail_once(*args, **kwargs):
                    if target is None or args[0] == target:
                        if field == 'rmtree': self.assertTrue(Path(args[0]).resolve().is_relative_to(f.root))
                        calls.append(None)
                        if len(calls) == 1: raise failure
                    return original(*args, **kwargs)
                with patch.object(owner, field, fail_once):
                    with self.assertRaises(RuntimeError) as caught: operation()
                    self.assertIs(caught.exception, failure)
                self.assertEqual(len(calls), 1)
                if field == 'rmtree': self.assertEqual((target / 'old.marker').read_bytes(), b'old')

    def test_path_provider_first_errors_never_retry(self):
        from dataclasses import replace
        cases = [('minimum', self.api._background_minimum_images, None, 'sets'),
                 ('unique-initial', self.api._background_writes, None, 'sets'),
                 ('unique-candidate', self.api._background_writes, None, 'sets'),
                 ('environment', self.api._task_background_store, 'paths', 'sets'),
                 ('environment', self.api._task_background_store, 'paths', 'suffixes')]
        for mode, service, group, field in cases:
            original = getattr(getattr(service, group) if group else service, field)
            def install(scope, port):
                if group: scope.enter_context(patch.object(service, group, replace(getattr(service, group), **{field: port})))
                else: scope.enter_context(patch.object(service, field, port))
            with ExitStack() as scope:
                _, operation, _ = self.write_failure_fixture(scope, mode); seen = Mock(wraps=original); install(scope, seen)
                operation(); count = seen.call_count
            self.assertGreater(count, 0)
            for index in range(1, count + 1):
                with self.subTest(mode=mode, field=field, index=index), ExitStack() as scope:
                    _, operation, _ = self.write_failure_fixture(scope, mode); calls = []; failure = RuntimeError('write-path-provider')
                    def fail_once():
                        calls.append(None)
                        if len(calls) == index: raise failure
                        return original()
                    install(scope, fail_once)
                    with self.assertRaises(RuntimeError) as caught: operation()
                    self.assertIs(caught.exception, failure); self.assertEqual(len(calls), index)

    def test_fallback_identity_and_exhausted_unique_clock_first_errors_never_retry(self):
        import time
        for mode in ['environment', 'unique-exhausted']:
            with self.subTest(mode=mode), ExitStack() as scope:
                f, operation, _ = self.write_failure_fixture(scope, mode)
                if mode == 'environment':
                    f.sanitize.return_value = ''
                    owner, field, original = self.api, 'safe_record_id', f.fallback
                else: owner, field, original = time, 'time', f.clock
                calls = []; failure = RuntimeError('branch-first')
                def fail_once(*args, **kwargs):
                    calls.append(None)
                    if len(calls) == 1: raise failure
                    return original(*args, **kwargs)
                scope.enter_context(patch.object(owner, field, fail_once))
                with self.assertRaises(RuntimeError) as caught: operation()
                self.assertIs(caught.exception, failure); self.assertEqual(len(calls), 1)

    def failure_fixture(self, scope, mode):
        f = TrainingBackgroundWriteContracts(); f.api = self.api
        temporary_directory = tempfile.TemporaryDirectory
        with patch.object(tempfile, 'TemporaryDirectory', side_effect=lambda **kwargs: temporary_directory(dir=self.root, **kwargs)):
            f.setUp()
        scope.callback(f.doCleanups)
        f.sets.mkdir(); source, _ = f.input_image()
        sample = f.sets / 'existing'; sample.mkdir(); shutil.copy2(source, sample / 'source.png')
        f.manifest['sets']['existing'] = {'id': 'existing'}
        operations = {'variants': ('create_background_variants_from_source', lambda: self.api.create_background_variants_from_source(source, f.sets / 'variants', 1)),
                      'minimum': ('ensure_background_set_minimum_images', lambda: self.api.ensure_background_set_minimum_images('existing', 2)),
                      'unique': ('unique_background_set_id', lambda: self.api.unique_background_set_id('existing')),
                      'update': ('update_background_set_manifest', lambda: self.api.update_background_set_manifest('existing', note='new')),
                      'environment': ('save_task_environment_background_set', lambda: self.api.save_task_environment_background_set('task', source, {'id': 'owner', 'username': 'Owner'}))}
        entry, operation = operations[mode]
        names = ['safe_background_set_id', 'sanitize_ai_detection_task_id', 'safe_record_id', 'image_file_list',
                 'load_background_sets_manifest', 'write_background_sets_manifest', 'create_background_variants_from_source',
                 'update_background_set_manifest', 'background_set_payload']
        ports = {}
        for name in names:
            if name != entry:
                port = Mock(wraps=getattr(self.api, name)); scope.enter_context(patch.object(self.api, name, port))
                ports[name] = (self.api, name, port)
        import time, uuid
        for owner, name in [(time, 'time'), (uuid, 'uuid4')]:
            port = Mock(wraps=getattr(owner, name)); scope.enter_context(patch.object(owner, name, port)); ports[name] = (owner, name, port)
        return f, operation, ports

    def test_first_callback_error_propagates_without_retry(self):
        for mode in ['variants', 'minimum', 'unique', 'update', 'environment']:
            with ExitStack() as scope:
                _, operation, ports = self.failure_fixture(scope, mode); operation()
                counts = {name: port.call_count for name, (_, _, port) in ports.items() if port.call_count}
            for name, count in counts.items():
                for index in range(1, count + 1):
                    with self.subTest(mode=mode, name=name, index=index), ExitStack() as scope:
                        _, operation, ports = self.failure_fixture(scope, mode); owner, field, original = ports[name]
                        calls = []; failure = RuntimeError('write-first')
                        def fail_once(*args, **kwargs):
                            calls.append(None)
                            if len(calls) == index: raise failure
                            return original(*args, **kwargs)
                        scope.enter_context(patch.object(owner, field, fail_once))
                        with self.assertRaises(RuntimeError) as caught: operation()
                        self.assertIs(caught.exception, failure); self.assertEqual(len(calls), index)

    def test_new_getter_first_error_propagates_without_retry(self):
        from dataclasses import replace
        cases = [('minimum', self.api._background_minimum_images, None, 'create'),
                 ('environment', self.api._task_background_store, 'identity', 'safe'),
                 ('environment', self.api._task_background_store, 'records', 'update_provider')]
        for mode, service, group, field in cases:
            original = getattr(getattr(service, group) if group else service, field)
            def install(scope, port):
                if group: scope.enter_context(patch.object(service, group, replace(getattr(service, group), **{field: port})))
                else: scope.enter_context(patch.object(service, field, port))
            with ExitStack() as scope:
                _, operation, _ = self.failure_fixture(scope, mode); seen = Mock(wraps=original); install(scope, seen)
                operation(); count = seen.call_count
            self.assertGreater(count, 0)
            for index in range(1, count + 1):
                with self.subTest(mode=mode, field=field, index=index), ExitStack() as scope:
                    _, operation, _ = self.failure_fixture(scope, mode); calls = []; failure = RuntimeError('write-getter')
                    def fail_once():
                        calls.append(None)
                        if len(calls) == index: raise failure
                        return original()
                    install(scope, fail_once)
                    with self.assertRaises(RuntimeError) as caught: operation()
                    self.assertIs(caught.exception, failure); self.assertEqual(len(calls), index)

    def test_task_background_captures_after_variants_before_two_clocks_and_owner_reads(self):
        self.stack.enter_context(patch.object(self.api,'update_background_set_manifest',self.api.update_background_set_manifest))
        for stage in ['clocks','owner-id','owner-name','legacy']:
            with self.subTest(stage=stage):
                events=[]; first=Mock(); second=Mock(side_effect=lambda identifier,**values:values); third=Mock(); fourth=Mock()
                self.clock.reset_mock(); self.payload.reset_mock(); self.api.update_background_set_manifest=first
                def create(source,directory,*,count):
                    self.assertEqual(source.read_bytes(),b'raw source bytes'); self.assertEqual(count,5)
                    (directory/'variant.png').write_bytes(b'variant'); self.api.update_background_set_manifest=second
                def clock():
                    events.append('clock')
                    if stage=='clocks': self.api.update_background_set_manifest=third if len(events)==1 else fourth
                    return 11.9 if len(events)==1 else 22.9
                class User(dict):
                    def get(inner,key,default=None):
                        events.append(key)
                        if stage=='owner-'+('id' if key=='id' else 'name'): self.api.update_background_set_manifest=third
                        if stage=='legacy' and key=='id': self.api.update_background_set_manifest=third; return None
                        return {'id':123,'username':'Alice'}.get(key,default)
                self.clock.side_effect=clock
                with patch.object(self.api,'create_background_variants_from_source',side_effect=create) as variants, patch.object(self.api,'image_file_list',return_value=[Path('image')]*2) as images:
                    result=self.api.save_task_environment_background_set('raw',self.source,User(),display_name='Scene')
                expected={'id':'task_env_fixture','name':'Scene','description':'用户首次检测前通过摄像头采集的空白生产环境背景',
                    'source':str(self.sets/'task_env_fixture/source.jpg'),'created_at':11,'updated_at':22,'status':'ready','image_count':2,
                    'generation_method':'camera_empty_environment_local_variants','owner_user_id':'legacy-fixture' if stage=='legacy' else '123','owner_username':'Alice','shared_with_user_ids':[]}
                self.assertEqual(events,['clock','clock','id','username']); first.assert_not_called(); third.assert_not_called(); fourth.assert_not_called()
                second.assert_called_once_with('task_env_fixture',**expected); self.assertEqual(result,{'projected':'task_env_fixture','meta':expected})
                self.assertIs(self.payload.call_args.args[1],result['meta']); variants.assert_called_once(); images.assert_called_once()
                self.assertEqual((self.sets/'task_env_fixture/variant.png').read_bytes(),b'variant')
                self.api.update_background_set_manifest=third; self.clock.side_effect=None
                with patch.object(self.api,'create_background_variants_from_source',return_value=[]), patch.object(self.api,'image_file_list',return_value=[]):
                    self.api.save_task_environment_background_set('raw',self.source,{'id':'next','username':'Next'})
                third.assert_called_once(); self.assertEqual(third.call_args.kwargs['owner_user_id'],'next')

    def test_task_background_none_argument_and_write_failures_preserve_generated_files(self):
        self.stack.enter_context(patch.object(self.api,'update_background_set_manifest',self.api.update_background_set_manifest))
        for stage in ['none','clock1','clock2','id','username','write']:
            with self.subTest(stage=stage):
                events=[]; first=Mock(side_effect=OSError('old write')); later=Mock()
                self.api.update_background_set_manifest=None if stage=='none' else first; self.payload.reset_mock()
                def create(source,directory,*,count): (directory/'variant.png').write_bytes(b'variant')
                def clock():
                    events.append('clock'); self.api.update_background_set_manifest=later
                    if stage=='clock'+str(len(events)): raise OSError(stage)
                    return 101.9
                class User(dict):
                    def get(inner,key,default=None):
                        events.append(key)
                        if stage==key: raise OSError(key)
                        return 'alice'
                self.clock.side_effect=clock
                with patch.object(self.api,'create_background_variants_from_source',side_effect=create) as variants, patch.object(self.api,'image_file_list',return_value=[Path('image')]):
                    with self.assertRaises(TypeError if stage=='none' else OSError): self.api.save_task_environment_background_set('raw',self.source,User())
                self.assertEqual(events,['clock'] if stage=='clock1' else ['clock','clock'] if stage=='clock2' else ['clock','clock','id'] if stage=='id' else ['clock','clock','id','username'])
                self.assertEqual(first.call_count,int(stage=='write')); later.assert_not_called(); self.payload.assert_not_called(); variants.assert_called_once()
                self.assertEqual((self.sets/'task_env_fixture/source.jpg').read_bytes(),b'raw source bytes')
                self.assertEqual((self.sets/'task_env_fixture/variant.png').read_bytes(),b'variant')


    def test_provider_lookup_task_background_errors_and_legacy_owner_capture(self):
        from local_inspection_service.training.task_background_store import TaskBackgroundStore, TaskBackgroundIdentity, TaskBackgroundPaths, TaskBackgroundRecords
        for stage in ['lookup','legacy-error','legacy-switch']:
            with self.subTest(stage=stage):
                first=Mock(side_effect=lambda identifier,**values:values); later=Mock(); target=[first]; self.clock.reset_mock(); self.payload.reset_mock()
                def provider():
                    self.assertEqual((self.sets/'task_env_fixture/source.jpg').read_bytes(),b'raw source bytes')
                    self.assertEqual((self.sets/'task_env_fixture/variant.png').read_bytes(),b'variant')
                    if stage=='lookup': raise OSError('lookup')
                    return target[0]
                def legacy():
                    target[0]=later
                    if stage=='legacy-error': raise OSError('legacy')
                    return 'legacy-id'
                def create(source,directory,*,count): (directory/'variant.png').write_bytes(b'variant')
                lookup=Mock(side_effect=provider); owner=Mock(side_effect=legacy)
                service=TaskBackgroundStore(TaskBackgroundIdentity(lambda value:'fixture',lambda value:'fallback',lambda: (lambda value:value),owner),
                    TaskBackgroundPaths(lambda:self.sets,lambda:{'.jpg'}),TaskBackgroundRecords(lookup,self.payload),create,lambda path:[Path('image')],self.clock)
                lookup.assert_not_called(); owner.assert_not_called(); self.clock.assert_not_called()
                if stage!='legacy-switch':
                    with self.assertRaisesRegex(OSError,'lookup' if stage=='lookup' else 'legacy'): service.save_task_environment_background_set('raw',self.source,{})
                    first.assert_not_called(); self.payload.assert_not_called()
                else:
                    result=service.save_task_environment_background_set('raw',self.source,{})
                    first.assert_called_once(); self.assertEqual(result['meta']['owner_user_id'],'legacy-id'); self.payload.assert_called_once()
                lookup.assert_called_once_with(); self.assertEqual(owner.call_count,int(stage!='lookup')); self.assertEqual(self.clock.call_count,0 if stage=='lookup' else 2)
                later.assert_not_called()


if __name__ == '__main__': unittest.main()
