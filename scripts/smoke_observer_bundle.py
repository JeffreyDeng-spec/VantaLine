"""Exercise observer trust boundaries without a database or paid calls."""
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from observer_bundle_contract import (
    ObserverBundleError, observer_bundle_lock, observer_json,
    observer_member_name, verify_observer_bundle,
)


class ObserverBundleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bundle = self.root/'bundle'
        self.bundle.mkdir()
        self.lock = self.root/'lock.json'
        shutil.copyfile(Path(__file__).resolve().parents[1]/'release/observer-dependencies.json', self.lock)
        for name in ('psycopg/__init__.py', 'psycopg_binary/__init__.py', 'typing_extensions.py'):
            p = self.bundle/name
            p.parent.mkdir(exist_ok=True)
            p.write_bytes(b'# synthetic trust-boundary fixture\n')
        self.manifest()

    def manifest(self):
        files = {p.relative_to(self.bundle).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in self.bundle.rglob('*') if p.is_file() and p.name != 'manifest.json'}
        (self.bundle/'manifest.json').write_text(json.dumps({
            'schema': 1, 'lock_sha256': hashlib.sha256(self.lock.read_bytes()).hexdigest(), 'files': files}))

    def verify(self, **kwargs):
        return verify_observer_bundle(self.bundle, self.lock, require_root=False, require_runtime=False, **kwargs)

    def test_complete_fixture(self):
        self.assertEqual(self.verify()['python'], [3, 10])

    def test_missing_extra_and_checksum(self):
        p = self.bundle/'typing_extensions.py'
        original = p.read_bytes()
        for kind in ('missing', 'changed', 'extra'):
            with self.subTest(kind=kind):
                if kind == 'missing': p.unlink()
                elif kind == 'changed': p.write_bytes(b'changed')
                else: (self.bundle/'psycopg/extra.py').write_bytes(b'extra')
                with self.assertRaises(ObserverBundleError): self.verify()
                p.write_bytes(original)
                (self.bundle/'psycopg/extra.py').unlink(missing_ok=True)

    def test_unexpected_package_even_with_consistent_manifest(self):
        (self.bundle/'rogue.py').write_bytes(b'')
        self.manifest()
        with self.assertRaises(ObserverBundleError): self.verify()

    def test_site_hooks_rejected(self):
        for name in ('psycopg/a.pth', 'psycopg/sitecustomize.py', '../x', '/x', 'a\\b', '.', '', [], None):
            with self.subTest(name=name), self.assertRaises(ObserverBundleError): observer_member_name(name)

    def test_links_rejected(self):
        p = self.bundle/'typing_extensions.py'
        p.unlink()
        outside = self.root/'outside'
        outside.write_bytes(b'x')
        for kind in ('hardlink', 'symlink'):
            with self.subTest(kind=kind):
                if kind == 'hardlink': os.link(outside, p)
                else: p.symlink_to(outside)
                with self.assertRaises(ObserverBundleError): self.verify()
                p.unlink()

    def test_bad_manifest_and_changed_lock(self):
        p = self.bundle/'manifest.json'
        p.write_text('{"schema":1,"schema":1}')
        with self.assertRaises(ObserverBundleError): self.verify()
        self.manifest()
        self.lock.write_bytes(self.lock.read_bytes()+b'\n')
        with self.assertRaises(ObserverBundleError): self.verify()

    def test_metadata_read_is_bounded(self):
        stream = io.BytesIO(b' '*(1024*1024+2))
        with patch.object(Path, 'open', return_value=stream), patch.object(stream, 'read', wraps=stream.read) as read:
            with self.assertRaises(ObserverBundleError): observer_json(self.lock)
            read.assert_called_once_with(1024*1024+1)

    def test_lock_types_and_null_fields(self):
        original = json.loads(self.lock.read_text())
        for field in ('schema', 'python', 'wheels'):
            for bad in (None, [], {}, True):
                with self.subTest(field=field, bad=bad):
                    value = dict(original); value[field] = bad
                    self.lock.write_text(json.dumps(value))
                    with self.assertRaises(ObserverBundleError): observer_bundle_lock(self.lock)
        for field in ('name', 'filename', 'sha256', 'url', 'version'):
            value = json.loads(json.dumps(original)); value['wheels'][0][field] = []
            self.lock.write_text(json.dumps(value))
            with self.assertRaises(ObserverBundleError): observer_bundle_lock(self.lock)

    def test_root_modes_and_runtime_fail_closed(self):
        self.bundle.chmod(0o777)
        with self.assertRaises(ObserverBundleError):
            verify_observer_bundle(self.bundle, self.lock, require_root=True, require_runtime=False)
        self.bundle.chmod(0o755)
        with patch('observer_bundle_contract.observer_runtime_compatible', return_value=False):
            with self.assertRaises(ObserverBundleError):
                verify_observer_bundle(self.bundle, self.lock, require_root=False)

    def test_inventory_error_not_silently_ignored(self):
        def bad_walk(*args, **kwargs):
            kwargs['onerror'](PermissionError())
            return iter(())
        with patch('observer_bundle_contract.os.walk', side_effect=bad_walk):
            with self.assertRaises(ObserverBundleError): self.verify()


if __name__ == '__main__':
    unittest.main()
