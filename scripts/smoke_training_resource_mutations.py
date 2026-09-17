"""Synthetic resource mutation contracts; destructive operations stay in verified fixtures."""
from contextlib import ExitStack
import copy
import itertools
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import unittest
import uuid
from unittest.mock import Mock, call, patch
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
PG_CHECK = '--postgres' in sys.argv
if PG_CHECK: sys.argv.remove('--postgres')


def available(lock):
    result = []
    def probe():
        got = lock.acquire(blocking=False); result.append(got)
        if got: lock.release()
    thread = threading.Thread(target=probe); thread.start(); thread.join(timeout=5)
    if thread.is_alive(): raise AssertionError('lock probe did not finish')
    return result[0]


class GuardedRecord(dict):
    def __init__(self, lock, **values):
        super().__init__(values); self.lock = lock
    def update(self, *args, **kwargs):
        if available(self.lock): raise AssertionError('mutation escaped shared guard')
        return super().update(*args, **kwargs)


class ResourceMutationContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.environment = patch.dict(os.environ); cls.environment.start()
        cls.runtime = tempfile.TemporaryDirectory(prefix='training-mutations-root-')
        root = Path(cls.runtime.name); (root / 'local_inspection_service/static').mkdir(parents=True)
        os.environ.update(LOCAL_INSPECTION_ROOT=str(root), VANTALINE_DATA_STORE='json',
                          LOCAL_INSPECTION_AUTO_RESUME_WORKER='0', VANTALINE_LABEL_INSPECTION_ENABLED='false')
        from local_inspection_service import server
        cls.api = server

    @classmethod
    def tearDownClass(cls): cls.runtime.cleanup(); cls.environment.stop()

    def setUp(self):
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory(prefix='training-mutations-'))).resolve()
        self.user = {'id': 'alice'}
        self.events = []
        self.pipeline_guard = threading.Lock(); self.training_guard = threading.RLock()
        self.pipeline = []; self.tasks = []; self.specs = []
        self.originals = {name: getattr(self.api, name) for name in ['load_pipeline_tasks', 'save_pipeline_task_batch_changes', 'load_training_task_records', 'save_training_task']}
        self.find = Mock(return_value=(None, None))
        self.resolve = Mock(side_effect=lambda value: Path(value))
        self.models = Mock(side_effect=lambda: self.specs)
        self.require = Mock()
        self.mutable = Mock(side_effect=lambda record, user: record.get('owner_user_id') == user['id'])
        self.owner = Mock(return_value='alice')
        self.unique_dataset = Mock(); self.unique_model = Mock()
        self.payload = Mock(return_value={'datasets': [], 'models': []})
        def load_pipeline():
            self.assertFalse(available(self.pipeline_guard)); self.events.append('pipeline-load'); return self.pipeline
        def load_tasks():
            self.assertFalse(available(self.training_guard)); self.events.append('training-load'); return self.tasks
        def batch(tasks, changed):
            self.assertFalse(available(self.pipeline_guard)); self.events.append(('pipeline-save', [r['id'] for r in changed]))
            self.assertIs(tasks, self.pipeline)
        def save(task):
            self.assertFalse(available(self.training_guard)); self.events.append(('training-save', task['job_id']))
        self.pipeline_load = Mock(side_effect=load_pipeline)
        self.training_load = Mock(side_effect=load_tasks)
        self.pipeline_save = Mock(side_effect=batch)
        self.training_save = Mock(side_effect=save)
        def clock():
            self.assertTrue(available(self.pipeline_guard)); self.assertTrue(available(self.training_guard))
            self.events.append('clock'); return 123.9
        self.clock = Mock(side_effect=clock)
        bindings = {'current_auth_user': lambda: self.user, 'find_dataset_resource': self.find,
            'list_trained_model_specs': self.models, 'resolve_service_path': self.resolve,
            'require_record_access': self.require, 'record_mutable_by_user': self.mutable,
            'record_owner_id': self.owner, 'assert_unique_dataset_name': self.unique_dataset,
            'assert_unique_model_name': self.unique_model, 'training_resources_payload': self.payload,
            '_pipeline_tasks_lock': self.pipeline_guard, '_training_task_lock': self.training_guard,
            'load_pipeline_tasks': self.pipeline_load, 'save_pipeline_task_batch_changes': self.pipeline_save,
            'load_training_task_records': self.training_load, 'save_training_task': self.training_save}
        for name, value in bindings.items(): self.stack.enter_context(patch.object(self.api, name, value))
        self.stack.enter_context(patch('time.time', self.clock))
        original_remove = shutil.rmtree
        def checked_remove(path, *args, **kwargs):
            target = Path(path).resolve()
            self.assertTrue(target.is_relative_to(self.root), str(target)); self.assertNotEqual(target, self.root)
            return original_remove(path, *args, **kwargs)
        self.remove = Mock(side_effect=checked_remove)
        self.stack.enter_context(patch.object(shutil, 'rmtree', self.remove))
        original_unlink = Path.unlink
        def checked_unlink(path, *args, **kwargs):
            target = path.resolve()
            self.assertTrue(target.is_relative_to(self.root), str(target)); self.assertNotEqual(target, self.root)
            return original_unlink(path, *args, **kwargs)
        self.unlink = Mock(side_effect=checked_unlink)
        self.stack.enter_context(patch.object(Path, 'unlink', lambda path, *a, **kw: self.unlink(path, *a, **kw)))
        for target in ['requests.request', 'subprocess.Popen', 'os.kill']:
            self.stack.enter_context(patch(target, side_effect=AssertionError('unexpected external operation')))

    def dataset(self, name='dataset', manifest=None):
        directory = self.root / name; directory.mkdir(exist_ok=True)
        item = {'id': name, 'owner_user_id': 'alice'}
        if manifest is not None: (directory / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
        self.find.return_value = (directory, item)
        return directory, item

    def model(self, run='model', metadata=None):
        directory = self.root / run; directory.mkdir(exist_ok=True)
        spec = {'run_id': run, 'run_dir': str(directory), 'owner_user_id': 'alice'}
        self.specs.append(spec)
        if metadata is not None: (directory / 'library_metadata.json').write_text(json.dumps(metadata), encoding='utf-8')
        return directory, spec

    def pipeline_record(self, name, **values):
        return GuardedRecord(self.pipeline_guard, id=name, owner_user_id='alice', **values)

    def training_record(self, name, **values):
        return GuardedRecord(self.training_guard, job_id=name, owner_user_id='alice', action='train_model', **values)

    def test_dataset_file_removal_authorization_lookup_and_missing_contract(self):
        self.assertIsNone(self.api.delete_training_dataset_resource('missing', self.user, missing_ok=True))
        self.find.assert_called_once_with('missing', user=self.user, include_samples=False, write=True)
        with self.assertRaises(HTTPException) as caught: self.api.delete_training_dataset_resource('missing', self.user)
        self.assertEqual((caught.exception.status_code, caught.exception.detail), (404, 'Dataset not found'))
        self.remove.assert_not_called()
        directory, item = self.dataset(); (directory / 'keep').write_text('fixture')
        self.assertIs(self.api.delete_training_dataset_resource('dataset', self.user), item)
        self.assertFalse(directory.exists()); self.remove.assert_called_once_with(directory)
        directory, item = self.dataset()
        self.remove.reset_mock(); self.remove.side_effect = [OSError('remove failed'), None]
        with self.assertRaisesRegex(OSError, 'remove failed'): self.api.delete_training_dataset_resource('dataset', self.user)
        self.remove.assert_called_once_with(directory); self.assertTrue(directory.exists())

    def test_model_file_removal_first_match_and_access_before_remove(self):
        directory, first = self.model(); self.specs.append({**first, 'owner_user_id': 'bob'})
        def authorize(record, user, *, write):
            self.assertIs(record, first); self.assertEqual(user, self.user); self.assertTrue(write)
            self.assertTrue(directory.exists()); self.remove.assert_not_called()
        self.require.side_effect = authorize
        self.assertIs(self.api.delete_training_model_resource('trained_model', self.user), first)
        self.require.assert_called_once_with(first, self.user, write=True); self.remove.assert_called_once_with(directory)
        self.require.reset_mock(); self.remove.reset_mock()
        self.assertIsNone(self.api.delete_training_model_resource('trained_model', self.user, missing_ok=True))
        self.require.assert_not_called(); self.remove.assert_not_called()
        self.model(); self.require.side_effect = HTTPException(403, 'denied')
        with self.assertRaises(HTTPException) as caught: self.api.delete_training_model_resource('model', self.user)
        self.assertEqual(caught.exception.status_code, 403); self.remove.assert_not_called()
        self.assertTrue(directory.exists())

    def test_pipeline_dataset_markers_guard_aliases_permissions_and_empty_batch(self):
        a = self.pipeline_record('a', dataset_id='data'); b = self.pipeline_record('b', samples_task_id='data')
        denied = self.pipeline_record('denied', dataset_id='data'); denied['owner_user_id'] = 'bob'
        unrelated = self.pipeline_record('unrelated', dataset_id='other')
        self.pipeline[:] = [a, b, denied, unrelated]
        self.assertEqual(self.api.mark_pipeline_dataset_deleted(' data ', self.user), 2)
        self.assertEqual(self.events, ['clock', 'pipeline-load', ('pipeline-save', ['a', 'b'])])
        for task in [a, b]:
            self.assertEqual((task['dataset_status'], task['dataset_deleted_at'], task['updated_at']), ('deleted', 123, 123))
        self.assertNotIn('dataset_status', denied); self.assertNotIn('dataset_status', unrelated)
        self.assertIs(self.pipeline_save.call_args.args[1][0], a)
        self.assertEqual(self.mutable.call_args_list, [call(a, self.user), call(b, self.user), call(denied, self.user)])
        self.pipeline_save.reset_mock(); self.assertEqual(self.api.mark_pipeline_dataset_deleted('../data', self.user), 0)
        self.pipeline_save.assert_called_once_with(self.pipeline, [])
        self.pipeline_load.reset_mock(); self.clock.reset_mock()
        self.assertEqual(self.api.mark_pipeline_dataset_deleted('   ', self.user), 0)
        self.pipeline_load.assert_not_called(); self.clock.assert_not_called(); self.assertTrue(available(self.pipeline_guard))

    def test_pipeline_model_markers_use_all_links_and_do_not_trim_identifier(self):
        a = self.pipeline_record('a', model_run_id='m_x'); b = self.pipeline_record('b', training_task_id='m_x')
        c = self.pipeline_record('c', ai_model_id='trained_m_x')
        no = self.pipeline_record('no', ai_model_id='trained_trained_m_x')
        self.pipeline[:] = [a, b, c, no]
        self.assertEqual(self.api.mark_pipeline_model_deleted('trained_m x', self.user), 3)
        self.assertEqual(self.events, ['clock', 'pipeline-load', ('pipeline-save', ['a', 'b', 'c'])])
        for task in [a, b, c]: self.assertEqual((task['model_status'], task['model_exists'], task['model_deleted_at'], task['updated_at']), ('deleted', False, 123, 123))
        self.assertNotIn('model_status', no)
        self.assertEqual(self.api.mark_pipeline_model_deleted(' trained_m x ', self.user), 0)
        self.assertTrue(available(self.pipeline_guard))

    def test_training_markers_filter_action_path_and_guard_mutation_and_save(self):
        a = self.training_record('a', dataset_dir='/root/data'); b = self.training_record('b', dataset_dir='/other/data')
        b['action'] = 'generate_samples'
        denied = self.training_record('denied', dataset_dir='/root/data'); denied['owner_user_id'] = 'bob'
        wrong = self.training_record('wrong', dataset_dir='/root/data'); wrong['action'] = 'other'
        no_path = self.training_record('no-path', dataset_id='data')
        self.tasks[:] = [a, b, denied, wrong, no_path]
        self.assertEqual(self.api.mark_training_task_dataset_deleted('../data..', self.user), 2)
        self.assertEqual(self.events, ['clock', 'training-load', ('training-save', 'a'), ('training-save', 'b')])
        self.assertEqual(self.training_save.call_args_list, [call(a), call(b)])
        self.assertEqual(self.mutable.call_args_list, [call(a, self.user), call(b, self.user), call(denied, self.user)])
        for task in [a, b]: self.assertEqual((task['dataset_status'], task['dataset_deleted_at'], task['updated_at']), ('deleted', 123, 123))
        for task in [denied, wrong, no_path]: self.assertNotIn('dataset_status', task)
        self.training_save.reset_mock()
        self.assertEqual(self.api.mark_training_task_dataset_deleted('data', self.user), 2)
        self.assertEqual(self.training_save.call_count, 2)
        self.assertTrue(available(self.training_guard))

    def test_marker_failures_release_guard_without_retry_or_rolling_back_objects(self):
        for kind in ['pipeline', 'training']:
            for stage in ['load', 'access', 'save']:
                with self.subTest(kind=kind, stage=stage), ExitStack() as stack:
                    record = self.pipeline_record('one', dataset_id='data') if kind == 'pipeline' else self.training_record('one', dataset_dir='/x/data')
                    records = self.pipeline if kind == 'pipeline' else self.tasks; records[:] = [record]
                    load = self.pipeline_load if kind == 'pipeline' else self.training_load
                    save = self.pipeline_save if kind == 'pipeline' else self.training_save
                    load.reset_mock(); save.reset_mock(); self.mutable.reset_mock()
                    original = (load.side_effect, self.mutable.side_effect, save.side_effect)
                    selected = {'load': load, 'access': self.mutable, 'save': save}[stage]
                    selected.side_effect = [RuntimeError(stage), [] if stage == 'load' else True]
                    fn = self.api.mark_pipeline_dataset_deleted if kind == 'pipeline' else self.api.mark_training_task_dataset_deleted
                    try:
                        with self.assertRaisesRegex(RuntimeError, stage): fn('data', self.user)
                        self.assertEqual(selected.call_count, 1)
                        self.assertTrue(available(self.pipeline_guard)); self.assertTrue(available(self.training_guard))
                        self.assertEqual('dataset_status' in record, stage == 'save')
                        if stage != 'save': save.assert_not_called()
                    finally: load.side_effect, self.mutable.side_effect, save.side_effect = original
        a = self.training_record('a', dataset_dir='/x/data'); b = self.training_record('b', dataset_dir='/x/data'); c = self.training_record('c', dataset_dir='/x/data')
        self.tasks[:] = [a, b, c]; self.training_save.reset_mock()
        self.training_save.side_effect = itertools.chain([None, OSError('second save')], itertools.repeat(None))
        with self.assertRaisesRegex(OSError, 'second save'): self.api.mark_training_task_dataset_deleted('data', self.user)
        self.assertEqual(self.training_save.call_args_list, [call(a), call(b)])
        self.assertIn('dataset_status', a); self.assertIn('dataset_status', b); self.assertNotIn('dataset_status', c)

    def test_dataset_delete_flow_order_missing_and_payload_merge_precedence(self):
        names = ['delete_training_dataset_resource', 'mark_training_task_dataset_deleted', 'mark_pipeline_dataset_deleted', 'training_resources_payload']
        events = []
        values = [None, 1, 2, {'status': 'payload-status', 'dataset_id': 'payload-id'}]
        with ExitStack() as stack:
            mocks = [stack.enter_context(patch.object(self.api, name, side_effect=lambda *a, i=i, **kw: events.append((i, a, kw)) or values[i])) for i, name in enumerate(names)]
            result = self.api.delete_training_dataset('data')
            self.assertEqual([event[0] for event in events], [0, 1, 2, 3])
            mocks[0].assert_called_once_with('data', self.user, missing_ok=True)
            mocks[1].assert_called_once_with('data', self.user); mocks[2].assert_called_once_with('data', self.user)
            mocks[3].assert_called_once_with(user=self.user)
            self.assertEqual(result, {'status': 'payload-status', 'dataset_id': 'payload-id', 'affected_training_tasks': 1, 'affected_pipeline_tasks': 2})
            values[:3] = [None, 0, 0]; mocks[3].reset_mock()
            with self.assertRaises(HTTPException) as caught: self.api.delete_training_dataset('data')
            self.assertEqual((caught.exception.status_code, caught.exception.detail), (404, 'Dataset not found'))
            mocks[3].assert_not_called()

    def test_delete_flows_stop_after_each_error_with_no_retry(self):
        for method, arg, names, values in [
            ('delete_training_dataset', 'data', ['delete_training_dataset_resource', 'mark_training_task_dataset_deleted', 'mark_pipeline_dataset_deleted', 'training_resources_payload'], [{}, 1, 1, {}]),
            ('delete_training_model', 'model', ['delete_training_model_resource', 'mark_pipeline_model_deleted', 'training_resources_payload'], [{}, 8, {}])]:
            for failed in range(len(names)):
                with self.subTest(method=method, failed=failed), ExitStack() as stack:
                    mocks = [stack.enter_context(patch.object(self.api, name, side_effect=[OSError('stage'), value] if index == failed else None, return_value=value)) for index, (name, value) in enumerate(zip(names, values))]
                    with self.assertRaisesRegex(OSError, 'stage'): getattr(self.api, method)(arg)
                    self.assertEqual([mock.call_count for mock in mocks], [1] * (failed + 1) + [0] * (len(names) - failed - 1))
        with patch.object(self.api, 'delete_training_model_resource', return_value={}) as delete, patch.object(self.api, 'mark_pipeline_model_deleted', return_value=8) as mark:
            self.assertEqual(self.api.delete_training_model('trained_model'), {'status': 'deleted', 'run_id': 'trained_model', 'datasets': [], 'models': []})
            delete.assert_called_once_with('trained_model', self.user); mark.assert_called_once_with('trained_model', self.user)

    def test_dataset_metadata_trimming_preserves_fields_and_writes_exact_bytes(self):
        original = {'samples': [1], 'display_name': 'old', 'note': 'old', 'unicode': '中文'}
        directory, item = self.dataset(manifest=original)
        request = self.api.TrainingResourceUpdateRequest(display_name='  ', note=' 新说明 ')
        result = self.api.update_training_dataset(' raw-id ', request)
        expected = {**original, 'display_name': ' raw-id ', 'note': '新说明', 'updated_at': 123}
        self.assertEqual((directory / 'manifest.json').read_text(encoding='utf-8'), json.dumps(expected, indent=2))
        self.find.assert_called_once_with(' raw-id ', user=self.user, include_samples=False, write=True)
        self.unique_dataset.assert_called_once_with(' raw-id ', 'alice', self.user, exclude_dataset_id=' raw-id ')
        self.owner.assert_called_once_with(item); self.payload.assert_called_once_with(user=self.user)
        self.assertEqual(result['status'], 'updated')
        self.unique_dataset.reset_mock(); self.unique_model.reset_mock()
        self.api.update_training_dataset('data', self.api.TrainingResourceUpdateRequest())
        self.unique_dataset.assert_not_called(); self.unique_model.assert_not_called()
        self.assertEqual(json.loads((directory / 'manifest.json').read_text()), expected)

    def test_dataset_update_read_errors_uniqueness_and_partial_write_failure(self):
        directory, item = self.dataset(); path = directory / 'manifest.json'
        for data in [None, '{broken']:
            if data is not None: path.write_text(data)
            with self.assertRaises(HTTPException) as caught: self.api.update_training_dataset('data', self.api.TrainingResourceUpdateRequest())
            self.assertEqual((caught.exception.status_code, caught.exception.detail), (500, 'Dataset manifest is unreadable'))
            self.assertIsInstance(caught.exception.__cause__, (OSError, json.JSONDecodeError))
        self.payload.assert_not_called(); self.clock.assert_not_called()
        path.write_text('{}')
        self.unique_dataset.side_effect = HTTPException(409, 'name exists')
        with self.assertRaises(HTTPException): self.api.update_training_dataset('data', self.api.TrainingResourceUpdateRequest(display_name='duplicate'))
        self.assertEqual(path.read_text(), '{}'); self.clock.assert_not_called(); self.payload.assert_not_called()
        self.unique_dataset.side_effect = None
        original_write = Path.write_text; attempts = []
        def partial(target, text, *a, **kw):
            attempts.append(target)
            original_write(target, 'partial', encoding='utf-8')
            if len(attempts) == 1: raise OSError('write failed')
            return original_write(target, text, *a, **kw)
        with patch.object(Path, 'write_text', partial):
            with self.assertRaisesRegex(OSError, 'write failed'): self.api.update_training_dataset('data', self.api.TrainingResourceUpdateRequest(note='note'))
        self.assertEqual(attempts, [path]); self.assertEqual(path.read_text(), 'partial'); self.payload.assert_not_called()
        path.write_text('[]')
        with self.assertRaises(TypeError): self.api.update_training_dataset('data', self.api.TrainingResourceUpdateRequest())

    def test_model_metadata_decode_fallback_and_owner_uniqueness(self):
        directory, spec = self.model('m_x', {'kept': True, 'note': 'old'})
        request = self.api.TrainingResourceUpdateRequest(display_name=' ', note=' new ')
        self.api.update_training_model('trained_m x', request)
        self.require.assert_called_once_with(spec, self.user, write=True)
        self.unique_model.assert_called_once_with('m x', 'alice', exclude_run_id='m_x')
        path = directory / 'library_metadata.json'
        self.assertEqual(path.read_text(), json.dumps({'kept': True, 'note': 'new', 'display_name': 'm x', 'updated_at': 123}, indent=2))
        path.write_text('{broken'); self.api.update_training_model('m_x', self.api.TrainingResourceUpdateRequest())
        self.assertEqual(json.loads(path.read_text()), {'updated_at': 123})
        self.payload.reset_mock(); original_read = Path.read_text
        with patch.object(Path, 'read_text', lambda p, *a, **kw: (_ for _ in ()).throw(PermissionError('read denied')) if p == path else original_read(p, *a, **kw)):
            with self.assertRaisesRegex(PermissionError, 'read denied'): self.api.update_training_model('m_x', request)
        self.payload.assert_not_called()

    def test_sample_deletion_order_manifest_records_and_extension_scope(self):
        directory, _ = self.dataset(manifest={'samples': [1, {'image': '/old/sample.png'}, {'image': '/other/sample.jpg'}, {'image': '/x/keep.png'}], 'other': True})
        expected_paths = []
        for split in ['train', 'val', 'test']:
            for relative in [f'images/{split}/sample.png', f'labels/{split}/sample.txt', f'previews/{split}/sample_boxed.jpg']:
                path = directory / relative; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b'fixture'); expected_paths.append(path)
        jpg = directory / 'images/train/sample.jpg'; jpg.write_bytes(b'keep')
        result = self.api.delete_training_dataset_sample('data', 'folder/sample.any')
        self.assertEqual(self.unlink.call_args_list, [call(path) for path in expected_paths])
        self.assertTrue(jpg.exists())
        self.assertEqual((result['sample'], result['removed_files'], result['removed_manifest_records']), ('folder/sample.any', 9, 2))
        self.assertEqual(json.loads((directory / 'manifest.json').read_text()), {'samples': [1, {'image': '/x/keep.png'}], 'other': True, 'sample_count': 2})
        self.clock.assert_not_called()

    def test_sample_unlink_failure_stops_and_manifest_oserror_is_swallowed_without_retry(self):
        directory, _ = self.dataset(manifest={'samples': [{'image': 'sample.png'}]})
        a = directory / 'images/train/sample.png'; b = directory / 'labels/train/sample.txt'
        for path in [a, b]: path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b'fixture')
        real = self.unlink.side_effect; calls = []
        def fail_second(path):
            calls.append(path)
            if len(calls) == 2: raise OSError('unlink')
            return real(path)
        self.unlink.side_effect = fail_second
        with self.assertRaisesRegex(OSError, 'unlink'): self.api.delete_training_dataset_sample('data', 'sample.png')
        self.assertEqual(calls, [a, b]); self.assertFalse(a.exists()); self.assertTrue(b.exists()); self.payload.assert_not_called()
        self.unlink.side_effect = real
        # A manifest write failure keeps the pre-write removed-record count, even with zero files removed.
        write_calls = []; original = Path.write_text
        def fail_once(path, text, *args, **kwargs):
            write_calls.append(path)
            if len(write_calls) == 1: raise OSError('manifest write')
            return original(path, text, *args, **kwargs)
        b.unlink(); self.unlink.reset_mock()
        with patch.object(Path, 'write_text', fail_once):
            result = self.api.delete_training_dataset_sample('data', 'sample.png')
        self.assertEqual((result['removed_files'], result['removed_manifest_records']), (0, 1))
        self.assertEqual(write_calls, [directory / 'manifest.json'])
        self.assertEqual(json.loads((directory / 'manifest.json').read_text())['samples'], [{'image': 'sample.png'}])
        self.payload.assert_called_once_with(user=self.user)

    def test_missing_sample_bad_manifest_and_unhandled_shape_errors(self):
        directory, _ = self.dataset()
        with self.assertRaises(HTTPException) as caught: self.api.delete_training_dataset_sample('data', 'none.png')
        self.assertEqual((caught.exception.status_code, caught.exception.detail), (404, 'Sample not found'))
        path = directory / 'manifest.json'; path.write_text('{broken')
        with self.assertRaises(HTTPException): self.api.delete_training_dataset_sample('data', 'none.png')
        path.write_text('[]')
        with self.assertRaises(AttributeError): self.api.delete_training_dataset_sample('data', 'none.png')
        self.payload.assert_not_called()


    def test_utf8_errors_remain_unhandled_and_model_writes_never_retry(self):
        directory, _ = self.dataset(); manifest = directory / 'manifest.json'
        run, _ = self.model(); metadata = run / 'library_metadata.json'
        manifest.write_bytes(b'\xff'); metadata.write_bytes(b'\xff')
        request = self.api.TrainingResourceUpdateRequest(note='changed')
        for operation in [lambda: self.api.update_training_dataset('data', request),
                          lambda: self.api.update_training_model('model', request),
                          lambda: self.api.delete_training_dataset_sample('data', 'none.png')]:
            with self.assertRaises(UnicodeDecodeError): operation()
        self.payload.assert_not_called(); self.clock.assert_not_called()
        metadata.write_text('{}'); self.unique_model.side_effect = HTTPException(409, 'duplicate')
        with self.assertRaises(HTTPException): self.api.update_training_model('model', self.api.TrainingResourceUpdateRequest(display_name='new'))
        self.assertEqual(metadata.read_text(), '{}'); self.clock.assert_not_called()
        self.unique_model.side_effect = None; writes = []
        original = Path.write_text
        def fail_once(path, text, *args, **kwargs):
            writes.append(path)
            if len(writes) == 1: raise OSError('metadata write')
            return original(path, text, *args, **kwargs)
        with patch.object(Path, 'write_text', fail_once):
            with self.assertRaisesRegex(OSError, 'metadata write'): self.api.update_training_model('model', request)
        self.assertEqual(writes, [metadata]); self.assertEqual(metadata.read_text(), '{}'); self.payload.assert_not_called()

    def test_response_query_failure_keeps_completed_file_changes(self):
        directory, _ = self.dataset(manifest={'samples': [{'image': 'sample.png'}]})
        run, _ = self.model(metadata={})
        for operation, path, field, expected in [
            (lambda: self.api.update_training_dataset('data', self.api.TrainingResourceUpdateRequest(note='saved')), directory / 'manifest.json', 'note', 'saved'),
            (lambda: self.api.update_training_model('model', self.api.TrainingResourceUpdateRequest(note='saved')), run / 'library_metadata.json', 'note', 'saved'),
            (lambda: self.api.delete_training_dataset_sample('data', 'sample.png'), directory / 'manifest.json', 'samples', [])]:
            self.payload.reset_mock(); self.payload.side_effect = [RuntimeError('projection'), {}]
            with self.assertRaisesRegex(RuntimeError, 'projection'): operation()
            self.payload.assert_called_once_with(user=self.user)
            self.assertEqual(json.loads(path.read_text())[field], expected)

    def test_http_write_contracts_missing_permissions_and_invalid_body(self):
        app = FastAPI()
        routes = [('DELETE', '/api/training/resources/datasets/{dataset_id}', self.api.delete_training_dataset),
                  ('PATCH', '/api/training/resources/datasets/{dataset_id}', self.api.update_training_dataset),
                  ('DELETE', '/api/training/resources/datasets/{dataset_id}/samples/{sample_name}', self.api.delete_training_dataset_sample),
                  ('DELETE', '/api/training/resources/models/{run_id}', self.api.delete_training_model),
                  ('PATCH', '/api/training/resources/models/{run_id}', self.api.update_training_model)]
        for method, path, endpoint in routes: app.add_api_route(path, endpoint, methods=[method])
        client = TestClient(app)
        for method, path, endpoint in routes:
            url = path.format(dataset_id='data', sample_name='sample.png', run_id='model')
            args = {'json': {}} if method == 'PATCH' else {}
            response = client.request(method, url, **args)
            self.assertEqual(response.status_code, 404)
            self.assertEqual(response.json(), {'detail': 'Model run not found' if 'models/' in url else 'Dataset not found'})
            with patch.object(self.api, 'current_auth_user', side_effect=HTTPException(401, 'Authentication required')):
                self.assertEqual(client.request(method, url, **args).status_code, 401)
        self.assertEqual(client.patch('/api/training/resources/datasets/data', json={'note': {}}).status_code, 422)
        self.dataset(); self.find.side_effect = HTTPException(403, 'denied')
        for method, path, _ in routes[:3]:
            self.assertEqual(client.request(method, path.format(dataset_id='data', sample_name='sample.png'), **({'json': {}} if method == 'PATCH' else {})).status_code, 403)
        self.model(); self.require.side_effect = HTTPException(403, 'denied')
        for method in ['DELETE', 'PATCH']:
            self.assertEqual(client.request(method, '/api/training/resources/models/model', **({'json': {}} if method == 'PATCH' else {})).status_code, 403)
        self.remove.assert_not_called(); self.unlink.assert_not_called()

    def test_missing_or_forbidden_model_http_delete_never_marks_pipeline(self):
        linked = self.pipeline_record('linked', model_run_id='model', model_status='available', model_exists=True)
        self.pipeline[:] = [linked]; before = dict(linked)
        app = FastAPI(); app.delete('/api/training/resources/models/{run_id}')(self.api.delete_training_model)
        client = TestClient(app)
        with patch.object(self.api, 'mark_pipeline_model_deleted', wraps=self.api.mark_pipeline_model_deleted) as marker:
            for scenario in ['missing-spec', 'missing-directory', 'forbidden']:
                with self.subTest(scenario=scenario):
                    if scenario == 'missing-directory':
                        self.specs[:] = [{'run_id': 'model', 'run_dir': str(self.root / 'missing-model')}]
                    elif scenario == 'forbidden':
                        self.specs.clear(); self.model()
                        self.require.side_effect = HTTPException(403, 'denied')
                    response = client.delete('/api/training/resources/models/trained_model')
                    expected = (403, 'denied') if scenario == 'forbidden' else (404, 'Model run not found')
                    self.assertEqual((response.status_code, response.json()), (expected[0], {'detail': expected[1]}))
                    marker.assert_not_called(); self.pipeline_load.assert_not_called(); self.pipeline_save.assert_not_called()
                    self.payload.assert_not_called(); self.remove.assert_not_called(); self.assertEqual(dict(linked), before)
        self.require.assert_called_once(); client.close()

    def test_independent_mutation_services_and_two_apps_keep_separate_storage(self):
        from local_inspection_service.training.resource_mutations import TrainingResourceMutations, ResourceWriteAccess, ResourceWriteCatalog, ResourceRetirement
        from local_inspection_service.training.dataset_links import TrainingDatasetLinks, DatasetLinkRecords
        from local_inspection_service.pipeline.resource_links import PipelineResourceLinks
        from local_inspection_service.training.resource_api import register_writes
        from local_inspection_service.training.dataset_catalog import clean_training_resource_id
        def compose(index):
            directory = self.root / str(index); directory.mkdir()
            dataset = directory / 'data'; dataset.mkdir()
            (dataset / 'manifest.json').write_text(json.dumps({'samples': [{'image': 'sample.png'}]}))
            model = directory / 'model'; model.mkdir()
            user = {'id': str(index)}
            record = {'id': 'data', 'owner_user_id': user['id']}
            spec = {'run_id': 'model', 'run_dir': str(model), 'owner_user_id': user['id']}
            tguard, pguard = threading.RLock(), threading.Lock()
            task = GuardedRecord(tguard, job_id='task', action='train_model', dataset_dir=str(dataset), owner_user_id=user['id'])
            pipeline = GuardedRecord(pguard, id='pipeline', dataset_id='data', model_run_id='model', owner_user_id=user['id'])
            current = Mock(return_value=user); require = Mock(); owner = Mock(return_value=user['id'])
            unique_data, unique_model = Mock(), Mock()
            find = Mock(side_effect=lambda identifier, **options: (dataset, record) if identifier == 'data' and dataset.exists() else (None, None))
            specs = Mock(return_value=[spec]); resolve = Mock(side_effect=Path)
            payload = Mock(return_value={'app_marker': index})
            tasks, save_task = Mock(return_value=[task]), Mock()
            pipelines, save_batch = Mock(return_value=[pipeline]), Mock()
            mutable = Mock(side_effect=lambda record, requester: record['owner_user_id'] == requester['id'])
            training = TrainingDatasetLinks(lambda: tguard, DatasetLinkRecords(tasks, save_task, lambda record: Path(record['dataset_dir']).name), mutable, clean_training_resource_id)
            linked = PipelineResourceLinks(lambda: pguard, pipelines, save_batch, mutable)
            mutations = TrainingResourceMutations(ResourceWriteAccess(current, require, owner, lambda: unique_data, lambda: unique_model),
                ResourceWriteCatalog(find, specs, lambda: resolve, payload),
                ResourceRetirement(lambda identifier, user, **options: mutations.delete_training_dataset_resource(identifier, user, **options),
                    lambda identifier, user, **options: mutations.delete_training_model_resource(identifier, user, **options),
                    training.mark_training_task_dataset_deleted, linked.mark_pipeline_dataset_deleted, linked.mark_pipeline_model_deleted))
            app = FastAPI(); routes = register_writes(app, mutations)
            for name in routes.__dataclass_fields__:
                self.assertEqual([r.endpoint for r in app.routes if r.name == name], [getattr(routes, name)])
            self.assertEqual(app.router.on_startup, [])
            for provider in [current, require, owner, unique_data, unique_model, find, specs, resolve, payload, tasks, save_task, pipelines, save_batch, mutable]:
                provider.assert_not_called()
            return {'client': TestClient(app), 'user': user, 'dataset': dataset, 'model': model, 'task': task, 'pipeline': pipeline,
                    'payload': payload, 'current': current, 'save_task': save_task, 'save_batch': save_batch}
        instances = [compose(0), compose(1)]
        with ExitStack() as stack:
            for name in ['current_auth_user', 'find_dataset_resource', 'training_resources_payload', 'delete_training_dataset_resource',
                         'delete_training_model_resource', 'mark_training_task_dataset_deleted', 'mark_pipeline_dataset_deleted', 'mark_pipeline_model_deleted']:
                stack.enter_context(patch.object(self.api, name, side_effect=AssertionError('entry point dependency')))
            operations = [('PATCH', '/datasets/data', {'note': 'saved'}), ('PATCH', '/models/model', {'note': 'saved'}),
                          ('DELETE', '/datasets/data/samples/sample.png', None), ('DELETE', '/datasets/data', None), ('DELETE', '/models/model', None)]
            for operation, suffix, body in operations:
                for index, instance in enumerate(instances):
                    response = instance['client'].request(operation, '/api/training/resources' + suffix, **({'json': body} if body is not None else {}))
                    self.assertEqual(response.status_code, 200, response.text)
                    self.assertEqual(response.json()['app_marker'], index)
                if operation == 'PATCH':
                    filename = 'manifest.json' if 'datasets' in suffix else 'library_metadata.json'
                    for instance in instances:
                        folder = instance['dataset'] if 'datasets' in suffix else instance['model']
                        self.assertEqual(json.loads((folder / filename).read_text())['note'], 'saved')
        for instance in instances:
            self.assertFalse(instance['dataset'].exists()); self.assertFalse(instance['model'].exists())
            self.assertEqual(instance['task']['dataset_status'], 'deleted')
            self.assertEqual(instance['pipeline']['dataset_status'], 'deleted'); self.assertEqual(instance['pipeline']['model_status'], 'deleted')
            self.assertEqual(instance['payload'].call_args_list, [call(user=instance['user'])] * 5)
            self.assertEqual(instance['current'].call_count, 5)
            instance['save_task'].assert_called_once_with(instance['task'])
            self.assertEqual(instance['save_batch'].call_count, 2)
            instance['client'].close()

    @unittest.skipUnless(PG_CHECK, 'use --postgres with an isolated test DSN')
    def test_real_postgres_markers_upsert_only_preserve_other_owner_and_model_snapshot(self):
        from types import SimpleNamespace
        import psycopg
        from psycopg import sql
        from local_inspection_service.storage.postgres_schema import postgres_ddl
        from local_inspection_service.storage.postgres_runtime_repository import PostgresRuntimeRepository
        schema = 'resource_markers_' + uuid.uuid4().hex
        dsn = os.environ['VANTALINE_POSTGRES_DSN']; api = self.api
        snapshot = {'pipeline': {'version': 7, 'secret_ref': 'fixture-ref', 'prompt_version': 'historical'}}
        self.clock.side_effect = None; self.clock.return_value = 123.9
        with psycopg.connect(dsn, autocommit=True) as control:
            control.execute(postgres_ddl(schema))
            try:
                with psycopg.connect(dsn) as connection, ExitStack() as stack:
                    repo = PostgresRuntimeRepository(connection, 'test', schema)
                    writes = []
                    def upsert(table, row, **kwargs):
                        writes.append((table, row.get('id') or row.get('task_id')))
                        return repo.upsert_row(table, row, **kwargs)
                    port = SimpleNamespace(fetch_all=repo.fetch_all, upsert_row=upsert,
                        replace_all=Mock(side_effect=AssertionError('must not replace table')))
                    stack.enter_context(patch.object(api, 'runtime_postgres_repository_or_none', return_value=port))
                    stack.enter_context(patch.object(api, 'resolve_model_profiles', side_effect=AssertionError('historical binding rewritten')))
                    stack.enter_context(patch.object(api, 'TRAINING_TASKS_DIR', self.root / 'tasks'))
                    stack.enter_context(patch.object(api, 'PIPELINE_TASKS_PATH', self.root / 'pipeline.json'))
                    stack.enter_context(patch.object(api, 'enrich_record_audit_fields', side_effect=lambda record, *args: record))
                    for name, callback in self.originals.items(): stack.enter_context(patch.object(api, name, callback))
                    for owner in ['alice', 'bob']:
                        api.save_pipeline_task({'id': owner, 'owner_user_id': owner, 'created_at': 1, 'updated_at': 2,
                            'dataset_id': 'data', 'model_run_id': 'model', 'model_profiles': copy.deepcopy(snapshot)})
                        api.save_training_task({'job_id': owner, 'task_id': owner, 'owner_user_id': owner, 'created_at': 1,
                            'updated_at': 2, 'dataset_dir': '/fixture/data', 'action': 'train_model', 'model_profiles': copy.deepcopy(snapshot)})
                    writes.clear()
                    self.assertEqual(api.mark_pipeline_dataset_deleted('data', self.user), 1)
                    self.assertEqual(api.mark_pipeline_model_deleted('trained_model', self.user), 1)
                    self.assertEqual(api.mark_training_task_dataset_deleted('data', self.user), 1)
                    self.assertEqual(writes, [('pipeline_tasks', 'alice'), ('pipeline_tasks', 'alice'), ('training_tasks', 'alice')])
                    pipelines = {record['id']: record for record in api.load_pipeline_tasks()}
                    tasks = {record['job_id']: record for record in api.load_training_task_records()}
                    self.assertEqual(pipelines['alice']['dataset_status'], 'deleted')
                    self.assertEqual(pipelines['alice']['model_status'], 'deleted')
                    self.assertFalse(pipelines['alice']['model_exists'])
                    self.assertEqual(tasks['alice']['dataset_status'], 'deleted')
                    for collection in [pipelines, tasks]:
                        self.assertNotIn('dataset_status', collection['bob'])
                        self.assertNotIn('model_status', collection['bob'])
                        for record in collection.values(): self.assertEqual(record['model_profiles'], snapshot)
                    self.assertEqual(repo.count_rows(('pipeline_tasks', 'training_tasks')), {'pipeline_tasks': 2, 'training_tasks': 2})
                    port.replace_all.assert_not_called(); self.assertEqual(list(self.root.rglob('*.json')), [])
            finally: control.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))


    def test_mutation_callbacks_capture_before_owner_and_path_arguments(self):
        from types import SimpleNamespace
        api=self.api
        for site in ('resolve-delete','resolve-update','unique-dataset','unique-model-owner','unique-model-id'):
            for mode in ('ordinary','prior','missing'):
                with self.subTest(site=site,mode=mode),ExitStack() as stack:
                    key=site+'-'+mode;self.specs[:]=[];directory,spec=self.model(key,{})
                    target='resolve_service_path' if site.startswith('resolve-') else 'assert_unique_dataset_name' if site=='unique-dataset' else 'assert_unique_model_name'
                    value=directory if site.startswith('resolve-') else None;a=Mock(return_value=value);b=Mock(return_value=value);c=Mock(return_value=value);events=[]
                    stack.enter_context(patch.object(api,target,a))
                    def prior():
                        if mode=='prior':setattr(api,target,b)
                        elif mode=='missing':setattr(api,target,None)
                    def argument():events.append('argument');setattr(api,target,c)
                    class Label(str):
                        def strip(inner):prior();return 'updated'
                    request=SimpleNamespace(display_name=Label('updated'),note=None)
                    if site.startswith('resolve-'):
                        class Spec(dict):
                            def get(inner,name,*args):
                                if name=='run_id':prior()
                                elif name=='run_dir':argument()
                                return super().get(name,*args)
                        self.specs[:]=[Spec(spec)]
                        action=(lambda:api.delete_training_model_resource(key,self.user)) if site=='resolve-delete' else (lambda:api.update_training_model(key,SimpleNamespace(display_name=None,note=None)))
                    elif site=='unique-dataset':
                        self.dataset(key,{})
                        def owner(item):argument();return 'alice'
                        stack.enter_context(patch.object(api,'record_owner_id',owner))
                        action=lambda:api.update_training_dataset(key,request)
                    else:
                        if site=='unique-model-owner':
                            def owner(item):argument();return 'alice'
                            stack.enter_context(patch.object(api,'record_owner_id',owner))
                        else:
                            class Spec(dict):
                                count=0
                                def get(inner,name,*args):
                                    if name=='run_id':
                                        inner.count+=1
                                        if inner.count==2:argument()
                                    return super().get(name,*args)
                            self.specs[:]=[Spec(spec)]
                        action=lambda:api.update_training_model(key,request)
                    if mode=='missing':
                        with self.assertRaises(TypeError):action()
                        a.assert_not_called();b.assert_not_called()
                    else:
                        action();(a if mode=='ordinary' else b).assert_called_once();(b if mode=='ordinary' else a).assert_not_called()
                    self.assertEqual(events,['argument']);c.assert_not_called()


    def test_marker_reads_and_permission_checks_remain_under_guard(self):
        for kind in ('training','pipeline-dataset','pipeline-model'):
            with self.subTest(kind=kind),ExitStack() as stack:
                lock=self.training_guard if kind=='training' else self.pipeline_guard;reads=[];permissions=[];test=self
                class Record(GuardedRecord):
                    def get(inner,key,*args):
                        test.assertFalse(available(lock),'record read outside marker guard');reads.append(key)
                        return super().get(key,*args)
                record=Record(lock,id='p',job_id='job',action='train_model',dataset_dir='/data',dataset_id='data',model_run_id='model',owner_user_id='alice')
                self.tasks[:]=[record] if kind=='training' else [];self.pipeline[:]=[] if kind=='training' else [record]
                def mutable(item,user):
                    self.assertFalse(available(lock),'permission outside marker guard');permissions.append(True);return True
                stack.enter_context(patch.object(self.api,'record_mutable_by_user',mutable))
                method={'training':'mark_training_task_dataset_deleted','pipeline-dataset':'mark_pipeline_dataset_deleted','pipeline-model':'mark_pipeline_model_deleted'}[kind]
                self.assertEqual(getattr(self.api,method)('model' if kind=='pipeline-model' else 'data',self.user),1)
                self.assertTrue(reads);self.assertEqual(permissions,[True]);self.assertTrue(available(lock))

    def test_first_errors_in_mutation_and_marker_operations_never_retry(self):
        api=self.api
        cases={'dataset-delete':['find'], 'model-delete':['remove','resolve','exists','is_dir','models'],
               'dataset-update':['current','find','loads','unique','clock','dumps','read','owner'],
               'sample-delete':['current','find','manifest-exists','file-exists','loads','read','dumps'],
               'model-update':['current','require','resolve','unique','clock','dumps','exists','is_dir','meta-exists','loads','owner','models','read'],
               'dataset-flow':['current'],'model-flow':['current'],
               'training':['clean','clock','dataset-id'],'pipeline-dataset':['clock'],'pipeline-model':['clock','load','save','mutable']}
        for kind,stages in cases.items():
            for stage in stages:
                with self.subTest(kind=kind,stage=stage),ExitStack() as stack:
                    key=kind+'-'+stage;self.specs[:]=[];directory,item=self.dataset(key,{'samples':[{'image':'sample.png'}]});run,spec=self.model(key+'-run',{});manifest=directory/'manifest.json';metadata=run/'library_metadata.json';image=directory/'images/train/sample.png';image.parent.mkdir(parents=True,exist_ok=True);image.write_bytes(b'fixture')
                    self.tasks[:]=[self.training_record('job',dataset_dir='/data')];self.pipeline[:]=[self.pipeline_record('p',dataset_id='data',model_run_id='model')]
                    failure=RuntimeError(kind+'-'+stage);calls=[]
                    def first(fn,*args,**kwargs):
                        calls.append(True)
                        if len(calls)==1:raise failure
                        return fn(*args,**kwargs)
                    request=api.TrainingResourceUpdateRequest(display_name='new',note='note')
                    action={'dataset-delete':lambda:api.delete_training_dataset_resource(key,self.user),'model-delete':lambda:api.delete_training_model_resource(key+'-run',self.user),'dataset-update':lambda:api.update_training_dataset(key,request),'sample-delete':lambda:api.delete_training_dataset_sample(key,'sample.png'),'model-update':lambda:api.update_training_model(key+'-run',request),'dataset-flow':lambda:api.delete_training_dataset(key),'model-flow':lambda:api.delete_training_model(key+'-run'),'training':lambda:api.mark_training_task_dataset_deleted('data',self.user),'pipeline-dataset':lambda:api.mark_pipeline_dataset_deleted('data',self.user),'pipeline-model':lambda:api.mark_pipeline_model_deleted('model',self.user)}[kind]
                    wanted=metadata if kind=='model-update' else manifest
                    if stage in ('exists','is_dir','manifest-exists','file-exists','meta-exists','read'):
                        target=Path;field='read_text' if stage=='read' else 'is_dir' if stage=='is_dir' else 'exists'
                        if stage in ('exists','is_dir'):wanted=run
                        elif stage=='file-exists':wanted=image
                        original=getattr(target,field)
                        def method(path,*args,**kwargs):return first(original,path,*args,**kwargs) if path==wanted else original(path,*args,**kwargs)
                    else:
                        target,field=(json,stage) if stage in ('loads','dumps') else (api.time,'time') if stage=='clock' else (shutil,'rmtree') if stage=='remove' else (api,{'find':'find_dataset_resource','resolve':'resolve_service_path','models':'list_trained_model_specs','current':'current_auth_user','unique':'assert_unique_model_name' if kind=='model-update' else 'assert_unique_dataset_name','owner':'record_owner_id','require':'require_record_access','clean':'clean_training_resource_id','dataset-id':'training_task_dataset_resource_id','load':'load_pipeline_tasks','save':'save_pipeline_task_batch_changes','mutable':'record_mutable_by_user'}[stage])
                        original=getattr(target,field)
                        def method(*args,**kwargs):return first(original,*args,**kwargs)
                    stack.enter_context(patch.object(target,field,method))
                    with self.assertRaises(RuntimeError) as caught:action()
                    self.assertIs(caught.exception,failure);self.assertEqual(calls,[True])
                    self.assertTrue(available(self.training_guard));self.assertTrue(available(self.pipeline_guard))


    def test_new_mutation_callback_and_guard_getter_failures(self):
        from dataclasses import replace
        api=self.api
        for site in ('resolve-delete','resolve-update','unique-dataset','unique-model','guard-training','guard-pipeline-dataset','guard-pipeline-model'):
            with self.subTest(site=site),ExitStack() as stack:
                self.specs[:]=[];directory,spec=self.model(site,{})
                self.dataset(site+'-data',{});request=api.TrainingResourceUpdateRequest(display_name='new')
                if site.startswith('guard-'):
                    service=api._training_dataset_links if site=='guard-training' else api._pipeline_resource_links;container=None;field='guard'
                    method={'guard-training':'mark_training_task_dataset_deleted','guard-pipeline-dataset':'mark_pipeline_dataset_deleted','guard-pipeline-model':'mark_pipeline_model_deleted'}[site]
                    action=lambda:getattr(api,method)('data',self.user)
                else:
                    service=api._training_resource_mutations;container='catalog' if site.startswith('resolve-') else 'access';field='resolve' if site.startswith('resolve-') else 'unique_dataset' if site=='unique-dataset' else 'unique_model'
                    if site=='resolve-delete':action=lambda:api.delete_training_model_resource(site,self.user)
                    elif site=='unique-dataset':action=lambda:api.update_training_dataset(site+'-data',request)
                    else:action=lambda:api.update_training_model(site,request)
                owner=getattr(service,container) if container else service;original=getattr(owner,field);failure=RuntimeError(site);calls=[]
                def getter():
                    calls.append(True)
                    if len(calls)==1:raise failure
                    return original()
                if container:stack.enter_context(patch.object(service,container,replace(owner,**{field:getter})))
                else:stack.enter_context(patch.object(service,field,getter))
                with self.assertRaises(RuntimeError) as caught:action()
                self.assertIs(caught.exception,failure);self.assertEqual(calls,[True]);self.assertTrue(directory.exists())
                self.assertTrue(available(self.pipeline_guard));self.assertTrue(available(self.training_guard))


    def test_model_path_resolver_capture_follows_spec_truth_test(self):
        api=self.api
        for kind in ('delete','update'):
            for mode in ('prior','missing'):
                with self.subTest(kind=kind,mode=mode),ExitStack() as stack:
                    key=kind+'-'+mode;self.specs[:]=[];directory,spec=self.model(key,{})
                    a=Mock(return_value=directory);b=Mock(return_value=directory);c=Mock(return_value=directory);events=[]
                    stack.enter_context(patch.object(api,'resolve_service_path',a))
                    class Spec(dict):
                        checks=0
                        def __bool__(inner):
                            inner.checks+=1
                            if inner.checks==1:setattr(api,'resolve_service_path',b if mode=='prior' else None)
                            return True
                        def get(inner,name,*args):
                            if name=='run_dir':events.append('argument');setattr(api,'resolve_service_path',c)
                            return super().get(name,*args)
                    self.specs[:]=[Spec(spec)]
                    def action():
                        if kind=='delete':return api.delete_training_model_resource(key,self.user)
                        return api.update_training_model(key,api.TrainingResourceUpdateRequest(note='note'))
                    if mode=='missing':
                        with self.assertRaises(TypeError):action()
                        b.assert_not_called()
                    else:action();b.assert_called_once()
                    a.assert_not_called();c.assert_not_called();self.assertEqual(events,['argument'])


if __name__ == '__main__': unittest.main()
