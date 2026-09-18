"""Original background pixels, random stream, library lookup and rendering contracts."""
from contextlib import ExitStack
import hashlib
import itertools
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, call, patch
import cv2
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class BackgroundContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.environment = patch.dict(os.environ); cls.environment.start()
        cls.runtime = tempfile.TemporaryDirectory(prefix='training-background-root-')
        root = Path(cls.runtime.name); (root / 'local_inspection_service/static').mkdir(parents=True)
        os.environ.update(LOCAL_INSPECTION_ROOT=str(root), VANTALINE_DATA_STORE='json',
                          LOCAL_INSPECTION_AUTO_RESUME_WORKER='0', VANTALINE_LABEL_INSPECTION_ENABLED='false')
        from local_inspection_service import server
        cls.api = server
        cls.files_helper = staticmethod(server.background_set_image_files)

    @classmethod
    def tearDownClass(cls): cls.runtime.cleanup(); cls.environment.stop()

    def setUp(self):
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory(prefix='training-background-')))
        self.directory = self.root / 'backgrounds'; self.directory.mkdir()
        self.default = self.root / 'default.png'
        self.selected = Mock(return_value='chosen')
        self.files = Mock(return_value=[])
        for name, value in {'BACKGROUND_DIR': self.directory, 'DEFAULT_BACKGROUND_IMAGE': self.default,
                            'IMAGE_REFERENCE_SUFFIXES': {'.png', '.jpg'}, 'selected_background_set_id': self.selected,
                            'background_set_image_files': self.files}.items():
            self.stack.enter_context(patch.object(self.api, name, value))
        for target in ['requests.request', 'subprocess.Popen', 'os.kill']:
            self.stack.enter_context(patch(target, side_effect=AssertionError('unexpected external operation')))

    def file(self, name, directory=None):
        path = (directory or self.directory) / name
        path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b'fixture')
        return path

    def manifest(self, value):
        path = self.directory / 'background_manifest.json'
        path.write_text(json.dumps(value), encoding='utf-8'); return path

    def item(self, name='one', **values):
        return {'id': name, 'path': self.root / (name + '.png'), 'source': 'fixture-source',
                'source_asset': name + '.png', 'background_set_id': 'set', 'library_size': 1, **values}

    def test_manifest_missing_decode_only_fallback_and_nonmapping_values(self):
        self.assertEqual(self.api.load_training_background_manifest(), {})
        path = self.manifest({'value': 1})
        self.assertEqual(self.api.load_training_background_manifest(), {'value': 1})
        for value in [[], None, False, 3]:
            self.manifest(value); self.assertEqual(self.api.load_training_background_manifest(), value)
        path.write_text('{broken'); self.assertEqual(self.api.load_training_background_manifest(), {})
        path.write_bytes(b'\xff')
        with self.assertRaises(UnicodeDecodeError): self.api.load_training_background_manifest()
        with patch.object(Path, 'read_text', side_effect=OSError('read failed')):
            with self.assertRaisesRegex(OSError, 'read failed'): self.api.load_training_background_manifest()
        with patch.object(Path, 'exists', side_effect=OSError('exists failed')):
            with self.assertRaisesRegex(OSError, 'exists failed'): self.api.load_training_background_manifest()

    def test_manifest_failure_precedes_selection_and_nonmapping_only_fails_with_files(self):
        with patch.object(self.api, 'load_training_background_manifest', side_effect=[OSError('manifest'), {}]) as read:
            with self.assertRaisesRegex(OSError, 'manifest'): self.api.training_background_library('asked')
            read.assert_called_once_with(); self.selected.assert_not_called(); self.files.assert_not_called()
        self.manifest([])
        self.assertEqual(self.api.training_background_library(), [])
        self.files.return_value = [self.file('one.png')]
        with self.assertRaises(AttributeError): self.api.training_background_library()

    def test_provider_order_duplicates_alias_prepend_and_source_priority(self):
        self.default.write_bytes(b'default')
        first = self.file('z image.png'); second = self.file('___.jpg')
        provided = [first, second, first]; self.files.return_value = provided; self.selected.return_value = 'green_conveyor'
        self.manifest({'asset': first.name, 'reference_photo': 'reference', 'workspace_path': 'workspace'})
        result = self.api.training_background_library('raw-request')
        self.assertEqual(provided, [self.default, first, second, first])
        self.assertEqual([item['path'] for item in result], provided)
        self.assertEqual([item['id'] for item in result], ['default', 'z_image', 'background_3', 'z_image'])
        self.assertEqual([item['source'] for item in result], [str(self.default), 'reference', str(second), 'reference'])
        self.assertEqual([item['library_index'] for item in result], [0, 1, 2, 3])
        self.assertEqual([item['library_size'] for item in result], [4] * 4)
        self.selected.assert_called_once_with('raw-request'); self.files.assert_called_once_with('green_conveyor')
        self.manifest({'asset': first.name, 'reference_photo': '', 'workspace_path': 'workspace'})
        self.assertEqual(self.api.training_background_library()[1]['source'], 'workspace')
        self.manifest({'asset': first.stem, 'reference_photo': 'not-a-full-filename'})
        self.assertEqual(self.api.training_background_library()[1]['source'], str(first))
        self.selected.return_value = 'other'; untouched = [first]; self.files.return_value = untouched
        self.assertEqual([item['path'] for item in self.api.training_background_library()], [first])
        self.assertEqual(untouched, [first])

    def test_empty_provider_fallback_sort_suffix_and_default_insertion(self):
        a = self.file('a.PNG'); z = self.file('z.jpg'); self.file('skip.txt')
        (self.directory / 'folder.png').mkdir(); self.default.write_bytes(b'default')
        self.selected.return_value = None
        result = self.api.training_background_library()
        self.assertEqual([item['path'] for item in result], [self.default, a, z])
        self.assertEqual([item['background_set_id'] for item in result], [None] * 3)
        self.assertEqual(self.files.return_value, [])
        with patch.object(self.api, 'DEFAULT_BACKGROUND_IMAGE', a):
            self.assertEqual([item['path'] for item in self.api.training_background_library()], [a, z])
        with patch.object(self.api, 'BACKGROUND_DIR', self.root / 'absent'):
            self.assertEqual([item['path'] for item in self.api.training_background_library()], [self.default])

    def test_actual_files_helper_reselects_and_preserves_first_metadata_id(self):
        sets = self.root / 'sets'; path = self.file('image.png', sets / 'B')
        self.selected.side_effect = ['A', 'B']
        with patch.object(self.api, 'BACKGROUND_SETS_DIR', sets), patch.object(self.api, 'background_set_image_files', self.files_helper):
            result = self.api.training_background_library('asked')
        self.assertEqual(self.selected.call_args_list, [call('asked'), call('A')])
        self.assertEqual([item['path'] for item in result], [path])
        self.assertEqual(result[0]['background_set_id'], 'A')

    def test_split_pools_and_small_list_aliases(self):
        for size in range(5):
            library = [self.item(str(index)) for index in range(size)]
            for split in ['train', 'val', 'test', 'preview', None, 'VAL']:
                actual = self.api.background_candidates_for_split(library, split)
                if size < 2:
                    self.assertIs(actual, library)
                else:
                    expected = [library[-2]] if size >= 3 and split == 'val' else [library[-1]] if size >= 3 and split == 'test' else library[:-2] if size >= 3 else [library[1]] if split in {'val', 'test'} else [library[0]]
                    self.assertEqual(actual, expected)
                    for item in actual: self.assertTrue(any(item is original for original in library))

    def test_original_pixel_fingerprints_metadata_rng_state_and_unchanged_inputs(self):
        golden = json.loads((Path(__file__).resolve().parents[1] / 'tests/backend_contract/training_background_pixels.json').read_text())['cases']
        small = np.arange(7 * 11 * 3, dtype=np.uint8).reshape(7, 11, 3)
        full = np.broadcast_to(np.arange(1280, dtype=np.uint16)[None, :, None] % 256, (900, 1280, 3)).astype(np.uint8).copy()
        saved_small = small.copy(); saved_full = full.copy()
        for name, function, args, seed in [('synthetic123', self.api.synthetic_training_background, [], 123),
                ('fit123', self.api.fit_training_background_to_canvas, [small], 123),
                ('augment1', self.api.augment_training_background, [full], 1), ('augment4', self.api.augment_training_background, [full], 4)]:
            with self.subTest(name=name):
                rng = np.random.default_rng(seed)
                result, metadata = function(*args, rng, **({'target_size': (10, 6)} if name == 'fit123' else {}))
                self.assertEqual({'sha': hashlib.sha256(result.tobytes()).hexdigest(), 'meta': metadata,
                                  'next': int(rng.integers(0, 1000000))}, golden[name])
                self.assertEqual(result.dtype, np.uint8)
        np.testing.assert_array_equal(small, saved_small); np.testing.assert_array_equal(full, saved_full)

    def test_fit_calls_both_area_resizes_and_skips_zero_crop_offset_draws(self):
        image = np.arange(4 * 6 * 3, dtype=np.uint8).reshape(4, 6, 3)
        rng = Mock(); rng.uniform.return_value = 1.0; rng.integers.return_value = 1
        resize = cv2.resize
        with patch.object(cv2, 'resize', wraps=resize) as spy:
            result, metadata = self.api.fit_training_background_to_canvas(image, rng, (6, 4))
        rng.uniform.assert_called_once_with(1.0, 1.08); rng.integers.assert_not_called()
        self.assertEqual(len(spy.call_args_list), 2)
        for item in spy.call_args_list: self.assertEqual(item.kwargs, {'interpolation': cv2.INTER_AREA})
        self.assertEqual([item.args[1] for item in spy.call_args_list], [(6, 4), (6, 4)])
        np.testing.assert_array_equal(result, image)
        self.assertEqual(metadata['background_crop_xywh'], [0, 0, 6, 4])

    def test_blur_threshold_choice_noise_and_fixed_texture_alpha(self):
        canvas = np.full((10, 12, 3), 10, dtype=np.uint8)
        for threshold, expected in [(0.35, 0), (0.349, 3)]:
            rng = Mock(); rng.uniform.side_effect = [1.0, 0.0, 1.0]
            rng.normal.side_effect = lambda *args, **kwargs: np.zeros(kwargs['size']) if 'size' in kwargs else 0.0
            rng.random.return_value = threshold; rng.choice.return_value = 3
            rng.integers.side_effect = lambda low, high: low
            blur, blend = cv2.GaussianBlur, cv2.addWeighted
            with patch.object(cv2, 'GaussianBlur', wraps=blur) as blur_spy, patch.object(cv2, 'addWeighted', wraps=blend) as blend_spy:
                result, meta = self.api.augment_training_background(canvas, rng)
            self.assertEqual(meta['background_augmentation']['blur_kernel'], expected)
            self.assertFalse(meta['background_augmentation']['glare_applied'])
            self.assertEqual(blend_spy.call_args.args[1], 0.03); self.assertEqual(blend_spy.call_args.args[3], 0.97)
            if expected: blur_spy.assert_called_once(); rng.choice.assert_called_once_with([3, 5])
            else: blur_spy.assert_not_called(); rng.choice.assert_not_called()
            np.testing.assert_array_equal(result, canvas)

    def render_ports(self, library, candidates, *, readable=True):
        image = np.zeros((3, 5, 3), dtype=np.uint8)
        canvas = np.ones((4, 6, 3), dtype=np.uint8)
        output = np.full_like(canvas, 2)
        base_meta = {'background_id': 'fallback', 'background_library_size': 0}
        ports = {'training_background_library': Mock(return_value=library),
                 'background_candidates_for_split': Mock(return_value=candidates),
                 'synthetic_training_background': Mock(return_value=(canvas, base_meta)),
                 'fit_training_background_to_canvas': Mock(return_value=(canvas, {'crop': True})),
                 'augment_training_background': Mock(return_value=(output, {'augmentation': True}))}
        for name, mock in ports.items(): self.stack.enter_context(patch.object(self.api, name, mock))
        reader = self.stack.enter_context(patch.object(cv2, 'imread', return_value=image if readable else None))
        rng = Mock(); rng.integers.return_value = 0
        return ports, reader, rng, image, canvas, output, base_meta

    def test_render_same_rng_selection_once_and_metadata_merge_order(self):
        item = self.item(); library = [item, self.item('other')]
        ports, reader, rng, image, canvas, output, _ = self.render_ports(library, [item])
        ports['fit_training_background_to_canvas'].return_value = (canvas, {'background_id': 'crop', 'crop': True})
        ports['augment_training_background'].return_value = (output, {'background_id': 'augment', 'background_split': 'ignored', 'background_policy': 'ignored'})
        actual, meta = self.api.render_training_background(rng, 'VAL', 'asked')
        self.assertIs(actual, output); self.assertEqual(meta, {'background_id': 'augment', 'background_source': 'fixture-source',
            'background_source_asset': 'one.png', 'background_set_id': 'set', 'background_library_size': 1,
            'background_split_pool_size': 1, 'background_split_pool_isolated': True, 'crop': True,
            'background_split': 'preview', 'background_policy': 'same_environment_library_with_per_sample_crop_shift_photometric_noise_texture_no_glare'})
        ports['training_background_library'].assert_called_once_with('asked')
        ports['background_candidates_for_split'].assert_called_once_with(library, 'preview')
        rng.integers.assert_called_once_with(0, 1); reader.assert_called_once_with(str(item['path']), cv2.IMREAD_COLOR)
        self.assertIs(ports['fit_training_background_to_canvas'].call_args.args[0], image)
        self.assertIs(ports['fit_training_background_to_canvas'].call_args.args[1], rng)
        self.assertIs(ports['augment_training_background'].call_args.args[0], canvas)
        self.assertIs(ports['augment_training_background'].call_args.args[1], rng)
        ports['synthetic_training_background'].assert_not_called()

    def test_empty_and_unreadable_fallback_share_meta_and_augment_once(self):
        for empty in [True, False]:
            with self.subTest(empty=empty), ExitStack() as scope:
                original_stack = self.stack; self.stack = scope
                try: ports, reader, rng, _, _, output, base_meta = self.render_ports([], [] if empty else [self.item()], readable=False)
                finally: self.stack = original_stack
                actual, meta = self.api.render_training_background(rng, 'test')
                self.assertIs(actual, output); self.assertIs(meta, base_meta)
                self.assertEqual(meta['background_split'], 'test')
                for key in ['background_set_id', 'crop', 'background_split_pool_size']: self.assertNotIn(key, meta)
                ports['synthetic_training_background'].assert_called_once_with(rng)
                ports['fit_training_background_to_canvas'].assert_not_called(); ports['augment_training_background'].assert_called_once()
                if empty: reader.assert_not_called(); rng.integers.assert_not_called(); self.assertNotIn('background_source_error', meta)
                else: reader.assert_called_once(); rng.integers.assert_called_once_with(0, 1); self.assertEqual(meta['background_source_error'], 'unreadable_background:' + str(self.item()['path']))

    def test_render_exceptions_propagate_without_retry_or_fallback(self):
        for stage in ['library', 'candidates', 'imread', 'fit', 'augment']:
            with self.subTest(stage=stage), ExitStack() as scope:
                original_stack = self.stack; self.stack = scope
                try: ports, reader, rng, *_ = self.render_ports([self.item()], [self.item()])
                finally: self.stack = original_stack
                chain = [ports['training_background_library'], ports['background_candidates_for_split'], reader,
                         ports['fit_training_background_to_canvas'], ports['augment_training_background']]
                index = ['library', 'candidates', 'imread', 'fit', 'augment'].index(stage)
                failure = RuntimeError(stage)
                chain[index].side_effect = itertools.chain([failure], itertools.repeat(chain[index].return_value))
                with self.assertRaisesRegex(RuntimeError, stage) as caught: self.api.render_training_background(rng)
                self.assertIs(caught.exception, failure)
                self.assertEqual([mock.call_count for mock in chain], [1] * (index + 1) + [0] * (4 - index))
                ports['synthetic_training_background'].assert_not_called()

    def test_manifest_and_library_first_errors_do_not_retry(self):
        self.default.write_bytes(b'default')
        self.file('one.png'); self.manifest({'asset': 'one.png'})
        cases = [('manifest-exists', Path, 'exists', self.api.load_training_background_manifest),
                 ('manifest-read', Path, 'read_text', self.api.load_training_background_manifest),
                 ('manifest-json', json, 'loads', self.api.load_training_background_manifest),
                 ('selected', self.api, 'selected_background_set_id', self.api.training_background_library),
                 ('files', self.api, 'background_set_image_files', self.api.training_background_library),
                 ('library-exists', Path, 'exists', self.api.training_background_library),
                 ('library-iterdir', Path, 'iterdir', self.api.training_background_library),
                 ('library-is-file', Path, 'is_file', self.api.training_background_library)]
        for label, owner, name, operation in cases:
            original = getattr(owner, name); calls = []
            def observe(*args, **kwargs):
                calls.append((args, kwargs)); return original(*args, **kwargs)
            with patch.object(owner, name, observe): operation()
            count = len(calls); self.assertGreater(count, 0, label)
            for index in range(1, count + 1):
                with self.subTest(label=label, index=index):
                    calls.clear(); failure = RuntimeError(label)
                    def fail_once(*args, **kwargs):
                        calls.append((args, kwargs))
                        if len(calls) == index: raise failure
                        return original(*args, **kwargs)
                    with patch.object(owner, name, fail_once):
                        with self.assertRaises(RuntimeError) as caught: operation()
                    self.assertIs(caught.exception, failure)
                    self.assertEqual(len(calls), index)

    def test_render_selection_first_error_does_not_retry_or_read(self):
        ports, reader, rng, *_ = self.render_ports([self.item()], [self.item()])
        failure = RuntimeError('selection')
        rng.integers.side_effect = itertools.chain([failure], itertools.repeat(0))
        with self.assertRaises(RuntimeError) as caught: self.api.render_training_background(rng)
        self.assertIs(caught.exception, failure); rng.integers.assert_called_once_with(0, 1)
        reader.assert_not_called()
        for name in ['synthetic_training_background', 'fit_training_background_to_canvas', 'augment_training_background']:
            ports[name].assert_not_called()

    def test_directory_dynamic(self):
     api=self.api;events=[]
     a=self.root/'A';b=self.root/'B';c=self.root/'C'
     for d in (a,b,c):d.mkdir();(d/(d.name+'.png')).write_bytes(b'x')
     realexists=Path.exists
     class Switching(type(Path())):
      def exists(inner):
       events.append('B.exists');api.BACKGROUND_DIR=c;return True
     self.stack.enter_context(patch.object(api,'BACKGROUND_DIR',a))
     def manifest():events.append('manifest');api.BACKGROUND_DIR=Switching(b);return {}
     self.stack.enter_context(patch.object(api,'load_training_background_manifest',manifest))
     self.selected.return_value='other';self.files.return_value=[]
     captured=None
     try:value=api.training_background_library()
     except BaseException as exc:captured=exc
     self.assertIsNone(captured);self.assertEqual([r['path'] for r in value],[c/'C.png']);self.assertEqual(events,['manifest','B.exists'])

    def test_default_dynamic(self):
     api=self.api;events=[];b=self.root/'B.png';c=self.root/'C.png'
     b.write_bytes(b'x');c.write_bytes(b'x')
     class Default(type(Path())):
      def exists(inner):
       events.append('exists')
       if events[0]!='manifest':return False
       api.DEFAULT_BACKGROUND_IMAGE=b;return True
     a=Default(self.root/'A.png')
     class Items(list):
      def __contains__(inner,value):events.append(('contains',value));api.DEFAULT_BACKGROUND_IMAGE=c;return False
     provided=Items([self.file('file.png')]);self.files.return_value=provided;self.selected.return_value='green_conveyor'
     self.stack.enter_context(patch.object(api,'DEFAULT_BACKGROUND_IMAGE',a))
     def manifest():events.append('manifest');return {}
     self.stack.enter_context(patch.object(api,'load_training_background_manifest',manifest))
     captured=None
     try:value=api.training_background_library()
     except BaseException as exc:captured=exc
     self.assertIsNone(captured);self.assertEqual(value[0]['path'],c);self.assertEqual(provided[0],c);self.assertEqual(events,['manifest','exists',('contains',b)])

    def test_suffix_dynamic(self):
     api=self.api;events=[]
     class S(str):
      def lower(inner):
       lowered=super().lower();events.append(lowered);api.IMAGE_REFERENCE_SUFFIXES={lowered};return lowered
     class P(type(Path())):
      @property
      def suffix(inner):return S(super().suffix)
     items=[P(self.file('a.ONE')),P(self.file('b.TWO'))];original=Path.iterdir
     self.stack.enter_context(patch.object(Path,'iterdir',lambda p:iter(items) if p==self.directory else original(p)))
     self.stack.enter_context(patch.object(api,'IMAGE_REFERENCE_SUFFIXES',{'.none'}))
     self.stack.enter_context(patch.object(api,'load_training_background_manifest',lambda:{}))
     self.selected.return_value='other';self.files.return_value=[]
     captured=None
     try:value=api.training_background_library()
     except BaseException as exc:captured=exc
     self.assertIsNone(captured);self.assertEqual([r['path'] for r in value],items);self.assertEqual(events,['.one','.two'])

    def test_green_conveyor_default_exists_failure_does_not_retry(self):
        self.selected.return_value = 'green_conveyor'
        self.files.return_value = [self.file('one.png')]
        original = Path.exists; failure = RuntimeError('default-exists'); calls = []
        def exists(path):
            if path == self.default:
                calls.append(path)
                if len(calls) == 1: raise failure
            return original(path)
        with patch.object(Path, 'exists', exists):
            with self.assertRaises(RuntimeError) as caught: self.api.training_background_library()
        self.assertIs(caught.exception, failure); self.assertEqual(calls, [self.default])

    def test_new_path_getter_first_errors_do_not_retry(self):
        from local_inspection_service.training.background_library import TrainingBackgroundLibrary, BackgroundPaths, BackgroundSetLookup
        first = self.file('one.png'); self.file('two.jpg'); self.default.write_bytes(b'default')
        def build(mode):
            getters = {'directory': Mock(return_value=self.directory), 'default_image': Mock(return_value=self.default),
                       'suffixes': Mock(return_value={'.png', '.jpg'})}
            lookup = BackgroundSetLookup(lambda: {}, lambda _: 'green_conveyor' if mode == 'green' else 'other',
                                         lambda _: [first] if mode == 'green' else [])
            service = TrainingBackgroundLibrary(BackgroundPaths(**getters), lookup)
            operation = service.load_training_background_manifest if mode == 'manifest' else service.training_background_library
            return getters, operation
        for mode, names in [('manifest', ['directory']), ('fallback', ['directory', 'default_image', 'suffixes']),
                            ('green', ['default_image'])]:
            getters, operation = build(mode); operation()
            counts = {name: getters[name].call_count for name in names}
            for name, count in counts.items():
                self.assertGreater(count, 0)
                for index in range(1, count + 1):
                    with self.subTest(mode=mode, name=name, index=index):
                        getters, operation = build(mode); port = getters[name]; failure = RuntimeError('getter-first')
                        port.side_effect = itertools.chain(itertools.repeat(port.return_value, index - 1), [failure], itertools.repeat(port.return_value))
                        with self.assertRaises(RuntimeError) as caught: operation()
                        self.assertIs(caught.exception, failure); self.assertEqual(port.call_count, index)

    def test_synthetic_first_error_propagates_for_empty_and_unreadable_pools(self):
        for empty in [True, False]:
            with self.subTest(empty=empty), ExitStack() as scope:
                original_stack = self.stack; self.stack = scope
                try: ports, reader, rng, *_ = self.render_ports([], [] if empty else [self.item()], readable=False)
                finally: self.stack = original_stack
                synthetic = ports['synthetic_training_background']; failure = RuntimeError('synthetic-first')
                synthetic.side_effect = itertools.chain([failure], itertools.repeat(synthetic.return_value))
                with self.assertRaisesRegex(RuntimeError, 'synthetic-first') as caught:
                    self.api.render_training_background(rng)
                self.assertIs(caught.exception, failure); synthetic.assert_called_once_with(rng)
                ports['augment_training_background'].assert_not_called()
                ports['fit_training_background_to_canvas'].assert_not_called()
                self.assertEqual(reader.call_count, 0 if empty else 1)
                self.assertEqual(rng.integers.call_count, 0 if empty else 1)

    def test_isolated_pool_flag_compares_id_sets_not_candidate_counts(self):
        item = self.item(); library = [item, {**item, 'path': self.root / 'duplicate.png'}]
        ports, _, rng, *_ = self.render_ports(library, [item])
        _, metadata = self.api.render_training_background(rng, 'val')
        self.assertFalse(metadata['background_split_pool_isolated'])
        self.assertEqual(metadata['background_split_pool_size'], 1)


    def test_independent_libraries_renderers_zero_constructor_reads_and_real_images(self):
        from local_inspection_service.training.background_library import TrainingBackgroundLibrary, BackgroundPaths, BackgroundSetLookup
        from local_inspection_service.training import background_rendering as rendering
        for name in ['background_candidates_for_split', 'synthetic_training_background', 'fit_training_background_to_canvas', 'augment_training_background']:
            self.assertIs(getattr(self.api, name), getattr(rendering, name))
        instances = []
        for index, color in enumerate([(0, 40, 180), (180, 30, 0)]):
            folder = self.root / str(index); folder.mkdir()
            path = folder / 'image.png'
            self.assertTrue(cv2.imwrite(str(path), np.full((7, 11, 3), color, dtype=np.uint8)))
            manifest = {'asset': 'image.png', 'reference_photo': 'source-' + str(index)}
            (folder / 'background_manifest.json').write_text(json.dumps(manifest))
            directory = Mock(return_value=folder); default = Mock(return_value=folder / 'absent')
            suffixes = Mock(return_value={'.png'}); selected = Mock(return_value=str(index)); files = Mock(return_value=[path])
            manifest_port = Mock()
            library = TrainingBackgroundLibrary(BackgroundPaths(directory, default, suffixes), BackgroundSetLookup(manifest_port, selected, files))
            manifest_port.side_effect = library.load_training_background_manifest
            renderer = rendering.TrainingBackgroundRenderer(library.training_background_library, rendering.background_candidates_for_split,
                rendering.synthetic_training_background, rendering.fit_training_background_to_canvas, rendering.augment_training_background)
            for callback in [directory, default, suffixes, selected, files, manifest_port]: callback.assert_not_called()
            instances.append((renderer, directory, default, suffixes, selected, files, manifest_port))
        results = []
        with ExitStack() as stack:
            for name in ['load_training_background_manifest', 'training_background_library', 'selected_background_set_id', 'background_set_image_files']:
                stack.enter_context(patch.object(self.api, name, side_effect=AssertionError('entry point dependency')))
            for index, (renderer, _, _, _, selected, files, manifest_port) in enumerate(instances):
                image, meta = renderer.render_training_background(np.random.default_rng(123), 'train', 'requested-' + str(index))
                self.assertEqual(image.shape, (900, 1280, 3)); self.assertEqual(image.dtype, np.uint8)
                self.assertEqual((meta['background_source'], meta['background_set_id']), ('source-' + str(index), str(index)))
                self.assertEqual(meta['background_original_size_px'], [11, 7])
                self.assertEqual(meta['background_split'], 'train')
                self.assertFalse(meta['background_augmentation']['glare_applied'])
                selected.assert_called_once_with('requested-' + str(index)); files.assert_called_once_with(str(index))
                manifest_port.assert_called_once_with(); results.append(image)
        self.assertGreater(results[0][:, :, 2].mean(), results[0][:, :, 0].mean() + 100)
        self.assertGreater(results[1][:, :, 0].mean(), results[1][:, :, 2].mean() + 100)
        self.assertFalse(np.array_equal(*results))


if __name__ == '__main__': unittest.main()
