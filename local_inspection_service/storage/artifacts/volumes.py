"""Validate kernel-enforced, preallocated temporary volumes on the system disk.

These are local ext4 loop filesystems, never a mount of object storage. Their
backing files reserve real system-disk blocks before accepting any application
work, so native tools cannot grow temporary storage beyond the three caps.
"""
import os
from pathlib import Path
import re


def validate_volumes(parent, roots, limits):
    parent = Path(parent).resolve()
    if parent == Path("/") or set(roots) != set(limits):
        raise ValueError("invalid temporary volume configuration")
    mounts = {}
    for line in Path("/proc/self/mountinfo").read_text().splitlines():
        fields = line.split()
        split = fields.index("-")
        mounts[fields[4]] = (fields[split + 1], fields[split + 2], fields[5])
    devices = set()
    for kind, root in roots.items():
        root = Path(root)
        if root.is_symlink() or root.resolve().parent != parent:
            raise ValueError("temporary volumes must be direct, real system-state directories")
        filesystem, device, options = mounts.get(str(root.resolve()), ("", "", ""))
        if filesystem != "ext4" or not re.fullmatch(r"/dev/loop[0-9]+", device) or "rw" not in options.split(","):
            raise ValueError("kernel-limited temporary filesystem is not mounted")
        backing = Path("/sys/class/block") / Path(device).name / "loop/backing_file"
        image = Path("/" + backing.read_text().strip().lstrip("/"))
        expected = parent / "volumes" / (kind + ".ext4")
        if image != expected or image.is_symlink():
            raise ValueError("unexpected temporary volume backing file")
        meta = image.stat()
        if (meta.st_dev != parent.stat().st_dev or meta.st_size != limits[kind]
                or meta.st_blocks * 512 < meta.st_size or meta.st_mode & 0o077):
            raise ValueError("temporary volume must be private and fully allocated on the system disk")
        device_number = root.stat().st_dev
        if device_number == parent.stat().st_dev or device_number in devices:
            raise ValueError("temporary storage classes must have independent hard limits")
        devices.add(device_number)
    return parent
