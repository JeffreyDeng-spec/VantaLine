"""Synthetic token-protected RunPod transfer contracts; no remote requests or real models."""
import asyncio
from contextlib import ExitStack
import hashlib
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, call, patch
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class BodyStream:
    def __init__(self, chunks): self.chunks = chunks; self.calls = 0; self.seen = []
    async def stream(self):
        self.calls += 1
        for chunk in self.chunks:
            if isinstance(chunk, BaseException): raise chunk
            self.seen.append(chunk)
            yield chunk


class TrainingTransferContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.environment = patch.dict(os.environ); cls.environment.start()
        cls.runtime = tempfile.TemporaryDirectory(prefix='training-transfer-root-')
        root = Path(cls.runtime.name); (root / 'local_inspection_service/static').mkdir(parents=True)
        os.environ.update(LOCAL_INSPECTION_ROOT=str(root), VANTALINE_DATA_STORE='json',
                          LOCAL_INSPECTION_AUTO_RESUME_WORKER='0', VANTALINE_LABEL_INSPECTION_ENABLED='false')
        from local_inspection_service import server
        cls.api = server
    @classmethod
    def tearDownClass(cls): cls.runtime.cleanup(); cls.environment.stop()
    def setUp(self):
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory(prefix='training-transfer-'))).resolve()
        self.output = self.root / 'output'; self.output.mkdir()
        self.archive = self.output / 'data.zip'; self.archive.write_bytes(b'synthetic-archive')
        self.target = self.output / 'upload/run.zip'; self.temp = self.target.with_suffix('.zip.uploading')
        self.task = {'runpod_dataset_token_sha256': ' digest ', 'runpod_artifact_token_sha256': ' digest ',
                     'runpod_dataset_token_expires_at': 100, 'runpod_artifact_token_expires_at': 100,
                     'runpod_dataset_archive_path': 'data.zip', 'runpod_artifact_upload_path': str(self.target)}
        self.find = Mock(return_value=self.task); self.hash = Mock(return_value='digest'); self.clock = Mock(return_value=100.9)
        self.resolve = Mock(side_effect=lambda value, **kwargs: self.output / value)
        self.limit = Mock(return_value=8); self.update = Mock(return_value={'ignored': True})
        values = {'OUTPUT_DIR': self.output, 'find_training_task': self.find, 'runpod_dataset_token_hash': self.hash,
                  'resolve_service_path': self.resolve, 'runpod_yolo_artifact_max_bytes': self.limit, 'update_training_task': self.update}
        for name, value in values.items(): self.stack.enter_context(patch.object(self.api, name, value))
        self.stack.enter_context(patch('time.time', self.clock))
        for target in ['requests.request', 'subprocess.Popen', 'os.kill']:
            self.stack.enter_context(patch(target, side_effect=AssertionError('unexpected external operation')))
    def download(self, job=' job ', token=' raw-token '): return self.api.download_runpod_training_dataset(job, token)
    def upload(self, chunks, job=' job ', token=' raw-token '):
        request = chunks if isinstance(chunks, BodyStream) else BodyStream(chunks)
        return asyncio.run(self.api.upload_runpod_training_artifact(job, token, request))
    def assert_http(self, code, detail, callback):
        with self.assertRaises(HTTPException) as caught: callback()
        self.assertEqual((caught.exception.status_code, caught.exception.detail), (code, detail)); return caught.exception
    def test_download_response_headers_filename_raw_token_and_inclusive_expiry(self):
        result = self.download(); self.find.assert_called_once_with('job'); self.hash.assert_called_once_with(' raw-token ')
        self.resolve.assert_called_once_with('data.zip'); self.clock.assert_called_once_with()
        self.assertEqual(result.path, self.archive); self.assertEqual(result.media_type, 'application/zip')
        self.assertEqual(result.filename, 'job_dataset.zip'); self.assertEqual(result.headers['cache-control'], 'no-store')
        self.assertEqual(result.headers['content-disposition'], 'attachment; filename="job_dataset.zip"')
        self.assertEqual(self.download('...').filename, 'training_dataset.zip')
        self.assertEqual(self.download('a@b-_.').filename, 'a@b-_dataset.zip')
    def test_identifier_validation_before_task_lookup_and_length_boundary(self):
        for job in ['', 'a/b', '../escape', 'x' * 161, '空间']:
            self.assert_http(404, 'Training dataset not found', lambda: self.download(job))
            self.assert_http(404, 'Training artifact upload not found', lambda: self.upload([b'a'], job))
        self.find.assert_not_called(); self.hash.assert_not_called(); self.resolve.assert_not_called(); self.limit.assert_not_called()
        self.download('x' * 160); self.find.assert_called_once_with('x' * 160)
    def test_missing_task_hash_and_token_mismatch_do_not_reveal_paths(self):
        for endpoint in ['dataset', 'artifact']:
            missing = 'Training dataset not found' if endpoint == 'dataset' else 'Training artifact upload not found'
            action = self.download if endpoint == 'dataset' else lambda: self.upload([b'a'])
            for record in [None, {}, {'runpod_' + endpoint + '_token_sha256': ''}]:
                self.find.return_value = record; self.assert_http(404, missing, action)
            self.hash.assert_not_called()
            self.find.return_value = self.task; self.hash.return_value = 'wrong'
            self.assert_http(404, missing, action); self.hash.reset_mock(); self.hash.return_value = 'digest'
        self.clock.assert_not_called(); self.resolve.assert_not_called(); self.limit.assert_not_called(); self.update.assert_not_called()
    def test_expired_zero_and_invalid_expiry_keep_error_boundaries(self):
        for endpoint in ['dataset', 'artifact']:
            key = 'runpod_' + endpoint + '_token_expires_at'
            action = self.download if endpoint == 'dataset' else lambda: self.upload([b'a'])
            detail = 'Training dataset URL expired' if endpoint == 'dataset' else 'Training artifact upload URL expired'
            self.task[key] = 99; self.clock.reset_mock(); self.assert_http(410, detail, action); self.clock.assert_called_once()
            self.task[key] = 'not-int'; self.clock.reset_mock()
            with self.assertRaises(ValueError): action()
            self.clock.assert_not_called(); self.task[key] = 0; self.clock.reset_mock(); action()
            self.assertEqual(self.clock.call_count, int(endpoint == 'artifact'))
    def test_download_outside_missing_directory_and_resolver_error(self):
        sibling = self.root / 'output-sibling'; sibling.mkdir(); sibling_archive = sibling / 'data.zip'
        sibling_archive.write_bytes(b'existing outside archive')
        for path in [self.root / 'outside.zip', self.output / 'missing.zip', self.output, sibling_archive]:
            self.resolve.side_effect = None; self.resolve.return_value = path
            self.assert_http(404, 'Training dataset not found', self.download)
        error = OSError('resolve'); self.resolve.side_effect = error
        with self.assertRaises(OSError) as caught: self.download()
        self.assertIs(caught.exception, error)
    def test_upload_exact_limit_ignores_empty_chunks_hashes_and_updates_after_replace(self):
        self.target.parent.mkdir(); self.temp.write_bytes(b'stale partial upload')
        def update(job, **values):
            self.assertEqual(self.target.read_bytes(), b'abcdefgh'); self.assertFalse(self.temp.exists())
            return {'ignored': True}
        self.update.side_effect = update; stream = BodyStream([b'', b'ab', b'cdefgh', b''])
        self.clock.side_effect = [100.9, 123.8]
        result = self.upload(stream); sha = hashlib.sha256(b'abcdefgh').hexdigest()
        self.assertEqual(result, {'ok': True, 'sha256': sha, 'size': 8}); self.assertEqual(stream.calls, 1)
        self.resolve.assert_not_called(); self.limit.assert_called_once_with()
        self.update.assert_called_once_with('job', runpod_artifact_archive_path=str(self.target),
            runpod_artifact_archive_sha256=sha, runpod_artifact_archive_size=8, runpod_artifact_uploaded_at=123,
            note='RunPod 训练产物已上传，等待平台导入模型。')
    def test_upload_relative_write_resolution_and_absolute_path_bypass(self):
        self.task['runpod_artifact_upload_path'] = ' nested/run.zip '
        self.upload([b'a']); self.resolve.assert_called_once_with('nested/run.zip', for_write=True)
        self.assertEqual((self.output / 'nested/run.zip').read_bytes(), b'a')
        self.resolve.reset_mock(); self.task['runpod_artifact_upload_path'] = str(self.target)
        self.upload([b'b']); self.resolve.assert_not_called(); self.assertEqual(self.target.read_bytes(), b'b')
    def test_upload_empty_or_outside_path_is_rejected_before_directory_or_stream(self):
        for path in ['', str(self.root / 'outside/run.zip'), str(self.output / '../outside/run.zip'), str(self.root / 'output-sibling/run.zip')]:
            self.task['runpod_artifact_upload_path'] = path; stream = BodyStream([b'a'])
            self.assert_http(404, 'Training artifact upload not found', lambda: self.upload(stream))
            self.assertEqual(stream.calls, 0)
        self.assertFalse((self.root / 'outside').exists()); self.limit.assert_not_called(); self.update.assert_not_called()
        self.assertFalse((self.root / 'output-sibling').exists())
    def test_upload_empty_and_oversize_cleanup_keep_previous_target(self):
        self.target.parent.mkdir(); self.target.write_bytes(b'previous')
        for chunks, code, detail in [([b'', b''], 400, 'Training artifact upload is empty'),
                                    ([b'ab', b'cdefghi', b'never'], 413, 'Training artifact upload is too large')]:
            stream = BodyStream(chunks); self.assert_http(code, detail, lambda: self.upload(stream))
            self.assertEqual(self.target.read_bytes(), b'previous'); self.assertFalse(self.temp.exists())
            self.assertEqual(stream.calls, 1); self.assertNotIn(b'never', stream.seen)
        self.update.assert_not_called()
        digest = Mock(wraps=hashlib.sha256()); stream = BodyStream([b'ab', b'cdefghi', b'never'])
        with patch('hashlib.sha256', return_value=digest), patch.object(Path, 'unlink', side_effect=OSError('keep evidence')) as unlink:
            self.assert_http(413, 'Training artifact upload is too large', lambda: self.upload(stream))
            unlink.assert_called_once_with()
        self.assertEqual(digest.update.call_args_list, [call(b'ab')]); digest.hexdigest.assert_not_called()
        self.assertEqual(self.temp.read_bytes(), b'ab'); self.assertEqual(self.target.read_bytes(), b'previous')
        self.assertEqual(stream.seen, [b'ab', b'cdefghi']); self.assertEqual(stream.calls, 1); self.update.assert_not_called()
    def test_stream_exception_cleans_partial_but_baseexception_keeps_evidence(self):
        for error in [RuntimeError('stream'), asyncio.CancelledError('cancel')]:
            stream = BodyStream([b'ab', error, b'never'])
            async def verify_stream_error():
                # Assert at the service boundary: Python 3.10 Task.result() can
                # replace CancelledError after the coroutine has already exited.
                with self.assertRaises(type(error)) as caught:
                    await self.api.upload_runpod_training_artifact(' job ', ' raw-token ', stream)
                self.assertIs(caught.exception, error)
            asyncio.run(verify_stream_error())
            self.assertFalse(self.target.exists()); self.assertEqual(stream.calls, 1)
            self.assertEqual(self.temp.exists(), isinstance(error, asyncio.CancelledError))
            if self.temp.exists(): self.assertEqual(self.temp.read_bytes(), b'ab'); self.temp.unlink()
        self.update.assert_not_called()
    def test_limit_failure_occurs_after_mkdir_outside_cleanup_block(self):
        error = RuntimeError('limit')
        def limit():
            self.assertTrue(self.target.parent.is_dir()); self.temp.write_bytes(b'existing temp'); raise error
        self.limit.side_effect = limit; stream = BodyStream([b'a'])
        with self.assertRaises(RuntimeError) as caught: self.upload(stream)
        self.assertIs(caught.exception, error); self.assertEqual(self.temp.read_bytes(), b'existing temp')
        self.assertEqual(stream.calls, 0); self.update.assert_not_called()
    def test_replace_failure_cleans_temp_and_cleanup_oserror_preserves_original(self):
        self.target.parent.mkdir(); self.target.write_bytes(b'previous'); error = OSError('replace')
        with patch.object(Path, 'replace', side_effect=error) as replace:
            with self.assertRaises(OSError) as caught: self.upload([b'ab'])
            self.assertIs(caught.exception, error); replace.assert_called_once_with(self.target)
        self.assertFalse(self.temp.exists()); self.assertEqual(self.target.read_bytes(), b'previous')
        with patch.object(Path, 'replace', side_effect=error), patch.object(Path, 'unlink', side_effect=OSError('cleanup')) as unlink:
            with self.assertRaises(OSError) as caught: self.upload([b'ab'])
            self.assertIs(caught.exception, error); unlink.assert_called_once_with()
        self.assertEqual(self.temp.read_bytes(), b'ab'); self.update.assert_not_called()
    def test_final_clock_or_update_failure_keeps_replaced_archive_without_retry(self):
        for stage in ['clock', 'update']:
            self.update.reset_mock(); self.clock.reset_mock(); error = RuntimeError(stage)
            self.clock.side_effect = [100, error] if stage == 'clock' else [100, 200]
            self.update.side_effect = [error, {}] if stage == 'update' else None
            with self.assertRaises(RuntimeError) as caught: self.upload([b'ab'])
            self.assertIs(caught.exception, error); self.assertEqual(self.target.read_bytes(), b'ab'); self.assertFalse(self.temp.exists())
            self.assertEqual(self.update.call_count, int(stage == 'update')); self.assertEqual(self.clock.call_count, 2)
    def test_http_download_bytes_put_body_errors_and_unsupported_methods(self):
        app = FastAPI(); app.get('/api/training/runpod/datasets/{job_id}/{token}/dataset.zip')(self.api.download_runpod_training_dataset)
        app.put('/api/training/runpod/artifacts/{job_id}/{token}/run.zip')(self.api.upload_runpod_training_artifact)
        with TestClient(app) as client:
            response = client.get('/api/training/runpod/datasets/job/token/dataset.zip')
            self.assertEqual(response.status_code, 200); self.assertEqual(response.content, b'synthetic-archive'); self.assertEqual(response.headers['cache-control'], 'no-store')
            response = client.put('/api/training/runpod/artifacts/job/token/run.zip', content=b'abc')
            self.assertEqual((response.status_code, response.json()), (200, {'ok': True, 'sha256': hashlib.sha256(b'abc').hexdigest(), 'size': 3}))
            response = client.put('/api/training/runpod/artifacts/job/token/run.zip', content=b'')
            self.assertEqual((response.status_code, response.json()), (400, {'detail': 'Training artifact upload is empty'}))
            self.assertEqual(client.post('/api/training/runpod/datasets/job/token/dataset.zip').status_code, 405)
            self.assertEqual(client.get('/api/training/runpod/artifacts/job/token/run.zip').status_code, 405)


    def test_open_write_and_synchronous_stream_failures_clean_once_without_retry(self):
        original_open, original_unlink = Path.open, Path.unlink
        for stage in ['open', 'write', 'stream']:
            error = OSError(stage); opened = []; unlinked = []; writes = []
            class Handle:
                def __init__(inner, handle): inner.handle = handle
                def __enter__(inner): inner.handle.__enter__(); return inner
                def __exit__(inner, *args): return inner.handle.__exit__(*args)
                def write(inner, value):
                    writes.append(value)
                    if stage == 'write' and len(writes) == 1: raise error
                    return inner.handle.write(value)
            def open_temp(path, *args, **kwargs):
                if path != self.temp: return original_open(path, *args, **kwargs)
                opened.append(path)
                if stage == 'open' and len(opened) == 1: raise error
                return Handle(original_open(path, *args, **kwargs))
            def unlink(path, *args, **kwargs):
                unlinked.append(path)
                return original_unlink(path, *args, **kwargs)
            stream = BodyStream([b'ab', b'cd'])
            if stage == 'stream':
                original_stream = stream.stream
                def fail_stream():
                    self.assertEqual(opened, [self.temp])
                    if stream.stream.call_count == 1: raise error
                    return original_stream()
                stream.stream = Mock(side_effect=fail_stream)
            with patch.object(Path, 'open', open_temp), patch.object(Path, 'unlink', unlink):
                with self.assertRaises(OSError) as caught: self.upload(stream)
            self.assertIs(caught.exception, error); self.assertEqual(opened, [self.temp]); self.assertEqual(unlinked, [self.temp])
            self.assertEqual(writes, [b'ab'] if stage == 'write' else [])
            self.assertFalse(self.temp.exists()); self.assertFalse(self.target.exists())
            if stage == 'open': self.assertEqual(stream.calls, 0)
            if stage == 'stream': stream.stream.assert_called_once_with()
        self.update.assert_not_called()

    def test_cleanup_non_oserror_replaces_original_and_final_digest_failure_keeps_file(self):
        original = RuntimeError('stream'); cleanup = ValueError('cleanup')
        with patch.object(Path, 'unlink', side_effect=cleanup) as unlink:
            with self.assertRaises(ValueError) as caught: self.upload([b'a', original])
            self.assertIs(caught.exception, cleanup); self.assertIs(caught.exception.__context__, original); unlink.assert_called_once_with()
        self.temp.unlink(); error = RuntimeError('hexdigest'); digest = Mock()
        digest.hexdigest.side_effect = [error, 'later success']
        with patch('hashlib.sha256', return_value=digest):
            with self.assertRaises(RuntimeError) as caught: self.upload([b'ab'])
            self.assertIs(caught.exception, error); digest.hexdigest.assert_called_once_with(); digest.update.assert_called_once_with(b'ab')
        self.assertEqual(self.target.read_bytes(), b'ab'); self.assertFalse(self.temp.exists()); self.update.assert_not_called()
        self.update.return_value = False
        self.assertEqual(self.upload([b'cd']), {'ok': True, 'sha256': hashlib.sha256(b'cd').hexdigest(), 'size': 2})
        self.update.assert_called_once()


    def test_download_file_read_is_deferred_until_response_send(self):
        response = self.download()
        self.assertIsNone(response.stat_result)
        self.archive.unlink()
        app = FastAPI()
        @app.get('/deferred')
        def deferred(): return response
        with TestClient(app) as client:
            with self.assertRaisesRegex(RuntimeError, 'does not exist'): client.get('/deferred')

    def test_callback_capture_before_argument_effects(self):
        for site in ['resolve-download', 'resolve-upload', 'update-path', 'update-clock']:
            for mode in ['ordinary', 'prior', 'missing']:
                with self.subTest(site=site, mode=mode), ExitStack() as stack:
                    f = TrainingTransferContracts()
                    f.api = self.api
                    f.setUp()
                    stack.callback(f.doCleanups)
                    api = self.api
                    events = []
                    armed = [False]
                    done = RuntimeError('captured')
                    target = 'resolve_service_path' if site.startswith('resolve') else 'update_training_task'

                    def hit(label, *args, **kwargs):
                        events.append(label)
                        raise done
                    ports = {label: Mock(side_effect=lambda *a, _label=label, **k: hit(_label, *a, **k)) for label in ['A', 'B', 'C']}
                    stack.enter_context(patch.object(api, target, ports['A']))

                    def prior():
                        events.append('prior')
                        armed[0] = True
                        setattr(api, target, None if mode == 'missing' else ports['B'] if mode == 'prior' else ports['A'])

                    def argument():
                        events.append('argument')
                        setattr(api, target, ports['C'])
                    if site == 'resolve-download':

                        class Task(dict):

                            def get(inner, key, *default):
                                if key == 'runpod_dataset_token_expires_at':
                                    prior()
                                    return 0
                                if key == 'runpod_dataset_archive_path':
                                    argument()
                                return super().get(key, *default)
                        f.find.return_value = Task(f.task)
                        operation = f.download
                    elif site == 'resolve-upload':

                        class Task(dict):

                            def get(inner, key, *default):
                                if key == 'runpod_artifact_upload_path':
                                    prior()
                                    return 'upload/run.zip'
                                return super().get(key, *default)
                        f.find.return_value = Task(f.task)
                        operation = lambda: f.upload([b'ab'])
                    else:
                        f.task['runpod_artifact_token_expires_at'] = 0
                        f.task['runpod_artifact_upload_path'] = 'upload/run.zip'

                        class Target(type(f.target)):

                            def __str__(inner):
                                if armed[0] and site == 'update-path':
                                    argument()
                                return super().__str__()
                        f.resolve.side_effect = lambda *a, **k: Target(f.target)
                        digest = Mock(wraps=hashlib.sha256())
                        sha = digest.hexdigest()
                        digest.hexdigest.side_effect = lambda: prior() or sha
                        stack.enter_context(patch('hashlib.sha256', return_value=digest))
                        if site == 'update-clock':
                            f.clock.side_effect = lambda: argument() or 100
                        operation = lambda: f.upload([b'ab'])
                    caught = None
                    try:
                        operation()
                    except BaseException as exc:
                        caught = exc
                    if mode == 'missing':
                        self.assertIs(type(caught), TypeError)
                    else:
                        self.assertIs(caught, done)
                    self.assertEqual(events, ['prior'] + ([] if site == 'resolve-upload' else ['argument']) + ([] if mode == 'missing' else ['B' if mode == 'prior' else 'A']))
                    self.assertEqual(ports['A'].call_count, int(mode == 'ordinary'))
                    self.assertEqual(ports['B'].call_count, int(mode == 'prior'))
                    ports['C'].assert_not_called()
                    if not site.startswith('resolve'):
                        armed[0] = False
                        self.assertEqual(f.target.read_bytes(), b'ab')
                        self.assertFalse(f.temp.exists())
                        f.clock.assert_called_once()

    def test_direct_path_first_failure_preserves_boundary_without_retry(self):
        cases = [('absolute', 'mkdir', 'parent'), ('absolute', 'resolve', 'target'),
                 ('download', 'exists', 'archive'), ('download', 'is_file', 'archive'),
                 ('download', 'resolve', 'output'), ('absolute', 'resolve', 'output'),
                 ('download', 'relative_to', 'archive'), ('absolute', 'relative_to', 'target')]
        for mode, method, selector in cases:
            for error_type in ([OSError, ValueError] if method == 'relative_to' else [OSError]):
                with self.subTest(mode=mode, method=method, selector=selector, error=error_type), ExitStack() as scope:
                    f, operation, _ = self.failure_fixture(scope, mode)
                    target = {'parent': f.target.parent, 'target': f.target, 'archive': f.archive, 'output': f.output}[selector]
                    original = getattr(Path, method); calls = []; failure = error_type('direct-path-first')
                    def fail_once(path, *args, **kwargs):
                        if path == target:
                            calls.append(None)
                            if len(calls) == 1: raise failure
                        return original(path, *args, **kwargs)
                    with patch.object(Path, method, fail_once):
                        if error_type is ValueError:
                            detail = 'Training dataset not found' if mode == 'download' else 'Training artifact upload not found'
                            caught = f.assert_http(404, detail, operation)
                            self.assertIs(caught.__cause__, failure)
                        else:
                            with self.assertRaises(OSError) as caught: operation()
                            self.assertIs(caught.exception, failure)
                    self.assertEqual(len(calls), 1)
                    f.update.assert_not_called(); f.limit.assert_not_called()
                    self.assertFalse(f.temp.exists()); self.assertFalse(f.target.exists())
                    self.assertEqual(f.archive.read_bytes(), b'synthetic-archive')

    def test_digest_update_first_failure_cleans_partial_without_retry(self):
        self.target.parent.mkdir(); self.target.write_bytes(b'previous')
        digest = Mock(wraps=hashlib.sha256()); original = digest.update
        failure = RuntimeError('digest-first'); calls = []
        def fail_once(chunk):
            calls.append(chunk)
            if len(calls) == 1: raise failure
            return original(chunk)
        digest.update = Mock(side_effect=fail_once)
        stream = BodyStream([b'ab', b'cd'])
        with patch('hashlib.sha256', return_value=digest):
            with self.assertRaises(RuntimeError) as caught: self.upload(stream)
        self.assertIs(caught.exception, failure); self.assertEqual(calls, [b'ab'])
        self.assertEqual(stream.calls, 1); self.assertEqual(stream.seen, [b'ab'])
        digest.hexdigest.assert_not_called(); self.update.assert_not_called()
        self.assertFalse(self.temp.exists()); self.assertEqual(self.target.read_bytes(), b'previous')

    def failure_fixture(self, scope, mode):
        fixture = TrainingTransferContracts(); fixture.setUp(); scope.callback(fixture.doCleanups)
        if mode == 'relative': fixture.task['runpod_artifact_upload_path'] = 'nested/run.zip'
        operation = fixture.download if mode == 'download' else lambda: fixture.upload([b'ab', b'cd'])
        import time
        names = {'find_training_task': fixture.find, 'runpod_dataset_token_hash': fixture.hash,
                 'resolve_service_path': fixture.resolve, 'runpod_yolo_artifact_max_bytes': fixture.limit,
                 'update_training_task': fixture.update}
        ports = {name: (self.api, name, port) for name, port in names.items()}
        ports['clock'] = (time, 'time', fixture.clock)
        return fixture, operation, ports

    def test_first_callback_error_propagates_without_retry(self):
        for mode in ['download', 'absolute', 'relative']:
            with ExitStack() as scope:
                _, operation, ports = self.failure_fixture(scope, mode); operation()
                counts = {name: port.call_count for name, (_, _, port) in ports.items() if port.call_count}
            for name, count in counts.items():
                for index in range(1, count + 1):
                    with self.subTest(mode=mode, name=name, index=index), ExitStack() as scope:
                        _, operation, ports = self.failure_fixture(scope, mode)
                        owner, field, original = ports[name]; calls = []; failure = RuntimeError('transfer-first')
                        def fail_once(*args, **kwargs):
                            calls.append(None)
                            if len(calls) == index: raise failure
                            return original(*args, **kwargs)
                        scope.enter_context(patch.object(owner, field, fail_once))
                        with self.assertRaises(RuntimeError) as caught: operation()
                        self.assertIs(caught.exception, failure); self.assertEqual(len(calls), index)

    def test_new_transfer_getter_first_error_propagates_without_retry(self):
        from dataclasses import replace
        transfer = self.api._training_transfer
        fields = [(mode, 'paths', field) for mode in ['download', 'relative'] for field in ['resolve', 'output']]
        fields += [('absolute', 'paths', 'output'), ('absolute', None, 'update_provider')]
        def install(scope, group_name, field, port):
            if group_name:
                group = getattr(transfer, group_name)
                scope.enter_context(patch.object(transfer, group_name, replace(group, **{field: port})))
            else: scope.enter_context(patch.object(transfer, field, port))
        for mode, group_name, field in fields:
            original = getattr(getattr(transfer, group_name) if group_name else transfer, field)
            with ExitStack() as scope:
                _, operation, _ = self.failure_fixture(scope, mode); observed = Mock(wraps=original)
                install(scope, group_name, field, observed); operation(); count = observed.call_count
            self.assertGreater(count, 0)
            for index in range(1, count + 1):
                with self.subTest(mode=mode, field=field, index=index), ExitStack() as scope:
                    _, operation, _ = self.failure_fixture(scope, mode); calls = []; failure = RuntimeError('transfer-getter-first')
                    def fail_once(*args, **kwargs):
                        calls.append(None)
                        if len(calls) == index: raise failure
                        return original(*args, **kwargs)
                    install(scope, group_name, field, fail_once)
                    with self.assertRaises(RuntimeError) as caught: operation()
                    self.assertIs(caught.exception, failure); self.assertEqual(len(calls), index)

    def test_independent_transfer_apps_real_streaming_files_and_no_constructor_reads(self):
        import httpx
        from local_inspection_service.training.runpod_upload_store import RunPodUploadStore
        from local_inspection_service.training.runpod_transfer import RunPodTrainingTransfer, TransferPaths
        from local_inspection_service.training.runpod_transfer_api import register
        instances = []
        def build(owner):
            root = self.root / owner; root.mkdir(); (root / 'data.zip').write_bytes(owner.encode())
            target = root / 'nested/run.zip'; token = 'fixture-' + owner; digest = hashlib.sha256(token.encode()).hexdigest()
            task = {'runpod_dataset_token_sha256': digest, 'runpod_artifact_token_sha256': digest,
                    'runpod_dataset_archive_path': 'data.zip', 'runpod_artifact_upload_path': 'nested/run.zip'}
            find = Mock(return_value=task); token_hash = Mock(side_effect=lambda value: hashlib.sha256(value.encode()).hexdigest())
            resolve = Mock(side_effect=lambda value, **kwargs: root / value); output = Mock(return_value=root)
            clock = Mock(return_value=321); limit = Mock(return_value=16)
            def update_task(job, **values):
                self.assertEqual(job, 'job'); self.assertEqual(target.read_bytes(), owner.encode() + b'-upload')
                task.update(values); return False
            update = Mock(side_effect=update_task)
            store = RunPodUploadStore(limit)
            transfer = RunPodTrainingTransfer(find, token_hash, clock, TransferPaths((lambda: resolve), output), store, (lambda: update))
            app = FastAPI(); routes = register(app, transfer)
            for name in routes.__dataclass_fields__:
                self.assertEqual([route.endpoint for route in app.routes if route.name == name], [getattr(routes, name)])
            self.assertEqual(app.router.on_startup, [])
            for callback in [find, token_hash, resolve, output, clock, limit, update]: callback.assert_not_called()
            return app, owner, token, root, target, task, find, resolve, output, clock, limit, update
        instances = [build(owner) for owner in ['alice', 'bob']]
        for name in ['find_training_task', 'runpod_dataset_token_hash', 'resolve_service_path', 'runpod_yolo_artifact_max_bytes', 'update_training_task']:
            self.stack.enter_context(patch.object(self.api, name, side_effect=AssertionError('unexpected root dependency')))
        async def request(instance):
            app, owner, token, *_ = instance
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='https://fixture.invalid') as client:
                invalid = await client.get('/api/training/runpod/datasets/job/other-token/dataset.zip')
                self.assertEqual((invalid.status_code, invalid.json()), (404, {'detail': 'Training dataset not found'}))
                result = await client.get(f'/api/training/runpod/datasets/job/{token}/dataset.zip')
                self.assertEqual(result.status_code, 200); self.assertEqual(result.content, owner.encode())
                self.assertEqual(result.headers['cache-control'], 'no-store')
                async def body():
                    yield owner.encode()
                    await asyncio.sleep(0)
                    yield b'-upload'
                result = await client.put(f'/api/training/runpod/artifacts/job/{token}/run.zip', content=body())
                self.assertEqual(result.status_code, 200)
                self.assertEqual(result.json(), {'ok': True, 'sha256': hashlib.sha256(owner.encode() + b'-upload').hexdigest(), 'size': len(owner) + 7})
        async def both(): await asyncio.gather(*(request(instance) for instance in instances))
        asyncio.run(both())
        for app, owner, token, root, target, task, find, resolve, output, clock, limit, update in instances:
            self.assertEqual(target.read_bytes(), owner.encode() + b'-upload'); self.assertFalse(target.with_suffix('.zip.uploading').exists())
            self.assertEqual(task['runpod_artifact_archive_path'], str(target)); self.assertEqual(task['runpod_artifact_uploaded_at'], 321)
            self.assertEqual(find.call_args_list, [call('job')] * 3)
            self.assertEqual(resolve.call_args_list, [call('data.zip'), call('nested/run.zip', for_write=True)])
            self.assertEqual(output.call_count, 2); clock.assert_called_once_with(); limit.assert_called_once_with(); update.assert_called_once()


if __name__ == '__main__': unittest.main()
