"""Authenticated snapshot and identity data boundaries; no live DB or services."""
import ast
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT)]
import release_observer_snapshot as snapshot_module
from release_runtime_contract import ContractError
from render_release_installer import render, OBSERVER_SOURCES
from local_inspection_service.runtime.observe_label_runtime import observation_object


@unittest.skipUnless(sys.platform == 'linux', 'Linux descriptor contract')
class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.target = self.root / 'untrusted-parent' / 'target'
        self.target.mkdir(parents=True)
        self.target.parent.chmod(0o777)
        self.storage = self.root / 'storage'
        self.storage.mkdir(mode=0o700)
        self.file = self.target / 'module.py'
        self.data = b'VALUE = 7\n'
        self.file.write_bytes(self.data)
        self.expected = {'module.py': hashlib.sha256(self.data).hexdigest()}
        self.real_stat = os.fstat
        def root_stat(fd):
            values = list(self.real_stat(fd)); values[4] = 0
            return os.stat_result(values)
        # CI runs unprivileged: only ownership is supplied; actual descriptors,
        # links, permissions, bounded reads, hashes and cleanup are exercised.
        self.owner = patch.object(snapshot_module.os, 'fstat', side_effect=root_stat)
        self.owner.start(); self.addCleanup(self.owner.stop)

    def assert_no_snapshot(self):
        self.assertEqual(list(self.storage.iterdir()), [])

    def foreign_stat(self, fd):
        values = list(self.real_stat(fd)); values[4] = 998
        return os.stat_result(values)

    def test_exact_bytes_private_modes_ignored_unknown_code_and_cleanup(self):
        (self.target / 'sitecustomize.py').write_text('raise Exception("poison")')
        with snapshot_module.observer_snapshot(self.target, self.storage, self.expected) as path:
            self.assertEqual((path / 'module.py').read_bytes(), self.data)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE((path / 'module.py').stat().st_mode), 0o600)
            self.assertFalse((path / 'sitecustomize.py').exists())
        self.assert_no_snapshot()

    def test_hash_rewrite_missing_file_and_child_failure_cleanup(self):
        self.file.write_bytes(b'raise Exception("attacker")\n')
        with self.assertRaises(ContractError):
            with snapshot_module.observer_snapshot(self.target, self.storage, self.expected):pass
        self.assert_no_snapshot()
        self.file.unlink()
        with self.assertRaises(FileNotFoundError):
            with snapshot_module.observer_snapshot(self.target, self.storage, self.expected):pass
        self.assert_no_snapshot()
        self.file.write_bytes(self.data)
        with self.assertRaises(RuntimeError):
            with snapshot_module.observer_snapshot(self.target, self.storage, self.expected):raise RuntimeError('child')
        self.assert_no_snapshot()

    def test_symlink_hardlink_fifo_and_writable_source_rejected(self):
        for kind in ('symlink', 'hardlink', 'fifo', 'writable'):
            with self.subTest(kind=kind):
                self.file.unlink(missing_ok=True)
                other = self.target / ('other-' + kind)
                other.write_bytes(self.data)
                if kind == 'symlink':self.file.symlink_to(other)
                elif kind == 'hardlink':os.link(other, self.file)
                elif kind == 'fifo':os.mkfifo(self.file)
                else:self.file.write_bytes(self.data);self.file.chmod(0o666)
                with self.assertRaises((OSError, ContractError)):
                    with snapshot_module.observer_snapshot(self.target, self.storage, self.expected):pass
                self.assert_no_snapshot()

    def test_owner_rejected_and_bounded_read(self):
        with patch.object(snapshot_module.os, 'fstat', side_effect=self.foreign_stat):
            with self.assertRaises(ContractError):
                with snapshot_module.observer_snapshot(self.target,self.storage,self.expected):pass
        self.assert_no_snapshot()
        with self.file.open('wb') as handle:handle.truncate(20*1024*1024+2)
        with self.assertRaises(ContractError):
            with snapshot_module.observer_snapshot(self.target,self.storage,self.expected):pass
        self.assert_no_snapshot()

    def test_invalid_authorization_and_traversal(self):
        for expected in ({}, None, {'../escape': 'a'*64}, {'/escape': 'a'*64}, {'a//b': 'a'*64}):
            with self.subTest(expected=expected),self.assertRaises(ContractError):
                with snapshot_module.observer_snapshot(self.target,self.storage,expected):pass
            self.assert_no_snapshot()

    def test_identity_regular_bounded_json_symlink_fifo_and_owner(self):
        self.file.write_text('{"schema":1}')
        self.assertEqual(observation_object(self.file), {'schema':1})
        for data in (b'[]',b'{broken',b' '*(16384+1)):
            self.file.write_bytes(data)
            with self.assertRaises((RuntimeError,ValueError)):observation_object(self.file)
        self.file.unlink();os.mkfifo(self.file)
        with self.assertRaises(RuntimeError):observation_object(self.file)
        self.file.unlink();self.file.symlink_to(self.target/'missing')
        with self.assertRaises(OSError):observation_object(self.file)
        self.file.unlink();self.file.write_text('{}')
        with patch.object(snapshot_module.os,'fstat',side_effect=self.foreign_stat),self.assertRaises(RuntimeError):observation_object(self.file)

    def test_real_source_authorization_import_closure_without_web(self):
        lines=render().decode().splitlines()
        value=[line for line in lines if line.startswith('OBSERVER_EXECUTION_FILES = ')]
        self.assertEqual(len(value),1)
        expected=ast.literal_eval(value[0].split(' = ',1)[1])
        self.assertEqual(len(expected),139)
        authorized={name:digest for name,digest in expected.items() if name in OBSERVER_SOURCES}
        target=self.root/'sources';target.mkdir()
        for name in OBSERVER_SOURCES:
            path=target/name;path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes((ROOT/name).read_bytes().replace(b'\r\n',b'\n'))
        with snapshot_module.observer_snapshot(target,self.storage,authorized) as path:
            code="import sys,json,pathlib;sys.path.insert(0,sys.argv[1]);import local_inspection_service.runtime.observe_label_runtime;print(json.dumps(sorted(pathlib.Path(m.__file__).relative_to(sys.argv[1]).as_posix() for n,m in sys.modules.items() if n.startswith('local_inspection_service') and getattr(m,'__file__',None))))"
            result=subprocess.run([sys.executable,'-I','-S','-B','-c',code,str(path)],check=True,capture_output=True,text=True,timeout=10)
            self.assertEqual(set(json.loads(result.stdout)),set(OBSERVER_SOURCES))
        self.assert_no_snapshot()


if __name__=='__main__':unittest.main()
