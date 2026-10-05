"""Synthetic execution boundaries; never start a process or contact an image provider."""
import ast
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import fields
import cv2
import json
import mimetypes
import os
from pathlib import Path
import requests
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
from typing import Any
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from local_inspection_service.model_profiles.snapshots import pinned

BASELINE = os.environ.get('VANTALINE_IMAGE_JOB_EXECUTION_BASELINE_SOURCE')
NAMES = ('run_windows_worker_image_job', 'run_cursor_image2_job', 'run_cos_codex_image_job', 'run_codex_image_job', 'run_image_generation_job')


class Resolver:
    def __init__(self):
        self.current = ContextVar('image-execution-fixture', default=None)
    def current_snapshot(self):
        return self.current.get()
    def snapshot_for_record(self, record):
        return {'image': {'version': 999}}
    @contextmanager
    def scope(self, value):
        token = self.current.set(value)
        try:
            yield
        finally:
            self.current.reset(token)


def create(b):
    b.update(Any=Any, Path=Path, time=time, json=json, mimetypes=mimetypes, requests=requests, shutil=shutil,
             cv2=cv2, subprocess=subprocess, os=os, signal=signal, pinned_model_profiles=pinned,
             __package__='local_inspection_service')
    if BASELINE:
        tree = ast.parse(Path(BASELINE).read_text(encoding='utf-8-sig'))
        nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in NAMES]
        assert len(nodes) == 5
        exec(compile(ast.Module(body=nodes, type_ignores=[]), BASELINE, 'exec'), b)
        return SimpleNamespace(**{name: b[name] for name in NAMES})
    from local_inspection_service.accessories.image_job_execution import ImageJobExecution
    from local_inspection_service.accessories.image_job_execution_ports import ImageExecutionFiles, ImageExecutionEvidence, ImageExecutionProviders
    def ports(cls):
        return cls(**{field.name: lambda name=field.name: b[name] for field in fields(cls)})
    service = ImageJobExecution(ports(ImageExecutionFiles), ports(ImageExecutionEvidence), ports(ImageExecutionProviders))
    b.update({name: getattr(service, name) for name in NAMES})
    b['_image_job_execution'] = service
    tree = ast.parse((ROOT / 'local_inspection_service/server.py').read_text(encoding='utf-8'))
    wrapper = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'run_image_generation_job')
    exec(compile(ast.Module(body=[wrapper], type_ignores=[]), 'actual_pinned_entry', 'exec'), b)
    return SimpleNamespace(**{name: b[name] for name in NAMES})


