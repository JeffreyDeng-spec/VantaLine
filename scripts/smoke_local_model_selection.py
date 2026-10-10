"""Local device and checkpoint selection contracts without hardware/model access."""
import ast
import builtins
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch, call

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from canonical_application_source_contract import read_checked_application_source
BASELINE = os.environ.get('VANTALINE_LOCAL_SELECTION_BASELINE_SOURCE')
NAMES = ('yolo_inference_device', 'detect_base_model')


def create(bindings):
    if BASELINE:
        nodes = [n for n in ast.parse(Path(BASELINE).read_text(encoding='utf-8')).body
                 if isinstance(n, ast.FunctionDef) and n.name in NAMES]
        assert len(nodes) == 2
        namespace = dict(bindings, os=os)
        exec(compile(ast.Module(body=nodes, type_ignores=[]), BASELINE, 'exec'), namespace)
        return SimpleNamespace(**{name: namespace[name] for name in NAMES}), namespace
    from local_inspection_service.detection.local_models import CheckpointSelection, yolo_inference_device
    selection = CheckpointSelection(lambda: bindings['DETECT_BASE_MODEL_OVERRIDE'],
        lambda: bindings['ROOT'], lambda: bindings['APP_DIR'], lambda path: bindings['_business_files'].exists(path))
    return SimpleNamespace(yolo_inference_device=yolo_inference_device,
                           detect_base_model=selection.detect_base_model), bindings


def require_root_selection_binding(source):
    tree = ast.parse(source)
    expected = {
        'detect_base_model': '_checkpoint_selection.detect_base_model',
        '_checkpoint_selection': 'CheckpointSelection(lambda: DETECT_BASE_MODEL_OVERRIDE, lambda: ROOT, lambda: APP_DIR, lambda path: _business_files.exists(path))',
    }
    for name, expression in expected.items():
        values = [n.value for n in tree.body if isinstance(n, ast.Assign)
                  and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name) and n.targets[0].id == name]
        if len(values) != 1 or ast.dump(values[0]) != ast.dump(ast.parse(expression, mode='eval').body):
            raise AssertionError('Local model selection binding changed: ' + name)
    if not any(isinstance(n, ast.ImportFrom) and n.module == 'detection.local_models'
               and any(a.name == 'yolo_inference_device' for a in n.names) for n in tree.body):
        raise AssertionError('Local device selection import changed')


