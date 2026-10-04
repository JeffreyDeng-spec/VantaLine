"""Process-shared reservations and pinned, verified read cache (Unix hosts)."""
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import shutil
import uuid

from .types import Artifact, ArtifactIntegrityError, ArtifactUnavailable, DiskCapacityError, checksum_file

GiB = 1024 ** 3


def shared_open(path: Path, flags: int):
    fd = os.open(path, flags | os.O_NOFOLLOW, 0o660)
    if os.fstat(fd).st_uid == os.geteuid():
        os.fchmod(fd, 0o660)
    return fd


def directory(path: Path):
    if not path.parent.exists():
        directory(path.parent)
    try:
        path.mkdir(mode=0o2770)
    except FileExistsError:
        pass
    else:
        path.chmod(0o2770)
    if path.is_symlink():
        raise ValueError("storage control directory must not be a symlink")


class DiskBudget:
    def __init__(self, root: Path, *, limits=None, reserve_bytes: int = 8 * GiB,
                 free_bytes=None, scratch_roots=None, preallocated=False):
        self.root = root
        self.limits = dict(limits if limits is not None else {"cache": 6*GiB, "work": 12*GiB, "upload": 2*GiB})
        if reserve_bytes < 0 or any(type(x) is not int or x <= 0 for x in self.limits.values()):
            raise ValueError("invalid disk limits")
        self.reserve_bytes = reserve_bytes
        self.free_bytes = free_bytes or (lambda: shutil.disk_usage(self.root).free)
        self.preallocated = preallocated
        self.scratch_roots = dict(scratch_roots or {key: root / "scratch" for key in self.limits})
        if set(self.scratch_roots) != set(self.limits):
            raise ValueError("scratch roots must cover every storage class")
        directory(root)
        directory(root / "reservations")
        for path in self.scratch_roots.values():
            directory(path)

    @contextmanager
    def locked(self):
        fd = shared_open(self.root / "budget.lock", os.O_CREAT | os.O_RDWR)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            os.close(fd)

    def _live(self):
        totals = {key: 0 for key in self.limits}
        for path in (self.root / "reservations").glob("*.json"):
            fd = shared_open(path, os.O_RDWR)
            try:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    row = json.loads(os.read(fd, 4096))
                    totals[row["kind"]] += row["bytes"]
                else:
                    # Kernel releases a dead process's flock; no PID/TTL guessing.
                    os.lseek(fd, 0, os.SEEK_SET)
                    row = json.loads(os.read(fd, 4096))
                    scratch = self.scratch_roots[row["kind"]] / path.stem
                    if scratch.exists():
                        try:
                            shutil.rmtree(scratch)
                        except PermissionError:
                            # Another service's private native authentication
                            # subtree is reclaimed when that service restarts.
                            # Retain its reservation; never pretend space is free.
                            totals[row["kind"]] += row["bytes"]
                            continue
                    path.unlink()
            finally:
                os.close(fd)
        return totals

    @contextmanager
    def reserve(self, kind: str, size: int):
        if kind not in self.limits or type(size) is not int or size < 0:
            raise ValueError("invalid reservation")
        fd, path = None, self.root / "reservations" / (uuid.uuid4().hex + ".json")
        with self.locked():
            live = self._live()
            pending = 0 if self.preallocated else sum(live.values()) + size
            if live[kind] + size > self.limits[kind] or self.free_bytes() - pending < self.reserve_bytes:
                raise DiskCapacityError("temporary storage capacity unavailable")
            if self.preallocated and shutil.disk_usage(self.scratch_roots[kind]).free < size:
                raise DiskCapacityError("temporary filesystem capacity unavailable")
            # One expensive preparation at a time, even across Web/worker processes.
            if kind == "work" and (live[kind] or size == 0):
                raise DiskCapacityError("training workspace is busy")
            fd = shared_open(path, os.O_RDWR | os.O_CREAT | os.O_EXCL)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX)
                os.write(fd, json.dumps({"kind": kind, "bytes": size}).encode())
                os.fsync(fd)
            except BaseException:
                os.close(fd)
                path.unlink(missing_ok=True)
                raise
        try:
            yield path.stem
        finally:
            with self.locked():
                path.unlink(missing_ok=True)
                os.close(fd)

    @contextmanager
    def workspace(self, kind: str, size: int):
        """Scratch is owned by a kernel-held reservation, including after a crash."""
        with self.reserve(kind, size) as identity:
            path = self.scratch_roots[kind] / identity
            directory(path)
            try:
                yield path
            finally:
                shutil.rmtree(path)


class ReadCache:
    def __init__(self, root: Path, budget: DiskBudget, objects):
        self.root, self.budget, self.objects = root, budget, objects
        directory(root)

    @contextmanager
    def _locked(self):
        fd = shared_open(self.root / "cache.lock", os.O_RDWR | os.O_CREAT)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            os.close(fd)

    def _evict(self, needed: int):
        blobs = list(self.root.glob("*.blob"))
        used = sum(p.stat().st_size for p in blobs)
        limit = self.budget.limits["cache"]
        if needed > limit:
            raise DiskCapacityError("file exceeds read cache capacity")
        def last_read(path):
            pin = path.with_suffix(".pin")
            return (pin if pin.exists() else path).stat().st_mtime_ns
        for path in sorted(blobs, key=last_read):
            if used + needed <= limit:
                break
            fd = shared_open(path.with_suffix(".pin"), os.O_RDWR | os.O_CREAT)
            try:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    continue
                size = path.stat().st_size
                path.unlink()
                used -= size
            finally:
                os.close(fd)
        if used + needed > limit:
            raise DiskCapacityError("read cache is pinned by active readers")

    @contextmanager
    def open(self, artifact: Artifact):
        if artifact.state != "ready":
            raise FileNotFoundError("file is not available")
        # Cache identities are hashes only. Domain filenames live in leased workspaces.
        path = self.root / (artifact.sha256 + ".blob")
        pin = None
        with self._locked():
            # Every download holds this lock until its rename. Any remaining
            # partial belongs to a terminated writer, never an active one.
            for partial in self.root.glob("*.part"):
                partial.unlink()
            for old_pin in self.root.glob("*.pin"):
                if not old_pin.with_suffix(".blob").exists():
                    old_pin.unlink()
            if path.exists() and checksum_file(path) != (artifact.sha256, artifact.size):
                raise ArtifactIntegrityError("cached object checksum mismatch")
            if not path.exists():
                self._evict(artifact.size)
                with self.budget.reserve("cache", artifact.size):
                    temporary = self.root / (uuid.uuid4().hex + ".part")
                    try:
                        self.objects.download(artifact, temporary)
                        os.chmod(temporary, 0o440)
                        os.replace(temporary, path)
                    finally:
                        temporary.unlink(missing_ok=True)
            pin = shared_open(path.with_suffix(".pin"), os.O_RDWR | os.O_CREAT)
            fcntl.flock(pin, fcntl.LOCK_SH)
            # Different service users share immutable 0440 blobs. They may
            # update the group-writable pin, never the blob's ownership/mtime.
            os.utime(path.with_suffix(".pin"), None)
        try:
            yield path
        finally:
            os.close(pin)
