#!/usr/bin/env python3
"""Failure-oriented file storage contracts; synthetic data, no cloud calls."""
from contextlib import contextmanager
import hashlib
import io
import multiprocessing
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local_inspection_service.storage.artifacts.types import (
    Artifact, ArtifactConflict, ArtifactIntegrityError, ArtifactUnavailable, logical_path,
)
from local_inspection_service.storage.artifacts.disk import DiskBudget, DiskCapacityError, ReadCache
from local_inspection_service.storage.artifacts.cos import CosObjects
from local_inspection_service.storage.artifacts.store import ArtifactStore


class Locations:
    def __init__(self):
        self.rows = {}
        self.fail = False

    def get(self, path):
        return self.rows.get(path)

    def list(self, prefix):
        return [v for k, v in sorted(self.rows.items()) if k.startswith(prefix + "/") and v.state == "ready"]

    def publish(self, row, *, expected_generation):
        if self.fail:
            raise RuntimeError("database unavailable")
        previous = self.rows.get(row.path)
        if (previous.generation if previous else 0) != expected_generation:
            raise ArtifactConflict("concurrent writer won")
        self.rows[row.path] = row
        return row


class Missing(Exception):
    def get_status_code(self):
        return 404


class Body:
    def __init__(self, data):
        self.data = data

    def get_raw_stream(self):
        return io.BytesIO(self.data)


class Client:
    def __init__(self):
        self.rows, self.calls = {}, []
        self.fail, self.corrupt = False, False

    def head_object(self, **kwargs):
        if self.fail:
            raise RuntimeError("signed-secret-must-never-escape")
        if kwargs["Key"] not in self.rows:
            raise Missing()

    def upload_file(self, **kwargs):
        self.calls.append(kwargs)
        self.rows[kwargs["Key"]] = Path(kwargs["LocalFilePath"]).read_bytes()

    def get_object(self, **kwargs):
        if self.fail:
            raise RuntimeError("signed-secret-must-never-escape")
        data = self.rows[kwargs["Key"]]
        return {"Body": Body(data + b"corrupt" if self.corrupt else data)}


def reserve_in_child(root, ready, stop, crash):
    budget = DiskBudget(Path(root), limits={"cache": 100, "work": 100, "upload": 100},
                        reserve_bytes=0, free_bytes=lambda: 10000)
    with budget.reserve("work", 30):
        ready.set()
        stop.wait(10)
        if crash:
            os._exit(7)


