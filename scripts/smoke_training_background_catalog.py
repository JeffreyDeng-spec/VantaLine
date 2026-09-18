"""Offline background catalog, seeding, manifest and selection contracts."""
from contextlib import ExitStack
import copy
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import Mock, call, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class TrainingBackgroundCatalogContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.environment = patch.dict(os.environ); cls.environment.start()
        cls.runtime = tempfile.TemporaryDirectory(prefix='background-catalog-root-')
        root = Path(cls.runtime.name); (root / 'local_inspection_service/static').mkdir(parents=True)
        os.environ.update(LOCAL_INSPECTION_ROOT=str(root), VANTALINE_DATA_STORE='json',
                          LOCAL_INSPECTION_AUTO_RESUME_WORKER='0', VANTALINE_LABEL_INSPECTION_ENABLED='false')
        from local_inspection_service import server
        cls.api = server
    @classmethod
    def tearDownClass(cls): cls.runtime.cleanup(); cls.environment.stop()
    def setUp(self):
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory(prefix='background-catalog-')))
        self.directory = self.root / 'backgrounds'; self.sets = self.directory / 'sets'
        self.manifest = self.directory / 'background_sets.json'; self.default = self.directory / 'default.png'
        self.output = self.root / 'outputs'; self.user = {'id': 'alice'}; self.events = []
        self.suffixes = {'.png', '.jpg'}; self.clock = Mock(side_effect=lambda: self.events.append('clock') or 101.9)
        self.minimum = Mock(side_effect=lambda value: self.events.append('minimum'))
        self.audit = Mock(side_effect=lambda meta, path: {'created_at': 11, 'updated_at': 22,
                         'owner_user_id': meta.get('owner_user_id', 'legacy'), 'owner_username': meta.get('owner_username', 'legacy')})
        self.visible = Mock(side_effect=lambda record, user, target: record.get('owner_user_id') == (target or user['id']))
        self.url = Mock(side_effect=lambda path: '/outputs/' + path.name)
        values = {'BACKGROUND_DIR': self.directory, 'BACKGROUND_SETS_DIR': self.sets, 'BACKGROUND_SETS_MANIFEST': self.manifest,
                  'DEFAULT_BACKGROUND_IMAGE': self.default, 'OUTPUT_DIR': self.output, 'SYSTEM_OWNER_ID': 'system-fixture',
                  'IMAGE_REFERENCE_SUFFIXES': self.suffixes, 'ensure_background_set_minimum_images': self.minimum,
                  'record_audit_fields': self.audit, 'record_visible_to_user': self.visible, 'public_output_url': self.url}
        for name, value in values.items(): self.stack.enter_context(patch.object(self.api, name, value))
        self.stack.enter_context(patch('time.time', self.clock))
        for target in ['requests.request', 'subprocess.Popen', 'os.kill']:
            self.stack.enter_context(patch(target, side_effect=AssertionError('unexpected external operation')))
    def source(self): self.directory.mkdir(exist_ok=True); self.default.write_bytes(b'synthetic source')
    def test_safe_identifier_exact_defaults_and_punctuation(self):
        for value, expected in [(None, 'green_conveyor'), ('', 'green_conveyor'), ('  ', 'green_conveyor'),
                                ('@@', 'green_conveyor'), (' A b/中 ', 'A_b'), ('..', '..'), ('.a-', '.a-'), (0, 'green_conveyor')]:
            self.assertEqual(self.api.safe_background_set_id(value), expected)
    def test_image_file_list_sort_suffix_directory_filter_and_late_suffixes(self):
        self.assertEqual(self.api.image_file_list(self.sets), [])
        self.sets.mkdir(parents=True)
        for name in ['b.JPG', 'a.png', 'c.txt', 'd.PNG']: (self.sets / name).write_bytes(b'fixture')
        (self.sets / 'folder.png').mkdir()
        self.assertEqual(self.api.image_file_list(self.sets), [self.sets / name for name in ['a.png', 'b.JPG', 'd.PNG']])
        self.assertEqual(self.api.image_file_list(self.sets / 'a.png'), [])
        self.suffixes.clear(); self.suffixes.add('.txt')
        self.assertEqual(self.api.image_file_list(self.sets), [self.sets / 'c.txt'])
        error = OSError('exists')
        with patch.object(Path, 'exists', side_effect=error):
            with self.assertRaises(OSError) as caught: self.api.image_file_list(self.sets)
            self.assertIs(caught.exception, error)
    def test_manifest_missing_errors_unicode_and_non_mapping_passthrough(self):
        self.assertEqual(self.api.load_background_sets_manifest(), {})
        self.directory.mkdir()
        for raw, expected in [('not json', {}), ('[]', []), ('null', None), ('"text"', 'text'), ('{"sets": {}}', {'sets': {}})]:
            self.manifest.write_text(raw, encoding='utf-8'); self.assertEqual(self.api.load_background_sets_manifest(), expected)
        with patch.object(Path, 'read_text', side_effect=OSError('read')): self.assertEqual(self.api.load_background_sets_manifest(), {})
        with patch.object(Path, 'exists', side_effect=OSError('exists')): self.assertEqual(self.api.load_background_sets_manifest(), {})
        self.manifest.write_bytes(bytes([255]))
        with self.assertRaises(UnicodeDecodeError): self.api.load_background_sets_manifest()
    def test_manifest_write_exact_json_and_only_background_directory_creation(self):
        value = {'name': '绿色', 'value': float('nan')}
        self.api.write_background_sets_manifest(value)
        self.assertEqual(self.manifest.read_text(encoding='utf-8'), json.dumps(value, indent=2))
        outside = self.root / 'uncreated/manifest.json'
        with patch.object(self.api, 'BACKGROUND_SETS_MANIFEST', outside):
            with self.assertRaises(FileNotFoundError): self.api.write_background_sets_manifest({})
        self.assertFalse(outside.parent.exists())
        other = self.root / 'new-backgrounds'
        with patch.object(self.api, 'BACKGROUND_DIR', other):
            with self.assertRaises(TypeError): self.api.write_background_sets_manifest({'bad': object()})
        self.assertTrue(other.is_dir())
    def test_seed_missing_default_short_circuits_all_dependencies(self):
        with patch.object(self.api, 'load_background_sets_manifest') as load, patch.object(self.api, 'write_background_sets_manifest') as write:
            self.api.seed_default_background_set(); load.assert_not_called(); write.assert_not_called()
        self.minimum.assert_not_called(); self.clock.assert_not_called(); self.assertFalse(self.sets.exists())
    def test_seed_copy_once_but_minimum_clock_write_repeat_and_existing_defaults_preserved(self):
        self.source(); existing = {'name': 'keep', 'nested': []}; value = {'sets': {'green_conveyor': existing}, 'default_set_id': None}
        with patch.object(self.api, 'load_background_sets_manifest', side_effect=lambda: self.events.append('load') or value) as load, \
             patch.object(self.api, 'write_background_sets_manifest', side_effect=lambda item: self.events.append('write')) as write, \
             patch.object(shutil, 'copy2', wraps=shutil.copy2) as copy_file:
            self.api.seed_default_background_set(); self.api.seed_default_background_set()
            self.assertEqual(self.events, ['load', 'minimum', 'clock', 'write'] * 2)
            copy_file.assert_called_once_with(self.default, self.sets / 'green_conveyor/default.png')
            self.assertEqual(load.call_count, 2); self.assertEqual(write.call_args_list, [call(value)] * 2)
            self.assertIs(value['sets']['green_conveyor'], existing); self.assertIsNone(value['default_set_id'])
            self.assertEqual(self.minimum.call_args_list, [call('green_conveyor')] * 2)
        self.assertEqual((self.sets / 'green_conveyor/default.png').read_bytes(), b'synthetic source')
    def test_seed_new_record_and_partial_failure_boundaries(self):
        for stage in ['minimum', 'clock', 'write']:
            with self.subTest(stage=stage), ExitStack() as stack:
                self.source(); case_sets = self.root / ('sets-' + stage); stack.enter_context(patch.object(self.api, 'BACKGROUND_SETS_DIR', case_sets))
                value = {'sets': []}; error = OSError(stage); write = Mock()
                stack.enter_context(patch.object(self.api, 'load_background_sets_manifest', return_value=value))
                stack.enter_context(patch.object(self.api, 'write_background_sets_manifest', write))
                self.minimum.reset_mock(); self.minimum.side_effect = None; self.clock.reset_mock(); self.clock.side_effect = None; self.clock.return_value = 101
                target = {'minimum': self.minimum, 'clock': self.clock, 'write': write}[stage]
                target.side_effect = [error, 101 if stage == 'clock' else None]
                with self.assertRaises(OSError) as caught: self.api.seed_default_background_set()
                self.assertIs(caught.exception, error); target.assert_called_once()
                self.assertEqual((case_sets / 'green_conveyor/default.png').read_bytes(), b'synthetic source')
                self.assertEqual(self.clock.call_count, int(stage != 'minimum')); self.assertEqual(write.call_count, int(stage == 'write'))
                if stage == 'write':
                    self.assertEqual(value['sets']['green_conveyor']['created_at'], 101)
                    self.assertEqual(value['sets']['green_conveyor']['source'], str(self.default)); self.assertEqual(value['default_set_id'], 'green_conveyor')
                else: self.assertEqual(value, {'sets': []})
    def test_directories_seed_before_scan_and_sorted_directories_only(self):
        def seed():
            self.sets.mkdir(parents=True); (self.sets / 'z').mkdir(); (self.sets / 'a').mkdir(); (self.sets / 'b').write_bytes(b'file')
        with patch.object(self.api, 'seed_default_background_set', side_effect=seed) as seeded:
            self.assertEqual(self.api.background_set_dirs(), [self.sets / 'a', self.sets / 'z']); seeded.assert_called_once_with()
        with patch.object(self.api, 'seed_default_background_set', side_effect=OSError('seed')):
            with self.assertRaisesRegex(OSError, 'seed'): self.api.background_set_dirs()
    def test_payload_system_fallback_copy_aliases_and_exact_fields(self):
        directory = self.sets / 'green_conveyor'; directory.mkdir(parents=True); (directory / 'photo.png').write_bytes(b'file')
        shared = ['alice']; meta = {'name': 'custom', 'owner_user_id': '', 'owner_username': 'old', 'shared_with_user_ids': shared}
        before = copy.deepcopy(meta); result = self.api.background_set_payload('green_conveyor', meta)
        self.assertEqual(meta, before); self.assertIs(meta['shared_with_user_ids'], shared)
        audited, audit_path = self.audit.call_args.args
        self.assertIsNot(audited, meta); self.assertEqual(audit_path, directory)
        self.assertEqual((audited['owner_user_id'], audited['owner_username'], audited['shared_with_user_ids']), ('system-fixture', 'system', ['*']))
        self.assertEqual(result, {'id': 'green_conveyor', 'name': 'custom', 'description': '', 'source': '',
            'created_at': 11, 'updated_at': 22, 'owner_user_id': 'system-fixture', 'owner_username': 'system', 'shared_with_user_ids': ['*'],
            'generation_method': '', 'status': 'ready', 'image_count': 1,
            'images': [{'name': 'photo.png', 'path': str(directory / 'photo.png'), 'url': '/api/backgrounds/green_conveyor/photo.png'}]})
        self.url.assert_not_called(); meta['owner_user_id'] = 'alice'
        result = self.api.background_set_payload('green_conveyor', meta)
        self.assertIs(result['shared_with_user_ids'], shared); self.assertEqual(result['owner_username'], 'old')
    def test_payload_status_empty_defaults_and_existing_prefix_url_rule(self):
        result = self.api.background_set_payload(' raw key ', {'shared_with_user_ids': 'wrong', 'status': 'custom'})
        self.assertEqual((result['id'], result['name'], result['status'], result['images']), ('raw_key', 'raw key', 'custom', []))
        self.assertEqual(result['shared_with_user_ids'], []); self.assertEqual(self.api.background_set_payload('x')['status'], 'empty')
        prefixed = self.root / 'outputs-sibling'; directory = prefixed / 'x'; directory.mkdir(parents=True); (directory / 'photo.png').write_bytes(b'file')
        with patch.object(self.api, 'BACKGROUND_SETS_DIR', prefixed):
            result = self.api.background_set_payload('x')
        self.assertEqual(result['images'][0]['url'], '/outputs/photo.png'); self.url.assert_called_once_with(directory / 'photo.png')
    def test_list_preseed_manifest_snapshot_raw_key_collision_and_duplicate_payloads(self):
        old = {'sets': {'raw key': {'name': 'unreachable raw metadata'}, 'z': {'name': 'old'}}}
        newer = {'sets': {'z': {'name': 'new'}, 'new': {'name': 'seeded'}}}; current = [old]; events = []
        def directories(): current[0] = newer; events.append('dirs'); return [Path('raw key'), Path('z')]
        def payload(identifier, meta): events.append(('payload', identifier, meta)); return {'id': self.api.safe_background_set_id(identifier), **meta}
        with patch.object(self.api, 'load_background_sets_manifest', side_effect=lambda: events.append('load') or current[0]) as load, \
             patch.object(self.api, 'background_set_dirs', side_effect=directories), patch.object(self.api, 'background_set_payload', side_effect=payload) as project:
            result = self.api.list_background_sets()
            self.assertEqual(result, [{'id': 'raw_key', 'name': 'unreachable raw metadata'}, {'id': 'raw_key'}, {'id': 'z', 'name': 'old'}])
            self.assertEqual(events[:2], ['load', 'dirs']); load.assert_called_once_with()
            self.assertEqual(project.call_args_list, [call('raw key', old['sets']['raw key']), call('raw_key', {}), call('z', old['sets']['z'])])
        self.visible.assert_not_called()
    def test_list_visibility_truthiness_and_target_after_projection(self):
        rows = [{'id': 'a', 'owner_user_id': 'alice'}, {'id': 'b', 'owner_user_id': 'bob'}]
        with patch.object(self.api, 'load_background_sets_manifest', return_value={}), \
             patch.object(self.api, 'background_set_dirs', return_value=[Path('a'), Path('b')]), \
             patch.object(self.api, 'background_set_payload', side_effect=lambda name, meta: rows[0 if name == 'a' else 1]):
            self.assertEqual(self.api.list_background_sets(None), rows); self.assertEqual(self.api.list_background_sets({}), rows)
            self.visible.assert_not_called(); result = self.api.list_background_sets(self.user, 'bob')
            self.assertEqual(result, [rows[1]]); self.assertIs(result[0], rows[1])
            self.assertEqual(self.visible.call_args_list, [call(row, self.user, 'bob') for row in rows])
    def test_selection_requested_short_circuit_status_rules_default_and_sorted_fallback(self):
        rows = [{'id': 'b', 'image_count': 1}, {'id': 'a', 'image_count': 2, 'status': ''},
                {'id': 'bad', 'image_count': 1, 'status': ' ready '}, {'id': 'zero', 'image_count': 0, 'status': 'ready'}]
        with patch.object(self.api, 'list_background_sets', return_value=rows) as listing, \
             patch.object(self.api, 'load_background_sets_manifest', return_value={'default_set_id': 'b'}) as load:
            self.assertEqual(self.api.selected_background_set_id('a', self.user, ''), 'a')
            listing.assert_called_once_with(self.user, ''); load.assert_not_called()
            self.assertEqual(self.api.selected_background_set_id('bad'), 'b'); load.assert_called_once_with()
            load.return_value = {'default_set_id': 'missing'}; self.assertEqual(self.api.selected_background_set_id(None), 'a')
            listing.return_value = []; self.assertIsNone(self.api.selected_background_set_id(None))
    def test_selection_invalid_count_and_manifest_types_propagate_without_repair(self):
        with patch.object(self.api, 'list_background_sets', return_value=[{'id': 'a', 'image_count': '1'}]), \
             patch.object(self.api, 'load_background_sets_manifest') as load:
            with self.assertRaises(TypeError): self.api.selected_background_set_id('a')
            load.assert_not_called()
        for value in [None, []]:
            with patch.object(self.api, 'list_background_sets', return_value=[]), patch.object(self.api, 'load_background_sets_manifest', return_value=value):
                with self.assertRaises(AttributeError): self.api.selected_background_set_id(None)
    def test_image_files_uses_single_argument_selection_and_empty_short_circuit(self):
        expected = [self.sets / 'chosen/photo.png']
        with patch.object(self.api, 'selected_background_set_id', return_value=None) as select, \
             patch.object(self.api, 'image_file_list', return_value=expected) as files:
            self.assertEqual(self.api.background_set_image_files(' raw '), []); select.assert_called_once_with(' raw '); files.assert_not_called()
            select.return_value = 'chosen'
            self.assertIs(self.api.background_set_image_files(' raw '), expected); files.assert_called_once_with(self.sets / 'chosen')


    def test_manifest_partial_write_failure_preserves_exact_evidence_without_retry(self):
        error = OSError('partial manifest write'); original_write = Path.write_text
        value = {'name': 'fixture', 'sets': {}}; encoded = json.dumps(value, indent=2)
        def write(path, text, *args, **kwargs):
            if write_mock.call_count == 1:
                path.write_bytes(text[:9].encode('utf-8'))
                raise error
            return original_write(path, text, *args, **kwargs)
        with patch.object(Path, 'write_text', autospec=True, side_effect=write) as write_mock:
            with self.assertRaises(OSError) as caught: self.api.write_background_sets_manifest(value)
            self.assertIs(caught.exception, error)
            write_mock.assert_called_once_with(self.manifest, encoded, encoding='utf-8')
        self.assertEqual(self.manifest.read_bytes(), encoded[:9].encode('utf-8'))
        self.assertEqual(value, {'name': 'fixture', 'sets': {}})

    def test_seed_partial_copy_failure_keeps_target_and_skips_later_work(self):
        self.source(); target = self.sets / 'green_conveyor/default.png'; original_copy = shutil.copy2
        error = OSError('partial source copy')
        def copy_source(source, destination, *args, **kwargs):
            if copying.call_count == 1:
                Path(destination).write_bytes(b'partial image')
                raise error
            return original_copy(source, destination, *args, **kwargs)
        with patch.object(shutil, 'copy2', side_effect=copy_source) as copying, \
             patch.object(self.api, 'write_background_sets_manifest') as write:
            with self.assertRaises(OSError) as caught: self.api.seed_default_background_set()
            self.assertIs(caught.exception, error); copying.assert_called_once_with(self.default, target)
            write.assert_not_called()
        self.assertEqual(target.read_bytes(), b'partial image'); self.assertEqual(self.default.read_bytes(), b'synthetic source')
        self.minimum.assert_not_called(); self.clock.assert_not_called(); self.assertFalse(self.manifest.exists())

    def _capture_callback_window(self, site, mode):
        import types
        ns = self.api.__dict__
        events = []
        field = {'payload': 'background_set_payload', 'safe': 'safe_background_set_id', 'images': 'image_file_list'}[site]

        def called(label):

            def callback(*args):
                events.append(label)
                return {'id': str(args[0])} if site == 'payload' else 'chosen' if site == 'safe' else [Path('image')]
            return callback
        a, b, c = (called('A'), called('B'), called('C'))

        def prior():
            events.append('prior')
            ns[field] = a if mode == 'ordinary' else b if mode == 'prior' else None

        def argument():
            events.append('argument')
            ns[field] = c
        if site == 'payload':
            ns[field] = a

            class Identifier(str):

                def __lt__(self, other):
                    prior()
                    return str.__lt__(self, other)

            class Metadata(dict):

                def get(self, key, *args):
                    argument()
                    return {'name': 'fixture'}
            meta = Metadata()
            ns['load_background_sets_manifest'] = lambda: {'sets': meta}
            ns['background_set_dirs'] = lambda: [types.SimpleNamespace(name=Identifier('a')), types.SimpleNamespace(name=Identifier('b'))]
            invoke = lambda: ns['list_background_sets']()
        elif site == 'safe':
            ns[field] = lambda value: 'missing'

            class Manifest(dict):

                def get(self, key, *args):
                    argument()
                    return 'chosen'
            ns['list_background_sets'] = lambda user, target: [{'id': 'chosen', 'image_count': 1}]

            def load():
                prior()
                return Manifest()
            ns['load_background_sets_manifest'] = load
            invoke = lambda: ns['selected_background_set_id']('missing')
        else:
            ns[field] = a

            class Selected(str):

                def __bool__(self):
                    prior()
                    return True

            class Directory:

                def __truediv__(self, value):
                    argument()
                    return Path('chosen')
            ns['BACKGROUND_SETS_DIR'] = Directory()
            ns['selected_background_set_id'] = lambda value: Selected('chosen')
            invoke = lambda: ns['background_set_image_files']('chosen')
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
            assert caught is None, (caught, events)
            assert events[index + 1:index + 2] == [('A' if mode == 'ordinary' else 'B')], events
            if site == 'payload':
                assert events[index + 2:] == ['argument', 'C'], events
        return events

    def _refresh_payload_per_item(self):
        import types
        ns = self.api.__dict__
        events = []

        def second(*args):
            events.append('B')
            return {'id': args[0]}

        def first(*args):
            events.append('A')
            ns['background_set_payload'] = second
            return {'id': args[0]}
        ns.update(background_set_payload=first, load_background_sets_manifest=lambda: {}, background_set_dirs=lambda: [Path('a'), Path('b')])
        assert ns['list_background_sets']() == [{'id': 'a'}, {'id': 'b'}]
        assert events == ['A', 'B'], events
        return events

    def test_callbacks_capture_before_argument_effects(self):
        for site in ['payload', 'safe', 'images']:
            for mode in ['ordinary', 'prior', 'missing']:
                with self.subTest(site=site, mode=mode), patch.dict(self.api.__dict__):
                    self._capture_callback_window(site, mode)

    def test_payload_callback_refreshes_for_each_item(self):
        with patch.dict(self.api.__dict__): self._refresh_payload_per_item()

    def test_direct_filesystem_and_json_first_failures_do_not_retry(self):
        cases = [('manifest-write', Path, 'mkdir', 'directory'), ('manifest-write', json, 'dumps', None),
                 ('manifest-read', Path, 'exists', 'manifest'), ('manifest-read', Path, 'read_text', 'manifest'),
                 ('manifest-read', json, 'loads', None), ('images', Path, 'exists', 'private'),
                 ('images', Path, 'is_dir', 'private'), ('images', Path, 'iterdir', 'private'),
                 ('images', Path, 'is_file', 'image'), ('seed', Path, 'mkdir', 'seed'),
                 ('seed', Path, 'exists', 'default'), ('seed', Path, 'exists', 'target'),
                 ('dirs', Path, 'exists', 'sets'), ('dirs', Path, 'iterdir', 'sets'),
                 ('dirs', Path, 'is_dir', 'private')]
        for mode, owner, field, selector in cases:
            errors = [RuntimeError('io-first')]
            if mode == 'manifest-read':
                errors.append(json.JSONDecodeError('invalid', '', 0) if field == 'loads' else OSError('read-first'))
            for failure in errors:
                with self.subTest(mode=mode, field=field, selector=selector, error=type(failure)), ExitStack() as scope:
                    f, _, _ = self.failure_fixture(scope, 'list')
                    paths = {'directory': f.directory, 'manifest': f.manifest, 'private': f.sets / 'private',
                             'image': f.sets / 'private/a.png', 'seed': f.sets / 'green_conveyor',
                             'default': f.default, 'target': f.sets / 'green_conveyor/default.png', 'sets': f.sets}
                    operations = {'manifest-write': lambda: self.api.write_background_sets_manifest({'sets': {}}),
                                  'manifest-read': self.api.load_background_sets_manifest,
                                  'images': lambda: self.api.image_file_list(paths['private']),
                                  'seed': self.api.seed_default_background_set, 'dirs': self.api.background_set_dirs}
                    original = getattr(owner, field); calls = []
                    def fail_once(*args, **kwargs):
                        if selector is None or args[0] == paths[selector]:
                            calls.append(None)
                            if len(calls) == 1: raise failure
                        return original(*args, **kwargs)
                    with patch.object(owner, field, fail_once):
                        if mode == 'manifest-read' and not isinstance(failure, RuntimeError):
                            self.assertEqual(operations[mode](), {})
                        else:
                            with self.assertRaises(type(failure)) as caught: operations[mode]()
                            self.assertIs(caught.exception, failure)
                    self.assertEqual(len(calls), 1)

    def test_path_and_policy_provider_first_failures_do_not_retry(self):
        from dataclasses import replace
        api = self.api
        cases = [('manifest-read', api._background_manifest, None, 'path'),
                 ('manifest-write', api._background_manifest, None, 'directory'),
                 ('manifest-write', api._background_manifest, None, 'path'),
                 ('payload-system', api._background_catalog, 'paths', 'sets'),
                 ('payload-system', api._background_catalog, 'access', 'system_owner'),
                 ('payload', api._background_catalog, 'paths', 'output'),
                 ('images', api._background_image_files, None, 'suffixes'),
                 ('seed', api._background_seeding, 'paths', 'sets'),
                 ('dirs', api._background_seeding, 'paths', 'sets'),
                 ('seed', api._background_seeding, 'paths', 'default'),
                 ('files', api._background_selection, None, 'sets')]
        def fixture(scope, mode):
            f, operation, _ = self.failure_fixture(scope, mode if mode in ['payload', 'seed', 'dirs', 'files'] else 'list')
            operations = {'manifest-read': api.load_background_sets_manifest,
                          'manifest-write': lambda: api.write_background_sets_manifest({'sets': {}}),
                          'payload-system': lambda: api.background_set_payload('green_conveyor'),
                          'images': lambda: api.image_file_list(f.sets / 'private')}
            return operations.get(mode, operation)
        for mode, service, group, field in cases:
            original = getattr(getattr(service, group) if group else service, field)
            def install(scope, port):
                if group: scope.enter_context(patch.object(service, group, replace(getattr(service, group), **{field: port})))
                else: scope.enter_context(patch.object(service, field, port))
            with ExitStack() as scope:
                operation = fixture(scope, mode); seen = Mock(wraps=original); install(scope, seen)
                operation(); count = seen.call_count
            self.assertGreater(count, 0)
            for index in range(1, count + 1):
                with self.subTest(mode=mode, field=field, index=index), ExitStack() as scope:
                    operation = fixture(scope, mode); calls = []; failure = RuntimeError('provider-first')
                    def fail_once():
                        calls.append(None)
                        if len(calls) == index: raise failure
                        return original()
                    install(scope, fail_once)
                    with self.assertRaises(RuntimeError) as caught: operation()
                    self.assertIs(caught.exception, failure); self.assertEqual(len(calls), index)

    def test_output_url_first_failure_does_not_retry(self):
        with ExitStack() as scope:
            f, operation, _ = self.failure_fixture(scope, 'payload')
            scope.enter_context(patch.object(self.api, 'OUTPUT_DIR', f.root))
            original = f.url; calls = []; failure = RuntimeError('url-first')
            def fail_once(path):
                calls.append(path)
                if len(calls) == 1: raise failure
                return original(path)
            scope.enter_context(patch.object(self.api, 'public_output_url', fail_once))
            with self.assertRaises(RuntimeError) as caught: operation()
            self.assertIs(caught.exception, failure); self.assertEqual(calls, [f.sets / 'private/a.png'])

    def failure_fixture(self, scope, mode):
        f = TrainingBackgroundCatalogContracts(); f.api = self.api; f.setUp(); scope.callback(f.doCleanups)
        f.source(); (f.sets / 'private').mkdir(parents=True); (f.sets / 'private/a.png').write_bytes(b'sample')
        f.manifest.write_text(json.dumps({'sets': {'private': {'owner_user_id': 'alice'}}, 'default_set_id': 'private'}), encoding='utf-8')
        operations = {
            'seed': ('seed_default_background_set', lambda: self.api.seed_default_background_set()),
            'dirs': ('background_set_dirs', lambda: self.api.background_set_dirs()),
            'payload': ('background_set_payload', lambda: self.api.background_set_payload('private')),
            'list': ('list_background_sets', lambda: self.api.list_background_sets(f.user)),
            'selection': ('selected_background_set_id', lambda: self.api.selected_background_set_id('missing', f.user)),
            'files': ('background_set_image_files', lambda: self.api.background_set_image_files('missing')),
        }
        entry, operation = operations[mode]
        names = ['safe_background_set_id', 'load_background_sets_manifest', 'write_background_sets_manifest',
                 'image_file_list', 'seed_default_background_set', 'background_set_dirs', 'background_set_payload',
                 'list_background_sets', 'selected_background_set_id', 'ensure_background_set_minimum_images',
                 'record_audit_fields', 'record_visible_to_user', 'public_output_url']
        ports = {}
        for name in names:
            if name != entry:
                original = getattr(self.api, name); port = Mock(wraps=original)
                scope.enter_context(patch.object(self.api, name, port)); ports[name] = (self.api, name, port)
        import time
        port = Mock(wraps=f.clock); scope.enter_context(patch.object(time, 'time', port)); ports['clock'] = (time, 'time', port)
        return f, operation, ports

    def test_first_callback_error_propagates_without_retry(self):
        for mode in ['seed', 'dirs', 'payload', 'list', 'selection', 'files']:
            with ExitStack() as scope:
                _, operation, ports = self.failure_fixture(scope, mode); operation()
                counts = {name: port.call_count for name, (_, _, port) in ports.items() if port.call_count}
            for name, count in counts.items():
                for index in range(1, count + 1):
                    with self.subTest(mode=mode, name=name, index=index), ExitStack() as scope:
                        _, operation, ports = self.failure_fixture(scope, mode)
                        owner, field, original = ports[name]; calls = []; failure = RuntimeError('background-first')
                        def fail_once(*args, **kwargs):
                            calls.append(None)
                            if len(calls) == index: raise failure
                            return original(*args, **kwargs)
                        scope.enter_context(patch.object(owner, field, fail_once))
                        with self.assertRaises(RuntimeError) as caught: operation()
                        self.assertIs(caught.exception, failure); self.assertEqual(len(calls), index)

    def test_new_getter_first_error_propagates_without_retry(self):
        from dataclasses import replace
        fields = [('list', self.api._background_catalog, 'records', 'payload'),
                  ('selection', self.api._background_selection, None, 'safe'),
                  ('files', self.api._background_selection, None, 'images')]
        for mode, service, group, name in fields:
            original = getattr(getattr(service, group) if group else service, name)
            def install(scope, port):
                if group: scope.enter_context(patch.object(service, group, replace(getattr(service, group), **{name: port})))
                else: scope.enter_context(patch.object(service, name, port))
            with ExitStack() as scope:
                _, operation, _ = self.failure_fixture(scope, mode); seen = Mock(wraps=original); install(scope, seen)
                operation(); count = seen.call_count
            self.assertGreater(count, 0)
            for index in range(1, count + 1):
                with self.subTest(mode=mode, name=name, index=index), ExitStack() as scope:
                    _, operation, _ = self.failure_fixture(scope, mode); calls = []; failure = RuntimeError('background-getter')
                    def fail_once():
                        calls.append(None)
                        if len(calls) == index: raise failure
                        return original()
                    install(scope, fail_once)
                    with self.assertRaises(RuntimeError) as caught: operation()
                    self.assertIs(caught.exception, failure); self.assertEqual(len(calls), index)

    def test_independent_background_compositions_real_files_and_no_constructor_reads(self):
        from local_inspection_service.training.background_manifest import BackgroundManifest
        from local_inspection_service.training.background_catalog import (safe_background_set_id, BackgroundImageFiles,
            BackgroundCatalogPaths, BackgroundCatalogRecords, BackgroundCatalogAccess, BackgroundCatalog)
        from local_inspection_service.training.background_seeding import BackgroundSeedPaths, BackgroundSeeding
        from local_inspection_service.training.background_selection import BackgroundSelection
        def build(owner):
            root = self.root / owner; directory = root / 'backgrounds'; sets = directory / 'sets'
            directory.mkdir(parents=True); default = directory / 'default.png'; default.write_bytes(owner.encode())
            manifest_path = directory / 'background_sets.json'; manifest_path.write_text(json.dumps({'sets': {'private': {'owner_user_id': 'hidden'}}}), encoding='utf-8')
            callbacks = []
            def port(fn): value = Mock(side_effect=fn); callbacks.append(value); return value
            manifest = BackgroundManifest(port(lambda: directory), port(lambda: manifest_path))
            files = BackgroundImageFiles(port(lambda: {'.png', '.jpg'}))
            def minimum(identifier): (sets / identifier / 'generated.jpg').write_bytes((owner + '-variant').encode())
            seed = BackgroundSeeding(BackgroundSeedPaths(port(lambda: default), port(lambda: sets)),
                port(manifest.load_background_sets_manifest), port(manifest.write_background_sets_manifest), port(minimum),
                port(lambda: seed.seed_default_background_set()), port(lambda: 101))
            def audit(meta, path): return {'created_at': 11, 'updated_at': 22, 'owner_user_id': meta.get('owner_user_id', ''), 'owner_username': meta.get('owner_username', '')}
            catalog = BackgroundCatalog(BackgroundCatalogPaths(port(lambda: sets), port(lambda: root / 'outputs')),
                BackgroundCatalogRecords(port(manifest.load_background_sets_manifest), port(seed.background_set_dirs),
                                         port(lambda: catalog.background_set_payload)),
                BackgroundCatalogAccess(port(lambda: 'system-' + owner), port(audit),
                    port(lambda item, user, target: '*' in item.get('shared_with_user_ids', []) or item['owner_user_id'] == (target or user['id']))),
                port(safe_background_set_id), port(files.image_file_list), port(lambda path: '/output/' + owner + '/' + path.name))
            selection = BackgroundSelection(port(lambda: safe_background_set_id), port(catalog.list_background_sets),
                port(manifest.load_background_sets_manifest), port(lambda identifier: selection.selected_background_set_id(identifier)),
                port(lambda: files.image_file_list), port(lambda: sets))
            for callback in callbacks: callback.assert_not_called()
            return owner, sets, manifest, seed, catalog, selection
        instances = [build(owner) for owner in ['alice', 'bob']]
        for name in ['safe_background_set_id', 'image_file_list', 'load_background_sets_manifest', 'write_background_sets_manifest',
                     'seed_default_background_set', 'background_set_dirs', 'background_set_payload', 'list_background_sets',
                     'selected_background_set_id', 'background_set_image_files', 'record_audit_fields', 'record_visible_to_user',
                     'public_output_url', 'ensure_background_set_minimum_images']:
            self.stack.enter_context(patch.object(self.api, name, side_effect=AssertionError('unexpected root dependency')))
        for index in [1, 0, 1, 0]:
            owner, sets, manifest, seed, catalog, selection = instances[index]; user = {'id': owner}
            self.assertEqual(selection.selected_background_set_id(None, user), 'green_conveyor')
            rows = catalog.list_background_sets(user)
            self.assertEqual([row['id'] for row in rows], ['green_conveyor']); self.assertEqual(rows[0]['owner_user_id'], 'system-' + owner)
            self.assertEqual(rows[0]['source'], str(sets.parent / 'default.png'))
            self.assertEqual(rows[0]['image_count'], 2)
            self.assertEqual(rows[0]['images'], [
                {'name': name, 'path': str(sets / 'green_conveyor' / name), 'url': '/api/backgrounds/green_conveyor/' + name}
                for name in ['default.png', 'generated.jpg']
            ])
            paths = selection.background_set_image_files(None)
            self.assertEqual(paths, [sets / 'green_conveyor/default.png', sets / 'green_conveyor/generated.jpg'])
            self.assertEqual(paths[0].read_bytes(), owner.encode()); self.assertEqual(paths[1].read_bytes(), (owner + '-variant').encode())
            saved = manifest.load_background_sets_manifest()
            self.assertEqual(saved['sets']['private']['owner_user_id'], 'hidden'); self.assertEqual(saved['default_set_id'], 'green_conveyor')


if __name__ == '__main__': unittest.main()
