"""Root configuration publication/rollback paths in private temporary directories."""
import base64
import ast
import json
import subprocess
import hashlib
import os
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from release_runtime_configuration import ConfigurationFiles
from release_runtime_contract import ContractError
from local_inspection_service.runtime.configuration import ConfigurationSnapshot


class ConfigurationPublication(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.files = ConfigurationFiles(self.root / "configuration", uid=os.getuid(), gid=os.getgid())

    def snapshot(self, **env):
        return ConfigurationSnapshot.capture({"VANTALINE_DATA_STORE": "postgres", "DATABASE_URL": "fixture", **env}, self.root)

    def test_immutable_versions_and_atomic_pointer_restore(self):
        first, second = self.snapshot(), self.snapshot(HTTP_PROXY="")
        self.assertIsNone(self.files.capture_pointer())
        for value in (first, second):
            self.assertEqual(self.files.install(value.export(), expected_revision=value.revision), value.revision)
            self.files.select(value.revision)
            self.assertEqual(self.files.capture_pointer(), value.revision)
        self.files.select(first.revision)
        self.assertEqual(self.files.capture_pointer(), first.revision)
        self.assertEqual((self.files.directory / "current/config.json").read_bytes(), first._payload)
        self.assertTrue((self.files.directory / second.revision).is_dir())
        self.files.select(None)
        self.assertIsNone(self.files.capture_pointer())

    def test_repeated_publication_validates_files_and_refuses_tampering(self):
        value = self.snapshot()
        self.files.install(value.export(), expected_revision=value.revision)
        self.files.install(value.export(), expected_revision=value.revision)
        path = self.files.directory / value.revision / "config.json"
        original = path.read_bytes()
        path.write_bytes(b"changed")
        with self.assertRaises(ContractError):
            self.files.install(value.export(), expected_revision=value.revision)
        self.assertEqual(path.read_bytes(), b"changed")
        path.write_bytes(original); path.chmod(0o644)
        with self.assertRaises(ContractError):
            self.files.install(value.export(), expected_revision=value.revision)

    def test_foreign_pointer_or_digest_rejected_before_selection(self):
        value = self.snapshot()
        with self.assertRaises(ContractError):
            self.files.install(value.export(), expected_revision="0" * 64)
        self.assertFalse(self.files.directory.exists())
        self.files.prepare()
        (self.files.directory / "current").symlink_to(self.root)
        with self.assertRaises(ContractError):
            self.files.select(None)
        self.assertTrue((self.files.directory / "current").is_symlink())

    def test_missing_fixed_parent_is_created_privately(self):
        files = ConfigurationFiles(self.root / 'new-parent/runtime', uid=os.getuid(), gid=os.getgid())
        files.prepare()
        self.assertEqual(files.directory.parent.stat().st_mode & 0o777, 0o750)
        self.assertEqual(files.directory.stat().st_mode & 0o777, 0o750)

    def test_installer_runs_without_application_imports_or_search_path(self):
        from render_release_installer import render
        text = render().decode()
        helper = text.split("<<'PY_VANTALINE_RUNTIME'\n", 1)[1].split('PY_VANTALINE_RUNTIME\n', 1)[0]
        for node in ast.walk(ast.parse(helper)):
            names = ([item.name for item in node.names] if isinstance(node, ast.Import)
                     else [node.module] if isinstance(node, ast.ImportFrom) else [])
            for name in names:
                self.assertIn(name.split('.')[0], sys.stdlib_module_names)
        result = subprocess.run([sys.executable, '-I', '-S', '-', 'capabilities'], input=helper,
            text=True, cwd=self.root, capture_output=True, check=True, env={})
        self.assertEqual(json.loads(result.stdout)['configuration_schema'], 1)
        self.assertEqual(result.stderr, '')

    def test_cos_credentials_remain_private_and_exact(self):
        credential_dir = self.root / "credentials"
        credential_dir.mkdir()
        path = credential_dir / "cos-credentials.json"
        path.write_bytes(b'{"COS_SECRET_ID":"fixture","COS_SECRET_KEY":"fixture"}')
        path.chmod(0o600)
        value = self.snapshot(VANTALINE_FILE_STORE="cos", VANTALINE_DATA_ROOT=str(self.root),
            VANTALINE_ARTIFACT_WORK_ROOT=str(self.root / "work"), VANTALINE_ARTIFACT_CACHE_ROOT=str(self.root / "cache"),
            VANTALINE_COS_BUCKET="fixture-123", CREDENTIALS_DIRECTORY=str(credential_dir))
        self.files.install(value.export(), expected_revision=value.revision)
        copy = self.files.directory / value.revision / "cos-credentials.json"
        self.assertEqual(copy.read_bytes(), path.read_bytes())
        self.assertEqual(copy.stat().st_mode & 0o777, 0o600)
        corrupted = value.export(); corrupted["credential"] = base64.b64encode(b"wrong").decode()
        with self.assertRaises(ContractError):
            self.files.install(corrupted, expected_revision=value.revision)


if __name__ == "__main__":
    unittest.main()
