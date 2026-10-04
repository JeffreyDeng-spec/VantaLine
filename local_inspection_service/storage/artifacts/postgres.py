"""Append-only file locations on explicit, independently owned connections."""
from __future__ import annotations
from contextlib import contextmanager
from typing import Callable, Any

from .types import Artifact, ArtifactConflict, logical_path


class PostgresLocations:
    def __init__(self, connect: Callable[[], Any]):
        # The storage composition supplies a new connection for every operation.
        # Never borrow a caller's business transaction or share across threads.
        self.connect = connect

    @contextmanager
    def transaction(self):
        conn = self.connect()
        try:
            with conn.cursor() as cursor:
                yield cursor
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def decode(row):
        return Artifact(row[0], int(row[1]), row[2], int(row[3]), row[4], int(row[5])) if row else None

    def get(self, path: str, *, generation: int | None = None) -> Artifact | None:
        path = logical_path(path)
        with self.transaction() as cursor:
            if generation is None:
                cursor.execute("SELECT logical_path,generation,sha256,size_bytes,state,mtime_ns "
                               "FROM vantaline.artifact_locations WHERE logical_path=%s "
                               "ORDER BY generation DESC LIMIT 1", (path,))
            else:
                cursor.execute("SELECT logical_path,generation,sha256,size_bytes,state,mtime_ns "
                               "FROM vantaline.artifact_locations WHERE logical_path=%s AND generation=%s",
                               (path, generation))
            return self.decode(cursor.fetchone())

    def list(self, prefix: str) -> list[Artifact]:
        prefix = logical_path(prefix).rstrip("/") + "/"
        with self.transaction() as cursor:
            # Literal prefix: '%' and '_' in user paths are not SQL wildcards.
            cursor.execute("SELECT logical_path,generation,sha256,size_bytes,state,mtime_ns FROM ("
                           "SELECT DISTINCT ON (logical_path) logical_path,generation,sha256,size_bytes,state,mtime_ns "
                           "FROM vantaline.artifact_locations WHERE left(logical_path,%s)=%s "
                           "ORDER BY logical_path,generation DESC) latest "
                           "WHERE state='ready' ORDER BY logical_path", (len(prefix), prefix))
            return [self.decode(row) for row in cursor.fetchall()]

    def publish(self, artifact: Artifact, *, expected_generation: int) -> Artifact:
        if artifact.generation != expected_generation + 1:
            raise ValueError("generation must advance exactly once")
        with self.transaction() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 7913383))", (artifact.path,))
            cursor.execute("SELECT coalesce(max(generation),0) FROM vantaline.artifact_locations "
                           "WHERE logical_path=%s", (artifact.path,))
            if int(cursor.fetchone()[0]) != expected_generation:
                raise ArtifactConflict("file changed concurrently")
            cursor.execute("INSERT INTO vantaline.artifact_locations "
                           "(logical_path,generation,object_key,sha256,size_bytes,state,created_at,mtime_ns) "
                           "VALUES (%s,%s,%s,%s,%s,%s,extract(epoch FROM clock_timestamp())::bigint,"
                           "coalesce(nullif(%s,0),(extract(epoch FROM clock_timestamp())*1000000000)::bigint)) "
                           "RETURNING logical_path,generation,sha256,size_bytes,state,mtime_ns",
                           (artifact.path, artifact.generation, artifact.key, artifact.sha256,
                            artifact.size, artifact.state, artifact.mtime_ns))
            published = self.decode(cursor.fetchone())
        return published
