#!/usr/bin/env python3
"""Offline integrity/failure contracts; no cloud access or customer data."""
import io
import json
from pathlib import Path
import tempfile
import unittest

from cos_migrate import inventory, load_manifest, object_key, transfer, restore


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

    def test_restore_works_without_original_disk_and_refuses_existing_target(self):
        self.scan()
        self.run_transfer()
        self.root.rename(self.base / "unmounted-disk")
        target = self.base / "restored"
        result = restore(self.client, "synthetic-bucket", "objects", self.manifest, target)
        self.assertEqual(result["restored_files"], 1)
        self.assertEqual((target / "outputs/a.png").read_bytes(), b"image-evidence")
        self.assertEqual(target.stat().st_mode & 0o777, 0o700)
        self.assertEqual((target / "outputs/a.png").stat().st_mode & 0o777, 0o600)
        with self.assertRaises(FileExistsError):
            restore(self.client, "synthetic-bucket", "objects", self.manifest, target)

    def test_restore_corruption_never_publishes_file(self):
        self.scan()
        self.run_transfer()
        _, files = load_manifest(self.manifest)
        self.client.objects[object_key("objects", files[0])] = b"x" * files[0]["size"]
        target = self.base / "corrupt-restore"
        with self.assertRaisesRegex(ValueError, "verification failed"):
            restore(self.client, "synthetic-bucket", "objects", self.manifest, target)
        self.assertEqual(list(target.rglob("*.*")), [])

    def test_restore_subset_missing_selection_and_space_gate(self):
        from unittest.mock import patch
        (self.root / "outputs/second.png").write_bytes(b"second")
        self.scan()
        self.run_transfer()
        target = self.base / "subset"
        result = restore(self.client, "synthetic-bucket", "objects", self.manifest,
                         target, ["outputs/second.png"])
        self.assertEqual(result["restored_files"], 1)
        self.assertFalse((target / "outputs/a.png").exists())
        with self.assertRaisesRegex(ValueError, "no files"):
            restore(self.client, "synthetic-bucket", "objects", self.manifest,
                    self.base / "missing", ["outputs/missing.png"])
        with patch("cos_migrate.shutil.disk_usage") as usage:
            usage.return_value.free = 0
            with self.assertRaisesRegex(ValueError, "insufficient"):
                restore(self.client, "synthetic-bucket", "objects", self.manifest,
                        self.base / "full")
        self.assertFalse((self.base / "full").exists())

    def test_manifest_cannot_select_file_outside_declared_subtrees(self):
        self.scan()
        rows = [json.loads(line) for line in self.manifest.read_text().splitlines()]
        rows[1]["path"] = "unselected/a.png"
        self.manifest.write_text("".join(json.dumps(row) + "\n" for row in rows))
        with self.assertRaisesRegex(ValueError, "outside selected"):
            load_manifest(self.manifest)

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
