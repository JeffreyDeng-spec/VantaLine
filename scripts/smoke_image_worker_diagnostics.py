"""Image worker diagnostics with synthetic logs/processes and unchanged-parent replay."""
import ast
from dataclasses import fields
import io
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace
from typing import Any
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from canonical_application_source_contract import read_checked_application_source
BASELINE = os.environ.get('VANTALINE_IMAGE_WORKER_DIAGNOSTICS_BASELINE_SOURCE')
NAMES = ('image_job_is_active', 'codex_log_has_generated_image', 'image_job_output_path', 'image_job_log_path',
         'read_image_worker_log_tail', 'classify_image_worker_failure', 'image_worker_process_alive',
         'codex_process_has_log_open', 'image_job_has_live_worker', 'running_image_job_is_stale')


def create(bindings):
    if BASELINE:
        nodes = [n for n in ast.parse(Path(BASELINE).read_text(encoding='utf-8-sig')).body if isinstance(n, ast.FunctionDef) and n.name in NAMES]
        assert len(nodes) == 10
        bindings.update(Any=Any, Path=Path, os=os, time=time)
        exec(compile(ast.Module(body=nodes, type_ignores=[]), BASELINE, 'exec'), bindings)
        return SimpleNamespace(**{n: bindings[n] for n in NAMES}), bindings
    from local_inspection_service.accessories.image_worker_diagnostics import ImageWorkerDiagnostics
    from local_inspection_service.accessories.image_worker_diagnostic_ports import ImageDiagnosticMedia, ImageDiagnosticRuntime, ImageDiagnosticPolicy
    def ports(cls): return cls(**{f.name: lambda name=f.name: bindings[name] for f in fields(cls)})
    service = ImageWorkerDiagnostics(ports(ImageDiagnosticMedia), ports(ImageDiagnosticRuntime), ports(ImageDiagnosticPolicy))
    bindings.update({n: getattr(service, n) for n in NAMES})
    return service, bindings


