"""Object publication precedes logical availability; no global filesystem hooks."""
from contextlib import contextmanager
import os
import hashlib
from pathlib import Path

from .types import Artifact, ArtifactConflict, ArtifactIntegrityError, checksum_file, logical_path
from .disk import DiskCapacityError, directory


class ArtifactStore:
    def __init__(self, locations, objects, cache, budget, staging: Path):
        self.locations, self.objects, self.cache = locations, objects, cache
        self.budget, self.staging = budget, staging
        directory(staging)

    def stat(self, path: str) -> Artifact:
        row = self.locations.get(logical_path(path))
        if row is None or row.state != "ready":
            raise FileNotFoundError("business file not found")
        return row

    def list(self, prefix: str):
        return self.locations.list(logical_path(prefix))

    def put_bytes(self, path: str, data: bytes, *, expected_generation: int) -> Artifact:
        path = logical_path(path)
        before = self.locations.get(path)
        if (before.generation if before else 0) != expected_generation:
            raise ArtifactConflict("file changed concurrently")
        with self.budget.workspace("upload", len(data)) as workspace:
            temporary = workspace / "payload"
            try:
                fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                with os.fdopen(fd, "wb") as out:
                    out.write(data)
                    out.flush()
                    os.fsync(out.fileno())
                row = Artifact(path, expected_generation + 1, hashlib.sha256(data).hexdigest(), len(data))
                self.objects.put(row, temporary)
                return self.locations.publish(row, expected_generation=expected_generation)
            finally:
                temporary.unlink(missing_ok=True)

    def put(self, path: str, source: Path, *, expected_generation: int) -> Artifact:
        path = logical_path(path)
        before = self.locations.get(path)
        if (before.generation if before else 0) != expected_generation:
            raise ArtifactConflict("file changed concurrently")
        if source.is_symlink() or not source.is_file():
            raise ValueError("upload source must be a regular file")
        size = source.stat().st_size
        with self.budget.workspace("upload", size) as workspace:
            # Own immutable snapshot: a producer may continue changing its source.
            temporary = workspace / "payload"
            try:
                fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                with os.fdopen(fd, "wb") as out, source.open("rb") as stream:
                    copied = 0
                    while block := stream.read(1024 * 1024):
                        copied += len(block)
                        if copied > size:
                            raise ArtifactIntegrityError("upload source changed size")
                        out.write(block)
                    out.flush()
                    os.fsync(out.fileno())
                sha, actual_size = checksum_file(temporary)
                if actual_size != size or checksum_file(source) != (sha, size):
                    raise ArtifactIntegrityError("upload source changed during snapshot")
                artifact = Artifact(path, expected_generation + 1, sha, size)
                self.objects.put(artifact, temporary)
                # No automatic retry of a conflicting logical write. Uploaded bytes
                # are immutable and remain recoverable if this transaction fails.
                return self.locations.publish(artifact, expected_generation=expected_generation)
            finally:
                temporary.unlink(missing_ok=True)

    @contextmanager
    def read(self, path: str):
        artifact = self.stat(path)
        with self.cache.open(artifact) as cached:
            with cached.open("rb") as stream:
                yield stream

    def read_bytes(self, path: str, *, max_bytes: int) -> bytes:
        artifact = self.stat(path)
        if artifact.size > max_bytes:
            raise DiskCapacityError("file exceeds operation size limit")
        with self.cache.open(artifact) as cached:
            return cached.read_bytes()

    @contextmanager
    def materialize(self, prefix: str, *, extra_bytes: int = 0):
        """Original filenames in a bounded single-job workspace, released on exit."""
        prefix = logical_path(prefix)
        try:
            rows = [self.stat(prefix)]
        except FileNotFoundError:
            rows = self.list(prefix)
        if not rows:
            raise FileNotFoundError("business file or directory not found")
        required = sum(r.size for r in rows) + extra_bytes
        if extra_bytes < 0:
            raise ValueError("negative workspace allowance")
        with self.budget.workspace("work", max(1, required)) as workspace:
            for row in rows:
                relative = Path(row.path).relative_to(Path(prefix).parent)
                target = workspace / relative
                directory(target.parent)
                # Direct download avoids a second full data-set copy in read cache.
                self.objects.download(row, target)
            yield workspace / Path(prefix).name

    def remove(self, path: str, *, expected_generation: int) -> None:
        row = self.stat(path)
        deleted = Artifact(row.path, expected_generation + 1, row.sha256, row.size, "deleted")
        self.locations.publish(deleted, expected_generation=expected_generation)