class SelectionContracts(unittest.TestCase):
    def setUp(self):
        self.files = SimpleNamespace(exists=Mock(return_value=False))
        self.service, self.bindings = create(dict(DETECT_BASE_MODEL_OVERRIDE='', ROOT=Path('/root'),
                                                APP_DIR=Path('/app'), _business_files=self.files))

    def device(self, configured, available=None, failure=None):
        original_import = builtins.__import__
        cuda = Mock(return_value=available, side_effect=failure)
        imports = []
        def load(name, *args, **kwargs):
            if name == 'torch':
                imports.append(name)
                return SimpleNamespace(cuda=SimpleNamespace(is_available=cuda))
            return original_import(name, *args, **kwargs)
        with patch.dict(os.environ, {'INSPECTION_YOLO_DEVICE': configured}), patch('builtins.__import__', load):
            result = self.service.yolo_inference_device()
        return result, imports, cuda

    def test_explicit_device_skips_torch_and_keeps_unvalidated_value(self):
        for value in ('cpu', '0', ' cuda:4 ', 'custom-device'):
            result, imports, cuda = self.device(value, failure=AssertionError('hardware access'))
            self.assertEqual(result, value.strip()); self.assertEqual(imports, []); cuda.assert_not_called()

    def test_dynamic_device_environment_and_cuda_truthiness(self):
        for available, expected in ((True, 0), (False, 'cpu'), (object(), 0), ([], 'cpu')):
            result, imports, cuda = self.device('  ', available)
            self.assertEqual(result, expected); self.assertEqual(imports, ['torch']); cuda.assert_called_once_with()
        self.assertEqual(self.device('cpu')[0], 'cpu')

    def test_cuda_exception_cpu_but_baseexception_propagates(self):
        for failure in (RuntimeError('cuda'), ImportError('missing'), ValueError('driver')):
            self.assertEqual(self.device('', failure=failure)[0], 'cpu')
        with self.assertRaises(SystemExit): self.device('', failure=SystemExit('stop'))

    def test_missing_torch_cpu_and_environment_error_outside_try(self):
        original_import = builtins.__import__
        def missing(name, *args, **kwargs):
            if name == 'torch': raise ImportError('missing synthetic torch')
            return original_import(name, *args, **kwargs)
        with patch.dict(os.environ, {'INSPECTION_YOLO_DEVICE': ''}), patch('builtins.__import__', missing):
            self.assertEqual(self.service.yolo_inference_device(), 'cpu')
        with patch.object(os, 'environ', SimpleNamespace(get=lambda *_: None)):
            with self.assertRaises(AttributeError): self.service.yolo_inference_device()

    def test_override_no_path_or_filesystem_access(self):
        for value in ('other.pt', object()):
            self.bindings['DETECT_BASE_MODEL_OVERRIDE'] = value
            self.bindings['ROOT'] = None; self.bindings['APP_DIR'] = None
            self.assertIs(self.service.detect_base_model(), value)
        self.files.exists.assert_not_called()

    def test_order_first_match_and_no_model_loading(self):
        paths = [Path('/root/yolo26s.pt'), Path('/app/yolo26s.pt'), Path('/root/yolo11s.pt'), Path('/root/yolov8s.pt')]
        for index, selected in enumerate(paths):
            self.files.exists.reset_mock(); self.files.exists.side_effect = lambda path: path == selected
            self.assertEqual(self.service.detect_base_model(), str(selected))
            self.assertEqual(self.files.exists.call_args_list, [call(path) for path in paths[:index + 1]])

    def test_all_missing_default_and_exception_is_not_swallowed(self):
        self.assertEqual(self.service.detect_base_model(), 'yolo26s.pt')
        self.assertEqual(self.files.exists.call_count, 4)
        failure = OSError('file access'); self.files.exists.side_effect = failure
        with self.assertRaises(OSError) as error: self.service.detect_base_model()
        self.assertIs(error.exception, failure)

    def test_candidate_paths_frozen_before_file_callbacks_but_reader_rebound(self):
        calls = []
        def first(path):
            calls.append(path)
            self.bindings['ROOT'] = Path('/changed')
            self.bindings['_business_files'] = SimpleNamespace(exists=lambda p: calls.append(p) or True)
            return False
        self.files.exists.side_effect = first
        self.assertEqual(self.service.detect_base_model(), str(Path('/app/yolo26s.pt')))
        self.assertEqual(calls, [Path('/root/yolo26s.pt'), Path('/app/yolo26s.pt')])

    def test_path_construction_failure_precedes_any_exists(self):
        self.bindings['APP_DIR'] = None
        with self.assertRaises(TypeError): self.service.detect_base_model()
        self.files.exists.assert_not_called()

    @unittest.skipIf(bool(BASELINE), 'candidate composition only')
    def test_independent_instances_zero_constructor_io_and_real_root_binding(self):
        from local_inspection_service.detection.local_models import CheckpointSelection
        fail = Mock(side_effect=AssertionError('constructor I/O'))
        CheckpointSelection(fail, fail, fail, fail); fail.assert_not_called()
        first = CheckpointSelection(lambda:'one', fail, fail, fail)
        second = CheckpointSelection(lambda:'two', fail, fail, fail)
        self.assertEqual([first.detect_base_model(), second.detect_base_model(), first.detect_base_model()], ['one','two','one'])
        require_root_selection_binding(read_checked_application_source(ROOT / 'local_inspection_service/server.py', encoding='utf-8'))

    @unittest.skipIf(bool(BASELINE), 'candidate composition only')
    def test_binding_guard_accepts_formatting_and_rejects_changed_dependencies(self):
        source = "from .detection.local_models import yolo_inference_device\n" + "detect_base_model = _checkpoint_selection.detect_base_model\n" + "_checkpoint_selection = CheckpointSelection(lambda : DETECT_BASE_MODEL_OVERRIDE, lambda : ROOT, lambda : APP_DIR, lambda path : _business_files.exists(path))\n"
        require_root_selection_binding(source)
        require_root_selection_binding(ast.unparse(ast.parse(source)))
        for old, new in [
            ('lambda : ROOT', 'lambda : APP_DIR'),
            ('lambda : DETECT_BASE_MODEL_OVERRIDE', 'DETECT_BASE_MODEL_OVERRIDE'),
            ('_business_files.exists(path)', '_business_files.is_file(path)'),
            ('detect_base_model = _checkpoint_selection.detect_base_model', 'detect_base_model = other.detect_base_model'),
            ('from .detection.local_models', 'from .other'),
        ]:
            with self.subTest(change=new), self.assertRaises(AssertionError):
                require_root_selection_binding(source.replace(old, new))
        with self.assertRaises(AssertionError):
            require_root_selection_binding(source + 'detect_base_model = _checkpoint_selection.detect_base_model\n')



if __name__ == '__main__': unittest.main()