class ExecutionContract(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='image-execution-contract-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.input = self.root / 'input.png'
        self.input.write_bytes(b'synthetic input')
        self.output = self.root / 'output.png'
        # Simulate the Linux process signal for the fully mocked timeout path on Windows.
        signal_fixture = patch.object(signal, 'SIGKILL', getattr(signal, 'SIGKILL', 9), create=True)
        signal_fixture.start()
        self.addCleanup(signal_fixture.stop)
        for module, name in [(requests, 'post'), (requests, 'get'), (subprocess, 'Popen')]:
            guard = patch.object(module, name, side_effect=AssertionError('Unexpected external execution'))
            guard.start()
            self.addCleanup(guard.stop)

    def fixture(self):
        resolver = Resolver()
        files = SimpleNamespace(runtime=Mock(return_value=None), exists=lambda path: path.exists(), is_file=lambda path: path.is_file(),
                                write_text=Mock(), write_bytes=Mock(), unlink=Mock())
        b = dict(_business_files=files, _image_files=SimpleNamespace(imread=Mock(return_value=object())),
                 image_job_output_path=lambda *args, **kwargs: self.output, IMAGE_WORKER_LOG_DIR=self.root / 'logs', ROOT=self.root,
                 safe_name=lambda value: value, resolve_service_path=Path, public_output_url=lambda path: '/synthetic/output',
                 mutate_candidate_image_job=Mock(side_effect=lambda path, candidate, job, updates, **kw: dict(updates)),
                 update_image_worker_status=Mock(), _image_worker_processes={}, image_job_prompt=lambda job: 'SYNTHETIC PROMPT',
                 codex_log_has_generated_image=Mock(return_value=True), classify_image_worker_failure=lambda *args: 'classified',
                 bounded_text=lambda text, size: str(text)[:size], LOCAL_CODEX_IMAGE_PROVIDER='local', CURSOR_IMAGE2_PROVIDER='cursor',
                 CURSOR_IMAGE2_QUEUE_STATUS='cursor-queued', CODEX_IMAGE_WORKER_QUEUE_STATUS='local-queued', MAX_IMAGE_WORKER_INPUTS=2,
                 cursor_image2_settings=Mock(return_value={'configured': True, 'endpoint': 'https://fixture.invalid', 'endpoint_public': 'redacted', 'model': 'fixture', 'api_key': 'fixture-key', 'timeout_seconds': 2}),
                 cursor_image2_payload=Mock(return_value={}), cursor_auth_headers=lambda key: {'Authorization': 'synthetic'},
                 extract_cursor_image2_bytes=lambda payload, settings: b'generated', windows_worker_base_url=Mock(),
                 windows_worker_headers=Mock(), windows_worker_image_timeout_seconds=lambda: 10,
                 windows_worker_image_response_bytes=Mock(), masked_url_for_status=lambda value: 'redacted',
                 resolve_model_profiles=lambda: resolver)
        service = create(b)
        return service, b, {'job_id': 'job', 'input_files': [str(self.input)]}, resolver

    def test_retired_windows_path_returns_without_external_io(self):
        s, b, job, _ = self.fixture()
        self.assertFalse(s.run_windows_worker_image_job(self.root, {}, job, reason='fixture'))
        updates = b['mutate_candidate_image_job'].call_args.args[3]
        self.assertEqual(updates['status'], 'failed')
        self.assertIn('retired', updates['error'])
        b['windows_worker_base_url'].assert_not_called()
        requests.post.assert_not_called()

    def test_cursor_configuration_fallback_precedes_missing_input_rejection(self):
        s, b, job, _ = self.fixture()
        fallback = b['run_codex_image_job'] = Mock()
        job['input_files'] = ['missing']
        b['cursor_image2_settings'].return_value = {'configured': False}
        s.run_cursor_image2_job(self.root, {}, job)
        fallback.assert_called_once()
        b['update_image_worker_status'].assert_not_called()
        requests.post.assert_not_called()

    def test_cursor_missing_or_empty_input_never_submits(self):
        for inputs in (['missing'], []):
            s, b, job, _ = self.fixture()
            job['input_files'] = inputs
            b['run_codex_image_job'] = Mock()
            s.run_cursor_image2_job(self.root, {}, job)
            self.assertEqual(b['update_image_worker_status'].call_args.kwargs['status'], 'failed')
            b['run_codex_image_job'].assert_not_called()
        requests.post.assert_not_called()

    def test_cursor_success_and_uncertain_storage_no_second_paid_call(self):
        s, b, job, _ = self.fixture()
        response = Mock()
        response.json.return_value = {}
        fallback = b['run_codex_image_job'] = Mock()
        with patch.object(requests, 'post', return_value=response) as post:
            s.run_cursor_image2_job(self.root, {}, job)
            post.assert_called_once()
        self.assertEqual(b['mutate_candidate_image_job'].call_args.args[3]['status'], 'completed')
        self.assertTrue(b['mutate_candidate_image_job'].call_args.kwargs['preprocess_clean_sprites'])
        b['_business_files'].write_bytes.side_effect = OSError('uncertain storage')
        b['_business_files'].runtime.return_value = object()
        with patch.object(requests, 'post', return_value=response) as post:
            s.run_cursor_image2_job(self.root, {}, job)
            post.assert_called_once()
        fallback.assert_not_called()
        self.assertEqual(b['update_image_worker_status'].call_args.kwargs['status'], 'failed')
        self.assertIn('未自动重试', b['update_image_worker_status'].call_args.kwargs['error'])

    def test_cursor_timeout_cloud_no_retry_and_legacy_local_fallback(self):
        for cloud, expected in [(object(), 0), (None, 1)]:
            s, b, job, _ = self.fixture()
            b['_business_files'].runtime.return_value = cloud
            fallback = b['run_codex_image_job'] = Mock()
            with patch.object(requests, 'post', side_effect=TimeoutError('unknown result')) as post:
                s.run_cursor_image2_job(self.root, {}, job)
                post.assert_called_once()
            self.assertEqual(fallback.call_count, expected)

    def test_local_cli_missing_inputs_and_cloud_dispatch(self):
        s, b, job, _ = self.fixture()
        cloud = object()
        b['_business_files'].runtime.return_value = cloud
        b['run_cos_codex_image_job'] = Mock(return_value='cloud-result')
        self.assertEqual(s.run_codex_image_job(self.root, {}, job), 'cloud-result')
        b['run_cos_codex_image_job'].assert_called_once_with(self.root, {}, job, cloud)
        b['_business_files'].runtime.return_value = None
        with patch.object(shutil, 'which', return_value=None):
            s.run_codex_image_job(self.root, {}, job)
        self.assertIn('not found', b['update_image_worker_status'].call_args.kwargs['error'])
        with patch.object(shutil, 'which', return_value='/synthetic/codex'):
            job['input_files'] = []
            s.run_codex_image_job(self.root, {}, job)
        self.assertEqual(b['update_image_worker_status'].call_args.kwargs['status'], 'failed')
        subprocess.Popen.assert_not_called()

    def test_local_process_success_cleanup_and_rejected_output(self):
        s, b, job, _ = self.fixture()
        self.output.write_bytes(b'synthetic output')
        process = Mock(returncode=0, pid=123)
        with patch.object(shutil, 'which', return_value='/synthetic/codex'), patch.object(subprocess, 'Popen', return_value=process) as popen:
            s.run_codex_image_job(self.root, {}, job)
        self.assertEqual(b['_image_worker_processes'], {})
        self.assertEqual(b['mutate_candidate_image_job'].call_args.args[3]['status'], 'completed')
        process.communicate.assert_called_once_with('SYNTHETIC PROMPT\n', timeout=900)
        self.assertTrue(popen.call_args.kwargs['start_new_session'])
        b['codex_log_has_generated_image'].return_value = False
        with patch.object(shutil, 'which', return_value='/synthetic/codex'), patch.object(subprocess, 'Popen', return_value=process):
            s.run_codex_image_job(self.root, {}, job)
        b['_business_files'].unlink.assert_called_once_with(self.output)
        self.assertEqual(b['mutate_candidate_image_job'].call_args.args[3]['status'], 'failed')

    def test_local_timeout_kills_once_and_clears_process(self):
        s, b, job, _ = self.fixture()
        process = Mock(returncode=None, pid=123)
        process.communicate.side_effect = subprocess.TimeoutExpired('synthetic', 900)
        with patch.object(shutil, 'which', return_value='/synthetic/codex'), patch.object(subprocess, 'Popen', return_value=process), patch.object(os, 'killpg', create=True) as kill:
            s.run_codex_image_job(self.root, {}, job)
        kill.assert_called_once_with(123, signal.SIGKILL)
        process.wait.assert_called_once_with(timeout=10)
        self.assertEqual(b['_image_worker_processes'], {})
        self.assertIn('900', b['update_image_worker_status'].call_args.kwargs['error'])

    def test_cloud_generation_order_callback_and_persistence_failure(self):
        from local_inspection_service.storage.artifacts import native
        s, b, job, _ = self.fixture()
        self.output.write_bytes(b'synthetic output')
        puts = []
        runtime = SimpleNamespace(key=lambda p: p.name, store=SimpleNamespace(locations=SimpleNamespace(get=lambda key: SimpleNamespace(generation=7)), put=lambda key, source, **kwargs: puts.append((key, kwargs))))
        @contextmanager
        def image_job(runtime_arg, inputs, prompt, on_process):
            self.assertIs(runtime_arg, runtime)
            self.assertEqual(inputs, [self.input])
            self.assertEqual(prompt('temporary'), 'SYNTHETIC PROMPT\n')
            on_process('fake-process')
            self.assertEqual(b['_image_worker_processes']['job'], 'fake-process')
            try:
                yield self.output, self.root / 'native.log', 0
            finally:
                on_process(None)
        with patch.object(native, 'image_job', image_job):
            s.run_cos_codex_image_job(self.root, {}, job, runtime)
        self.assertEqual(puts, [('job.log', {'expected_generation': 7}), ('output.png', {'expected_generation': 7})])
        self.assertEqual(b['_image_worker_processes'], {})
        self.assertEqual(b['mutate_candidate_image_job'].call_args.args[3]['status'], 'completed')
        runtime.store.put = Mock(side_effect=OSError('upload unknown'))
        with patch.object(native, 'image_job', image_job):
            s.run_cos_codex_image_job(self.root, {}, job, runtime)
        runtime.store.put.assert_called_once()
        self.assertEqual(b['update_image_worker_status'].call_args.kwargs['status'], 'failed')

    def test_pinned_actual_entry_dispatch_and_failure_cleanup(self):
        s, b, job, resolver = self.fixture()
        seen = []
        b['run_cursor_image2_job'] = lambda *args: seen.append(('cursor', resolver.current_snapshot()))
        b['run_codex_image_job'] = lambda *args: seen.append(('local', resolver.current_snapshot()))
        job['model_profiles'] = {'image': {'version': 3}}
        job.update(provider='cursor', status='local-queued')
        s.run_image_generation_job(self.root, {}, job)
        self.assertEqual(seen, [('cursor', job['model_profiles'])])
        self.assertIsNone(resolver.current_snapshot())
        job.update(provider='unknown', status='unknown')
        s.run_image_generation_job(self.root, {}, job)
        self.assertEqual(seen[-1], ('local', job['model_profiles']))
        b['run_codex_image_job'] = Mock(side_effect=RuntimeError('provider failed'))
        with self.assertRaisesRegex(RuntimeError, 'provider failed'):
            s.run_image_generation_job(self.root, {}, job)
        self.assertIsNone(resolver.current_snapshot())

    @unittest.skipIf(BASELINE, 'candidate composition only')
    def test_explicit_assembly(self):
        from local_inspection_service.accessories.image_job_execution_ports import ImageExecutionFiles, ImageExecutionEvidence, ImageExecutionProviders
        tree = ast.parse((ROOT / 'local_inspection_service/server.py').read_text(encoding='utf-8'))
        assignment = next(n for n in tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == '_image_job_execution' for t in n.targets))
        for group, cls in zip(assignment.value.keywords, (ImageExecutionFiles, ImageExecutionEvidence, ImageExecutionProviders)):
            self.assertEqual({k.arg for k in group.value.keywords}, {field.name for field in fields(cls)})
            for getter in group.value.keywords:
                self.assertIsInstance(getter.value, ast.Lambda)
                self.assertEqual(getter.value.body.id, getter.arg)
                self.assertFalse(getter.value.args.args)


if __name__ == '__main__':
    unittest.main(verbosity=2)
