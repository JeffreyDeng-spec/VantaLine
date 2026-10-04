#!/usr/bin/env python3
"""Linux-only disposable loop-filesystem test. Requires root; no business paths.

Uses three 64 MiB synthetic volumes, never the production sizing or mount paths.
Exercises ENOSPC, backing validation and cross-user verified cache leases.
"""
import errno
import multiprocessing
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from smoke_artifact_storage import Client, Locations
from local_inspection_service.storage.artifacts.cos import CosObjects
from local_inspection_service.storage.artifacts.disk import DiskBudget, ReadCache
from local_inspection_service.storage.artifacts.files import BusinessFiles
from local_inspection_service.storage.artifacts.runtime import ArtifactRuntime
from local_inspection_service.storage.artifacts.store import ArtifactStore
from local_inspection_service.storage.artifacts.volumes import validate_volumes


def command(*args):
    subprocess.run(args, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def main():
    if sys.platform != "linux" or os.geteuid() != 0:
        raise RuntimeError("run this disposable Linux capacity test as root")
    with tempfile.TemporaryDirectory(prefix="vantaline-artifact-volume-test-") as name:
        parent = Path(name)
        parent.chmod(0o2775)
        os.chown(parent, 0, 65534)
        volumes = parent / "volumes"
        volumes.mkdir(mode=0o711)
        size = 64 * 1024 * 1024
        limits = {kind: size for kind in ("cache", "work", "upload")}
        roots, mounted = {}, []
        try:
            for kind in limits:
                image = volumes / (kind + ".ext4")
                fd = os.open(image, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                try:
                    os.posix_fallocate(fd, 0, size)
                finally:
                    os.close(fd)
                command("mkfs.ext4", "-F", "-m", "0", "-E", "nodiscard,lazy_itable_init=0", str(image))
                root = parent / kind
                root.mkdir()
                command("mount", "-o", "loop,nodev,nosuid", str(image), str(root))
                mounted.append(root)
                root.chmod(0o2770)
                os.chown(root, 0, 65534)
                roots[kind] = root
            validate_volumes(parent, roots, limits)
            budget = DiskBudget(parent / "control", limits=limits, preallocated=True, reserve_bytes=0,
                                free_bytes=lambda: shutil.disk_usage(parent).free,
                                scratch_roots={kind: root / "scratch" for kind, root in roots.items()})
            original_free = shutil.disk_usage(parent).free
            with budget.workspace("work", 1) as work:
                try:
                    with (work / "oversized").open("wb", buffering=0) as handle:
                        for _ in range(70):
                            handle.write(b"x" * (1024 * 1024))
                    raise AssertionError("kernel allowed workspace to exceed its volume")
                except OSError as error:
                    assert error.errno == errno.ENOSPC
            assert original_free - shutil.disk_usage(parent).free < 2 * 1024 * 1024
            client, locations = Client(), Locations()
            objects = CosObjects(client, "synthetic-bucket")
            store = ArtifactStore(locations, objects, ReadCache(roots["cache"], budget, objects), budget, parent / "stage")
            row = store.put_bytes("outputs/private.png", b"synthetic-image", expected_generation=0)
            store.read_bytes(row.path)
            for root, directories, files in os.walk(parent):
                if Path(root) == volumes:
                    continue
                os.chown(root, 0, 65534)
                for filename in files:
                    if Path(root) != volumes:
                        os.chown(Path(root) / filename, 0, 65534)
            runtime = ArtifactRuntime(store, parent, "cos")
            def other_service():
                os.setgroups([65534])
                os.setgid(65534)
                os.setuid(65534)
                with BusinessFiles(runtime_provider=lambda: runtime).local_file(parent / row.path) as local:
                    assert local.name == "private.png" and local.read_bytes() == b"synthetic-image"
            child = multiprocessing.get_context("fork").Process(target=other_service)
            child.start()
            child.join(10)
            if child.is_alive():
                child.kill()
                child.join()
                raise AssertionError("cross-user cache access hung")
            assert child.exitcode == 0, "cross-user verified cache lease failed"
            print("PASS kernel capacity, backing allocation, workspace cleanup and cross-user cache lease")
        finally:
            for root in reversed(mounted):
                command("umount", str(root))


if __name__ == "__main__":
    main()
