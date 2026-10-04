"""Root-owned configuration files; data from Web never becomes executable input."""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile
import uuid

from release_runtime_contract import ContractError, sync_directory
from local_inspection_service.runtime.configuration_contract import (
    ConfigurationError, CONFIGURATION_LIMIT, configuration_validate, configuration_bytes)


class ConfigurationFiles:
    def __init__(self, directory=Path("/etc/vantaline/runtime"), *, uid=0, gid):
        self.directory, self.uid, self.gid = directory, uid, gid

    def _directory(self, path, *, create=False):
        if create:
            try:
                path.mkdir(mode=0o750)
                os.chown(path, self.uid, self.gid)
            except FileExistsError:
                pass
        info = path.lstat()
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != self.uid
                or info.st_gid != self.gid or stat.S_IMODE(info.st_mode) & 0o027):
            raise ContractError("Untrusted runtime configuration directory")

    def prepare(self):
        try:
            parent = self.directory.parent.lstat()
        except FileNotFoundError:
            ancestor = self.directory.parent.parent.lstat()
            if (not stat.S_ISDIR(ancestor.st_mode) or ancestor.st_uid != self.uid
                    or stat.S_IMODE(ancestor.st_mode) & 0o022):
                raise ContractError("Untrusted runtime configuration ancestor")
            try:
                self.directory.parent.mkdir(mode=0o750)
                os.chown(self.directory.parent, self.uid, self.gid)
                sync_directory(self.directory.parent.parent)
            except FileExistsError:
                pass
            parent = self.directory.parent.lstat()
        if (not stat.S_ISDIR(parent.st_mode) or parent.st_uid != self.uid
                or stat.S_IMODE(parent.st_mode) & 0o022):
            raise ContractError("Untrusted runtime configuration parent")
        self._directory(self.directory, create=True)

    def capture_pointer(self):
        self.prepare()
        path = self.directory / "current"
        if not os.path.lexists(path):
            return None
        info = path.lstat()
        if not stat.S_ISLNK(info.st_mode) or info.st_uid != self.uid:
            raise ContractError("Untrusted runtime configuration pointer")
        revision = os.readlink(path)
        if not re.fullmatch("[0-9a-f]{64}", revision):
            raise ContractError("Untrusted runtime configuration pointer")
        self._directory(self.directory / revision)
        return revision

    def _read(self, path, *, mode, limit):
        try:
            descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(descriptor, "rb") as handle:
                info = os.fstat(handle.fileno())
                if (not stat.S_ISREG(info.st_mode) or info.st_uid != self.uid or info.st_gid != self.gid
                        or stat.S_IMODE(info.st_mode) != mode or info.st_nlink != 1):
                    raise ContractError("Untrusted runtime configuration file")
                value = handle.read(limit + 1)
            if len(value) > limit:
                raise ContractError("Runtime configuration file too large")
            return value
        except OSError:
            raise ContractError("Runtime configuration file unavailable") from None

    def _write(self, directory, name, value, mode):
        descriptor = os.open(directory / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
        with os.fdopen(descriptor, "wb") as handle:
            os.fchown(handle.fileno(), self.uid, self.gid)
            os.fchmod(handle.fileno(), mode)
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())

    def install(self, snapshot, *, expected_revision):
        if (not isinstance(snapshot, dict) or snapshot.keys() != {"configuration", "revision", "credential"}
                or snapshot["revision"] != expected_revision):
            raise ContractError("Runtime configuration snapshot mismatch")
        try:
            revision = configuration_validate(snapshot["configuration"])
            if revision != expected_revision:
                raise ContractError("Runtime configuration digest mismatch")
            raw = configuration_bytes(snapshot["configuration"])
            credential = None
            credential_hash = snapshot["configuration"]["cos_credential_sha256"]
            if credential_hash is not None:
                if not isinstance(snapshot["credential"], str) or len(snapshot["credential"]) > 22000:
                    raise ValueError()
                credential = base64.b64decode(snapshot["credential"], validate=True)
                if len(credential) > 16384 or hashlib.sha256(credential).hexdigest() != credential_hash:
                    raise ValueError()
            elif snapshot["credential"] is not None:
                raise ValueError()
        except (ConfigurationError, ValueError, TypeError, KeyError):
            raise ContractError("Runtime configuration snapshot invalid") from None
        self.prepare()
        target = self.directory / revision
        if target.exists() or target.is_symlink():
            self._directory(target)
            if self._read(target / "config.json", mode=0o640, limit=CONFIGURATION_LIMIT) != raw:
                raise ContractError("Existing runtime configuration differs")
            if credential is not None:
                if self._read(target / "cos-credentials.json", mode=0o600, limit=16384) != credential:
                    raise ContractError("Existing runtime credential differs")
            elif os.path.lexists(target / "cos-credentials.json"):
                raise ContractError("Unexpected runtime credential")
        else:
            temporary = Path(tempfile.mkdtemp(prefix=".configuration-", dir=self.directory))
            os.chown(temporary, self.uid, self.gid)
            os.chmod(temporary, 0o750)
            try:
                self._write(temporary, "config.json", raw, 0o640)
                if credential is not None:
                    self._write(temporary, "cos-credentials.json", credential, 0o600)
                sync_directory(temporary)
                os.rename(temporary, target)
                sync_directory(self.directory)
            finally:
                # Remove only the exclusive scratch directory and known files.
                if temporary.exists():
                    for name in ("config.json", "cos-credentials.json"):
                        (temporary / name).unlink(missing_ok=True)
                    temporary.rmdir()
        return revision

    def value(self, revision):
        if not isinstance(revision, str) or not re.fullmatch("[0-9a-f]{64}", revision):
            raise ContractError("Invalid runtime configuration revision")
        self.prepare()
        directory = self.directory / revision
        self._directory(directory)
        try:
            raw = self._read(directory / "config.json", mode=0o640, limit=CONFIGURATION_LIMIT)
            value = json.loads(raw)
            if configuration_validate(value) != revision or configuration_bytes(value) != raw:
                raise ContractError("Runtime configuration digest mismatch")
            credential_hash = value["cos_credential_sha256"]
            if credential_hash is not None:
                credential = self._read(directory / "cos-credentials.json", mode=0o600, limit=16384)
                if hashlib.sha256(credential).hexdigest() != credential_hash:
                    raise ContractError("Runtime credential digest mismatch")
            elif os.path.lexists(directory / "cos-credentials.json"):
                raise ContractError("Unexpected runtime credential")
            return value
        except (ValueError, TypeError, ConfigurationError):
            raise ContractError("Runtime configuration invalid") from None

    def select(self, revision):
        self.prepare()
        if revision is not None and (not isinstance(revision, str) or not re.fullmatch("[0-9a-f]{64}", revision)):
            raise ContractError("Invalid runtime configuration revision")
        current = self.directory / "current"
        self.capture_pointer()  # Reject a foreign regular file or out-of-tree target.
        if revision is None:
            current.unlink(missing_ok=True)
        else:
            self.value(revision)
            temporary = self.directory / (".current-" + uuid.uuid4().hex)
            try:
                temporary.symlink_to(revision)
                os.lchown(temporary, self.uid, self.gid)
                os.replace(temporary, current)
            finally:
                temporary.unlink(missing_ok=True)
        sync_directory(self.directory)
