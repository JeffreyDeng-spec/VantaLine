#!/usr/bin/env python3
"""Real PostgreSQL CAS tests in an explicitly named disposable test database."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import os
from pathlib import Path
import sys
import threading
import unittest

import psycopg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from local_inspection_service.storage.artifacts.postgres import PostgresLocations
from local_inspection_service.storage.artifacts.types import Artifact, ArtifactConflict

DSN = os.environ["ARTIFACT_TEST_DATABASE_URL"]


class PostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with psycopg.connect(DSN) as conn:
            name = conn.execute("SELECT current_database()").fetchone()[0]
            if name != "vantaline_cos_storage_test":
                raise RuntimeError("refusing any database other than vantaline_cos_storage_test")
            conn.execute("CREATE SCHEMA IF NOT EXISTS vantaline")
            conn.execute("CREATE TABLE IF NOT EXISTS vantaline.feature_migrations "
                         "(version TEXT PRIMARY KEY,applied_at BIGINT,metadata_json JSONB)")
        migration = (ROOT / "local_inspection_service/storage/migrations/2026_10_04_artifact_locations.sql").read_text()
        with psycopg.connect(DSN, autocommit=True) as conn:
            conn.execute(migration)
            conn.execute(migration)
            index = (ROOT / "local_inspection_service/storage/migrations/2026_10_10_artifact_prefix_index.sql").read_text()
            conn.execute(index)
            conn.execute(index)

    def setUp(self):
        with psycopg.connect(DSN) as conn:
            conn.execute("TRUNCATE vantaline.artifact_locations")
        self.repo = PostgresLocations(lambda: psycopg.connect(DSN))

    @staticmethod
    def row(path="outputs/item.png", generation=1, data=b"fixture", state="ready"):
        return Artifact(path, generation, hashlib.sha256(data).hexdigest(), len(data), state)

    def test_versions_survive_replacement_and_tombstone(self):
        first = self.repo.publish(self.row(), expected_generation=0)
        second = self.repo.publish(self.row(generation=2, data=b"new"), expected_generation=1)
        self.assertEqual(self.repo.get(first.path), second)
        self.assertEqual(self.repo.get(first.path, generation=1), first)
        self.repo.publish(self.row(generation=3, data=b"new", state="deleted"), expected_generation=2)
        self.assertEqual(self.repo.list("outputs"), [])
        self.assertEqual(self.repo.get(first.path, generation=1), first)

    def test_concurrent_cas_has_one_winner(self):
        barrier = threading.Barrier(2)
        def writer(contents):
            barrier.wait(timeout=10)
            try:
                return self.repo.publish(self.row(data=contents), expected_generation=0)
            except ArtifactConflict:
                return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(writer, [b"one", b"two"]))
        self.assertEqual(sum(r is not None for r in outcomes), 1)
        with psycopg.connect(DSN) as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM vantaline.artifact_locations").fetchone()[0], 1)

    def test_list_prefix_is_literal_and_owner_directories_are_distinct(self):
        paths = ["outputs/users/a_/a.png", "outputs/users/ab/b.png", "outputs/users/a%/c.png"]
        for path in paths:
            self.repo.publish(self.row(path), expected_generation=0)
        self.assertEqual([r.path for r in self.repo.list("outputs/users/a_")], [paths[0]])
        self.assertEqual([r.path for r in self.repo.list("outputs/users/a%")], [paths[2]])

    def test_directory_projection_matches_latest_ready_descendants(self):
        paths = ["outputs/users/a_/file.png", "outputs/users/a%/deep/file.png",
                 "outputs/users/中文/file.png", "outputs/users/flat.png",
                 "outputs/users/deleted/file.png", "outputs/users/retained/one.png",
                 "outputs/users/retained/two.png", "outputs/users2/foreign/file.png"]
        for path in paths:
            self.repo.publish(self.row(path), expected_generation=0)
        for path in [paths[4], paths[5]]:
            self.repo.publish(self.row(path, generation=2, state="deleted"), expected_generation=1)
        for prefix in ["outputs/users", "outputs/users/a_", "outputs/users/a%", "outputs/users/retained"]:
            base = prefix + "/"
            with psycopg.connect(DSN) as connection:
                old = connection.execute(
                    "SELECT logical_path,generation,sha256,size_bytes,state,mtime_ns FROM ("
                    "SELECT DISTINCT ON (logical_path) logical_path,generation,sha256,size_bytes,state,mtime_ns "
                    "FROM vantaline.artifact_locations WHERE left(logical_path,%s)=%s "
                    "ORDER BY logical_path,generation DESC) latest WHERE state='ready' ORDER BY logical_path",
                    (len(base), base)).fetchall()
            self.assertEqual(self.repo.list(prefix), [self.repo.decode(row) for row in old])
            expected = sorted({r[0][len(base):].split("/", 1)[0]
                               for r in old if "/" in r[0][len(base):]})
            self.assertEqual(sorted(self.repo.directories(prefix)), expected)
        self.assertEqual(set(self.repo.directories("outputs/users")), {"a_", "a%", "中文", "retained"})

    def test_directory_projection_rejects_invalid_child_name(self):
        row = self.row()
        with psycopg.connect(DSN) as connection:
            connection.execute(
                "INSERT INTO vantaline.artifact_locations "
                "(logical_path,generation,object_key,sha256,size_bytes,state,created_at) "
                "VALUES (%s,1,%s,%s,1,'ready',1)",
                ("outputs/users/../invalid.png", row.key, row.sha256))
        with self.assertRaises(ValueError):
            self.repo.directories("outputs/users")
        self.assertEqual(self.repo.directories("outputs/other"), [])

    def test_conflict_rolls_back_and_next_operation_works(self):
        first = self.repo.publish(self.row(), expected_generation=0)
        with self.assertRaises(ArtifactConflict):
            self.repo.publish(self.row(data=b"wrong"), expected_generation=0)
        self.assertEqual(self.repo.get(first.path), first)
        self.repo.publish(self.row(generation=2), expected_generation=1)

    def test_key_hash_constraint(self):
        row = self.row()
        with self.assertRaises(psycopg.errors.CheckViolation), psycopg.connect(DSN) as conn:
            conn.execute("INSERT INTO vantaline.artifact_locations VALUES (%s,1,'wrong',%s,1,'ready',1)",
                         (row.path, row.sha256))


if __name__ == "__main__":
    unittest.main()
