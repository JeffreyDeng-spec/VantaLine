#!/usr/bin/env python3
"""Offline integrity/failure contracts; no cloud access or customer data."""
import io
import json
from pathlib import Path
import tempfile
import unittest

from cos_migrate import inventory, load_manifest, object_key, transfer


class Missing(Exception):
    def get_status_code(self):
        return 404


class Body:
    def __init__(self, data):
        self.data = data

    def get_raw_stream(self):
        return io.BytesIO(self.data)


class FakeCOS:
    def __init__(self):
        self.objects = {}
        self.uploads = 0
        self.after_upload = lambda: None

    def head_object(self, *, Bucket, Key):
        if Key not in self.objects:
            raise Missing()
        return {"Content-Length": str(len(self.objects[Key]))}

    def upload_file(self, *, Key, LocalFilePath, **kwargs):
        assert kwargs["StorageClass"] == "STANDARD"
        assert kwargs["EnableMD5"] is True
        self.objects[Key] = Path(LocalFilePath).read_bytes()
        self.uploads += 1
        self.after_upload()

    def get_object(self, *, Bucket, Key):
        return {"Body": Body(self.objects[Key])}


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "data"
        (self.root / "outputs").mkdir(parents=True)
        (self.root / "outputs" / "a.png").write_bytes(b"image-evidence")
        self.manifest = self.base / "manifest.jsonl"
        self.client = FakeCOS()

    def scan(self):
        return inventory(self.root, ["outputs"], self.manifest)

    def run_transfer(self, name="receipt.jsonl", upload=True):
        return transfer(self.client, "synthetic-bucket", "objects", self.manifest,
                        self.base / name, upload=upload)

    def test_resume_deduplicates_and_verifies_without_deletion(self):
        (self.root / "outputs" / "duplicate.png").write_bytes(b"image-evidence")
        self.scan()
        self.assertEqual(self.run_transfer()["verified_files"], 2)
        self.assertEqual(self.client.uploads, 1)
        self.run_transfer("resumed.jsonl")
        self.assertEqual(self.client.uploads, 1)
        self.assertTrue((self.root / "outputs" / "a.png").is_file())
        self.run_transfer("verified.jsonl", upload=False)

    def test_secret_and_symlink_exclusions_are_recorded(self):
        (self.root / "outputs" / "runtime_secrets.local.env").write_text("synthetic")
        (self.root / "outputs" / "outside").symlink_to(self.base)
        result = self.scan()
        self.assertEqual(result["excluded"], 2)
        _, files = load_manifest(self.manifest)
        self.assertEqual(len(files), 1)
        self.assertEqual(self.manifest.stat().st_mode & 0o777, 0o600)

    def test_same_length_remote_corruption_fails_without_overwrite(self):
        self.scan()
        _, files = load_manifest(self.manifest)
        key = object_key("objects", files[0])
        self.client.objects[key] = b"x" * files[0]["size"]
        with self.assertRaisesRegex(ValueError, "verification failed"):
            self.run_transfer()
        self.assertEqual(self.client.uploads, 0)
        self.assertNotIn('"type": "complete"', (self.base / "receipt.jsonl").read_text())

    def test_change_before_upload_fails(self):
        self.scan()
        (self.root / "outputs" / "a.png").write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "differs from inventory"):
            self.run_transfer()
        self.assertEqual(self.client.uploads, 0)

    def test_change_during_upload_fails(self):
        self.scan()
        self.client.after_upload = lambda: (self.root / "outputs" / "a.png").write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "changed during upload"):
            self.run_transfer()

    def test_truncated_manifest_and_invalid_totals_fail(self):
        self.scan()
        lines = self.manifest.read_text().splitlines()
        self.manifest.write_text("\n".join(lines[:-1]) + "\n")
        with self.assertRaisesRegex(ValueError, "incomplete"):
            load_manifest(self.manifest)
        footer = json.loads(lines[-1])
        footer["bytes"] += 1
        self.manifest.write_text("\n".join(lines[:-1] + [json.dumps(footer)]) + "\n")
        with self.assertRaisesRegex(ValueError, "totals"):
            load_manifest(self.manifest)

    def test_scan_refuses_overlap_escape_and_overwrite(self):
        for includes in (["../outside"], ["outputs", "outputs/a.png"]):
            with self.assertRaises(ValueError):
                inventory(self.root, includes, self.manifest)
        with self.assertRaises(ValueError):
            inventory(self.root, ["outputs"], self.root / "manifest.jsonl")
        self.scan()
        with self.assertRaises(FileExistsError):
            self.scan()


if __name__ == "__main__":
    unittest.main()
