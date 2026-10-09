"""Bootstrap root precedence and exact derived-layout regression."""
from dataclasses import FrozenInstanceError
import hashlib
import importlib.util
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from local_inspection_service.runtime.bootstrap_locations import RootLocator, RuntimeLocations

BASELINE = ROOT / 'tests/backend_contract/bootstrap_locations_baseline.py'
assert hashlib.sha256(BASELINE.read_bytes().replace(b'\r\n', b'\n')).hexdigest() == 'd1d7d7a616c2fa119b1d17c0787cb0b6b68cc9e3c4c8b98a7a9d7c97cf5d8699'
spec = importlib.util.spec_from_file_location('frozen_bootstrap', BASELINE)
frozen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(frozen)


class BootstrapContract(unittest.TestCase):
    def test_original_root_resolution_and_environment_order(self):
        with tempfile.TemporaryDirectory(prefix='bootstrap-locations-') as temporary:
            anchor = str(Path(temporary) / 'release' / 'local_inspection_service' / 'server.py')
            values = ['', 'relative', str(Path(temporary) / 'new'), str(Path(temporary) / 'local_inspection_service'), '~', '  ']
            keys = ('LOCAL_INSPECTION_ROOT', 'INSPECTION_SERVICE_ROOT', 'VANTALINE_REPO_ROOT')
            cases = [{}] + [{key:value} for key in keys for value in values]
            cases += [dict(zip(keys, values)) for values in (('first','second','third'), ('','second','third'), ('','','third'), ('','',''))]
            for environment in cases:
                for allowed in (True, False):
                    with self.subTest(environment=environment, allowed=allowed):
                        calls = []
                        def probe(path):
                            calls.append(path)
                            return allowed
                        frozen.os = SimpleNamespace(environ=environment)
                        frozen.__file__ = anchor
                        frozen._business_files = SimpleNamespace(is_dir=probe)
                        def outcome(fn):
                            try:
                                return ('value', fn())
                            except RuntimeError as error:
                                return (type(error), str(error))
                        before = outcome(frozen.resolve_service_root)
                        old_calls = list(calls); calls.clear()
                        locator = RootLocator(environment, anchor, probe)
                        self.assertEqual(calls, [])
                        self.assertEqual(outcome(locator.resolve), before)
                        self.assertEqual(calls, old_calls)

    def test_live_environment_and_callback_error_identity(self):
        environment = {'LOCAL_INSPECTION_ROOT':'first'}
        failure = RuntimeError('synthetic directory probe failed')
        probe = Mock(side_effect=failure)
        locator = RootLocator(environment, str(ROOT / 'local_inspection_service/server.py'), probe)
        probe.assert_not_called()
        with self.assertRaises(RuntimeError) as caught:
            locator.resolve()
        self.assertIs(caught.exception, failure)
        locator.is_dir = lambda _: True
        self.assertEqual(locator.resolve(), Path('first').resolve())
        environment['LOCAL_INSPECTION_ROOT']='second'
        self.assertEqual(locator.resolve(), Path('second').resolve())

    def test_all_original_paths_and_independent_layouts(self):
        with tempfile.TemporaryDirectory(prefix='bootstrap-layout-') as temporary:
            a, b = (RuntimeLocations.from_root(Path(temporary)/label) for label in ('a','b'))
            for layout in (a,b):
                expected = frozen.original_locations(layout.root)
                self.assertEqual(len(layout.__dataclass_fields__),30)
                for name in layout.__dataclass_fields__:
                    self.assertEqual(getattr(layout,name),expected[name.upper()])
                self.assertFalse(layout.root.exists())
            self.assertNotEqual(a.data_dir,b.data_dir)
            with self.assertRaises(FrozenInstanceError):
                a.root=b.root

    def test_actual_entry_uses_original_anchor_and_same_layout(self):
        from scripts import verify_backend_contract as contract
        self.assertEqual(contract.encoded(contract.capture()),contract.BASELINE.read_text(encoding='utf-8'))
        from local_inspection_service import server
        self.assertEqual(server._root_locator.entry_file,server.__file__)
        self.assertEqual(server.resolve_service_root,server._root_locator.resolve)
        self.assertEqual(server._runtime_locations.root,server.ROOT)
        for name in server._runtime_locations.__dataclass_fields__:
            self.assertEqual(getattr(server,name.upper()),getattr(server._runtime_locations,name))


if __name__ == '__main__':
    unittest.main()
