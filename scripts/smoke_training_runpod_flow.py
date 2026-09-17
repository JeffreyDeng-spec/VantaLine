"""Offline contracts for RunPod payloads, submission and existing polling behavior."""
from contextlib import ExitStack
from itertools import chain, repeat
import base64
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class FlowFixture:
    def __init__(self, root):
        self.root = Path(root)
        self.task = {'job_id': 'old-id', 'runpod_job_id': 'old-remote', 'epochs': 800,
                     'model_variant': 'yolo_ocr', 'mode': 'yolo', 'status': 'original-state', 'owner_user_id': 'alice'}
        self.dataset = {'dataset_dir': 'synthetic-dataset', 'dataset_yaml': 'synthetic-yaml'}
        self.archive = {'sha256': 'synthetic-sha', 'url': 'https://fixture.invalid/dataset', 'path': str(self.root / 'dataset.zip')}
        self.payload_value = {'synthetic_input': True}
        self.submission = {'id': ' remote / id ', 'status': 'IN_QUEUE'}
        self.output = {'ok': True, 'synthetic_output': True}
        self.import_updates = {'training_run_dir': 'synthetic-run', 'imported_model_path': 'synthetic-model'}
        self.updates = []
        self.timeline = Mock()
        self.endpoint = Mock(return_value='endpoint-fixture')
        self.timeout = Mock(return_value=5)
        self.ttl = Mock(return_value=3)
        self.poll = Mock(return_value=2)
        self.inline = Mock(return_value=0)
        self.upload = Mock(return_value={'url': 'https://fixture.invalid/upload'})
        self.archive_create = Mock(return_value=self.archive)
        self.payload = Mock(return_value=self.payload_value)
        self.submit = Mock(side_effect=lambda value: self.submission)
        self.http = Mock(side_effect=lambda *args, **kwargs: {'status': 'COMPLETED', 'output': self.output})
        self.extract = Mock(return_value=self.output)
        self.importer = Mock(return_value=self.import_updates)
        self.summary = Mock(side_effect=lambda value: {'summary': value.get('status', 'output')})
        self.bound = Mock(side_effect=lambda value, limit: str(value)[:limit])
        self.update = Mock(side_effect=self.updated)
        self.sync = Mock()
        self.warmup = Mock()
        self.monotonic = Mock(return_value=100)
        self.sleep = Mock()
        for name in ('endpoint', 'timeout', 'ttl', 'poll', 'inline', 'upload', 'archive_create', 'payload',
                     'submit', 'http', 'extract', 'importer', 'summary', 'bound', 'update', 'sync', 'warmup', 'monotonic', 'sleep'):
            self.timeline.attach_mock(getattr(self, name), name)

    def updated(self, job, **values):
        self.updates.append(values)
        return {'status': 'replacement-state'}

    def bind(self, api, stack):
        bindings = {'runpod_yolo_endpoint_id': self.endpoint, 'runpod_yolo_job_timeout_seconds': self.timeout,
                    'runpod_yolo_dataset_token_ttl_seconds': self.ttl, 'runpod_yolo_poll_interval_seconds': self.poll,
                    'runpod_yolo_inline_dataset_max_bytes': self.inline, 'create_runpod_training_artifact_upload': self.upload,
                    'create_runpod_training_dataset_archive': self.archive_create, 'runpod_training_input_payload': self.payload,
                    'submit_runpod_yolo_training': self.submit, 'runpod_yolo_http_request': self.http,
                    'extract_runpod_worker_output': self.extract, 'import_runpod_yolo_artifacts': self.importer,
                    'runpod_public_response_summary': self.summary, 'bounded_text': self.bound,
                    'update_training_task': self.update, 'sync_training_state_from_task': self.sync, 'start_yolo_warmup': self.warmup}
        for name, value in bindings.items():
            stack.enter_context(patch.object(api, name, value))
        stack.enter_context(patch('time.monotonic', self.monotonic))
        stack.enter_context(patch('time.sleep', self.sleep))


class RunPodFlowContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.environment = patch.dict(os.environ)
        cls.environment.start()
        cls.runtime = tempfile.TemporaryDirectory(prefix='runpod-flow-root-')
        root = Path(cls.runtime.name)
        (root / 'local_inspection_service/static').mkdir(parents=True)
        os.environ.update(LOCAL_INSPECTION_ROOT=str(root), VANTALINE_DATA_STORE='json',
                          LOCAL_INSPECTION_AUTO_RESUME_WORKER='0', VANTALINE_LABEL_INSPECTION_ENABLED='false')
        from local_inspection_service import server
        cls.api = server
        cls.capture_entries()

    @classmethod
    def capture_entries(cls):
        cls.payload_entry = staticmethod(cls.api.runpod_training_input_payload)
        cls.submit_entry = staticmethod(cls.api.submit_runpod_yolo_training)
        cls.output_entry = staticmethod(cls.api.extract_runpod_worker_output)

    @classmethod
    def tearDownClass(cls):
        cls.runtime.cleanup()
        cls.environment.stop()

    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory(prefix='runpod-flow-')))
        self.f = FlowFixture(self.root)
        self.f.bind(self.api, self.stack)
        self.stack.enter_context(patch('requests.request', side_effect=AssertionError('unexpected network')))
        self.stack.enter_context(patch('subprocess.Popen', side_effect=AssertionError('unexpected process')))
        self.stack.enter_context(patch('os.kill', side_effect=AssertionError('unexpected signal')))
        self.stack.enter_context(patch.dict(os.environ))
        for name in ('VANTALINE_RUNPOD_YOLO_BASE_MODEL', 'VANTALINE_RUNPOD_YOLO_BASE_MODEL_SHA256',
                     'VANTALINE_RUNPOD_YOLO_BASE_MODEL_URL', 'VANTALINE_RUNPOD_YOLO_BASE_MODEL_URL_SHA256', 'VANTALINE_RUNPOD_YOLO_DEVICE'):
            os.environ.pop(name, None)

    def test_payload_exact_defaults_mode_priority_bounds_and_inline_boundary(self):
        f = self.f
        Path(f.archive['path']).write_bytes(b'synthetic')
        task = {**f.task, 'train_mode': 'special', 'image_size': 9000}
        result = self.payload_entry('job', task, f.archive)
        self.assertEqual(result, {'job_id': 'job', 'train_mode': 'special', 'epochs': 500, 'imgsz': 1280,
            'dataset_sha256': 'synthetic-sha', 'return_artifact_b64': False, 'artifact_upload_url': 'https://fixture.invalid/upload',
            'inference_smoke': True, 'timeout_seconds': 5, 'dataset_url': f.archive['url'], 'base_model': '/models/vantaline-yolo-base.pt'})
        f.upload.assert_called_once_with('job', task)
        self.assertEqual([call[0] for call in f.timeline.mock_calls], ['upload', 'timeout', 'inline'])
        for limit, expected_inline in [(9, True), (8, False), (-1, False), (0, False)]:
            f.inline.return_value = limit
            result = self.payload_entry('job', {**f.task, 'epochs': 0, 'image_size': 0}, f.archive)
            self.assertEqual('dataset_archive_b64' in result, expected_inline)
            self.assertEqual('dataset_url' in result, not expected_inline)
            self.assertEqual(result['epochs'], 1)
            self.assertEqual(result['imgsz'], 640)
            if expected_inline:
                self.assertEqual(base64.b64decode(result['dataset_archive_b64']), b'synthetic')
        f.http.assert_not_called()

    def test_payload_upload_precedes_validation_and_never_retries(self):
        f = self.f
        for task, archive, error in [({**f.task, 'epochs': 'bad'}, f.archive, ValueError), (f.task, {}, KeyError)]:
            f.upload.reset_mock()
            f.timeout.reset_mock()
            with self.assertRaises(error):
                self.payload_entry('job', task, archive)
            f.upload.assert_called_once_with('job', task)
            f.timeout.assert_not_called()
        f.upload.reset_mock()
        f.upload.side_effect = [RuntimeError('unknown upload'), {'url': 'second-success'}]
        with self.assertRaisesRegex(RuntimeError, 'unknown upload'):
            self.payload_entry('job', f.task, f.archive)
        f.upload.assert_called_once()
        f.http.assert_not_called()

    def test_payload_environment_whitespace_checksums_and_read_failure(self):
        f = self.f
        os.environ.update(VANTALINE_RUNPOD_YOLO_BASE_MODEL='   ', VANTALINE_RUNPOD_YOLO_BASE_MODEL_SHA256=' hash ', VANTALINE_RUNPOD_YOLO_DEVICE=' 0 ')
        result = self.payload_entry('job', f.task, f.archive)
        self.assertEqual((result['base_model'], result['base_model_sha256'], result['device']), ('', 'hash', '0'))
        os.environ['VANTALINE_RUNPOD_YOLO_BASE_MODEL_URL'] = ' https://fixture.invalid/base.pt '
        f.upload.reset_mock()
        with self.assertRaisesRegex(RuntimeError, 'VANTALINE_RUNPOD_YOLO_BASE_MODEL_URL_SHA256 is required'):
            self.payload_entry('job', f.task, f.archive)
        f.upload.assert_called_once()
        os.environ['VANTALINE_RUNPOD_YOLO_BASE_MODEL_URL_SHA256'] = ' remote-hash '
        result = self.payload_entry('job', f.task, f.archive)
        self.assertEqual(result['base_model_url'], 'https://fixture.invalid/base.pt')
        self.assertEqual(result['base_model_sha256'], 'remote-hash')
        self.assertNotIn('base_model', result)
        Path(f.archive['path']).write_bytes(b'synthetic')
        f.inline.return_value = 9
        f.upload.reset_mock()
        with patch.object(Path, 'read_bytes', side_effect=OSError('read failure')) as read:
            with self.assertRaisesRegex(OSError, 'read failure'):
                self.payload_entry('job', f.task, f.archive)
        read.assert_called_once()
        f.upload.assert_called_once()
        f.http.assert_not_called()

    def test_submit_preserves_payload_identity_policy_cap_and_single_post(self):
        f = self.f
        payload = {'nested': []}
        result = self.submit_entry(payload)
        f.http.assert_called_once_with('POST', 'run', json_body={'input': payload, 'policy': {'executionTimeout': 5000, 'ttl': 8000}})
        self.assertIs(f.http.call_args.kwargs['json_body']['input'], payload)
        self.assertEqual([call[0] for call in f.timeline.mock_calls], ['timeout', 'ttl', 'http'])
        self.assertEqual(result['status'], 'COMPLETED')
        f.timeout.return_value = 800000
        self.submit_entry(payload)
        self.assertEqual(f.http.call_args.kwargs['json_body']['policy'], {'executionTimeout': 800000000, 'ttl': 604800000})
        f.timeout.return_value = -2
        f.ttl.return_value = -3
        self.submit_entry(payload)
        self.assertEqual(f.http.call_args.kwargs['json_body']['policy'], {'executionTimeout': -2000, 'ttl': -5000})
        f.http.reset_mock()
        f.http.side_effect = [RuntimeError('POST unknown outcome'), {'id': 'would-repeat'}]
        with self.assertRaisesRegex(RuntimeError, 'POST unknown outcome'):
            self.submit_entry(payload)
        f.http.assert_called_once()

    def test_output_parser_strict_boolean_identity_and_terminal_whitespace(self):
        f = self.f
        output = {'ok': True, 'nested': []}
        self.assertIs(self.output_entry({'output': output}), output)
        self.assertEqual(self.output_entry({'output': json.dumps(output)}), output)
        for value in (None, [], 1, '[]', 'null'):
            with self.assertRaisesRegex(RuntimeError, 'without a JSON worker output'):
                self.output_entry({'output': value})
        for value in ({'ok': 1, 'error': 'error-first', 'message': 'later'}, {'ok': False, 'message': 'message'}, 'invalid json'):
            with self.assertRaisesRegex(RuntimeError, 'RunPod worker failed:'):
                self.output_entry({'output': value})
            self.assertEqual(f.bound.call_args.args[1], 300)
        self.assertFalse(self.api.runpod_terminal_status(' completed '))
        for value in ('completed', 'FAILED', 'Cancelled', 'CANCELED', 'timed_out'):
            self.assertTrue(self.api.runpod_terminal_status(value))
        with self.assertRaises(AttributeError):
            self.api.runpod_terminal_status(None)

    def test_flow_full_status_sequence_import_order_original_state_and_mode(self):
        f = self.f
        statuses = ['in_queue', ' IN_PROGRESS ', '', 'unrecognized', ' completed ']
        f.http.side_effect = [{'status': value, 'output': f.output} for value in statuses]
        with patch('time.time', return_value=123):
            self.api.run_runpod_training_task('job', f.task, f.dataset)
        self.assertEqual([update['progress'] for update in f.updates], [78, 82, 86, 92, 96, 96, 96, 100])
        self.assertEqual([update['status'] for update in f.updates], ['running'] * 6 + ['original-state', 'completed'])
        self.assertEqual([update['remote_training_status'] for update in f.updates], ['preparing_dataset', 'IN_QUEUE', 'IN_QUEUE', 'IN_PROGRESS', 'UNKNOWN', 'UNRECOGNIZED', 'COMPLETED', 'COMPLETED'])
        f.archive_create.assert_called_once_with('job', f.task, f.dataset)
        f.payload.assert_called_once_with('job', f.task, f.archive)
        f.submit.assert_called_once_with(f.payload_value)
        self.assertIs(f.submit.call_args.args[0], f.payload_value)
        self.assertEqual(f.http.call_count, 5)
        self.assertTrue(all(call.args == ('GET', 'status/remote%20%2F%20id') and not call.kwargs for call in f.http.call_args_list))
        f.importer.assert_called_once_with({**f.task, 'job_id': 'job', 'runpod_job_id': 'remote / id'}, f.output)
        self.assertIsNot(f.importer.call_args.args[0], f.task)
        self.assertEqual(f.task['job_id'], 'old-id')
        self.assertIs(f.importer.call_args.args[1], f.output)
        self.assertEqual(f.summary.call_count, 8)
        self.assertEqual([call[0] for call in f.timeline.mock_calls][-7:], ['extract', 'importer', 'summary', 'summary', 'update', 'sync', 'warmup'])
        self.assertEqual(f.updates[-1]['completed_at'], 123)
        self.assertEqual((f.updates[-1]['current_epoch'], f.updates[-1]['total_epochs']), (500, 500))
        f.warmup.assert_called_once_with('training_completed', ['trained_job__yolo_ocr'])
        self.assertEqual(f.monotonic.call_count, 6)
        f.timeout.assert_called_once()
        f.ttl.assert_called_once()
        f.poll.assert_called_once()

    def test_completed_submission_still_polls_and_timeout_comparison_before_sleep(self):
        f = self.f
        f.submission = {'job_id': ' done ', 'status': 'COMPLETED'}
        f.monotonic.side_effect = [100, 108]
        self.api.run_runpod_training_task('job', f.task, f.dataset)
        f.sleep.assert_called_once_with(2)
        f.http.assert_called_once_with('GET', 'status/done')
        self.assertEqual([call[0] for call in f.timeline.mock_calls][:13], ['endpoint', 'update', 'archive_create', 'payload', 'submit', 'summary', 'update', 'monotonic', 'timeout', 'ttl', 'poll', 'monotonic', 'sleep'])
        # It can finish after the deadline while sleeping/requesting; there is no new post-GET deadline guard.
        f.http.reset_mock()
        f.sleep.reset_mock()
        f.monotonic.side_effect = [100, 108, 999]
        self.api.run_runpod_training_task('job', f.task, f.dataset)
        f.http.assert_called_once()
        self.assertEqual(f.monotonic.call_count, 4)

    def test_timeout_over_threshold_and_missing_submission_id_do_not_poll(self):
        f = self.f
        f.monotonic.side_effect = [100, 108.01]
        with self.assertRaisesRegex(RuntimeError, 'polling exceeded configured timeout'):
            self.api.run_runpod_training_task('job', f.task, f.dataset)
        f.sleep.assert_not_called()
        f.http.assert_not_called()
        f.importer.assert_not_called()
        f.sync.assert_not_called()
        self.assertEqual(len(f.updates), 2)
        f.submission = {'id': ' ', 'job_id': 'ignored-by-truthy-space'}
        f.monotonic.reset_mock()
        with self.assertRaisesRegex(RuntimeError, 'did not return a job id'):
            self.api.run_runpod_training_task('job', f.task, f.dataset)
        f.monotonic.assert_not_called()
        f.http.assert_not_called()

    def test_terminal_failures_leave_intermediate_original_status_and_raise_once(self):
        for status in ('FAILED', 'CANCELLED', 'CANCELED', 'TIMED_OUT'):
            with self.subTest(status=status), ExitStack() as stack:
                f = FlowFixture(self.root)
                f.bind(self.api, stack)
                f.http.side_effect = [{'status': status, 'error': 'first', 'message': 'second'}, {'status': 'COMPLETED'}]
                with self.assertRaisesRegex(RuntimeError, 'RunPod training ended with ' + status + ': first'):
                    self.api.run_runpod_training_task('job', f.task, f.dataset)
                f.http.assert_called_once()
                self.assertEqual(f.updates[-1]['status'], 'original-state')
                self.assertEqual(f.updates[-1]['progress'], 96)
                f.bound.assert_called_once_with('first', 300)
                f.importer.assert_not_called()
                f.sync.assert_not_called()
                f.warmup.assert_not_called()
                self.assertFalse(any(update['status'] == 'failed' for update in f.updates))

    def test_flow_unknown_outcome_stops_without_retries_or_later_stages(self):
        order = ['archive_create', 'payload', 'submit', 'http', 'extract', 'importer', 'sync', 'warmup']
        for failed in order:
            with self.subTest(failed=failed), ExitStack() as stack:
                f = FlowFixture(self.root)
                f.bind(self.api, stack)
                target = getattr(f, failed)
                valid={'archive_create':f.archive,'payload':f.payload_value,'submit':f.submission,'http':{'status':'COMPLETED','output':f.output},'extract':f.output,'importer':f.import_updates,'sync':None,'warmup':None}[failed]
                target.side_effect = chain([RuntimeError('unknown ' + failed)],repeat(valid))
                with self.assertRaisesRegex(RuntimeError, 'unknown ' + failed):
                    self.api.run_runpod_training_task('job', f.task, f.dataset)
                for name in order:
                    callback = getattr(f, name)
                    if order.index(name) <= order.index(failed):
                        callback.assert_called_once()
                    else:
                        callback.assert_not_called()
                self.assertFalse(any(update['status'] == 'failed' for update in f.updates))
                completed = [update for update in f.updates if update['status'] == 'completed']
                self.assertEqual(len(completed), 1 if failed in ('sync', 'warmup') else 0)

    def test_keyword_collisions_preserve_before_and_after_import_side_effects(self):
        f = self.f
        with self.assertRaisesRegex(TypeError, 'status'):
            self.api.run_runpod_training_task('job', f.task, {'status': 'conflict'})
        f.endpoint.assert_called_once()
        f.update.assert_not_called()
        f.archive_create.assert_not_called()
        f.import_updates['status'] = 'conflict'
        with self.assertRaisesRegex(TypeError, 'status'):
            self.api.run_runpod_training_task('job', f.task, f.dataset)
        f.importer.assert_called_once()
        self.assertEqual(len(f.updates), 3)
        f.sync.assert_not_called()
        f.warmup.assert_not_called()

    def test_summary_and_completed_write_fail_after_import_without_settlement(self):
        for failed in ('summary-state', 'summary-output', 'completed-update'):
            with self.subTest(failed=failed), ExitStack() as stack:
                f = FlowFixture(self.root)
                f.bind(self.api, stack)
                if failed.startswith('summary'):
                    offset = 2 if failed == 'summary-state' else 3
                    f.summary.side_effect = chain([{'summary': index} for index in range(offset)]+[RuntimeError(failed)],repeat({'would':'succeed'}))
                else:
                    def update(job, **values):
                        if values.get('status') == 'completed':
                            raise RuntimeError(failed)
                        return f.updated(job, **values)
                    f.update.side_effect = update
                with self.assertRaisesRegex(RuntimeError, failed):
                    self.api.run_runpod_training_task('job', f.task, f.dataset)
                f.importer.assert_called_once()
                self.assertEqual(f.summary.call_count, 3 if failed == 'summary-state' else 4)
                self.assertEqual(f.update.call_count, 4 if failed == 'completed-update' else 3)
                self.assertFalse(any(update['status'] in ('completed', 'failed') for update in f.updates))
                f.sync.assert_not_called()
                f.warmup.assert_not_called()


    def test_inline_file_access_short_circuit_empty_path_and_environment_timing(self):
        f = self.f
        for limit, expected in [(0, []), (-1, ['exists', 'stat']), (10, ['exists', 'stat', 'read'])]:
            f.inline.return_value = limit
            seen = []
            def exists(path):
                seen.append('exists')
                return True
            def stat(path):
                from types import SimpleNamespace
                seen.append('stat')
                return SimpleNamespace(st_size=5)
            def read(path):
                seen.append('read')
                os.environ['VANTALINE_RUNPOD_YOLO_BASE_MODEL'] = 'late-model'
                return b'bytes'
            with patch.object(Path, 'exists', exists), patch.object(Path, 'stat', stat), patch.object(Path, 'read_bytes', read):
                result = self.payload_entry('job', f.task, {**f.archive, 'path': ''})
            self.assertEqual(seen, expected)
            self.assertEqual('dataset_archive_b64' in result, limit == 10)
            if limit == 10:
                self.assertEqual(result['base_model'], 'late-model')
        f.inline.return_value = 10
        with patch.object(Path, 'exists', return_value=False) as exists, patch.object(Path, 'stat') as stat, patch.object(Path, 'read_bytes') as read:
            self.payload_entry('job', f.task, f.archive)
        exists.assert_called_once()
        stat.assert_not_called()
        read.assert_not_called()

    def test_flow_nonstring_job_id_and_warmup_fallbacks_keep_original_priority(self):
        f = self.f
        for task, variant in [({'model_variant': 'other', 'mode': 'yolo_ocr', 'train_mode': 'yolo_ocr'}, 'yolo'),
                              ({'mode': 'yolo_ocr', 'train_mode': 'yolo'}, 'yolo_ocr'), ({}, 'yolo')]:
            f.submission = {'id': 17}
            f.warmup.reset_mock()
            f.http.reset_mock()
            self.api.run_runpod_training_task('job', task, f.dataset)
            f.http.assert_called_once_with('GET', 'status/17')
            f.warmup.assert_called_once_with('training_completed', ['trained_job__' + variant])
            self.assertEqual(f.updates[-2]['status'], 'running')
            self.assertEqual(f.updates[-1]['current_epoch'], 1)
            self.assertEqual(f.updates[-1]['total_epochs'], 1)

    def test_outer_runner_keeps_one_historical_model_scope_through_runpod_completion(self):
        from scripts.smoke_training_runner import Fixture as RunnerFixture
        f = self.f
        flow = self.api.run_runpod_training_task
        outer = RunnerFixture(self.root)
        outer.task['action'] = 'train_model'
        outer.mode.side_effect = None
        outer.mode.return_value = 'runpod'
        outer.bind(self.api, self.stack)
        f.bind(self.api, self.stack)
        outer.runpod.side_effect = flow
        outer.resolver.version = 999
        seen = []
        def submit(payload):
            seen.append(outer.resolver.current_snapshot())
            return f.submission
        def importer(task, output):
            seen.append(outer.resolver.current_snapshot())
            return f.import_updates
        def warmup(*args):
            seen.append(outer.resolver.current_snapshot())
        f.submit.side_effect = submit
        f.importer.side_effect = importer
        f.warmup.side_effect = warmup
        self.api.run_training_task('job')
        outer.runpod.assert_called_once()
        f.submit.assert_called_once()
        f.importer.assert_called_once()
        f.warmup.assert_called_once()
        self.assertEqual(seen, [outer.binding['model_profiles']] * 3)
        self.assertEqual(outer.resolver.scopes, [outer.binding['model_profiles']])
        self.assertIsNone(outer.resolver.current_snapshot())


    def test_independent_payload_submission_flow_and_zero_call_construction(self):
        from local_inspection_service.training.runpod_submission import RunPodPayload, RunPodSubmission
        from local_inspection_service.training.runpod_outputs import RunPodOutputParser, runpod_terminal_status
        from local_inspection_service.training.runpod_flow import RunPodFlow, RunPodFlowSettings, RunPodFlowRecords, RunPodFlowInputs, RunPodFlowResults
        first, second = FlowFixture(self.root / 'one'), FlowFixture(self.root / 'two')
        for fixture, name in [(first, 'one'), (second, 'two')]:
            with ExitStack() as stack:
                fixture.bind(self.api, stack)
                state = {'environment': {'VANTALINE_RUNPOD_YOLO_BASE_MODEL': name}}
                environment = Mock(side_effect=lambda: state['environment'])
                payload = RunPodPayload(fixture.upload, fixture.timeout, fixture.inline, environment)
                submission = RunPodSubmission(fixture.timeout, fixture.ttl, fixture.http)
                parser = RunPodOutputParser(lambda:fixture.bound)
                flow = RunPodFlow(
                    RunPodFlowSettings(fixture.endpoint, fixture.timeout, fixture.ttl, fixture.poll),
                    RunPodFlowRecords(lambda:fixture.update, fixture.sync, lambda:fixture.warmup),
                    RunPodFlowInputs(fixture.archive_create, fixture.payload, fixture.submit),
                    RunPodFlowResults(lambda:fixture.http, fixture.summary, parser.extract_runpod_worker_output,
                                      lambda:fixture.importer, lambda:runpod_terminal_status, lambda:fixture.bound))
                self.assertEqual(fixture.timeline.mock_calls, [])
                environment.assert_not_called()
                result = payload.runpod_training_input_payload('job', fixture.task, fixture.archive)
                self.assertEqual(result['base_model'], name)
                state['environment'] = {'VANTALINE_RUNPOD_YOLO_BASE_MODEL': 'replaced-' + name}
                self.assertEqual(payload.runpod_training_input_payload('job', fixture.task, fixture.archive)['base_model'], 'replaced-' + name)
                submitted = submission.submit_runpod_yolo_training(result)
                self.assertEqual(submitted['status'], 'COMPLETED')
                self.assertIs(fixture.http.call_args.kwargs['json_body']['input'], result)
                with patch.object(self.api, 'runpod_yolo_http_request', side_effect=AssertionError('root request dependency')):
                    flow.run_runpod_training_task('job', fixture.task, fixture.dataset)
                fixture.importer.assert_called_once()
                fixture.warmup.assert_called_once()
                self.assertEqual(fixture.updates[-1]['status'], 'completed')
        self.assertIsNot(first.updates, second.updates)

    def test_each_task_update_failure_blocks_later_side_effects_without_retry(self):
        for failed_index in (1, 2, 3, 4):
            with self.subTest(failed_index=failed_index), ExitStack() as stack:
                f = FlowFixture(self.root)
                f.bind(self.api, stack)
                def update(job, **values):
                    if f.update.call_count == failed_index:
                        raise RuntimeError('task write failed')
                    return f.updated(job, **values)
                f.update.side_effect = update
                with self.assertRaisesRegex(RuntimeError, 'task write failed'):
                    self.api.run_runpod_training_task('job', f.task, f.dataset)
                self.assertEqual(f.update.call_count, failed_index)
                self.assertEqual(len(f.updates), failed_index - 1)
                for callback in (f.archive_create, f.payload, f.submit):
                    self.assertEqual(callback.call_count, 1 if failed_index > 1 else 0)
                self.assertEqual(f.http.call_count, 1 if failed_index >= 3 else 0)
                self.assertEqual(f.importer.call_count, 1 if failed_index == 4 else 0)
                self.assertEqual(f.summary.call_count, {1: 0, 2: 1, 3: 2, 4: 4}[failed_index])
                f.sync.assert_not_called()
                f.warmup.assert_not_called()


    def test_flow_and_parser_capture_callbacks_before_argument_evaluation(self):
        api=self.api
        for stage in ('request','import','warmup','flow-bound','parser-bound','terminal'):
            for mode in ('ordinary','prior','missing'):
                with self.subTest(stage=stage,mode=mode),ExitStack() as stack:
                    f=FlowFixture(self.root/(stage+'-'+mode));f.root.mkdir();f.bind(api,stack);events=[]
                    field={'request':'runpod_yolo_http_request','import':'import_runpod_yolo_artifacts','warmup':'start_yolo_warmup','flow-bound':'bounded_text','parser-bound':'bounded_text','terminal':'runpod_terminal_status'}[stage]
                    original=getattr(api,field)
                    def callback(label):
                        def call(*args,**kwargs):events.append(label);return original(*args,**kwargs)
                        return call
                    stack.enter_context(patch.object(api,field,callback('A')))
                    def before():
                        if mode!='ordinary':setattr(api,field,callback('B') if mode=='prior' else None)
                    def argument():events.append('argument');setattr(api,field,callback('C'))
                    job='job'
                    if stage=='request':
                        class Remote(str):
                            def __str__(self):return self
                            def strip(self,*args):return self
                            def encode(self,*args,**kwargs):argument();return super().encode(*args,**kwargs)
                        f.submission['id']=Remote('remote / id');f.sleep.side_effect=lambda *_:before()
                    elif stage=='import':
                        class Task(dict):
                            def __iter__(self):return super().__iter__()
                            def keys(self):argument();return super().keys()
                        f.task=Task(f.task);f.extract.side_effect=lambda *_:before() or f.output
                    elif stage=='warmup':
                        class Job:
                            def __format__(self,spec):argument();return 'job'
                        job=Job();f.sync.side_effect=lambda *_:before()
                    elif stage in ('flow-bound','parser-bound'):
                        class Detail:
                            def __str__(self):argument();return 'failure detail'
                        class Output(dict):
                            def get(self,key,default=None):
                                if key=='error':before()
                                return super().get(key,default)
                        output=Output(ok=False,status='FAILED',error=Detail())
                        if stage=='flow-bound':f.http.side_effect=lambda *a,**kw:output
                    else:
                        reads=[]
                        class Status:
                            def __str__(self):argument();return 'COMPLETED'
                        class Body(dict):
                            def get(self,key,default=None):
                                if key=='status':
                                    reads.append(True)
                                    if len(reads)>1:return Status()
                                    return ''
                                return super().get(key,default)
                        f.summary.side_effect=None;f.summary.return_value={};f.http.side_effect=lambda *a,**kw:Body()
                        def update(job,**values):
                            if values.get('progress')==96:before()
                            return f.updated(job,**values)
                        f.update.side_effect=update
                    caught=None
                    try:
                        if stage=='parser-bound':self.output_entry({'output':output})
                        else:api.run_runpod_training_task(job,f.task,f.dataset)
                    except BaseException as error:caught=error
                    self.assertIn('argument',events);pos=events.index('argument');after=[x for x in events[pos+1:] if x in ('A','B','C')]
                    if mode=='missing':self.assertIsInstance(caught,TypeError);self.assertEqual(after,[])
                    else:
                        self.assertEqual(after[0],'A' if mode=='ordinary' else 'B')
                        if stage in ('flow-bound','parser-bound','terminal'):self.assertIsInstance(caught,RuntimeError)
                        else:self.assertIsNone(caught)


    def test_every_task_update_captures_writer_before_arguments(self):
        import time
        api=self.api
        for stage in ('preparing','submitted','polling','completed'):
            for mode in ('ordinary','prior','missing'):
                with self.subTest(stage=stage,mode=mode),ExitStack() as stack:
                    f=FlowFixture(self.root/(stage+'-'+mode));f.root.mkdir();f.bind(api,stack);events=[]
                    def callback(label):
                        def call(*args,**kwargs):events.append(label);return f.update(*args,**kwargs)
                        return call
                    stack.enter_context(patch.object(api,'update_training_task',callback('A')))
                    def before():
                        if mode!='ordinary':api.update_training_task=callback('B') if mode=='prior' else None
                    def argument():events.append('argument');api.update_training_task=callback('C')
                    if stage=='preparing':
                        class Dataset(dict):
                            def __iter__(self):return super().__iter__()
                            def keys(self):argument();return super().keys()
                        f.dataset=Dataset(f.dataset);f.endpoint.side_effect=lambda:before() or 'endpoint'
                    elif stage=='submitted':
                        class Submission(dict):
                            def get(self,key,default=None):
                                if key=='status':argument()
                                return super().get(key,default)
                        f.submission=Submission(f.submission);f.submit.side_effect=lambda *_:before() or f.submission
                    elif stage=='polling':
                        terminal=api.runpod_terminal_status
                        stack.enter_context(patch.object(api,'runpod_terminal_status',side_effect=lambda value:argument() or terminal(value)))
                        f.http.side_effect=lambda *a,**kw:before() or {'status':'COMPLETED','output':f.output}
                    else:
                        f.importer.side_effect=lambda *a:before() or f.import_updates
                        stack.enter_context(patch.object(time,'time',side_effect=lambda:argument() or 12345))
                    caught=None
                    try:api.run_runpod_training_task('job',f.task,f.dataset)
                    except BaseException as error:caught=error
                    self.assertIn('argument',events);after=[x for x in events[events.index('argument')+1:] if x in ('A','B','C')]
                    if mode=='missing':self.assertIsInstance(caught,TypeError);self.assertEqual(after,[])
                    else:self.assertIsNone(caught);self.assertEqual(after[0],'A' if mode=='ordinary' else 'B')


    def test_payload_submission_and_environment_first_errors(self):
        api=self.api
        stages=('payload-timeout','inline','exists','stat','env-url','env-url-sha','env-base','env-base-sha','env-device','submit-timeout','submit-ttl')
        for stage in stages:
            with self.subTest(stage=stage),ExitStack() as stack:
                f=FlowFixture(self.root/stage);f.root.mkdir();f.bind(api,stack);path=f.root/'data.zip';path.write_bytes(b'fixture');f.archive['path']=str(path);f.inline.return_value=100;calls=[];failure=OSError(stage)
                if stage.startswith('env-'):
                    target_key={'env-url':'VANTALINE_RUNPOD_YOLO_BASE_MODEL_URL','env-url-sha':'VANTALINE_RUNPOD_YOLO_BASE_MODEL_URL_SHA256','env-base':'VANTALINE_RUNPOD_YOLO_BASE_MODEL','env-base-sha':'VANTALINE_RUNPOD_YOLO_BASE_MODEL_SHA256','env-device':'VANTALINE_RUNPOD_YOLO_DEVICE'}[stage]
                    class Env(dict):
                        def get(self,key,default=None):
                            if key==target_key:
                                calls.append(True)
                                if len(calls)==1:raise failure
                            return super().get(key,default)
                    env=Env({'VANTALINE_RUNPOD_YOLO_BASE_MODEL_URL':'https://fixture.invalid/model','VANTALINE_RUNPOD_YOLO_BASE_MODEL_URL_SHA256':'hash'} if stage=='env-url-sha' else {})
                    stack.enter_context(patch.object(os,'environ',env))
                else:
                    field={'payload-timeout':'runpod_yolo_job_timeout_seconds','inline':'runpod_yolo_inline_dataset_max_bytes','submit-timeout':'runpod_yolo_job_timeout_seconds','submit-ttl':'runpod_yolo_dataset_token_ttl_seconds'}.get(stage,stage)
                    target=Path if stage in ('exists','stat') else api;original=getattr(target,field)
                    if stage=='stat':
                        stack.enter_context(patch.object(Path,'exists',return_value=True))
                        read=stack.enter_context(patch.object(Path,'read_bytes',autospec=True,side_effect=Path.read_bytes))
                    def first(*args,**kwargs):
                        calls.append(True)
                        if len(calls)==1:raise failure
                        return original(*args,**kwargs)
                    stack.enter_context(patch.object(target,field,first))
                with self.assertRaises(BaseException) as caught:
                    if stage.startswith('submit-'):self.submit_entry(f.payload_value)
                    else:self.payload_entry('job',f.task,f.archive)
                self.assertIs(caught.exception,failure);self.assertEqual(calls,[True]);f.http.assert_not_called()
                self.assertEqual(f.upload.call_count,int(not stage.startswith('submit-')))
                if stage=='stat':read.assert_not_called()

    def test_flow_first_errors_leave_original_records_and_never_retry(self):
        import time
        api=self.api
        stages=('endpoint','timeout','ttl','poll','clock-start','clock-check','sleep','summary-submit','summary-poll','terminal-poll','terminal-final','quote','completed-clock','bound')
        for stage in stages:
            with self.subTest(stage=stage),ExitStack() as stack:
                f=FlowFixture(self.root/stage);f.root.mkdir();f.bind(api,stack);calls=[];failure=OSError(stage)
                if stage=='terminal-final':
                    reads=[]
                    class Body(dict):
                        def get(self,key,default=None):
                            if key=='status':reads.append(True);return '' if len(reads)==1 else 'COMPLETED'
                            return super().get(key,default)
                    f.http.side_effect=lambda *a,**k:Body();f.summary.side_effect=None;f.summary.return_value={}
                if stage=='bound':f.http.side_effect=lambda *a,**k:{'status':'FAILED','error':'failure detail'}
                if stage=='quote':
                    class Remote(str):
                        def __str__(self):return self
                        def strip(self,*args):return self
                        def encode(self,*args,**kwargs):
                            calls.append(True)
                            if len(calls)==1:raise failure
                            return super().encode(*args,**kwargs)
                    f.submission['id']=Remote('remote / id')
                    fail_at=1
                else:
                    field={'endpoint':'runpod_yolo_endpoint_id','timeout':'runpod_yolo_job_timeout_seconds','ttl':'runpod_yolo_dataset_token_ttl_seconds','poll':'runpod_yolo_poll_interval_seconds','clock-start':'monotonic','clock-check':'monotonic','sleep':'sleep','summary-submit':'runpod_public_response_summary','summary-poll':'runpod_public_response_summary','terminal-poll':'runpod_terminal_status','terminal-final':'runpod_terminal_status','completed-clock':'time','bound':'bounded_text'}[stage]
                    target=time if field in ('monotonic','sleep','time') else api;original=getattr(target,field);fail_at=2 if stage in ('clock-check','summary-poll','terminal-final') else 1
                    def first(*args,**kwargs):
                        calls.append(True)
                        if len(calls)==fail_at:raise failure
                        return original(*args,**kwargs)
                    stack.enter_context(patch.object(target,field,first))
                with self.assertRaises(BaseException) as caught:api.run_runpod_training_task('job',f.task,f.dataset)
                self.assertIs(caught.exception,failure);self.assertEqual(len(calls),fail_at)
                self.assertFalse(any(u['status'] in ('failed','completed') for u in f.updates));f.sync.assert_not_called();f.warmup.assert_not_called()
                self.assertEqual(f.importer.call_count,int(stage=='completed-clock'))

    def test_parser_and_failure_details_preserve_exception_boundaries(self):
        api=self.api
        for stage in ('json-os','json-value','json-base','parser-bound','parser-detail','flow-detail'):
            with self.subTest(stage=stage),ExitStack() as stack:
                f=FlowFixture(self.root/stage);f.root.mkdir();f.bind(api,stack);calls=[]
                failure=KeyboardInterrupt(stage) if stage=='json-base' else ValueError(stage) if stage=='json-value' else OSError(stage)
                if stage.startswith('json-'):
                    original=json.loads
                    def first(*args,**kwargs):
                        calls.append(True)
                        if len(calls)==1:raise failure
                        return original(*args,**kwargs)
                    stack.enter_context(patch.object(json,'loads',first));output='{"ok":true}'
                elif stage=='parser-bound':
                    def first(*args,**kwargs):
                        calls.append(True)
                        if len(calls)==1:raise failure
                        return f.bound(*args,**kwargs)
                    stack.enter_context(patch.object(api,'bounded_text',first));output={'ok':False,'error':'detail'}
                else:
                    class Detail:
                        def __str__(self):
                            calls.append(True)
                            if len(calls)==1:raise failure
                            return 'detail'
                    output={'ok':False,'error':Detail()}
                    f.http.side_effect=lambda *a,**kw:{**output,'status':'FAILED'}
                with self.assertRaises(BaseException) as caught:
                    if stage=='flow-detail':api.run_runpod_training_task('job',f.task,f.dataset)
                    else:self.output_entry({'output':output})
                self.assertIs(caught.exception,failure);self.assertEqual(calls,[True]);f.bound.assert_not_called();f.importer.assert_not_called()


    def test_new_getter_failures_propagate_without_retries(self):
        from dataclasses import replace
        api=self.api
        stages=('update-1','update-2','update-3','update-4','request','import','warmup','flow-bound','parser-bound','terminal-1','terminal-2','env-url','env-url-sha','env-base','env-base-sha','env-device')
        for stage in stages:
            with self.subTest(stage=stage),ExitStack() as stack:
                f=FlowFixture(self.root/stage);f.root.mkdir();f.bind(api,stack);failure=OSError(stage);calls=[];fail_at=1;g=api._runpod_flow
                if stage.startswith('env-'):
                    service=api._runpod_payload;field='environment'
                    fail_at={'env-url':1,'env-url-sha':2,'env-base':2,'env-base-sha':3,'env-device':4}[stage]
                    env={'VANTALINE_RUNPOD_YOLO_BASE_MODEL_URL':'https://fixture.invalid/model','VANTALINE_RUNPOD_YOLO_BASE_MODEL_URL_SHA256':'hash'} if stage=='env-url-sha' else {}
                    stack.enter_context(patch.object(os,'environ',env));invoke=lambda:self.payload_entry('job',f.task,f.archive)
                elif stage=='parser-bound':
                    service=api._runpod_output_parser;field='bound_text';invoke=lambda:self.output_entry({'output':{'ok':False,'error':'detail'}})
                else:
                    invoke=lambda:api.run_runpod_training_task('job',f.task,f.dataset)
                    group='records' if stage.startswith('update-') or stage=='warmup' else 'results';service=getattr(g,group)
                    field='update_provider' if stage.startswith('update-') else {'import':'import_artifacts','flow-bound':'bound_text','terminal-1':'terminal','terminal-2':'terminal'}.get(stage,stage)
                    if stage.startswith('update-'):fail_at=int(stage[-1])
                    if stage=='terminal-2':
                        fail_at=2;reads=[]
                        class Body(dict):
                            def get(self,key,default=None):
                                if key=='status':reads.append(True);return '' if len(reads)==1 else 'COMPLETED'
                                return super().get(key,default)
                        f.http.side_effect=lambda *a,**kw:Body();f.summary.side_effect=None;f.summary.return_value={}
                    if stage=='flow-bound':f.http.side_effect=lambda *a,**kw:{'status':'FAILED','error':'detail'}
                original=getattr(service,field)
                def getter():
                    calls.append(True)
                    if len(calls)==fail_at:raise failure
                    return original()
                if stage.startswith('env-') or stage=='parser-bound':stack.enter_context(patch.object(service,field,getter))
                else:stack.enter_context(patch.object(g,group,replace(service,**{field:getter})))
                with self.assertRaises(BaseException) as caught:invoke()
                self.assertIs(caught.exception,failure);self.assertEqual(len(calls),fail_at)
                self.assertFalse(any(u['status']=='failed' for u in f.updates));f.warmup.assert_not_called()


    def test_terminal_classifier_is_resolved_after_get_response(self):
        f=self.f;api=self.api;early=Mock(return_value=False);current=Mock(return_value=True)
        self.stack.enter_context(patch.object(api,'runpod_terminal_status',early))
        def response(*args,**kwargs):api.runpod_terminal_status=current;return {'status':'COMPLETED','output':f.output}
        f.http.side_effect=response;api.run_runpod_training_task('job',f.task,f.dataset)
        early.assert_not_called();current.assert_called_once_with('COMPLETED')
        self.assertEqual(f.updates[2]['status'],f.task['status']);self.assertEqual(f.updates[-1]['status'],'completed')

if __name__ == '__main__':
    unittest.main()
