"""Private configuration roundtrip using synthetic credentials and temporary files."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local_inspection_service.runtime.configuration import ConfigurationSnapshot, ConfigurationError


class ConfigurationIO(unittest.TestCase):
    def test_roundtrip_preserves_unset_empty_and_worker_credential_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            value = ConfigurationSnapshot.capture({"VANTALINE_DATA_STORE": "postgres", "DATABASE_URL": "synthetic",
                "HTTP_PROXY": "", "VANTALINE_PROFILE_" + "B" * 32: "fixture"}, root)
            path = root / "config.json"
            path.write_text(json.dumps(value.export()["configuration"]))
            path.chmod(0o640)
            worker = ConfigurationSnapshot.read_worker(path, credentials_directory=None, owner=os.getuid())
            env = {"CREDENTIALS_DIRECTORY": "/run/worker-own", "HTTPS_PROXY": "must-be-unset", "HTTP_PROXY": "must-be-empty"}
            self.assertEqual(worker.apply_worker_environment(env), root.resolve())
            self.assertEqual(env["CREDENTIALS_DIRECTORY"], "/run/worker-own")
            self.assertNotIn("HTTPS_PROXY", env)
            self.assertEqual(env["HTTP_PROXY"], "")
            self.assertEqual(worker.revision, value.revision)
            self.assertNotIn("synthetic", repr(worker))
            path.chmod(0o644)
            with self.assertRaises(ConfigurationError):
                ConfigurationSnapshot.read_worker(path, credentials_directory=None, owner=os.getuid())

    def test_cos_copy_requires_same_bytes_and_private_distinct_service_credential(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            web, worker = root / "web-credentials", root / "worker-credentials"
            web.mkdir(); worker.mkdir()
            credential = web / "cos-credentials.json"
            credential.write_text(json.dumps({"COS_SECRET_ID": "fixture-id", "COS_SECRET_KEY": "fixture-key"}))
            credential.chmod(0o600)
            env = {"VANTALINE_DATA_STORE": "postgres", "DATABASE_URL": "fixture", "VANTALINE_FILE_STORE": "cos",
                "VANTALINE_DATA_ROOT": str(root), "VANTALINE_ARTIFACT_WORK_ROOT": str(root / "work"),
                "VANTALINE_ARTIFACT_CACHE_ROOT": str(root / "cache"), "VANTALINE_COS_BUCKET": "fixture-123",
                "CREDENTIALS_DIRECTORY": str(web)}
            value = ConfigurationSnapshot.capture(env, root)
            path = root / "config.json"
            path.write_text(json.dumps(value.export()["configuration"]))
            path.chmod(0o640)
            copy = worker / "cos-credentials.json"
            copy.write_bytes(credential.read_bytes()); copy.chmod(0o600)
            loaded = ConfigurationSnapshot.read_worker(path, credentials_directory=worker, owner=os.getuid())
            self.assertEqual(loaded.revision, value.revision)
            env["CREDENTIALS_DIRECTORY"] = str(worker)
            loaded.apply_worker_environment(env)
            self.assertEqual(env["CREDENTIALS_DIRECTORY"], str(worker))
            copy.write_text('{"COS_SECRET_ID":"different","COS_SECRET_KEY":"different"}')
            with self.assertRaises(ConfigurationError):
                ConfigurationSnapshot.read_worker(path, credentials_directory=worker, owner=os.getuid())

    def test_capture_preserves_storage_reader_credential_compatibility(self):
        from local_inspection_service.storage.artifacts.runtime import build_runtime
        import base64
        for extra in ({"COS_SESSION_TOKEN": None}, {"metadata": {"owner": "synthetic"}}):
            with self.subTest(extra=extra), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                data, credentials = root / "data", root / "credentials"
                data.mkdir(); credentials.mkdir()
                raw = json.dumps({"COS_SECRET_ID": "fixture", "COS_SECRET_KEY": "fixture", **extra}).encode()
                path = credentials / "cos-credentials.json"
                path.write_bytes(raw); path.chmod(0o600)
                # Real pre-bridge reader; SDK construction and database connection
                # are lazy and never invoked by this local configuration test.
                runtime = build_runtime("cos", data, root / "work", root / "cache",
                    "fixture-123", "synthetic", credentials)
                self.assertEqual(runtime.mode, "cos")
                snapshot = ConfigurationSnapshot.capture({"VANTALINE_DATA_STORE": "postgres",
                    "DATABASE_URL": "synthetic", "VANTALINE_FILE_STORE": "cos",
                    "VANTALINE_DATA_ROOT": str(data), "VANTALINE_ARTIFACT_WORK_ROOT": str(root / "work"),
                    "VANTALINE_ARTIFACT_CACHE_ROOT": str(root / "cache"), "VANTALINE_COS_BUCKET": "fixture-123",
                    "CREDENTIALS_DIRECTORY": str(credentials)}, data)
                self.assertEqual(base64.b64decode(snapshot.export()["credential"]), raw)
                config = root / "config.json"
                config.write_bytes(snapshot._payload); config.chmod(0o640)
                loaded = ConfigurationSnapshot.read_worker(config, credentials_directory=credentials, owner=os.getuid())
                self.assertEqual(loaded.export(), snapshot.export())

    def test_symlink_and_oversized_private_input_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "target"
            target.write_text("x" * (256 * 1024 + 1)); target.chmod(0o600)
            link = root / "link"; link.symlink_to(target)
            for path in (target, link):
                with self.assertRaises(ConfigurationError):
                    ConfigurationSnapshot.read_worker(path, credentials_directory=None, owner=os.getuid())


if __name__ == "__main__":
    unittest.main()
