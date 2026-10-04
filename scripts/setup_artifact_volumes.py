#!/usr/bin/env python3
"""Provision local temporary capacity caps; never touches a business-data mount.

Run from a verified immutable release as root. Defaults to a read-only plan;
--apply creates only previously absent private backing files and systemd mounts.
Existing files are never reformatted or replaced. No cloud resources are created.
"""
import argparse
import grp
import json
import os
from pathlib import Path
import pwd
import shutil
import subprocess

GiB = 1024 ** 3
LIMITS = {"cache": 6 * GiB, "work": 12 * GiB, "upload": 2 * GiB}


def run(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout.strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-root", type=Path, default=Path("/var/lib/vantaline-artifacts"))
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    parent = args.state_root
    if (not parent.is_absolute() or parent.parent != Path("/var/lib")
            or not parent.name.startswith("vantaline-artifacts") or parent.is_symlink()):
        raise ValueError("state root must be a direct dedicated /var/lib/vantaline-artifacts directory")
    if parent.exists() and parent.stat().st_uid != 0:
        raise ValueError("state directory must be root-owned")
    if parent.parent.stat().st_dev != Path("/").stat().st_dev:
        raise ValueError("state directory must reside on the system disk")
    missing = sum(size for kind, size in LIMITS.items() if not (parent / "volumes" / (kind + ".ext4")).exists())
    free = shutil.disk_usage(parent.parent).free
    if free - missing < 9 * GiB:
        raise RuntimeError("preallocation would leave less than the 8 GiB reserve plus 1 GiB setup margin")
    print(json.dumps({"state_root": str(parent), "limits": LIMITS, "new_allocation_bytes": missing,
                      "system_free_before": free, "apply": args.apply}))
    if not args.apply:
        return
    if os.geteuid() != 0:
        raise PermissionError("provisioning requires root")
    uid, gid = pwd.getpwnam("vantaline").pw_uid, grp.getgrnam("vantaline").gr_gid
    parent.mkdir(mode=0o755, exist_ok=True)
    volumes = parent / "volumes"
    volumes.mkdir(mode=0o711, exist_ok=True)
    if volumes.is_symlink() or volumes.stat().st_uid != 0:
        raise ValueError("invalid backing-file directory")
    units = []
    for kind, size in LIMITS.items():
        image, mount = volumes / (kind + ".ext4"), parent / kind
        if image.is_symlink() or mount.is_symlink():
            raise ValueError("temporary volume paths cannot be symlinks")
        if not image.exists():
            fd = os.open(image, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            try:
                os.posix_fallocate(fd, 0, size)
                os.fsync(fd)
            finally:
                os.close(fd)
            # Only the just-created private image reaches mkfs. nodiscard keeps
            # all backing blocks allocated instead of punching sparse holes.
            run("mkfs.ext4", "-F", "-m", "0", "-E", "nodiscard,lazy_itable_init=0", str(image))
        if image.stat().st_size != size or image.stat().st_blocks * 512 < size:
            raise RuntimeError("existing backing image is incomplete; inspect it without reformatting")
        if run("blkid", "-p", "-s", "TYPE", "-o", "value", str(image)) != "ext4":
            raise RuntimeError("existing backing image is not an ext4 filesystem")
        mount.mkdir(mode=0o755, exist_ok=True)
        if not mount.is_mount() and any(mount.iterdir()):
            raise RuntimeError("refusing to hide existing files under a temporary mount")
        unit = run("systemd-escape", "--path", "--suffix=mount", str(mount))
        body = ("[Unit]\nDescription=VantaLine bounded local " + kind + " storage\n"
                "Before=vantaline.service vantaline-codex-compare.service\n\n[Mount]\nWhat=" + str(image)
                + "\nWhere=" + str(mount) + "\nType=ext4\nOptions=loop,nodev,nosuid\n\n[Install]\nWantedBy=local-fs.target\n")
        target = Path("/etc/systemd/system") / unit
        if target.exists():
            if target.is_symlink() or target.read_text() != body:
                raise RuntimeError("existing mount unit differs; refusing to replace it")
        else:
            with target.open("x") as handle:
                handle.write(body)
        units.append(unit)
    run("systemctl", "daemon-reload")
    for unit in units:
        run("systemctl", "enable", "--now", unit)
    for path in [parent / "control", *(parent / kind for kind in LIMITS), parent / "upload" / "spool"]:
        path.mkdir(exist_ok=True)
        os.chown(path, uid, gid)
        path.chmod(0o2770)
    from sys import path as imports
    imports.insert(0, str(Path(__file__).resolve().parents[1]))
    from local_inspection_service.storage.artifacts.volumes import validate_volumes
    validate_volumes(parent, {kind: parent / kind for kind in LIMITS}, LIMITS)
    print(json.dumps({"verified": True, "application_configuration_changed": False,
                      "system_free_after": shutil.disk_usage(parent).free, "mount_units": units}))


if __name__ == "__main__":
    main()