def scratch_in_child(root, ready):
    budget = DiskBudget(Path(root), limits={"cache": 100, "work": 100, "upload": 100},
                        reserve_bytes=0, free_bytes=lambda: 10000)
    with budget.workspace("upload", 50) as path:
        (path / "interrupted").write_bytes(b"private synthetic partial")
        ready.set()
        os._exit(7)


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.budget = DiskBudget(self.root / "control", limits={"cache": 100, "work": 100, "upload": 100},
                                 reserve_bytes=0, free_bytes=lambda: 10000)
        self.client, self.locations = Client(), Locations()
        self.objects = CosObjects(self.client, "synthetic-bucket")
        self.cache = ReadCache(self.root / "cache", self.budget, self.objects)
        self.store = ArtifactStore(self.locations, self.objects, self.cache, self.budget, self.root / "stage")

    def tearDown(self):
        self.temp.cleanup()

    def put(self, path="outputs/users/a/image.png", contents=b"image", expected=0):
        source = self.root / "source"
        source.write_bytes(contents)
        return self.store.put(path, source, expected_generation=expected)

    def test_roundtrip_dedup_and_legacy_path(self):
        one = self.put()
        two = self.put("uploads/second.png")
        self.assertEqual(one.key, two.key)
        self.assertEqual(len(self.client.calls), 1)
        self.assertEqual(self.client.calls[0]["StorageClass"], "STANDARD")
        self.assertEqual(self.store.read_bytes(one.path, max_bytes=20), b"image")

    def test_upload_failure_cannot_publish(self):
        self.client.fail = True
        with self.assertRaisesRegex(ArtifactUnavailable, "COS upload unavailable") as raised:
            self.put()
        self.assertNotIn("signed-secret", str(raised.exception))
        self.assertFalse(self.locations.rows)
        self.assertEqual((self.root / "source").read_bytes(), b"image")
        self.assertFalse(list((self.root / "stage").iterdir()))

    def test_dead_writer_scratch_and_cache_partials_are_reclaimed(self):
        ctx = multiprocessing.get_context("fork")
        ready = ctx.Event()
        child = ctx.Process(target=scratch_in_child, args=(str(self.budget.root), ready))
        child.start()
        self.assertTrue(ready.wait(10))
        child.join(10)
        self.assertEqual(child.exitcode, 7)
        self.assertTrue(list((self.budget.root / "scratch").iterdir()))
        with self.budget.reserve("upload", 100):
            self.assertFalse(list((self.budget.root / "scratch").iterdir()))
        (self.cache.root / "interrupted.part").write_bytes(b"partial")
        row = self.put()
        self.store.read_bytes(row.path, max_bytes=100)
        self.assertFalse((self.cache.root / "interrupted.part").exists())

    def test_import_receipt_binding_remote_corruption_and_no_overwrite(self):
        import json
        from cos_migrate import inventory, transfer
        from import_cos_locations import load_pair, import_rows
        source = self.root / "source-tree"
        (source / "outputs").mkdir(parents=True)
        (source / "outputs/item.png").write_bytes(b"source")
        manifest, receipt = self.root / "manifest.jsonl", self.root / "receipt.jsonl"
        inventory(source, ["outputs"], manifest)
        transfer(self.client, "synthetic-bucket", "objects", manifest, receipt, upload=True)
        rows = load_pair(manifest, receipt, "synthetic-bucket")
        self.client.corrupt = True
        with self.assertRaises(ArtifactIntegrityError):
            import_rows(self.store, rows, apply=True)
        self.assertFalse(self.locations.rows)
        self.client.corrupt = False
        result = import_rows(self.store, rows, apply=True)
        self.assertEqual(result["published"], 1)
        self.assertEqual(import_rows(self.store, rows, apply=True)["already_indexed"], 1)
        self.put("outputs/item.png", b"new", expected=1)
        with self.assertRaises(ArtifactConflict):
            import_rows(self.store, rows, apply=True)
        records = [json.loads(line) for line in receipt.read_text().splitlines()]
        records[-1]["verified_files"] = 10
        receipt.write_text("\n".join(json.dumps(r) for r in records))
        with self.assertRaises(ValueError):
            load_pair(manifest, receipt, "synthetic-bucket")

    def test_readback_corruption_cannot_publish(self):
        self.client.corrupt = True
        with self.assertRaises(ArtifactIntegrityError):
            self.put()
        self.assertFalse(self.locations.rows)
        self.assertEqual(len(self.client.rows), 1)

    def test_database_failure_preserves_source_and_remote_object(self):
        self.locations.fail = True
        with self.assertRaisesRegex(RuntimeError, "database"):
            self.put()
        self.assertFalse(self.locations.rows)
        self.assertEqual(len(self.client.rows), 1)
        self.assertTrue((self.root / "source").exists())

    def test_expected_generation_conflict_and_tombstone(self):
        first = self.put()
        with self.assertRaises(ArtifactConflict):
            self.put(contents=b"other")
        second = self.put(contents=b"other", expected=1)
        self.assertEqual(second.generation, 2)
        self.store.remove(second.path, expected_generation=2)
        self.assertEqual(self.locations.get(second.path).generation, 3)
        with self.assertRaises(FileNotFoundError):
            self.store.stat(second.path)
        self.assertIn(first.key, self.client.rows)
        self.assertIn(second.key, self.client.rows)

    def test_paths_reject_escape_and_secrets(self):
        for path in ["/outputs/a", "outputs/../auth.json", "outputs//a", "uploads\\a",
                     "auth.json", "outputs/.private", "uploads/runtime.env", "uploads/config.json"]:
            with self.subTest(path=path), self.assertRaises(ValueError):
                logical_path(path)

    def test_verified_cached_reads_survive_cos_outage(self):
        row = self.put()
        self.store.read_bytes(row.path, max_bytes=100)
        self.client.fail = True
        self.assertEqual(self.store.read_bytes(row.path, max_bytes=100), b"image")
        blob = self.root / "cache" / (row.sha256 + ".blob")
        blob.chmod(0o660)  # simulate out-of-band corruption of an immutable cache
        blob.write_bytes(b"wrong")
        with self.assertRaises(ArtifactIntegrityError):
            self.store.read_bytes(row.path, max_bytes=100)

    def test_pinned_cache_cannot_be_evicted(self):
        first = self.put(contents=b"a" * 70)
        second = self.put("uploads/b.png", b"b" * 70)
        with self.store.read(first.path) as stream:
            with self.assertRaises(DiskCapacityError):
                self.store.read_bytes(second.path, max_bytes=100)
            self.assertEqual(stream.read(), b"a" * 70)
        self.assertEqual(self.store.read_bytes(second.path, max_bytes=100), b"b" * 70)
        self.assertLessEqual(sum(p.stat().st_size for p in (self.root / "cache").glob("*.blob")), 100)

    def test_reservation_and_free_disk_failure_precede_network(self):
        with self.assertRaises(DiskCapacityError):
            self.put(contents=b"a" * 101)
        self.budget.free_bytes = lambda: 3
        with self.assertRaises(DiskCapacityError):
            self.put()
        self.assertFalse(self.client.calls)

    def test_directory_materialization_and_cleanup(self):
        self.put("outputs/task/images/a.png", b"a")
        self.put("outputs/task/labels/a.txt", b"label")
        with self.store.materialize("outputs/task", extra_bytes=20) as path:
            self.assertEqual((path / "images/a.png").read_bytes(), b"a")
            self.assertEqual((path / "labels/a.txt").read_bytes(), b"label")
            with self.assertRaises(DiskCapacityError):
                with self.store.materialize("outputs/task"):
                    self.fail("second training preparation admitted")
        self.assertFalse(path.exists())
        self.assertFalse(list((self.root / "control/reservations").iterdir()))

    def test_download_corruption_leaves_no_file(self):
        row = self.put()
        self.client.corrupt = True
        target = self.root / "download"
        with self.assertRaises(ArtifactIntegrityError):
            self.objects.download(row, target)
        self.assertFalse(target.exists())

    def test_cross_process_admission_and_crash_release(self):
        context = multiprocessing.get_context("fork")
        ready, stop = context.Event(), context.Event()
        process = context.Process(target=reserve_in_child, args=(str(self.budget.root), ready, stop, True))
        process.start()
        try:
            self.assertTrue(ready.wait(10))
            with self.assertRaises(DiskCapacityError):
                with self.budget.reserve("work", 1):
                    self.fail("second process admitted")
        finally:
            stop.set()
            process.join(10)
            if process.is_alive():
                process.kill()
                process.join()
        self.assertEqual(process.exitcode, 7)
        with self.budget.reserve("work", 100):
            pass


if __name__ == "__main__":
    unittest.main()