class ImageDiagnosticsContract(unittest.TestCase):
    def fixture(self):
        files = SimpleNamespace(exists=Mock(return_value=True), read_text=Mock(return_value=''), read_bytes=Mock(return_value=b''),
                                open_read=Mock(), iterdir=Mock(return_value=[]), stat=Mock(return_value=SimpleNamespace(st_mtime=900)))
        bindings = {'_business_files': files, 'resolve_service_path': Mock(side_effect=lambda v, **kw: Path(v)),
                    'safe_name': Mock(side_effect=lambda v: 'safe_' + v), 'IMAGE_WORKER_LOG_DIR': Path('/synthetic/logs'),
                    '_image_worker_processes': {}, 'IMAGE_JOB_ACTIVE_STATUSES': {'queued', 'running'},
                    'IMAGE_WORKER_LOG_TAIL_BYTES': 4, 'IMAGE_WORKER_STALE_SECONDS': 100, 'LOCAL_CODEX_IMAGE_PROVIDER': 'local'}
        service, bindings = create(bindings)
        return SimpleNamespace(s=service, b=bindings, files=files)

    def test_paths_defaults_and_active_policy(self):
        f = self.fixture()
        self.assertTrue(f.s.image_job_is_active('queued')); self.assertFalse(f.s.image_job_is_active('stopped'))
        f.b['IMAGE_JOB_ACTIVE_STATUSES'] = {'stopped'}; self.assertTrue(f.s.image_job_is_active('stopped'))
        self.assertEqual(f.s.image_job_output_path({'output_path': 'out.png'}, for_write=True), Path('out.png'))
        f.b['resolve_service_path'].assert_called_with('out.png', for_write=True)
        self.assertEqual(f.s.image_job_log_path({'log_path': ' exact.log '}), Path('exact.log'))
        f.b['resolve_service_path'].assert_called_with('exact.log')
        self.assertEqual(f.s.image_job_log_path({'task_id': 'task'}), Path('/synthetic/logs/safe_task.log'))
        self.assertEqual(f.s.image_job_log_path({}), Path('/synthetic/logs/safe_image_worker.log'))

    def test_log_markers_errors_tail_and_close(self):
        f = self.fixture(); log = Path('log')
        for text, expected in [('prefix /.codex/generated_images/output.png', True), ('/home/dministrator/.codex/generated_images/x', True), ('image elsewhere', False)]:
            f.files.read_text.return_value = text; self.assertEqual(f.s.codex_log_has_generated_image(log), expected)
        f.files.read_text.side_effect = OSError('synthetic'); self.assertFalse(f.s.codex_log_has_generated_image(log))
        f.files.exists.return_value = False; self.assertFalse(f.s.codex_log_has_generated_image(log)); self.assertEqual(f.s.read_image_worker_log_tail(log), '')
        f.files.exists.return_value = True; handle = io.BytesIO(b'prefix\xffABC'); f.files.open_read.return_value = handle
        self.assertEqual(f.s.read_image_worker_log_tail(log), 'ABC'); self.assertTrue(handle.closed)
        f.files.open_read.side_effect = OSError('synthetic'); self.assertEqual(f.s.read_image_worker_log_tail(log), '')
        failure = RuntimeError('not an IO failure'); f.files.open_read.side_effect = failure
        with self.assertRaises(RuntimeError) as caught: f.s.read_image_worker_log_tail(log)
        self.assertIs(caught.exception, failure)

    def test_failure_classification_order_and_fallback(self):
        f = self.fixture(); f.b['read_image_worker_log_tail'] = Mock(return_value='429 FORBIDDEN fallback requires approval'); f.files.exists.return_value = False
        result = f.s.classify_image_worker_failure(Path('log'), 0, Path('output.png'), stale=True)
        expected = ['图像生成供应商限流（TooManyRequests/429）', '备用图像连接器被拒绝（FORBIDDEN）', 'CLI fallback 需要显式配置或批准',
                    '任务标记为 running，但当前服务没有发现仍在写日志的 Image Worker 进程', 'Codex CLI 退出码 0，但没有写出目标 PNG', '未生成目标 PNG：output.png']
        self.assertEqual(result, '；'.join(expected) + '。请稍后重试，或配置并批准可用的 Image Worker fallback 后重新排队。')
        f.files.exists.return_value = True; f.b['read_image_worker_log_tail'] = lambda p: ''
        self.assertTrue(f.s.classify_image_worker_failure(Path('log'), None, Path('out')).startswith('图像生成结束但未产出可用图片。'))
        self.assertTrue(f.s.classify_image_worker_failure(Path('log'), 7, Path('out')).startswith('Codex CLI 退出码 7。'))

    def test_registered_process_poll_and_short_circuit(self):
        f = self.fixture(); self.assertFalse(f.s.image_worker_process_alive('missing'))
        process = SimpleNamespace(poll=Mock(return_value=None)); f.b['_image_worker_processes'] = {'job': process}
        self.assertTrue(f.s.image_worker_process_alive('job')); process.poll.return_value = 0; self.assertFalse(f.s.image_worker_process_alive('job'))
        f.b['image_worker_process_alive'] = Mock(return_value=True); f.b['codex_process_has_log_open'] = Mock(side_effect=AssertionError('short circuit'))
        self.assertTrue(f.s.image_job_has_live_worker({'job_id': 'job'}, Path('log')))
        f.b['codex_process_has_log_open'].assert_not_called()
        f.b['image_worker_process_alive'].return_value = False; sentinel = object(); f.b['codex_process_has_log_open'] = Mock(return_value=sentinel)
        self.assertIs(f.s.image_job_has_live_worker({}, Path('log')), sentinel)

    def test_proc_descriptor_search_and_failure_boundaries(self):
        f = self.fixture(); log = Path('synthetic.log'); f.files.iterdir.side_effect = lambda p: [Path('/proc/not-pid'), Path('/proc/3'), Path('/proc/4')] if p == Path('/proc') else [p / '0', p / '1']
        f.files.read_bytes.side_effect = lambda p: b'other' if p.parts[-2] == '3' else b'python\x00codex\x00worker'
        with patch.object(os, 'readlink', side_effect=[OSError('gone'), str(log.resolve()) + ' (deleted)']) as readlink:
            self.assertTrue(f.s.codex_process_has_log_open(log)); self.assertEqual(readlink.call_count, 2)
        f.files.read_bytes.side_effect = OSError('gone'); self.assertFalse(f.s.codex_process_has_log_open(log))
        f.files.iterdir.side_effect = OSError('proc root unavailable')
        with self.assertRaisesRegex(OSError, 'proc root unavailable'): f.s.codex_process_has_log_open(log)
        f.files.exists.return_value = False; self.assertFalse(f.s.codex_process_has_log_open(log))

    def test_staleness_boundary_and_preserved_error_handling(self):
        f = self.fixture(); f.b['image_job_has_live_worker'] = Mock(return_value=False); log = Path('log')
        with patch.object(time, 'time', return_value=1000):
            self.assertTrue(f.s.running_image_job_is_stale({}, log)); f.files.stat.return_value.st_mtime = 901; self.assertFalse(f.s.running_image_job_is_stale({}, log))
            f.files.exists.return_value = False
            self.assertTrue(f.s.running_image_job_is_stale({'started_at': 900, 'provider': 'local', 'generation_method': 'codex_exec_image_worker'}, log))
            self.assertFalse(f.s.running_image_job_is_stale({}, log))
            self.assertFalse(f.s.running_image_job_is_stale({'started_at': 'invalid'}, log))
            with self.assertRaises(OverflowError): f.s.running_image_job_is_stale({'started_at': float('inf')}, log)
            f.b['image_job_has_live_worker'].return_value = True
            with patch.object(time, 'time', side_effect=AssertionError('clock must not run')): self.assertFalse(f.s.running_image_job_is_stale({}, log))

    def test_late_media_and_tail_policy_lookup(self):
        f = self.fixture(); handle = io.BytesIO(b'prefixXYZ'); replacement = SimpleNamespace(open_read=Mock(return_value=handle))
        def exists(path): f.b['_business_files'] = replacement; f.b['IMAGE_WORKER_LOG_TAIL_BYTES'] = 3; return True
        f.files.exists.side_effect = exists
        self.assertEqual(f.s.read_image_worker_log_tail(Path('log')), 'XYZ'); self.assertTrue(handle.closed)
        f = self.fixture(); f.b['read_image_worker_log_tail'] = lambda p: f.b.update(_business_files=SimpleNamespace(exists=lambda p: False)) or ''
        self.assertIn('未生成目标 PNG', f.s.classify_image_worker_failure(Path('log'), None, Path('out')))

    @unittest.skipIf(bool(BASELINE), 'candidate wiring only')
    def test_wiring_and_light_import(self):
        tree = ast.parse(read_checked_application_source(ROOT / 'local_inspection_service/server.py', encoding='utf-8'))
        from accessory_image_test_ports import binding as owner_binding
        binding = owner_binding(ROOT,'diagnostics')
        count = 0
        for group in binding.keywords:
            if group.arg=='policy':
                self.assertIsInstance(group.value,ast.Name);self.assertEqual(group.value.id,'diagnostic_policy')
                from dataclasses import fields
                from local_inspection_service.accessories.image_worker_diagnostic_ports import ImageDiagnosticPolicy
                count+=len(fields(ImageDiagnosticPolicy));continue
            for kw in group.value.keywords:
                self.assertIsInstance(kw.value,(ast.Lambda,ast.Attribute))
                if isinstance(kw.value,ast.Attribute):self.assertEqual(kw.value.attr,kw.arg)
                else:self.assertFalse(kw.value.args.args);self.assertIsInstance(kw.value.body,ast.Attribute)
                count+=1
        self.assertEqual(count,13)
        from accessory_image_test_ports import edge_errors, DIAGNOSTIC_EDGES
        self.assertEqual(edge_errors(binding,DIAGNOSTIC_EDGES),[])
        for name in NAMES:
            node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
            self.assertEqual(len(node.body), 1); self.assertIsInstance(node.body[0], ast.Return); self.assertEqual(node.body[0].value.func.attr, name)
        subprocess.run([sys.executable, '-B', '-c', 'import sys; import local_inspection_service.accessories.image_worker_diagnostics; assert "local_inspection_service.server" not in sys.modules'], cwd=ROOT, check=True)


if __name__ == '__main__':
    unittest.main()
