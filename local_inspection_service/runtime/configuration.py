"""Capture immutable process configuration and read private worker configuration."""
from dataclasses import dataclass, field
import base64
import hashlib
import json
import os
from pathlib import Path
import stat

from .configuration_contract import (ConfigurationError, CONFIGURATION_LIMIT,
    CONFIGURATION_ENVIRONMENT, configuration_capture, configuration_validate,
    configuration_bytes)


def private_bytes(path: Path, *, owner: int | None, maximum: int, group_read=False):
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as handle:
            info = os.fstat(handle.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                    or (owner is not None and info.st_uid != owner)
                    or stat.S_IMODE(info.st_mode) & (0o027 if group_read else 0o077)):
                raise ConfigurationError("Private runtime configuration unavailable")
            value = handle.read(maximum + 1)
        if len(value) > maximum:
            raise ConfigurationError("Private runtime configuration unavailable")
        return value
    except OSError:
        raise ConfigurationError("Private runtime configuration unavailable") from None


def credential_digest(raw: bytes):
    try:
        value = json.loads(raw)
        if (not isinstance(value, dict) or not {"COS_SECRET_ID", "COS_SECRET_KEY"} <= value.keys()
                or not value.keys() <= {"COS_SECRET_ID", "COS_SECRET_KEY", "COS_SESSION_TOKEN"}
                or any(not isinstance(v, str) or not v or "\x00" in v for v in value.values())):
            raise ValueError()
        return hashlib.sha256(raw).hexdigest()
    except (ValueError, TypeError):
        raise ConfigurationError("Runtime storage credential is invalid") from None


@dataclass(frozen=True)
class ConfigurationSnapshot:
    revision: str
    _payload: bytes = field(repr=False)
    _credential: bytes | None = field(repr=False)

    @classmethod
    def capture(cls, environment, data_directory: Path):
        credential = None
        if environment.get("VANTALINE_FILE_STORE", "local") in ("hybrid", "cos"):
            directory = environment.get("CREDENTIALS_DIRECTORY")
            if not directory:
                raise ConfigurationError("Runtime storage credential is unavailable")
            credential = private_bytes(Path(directory) / "cos-credentials.json", owner=None, maximum=16384)
        value = configuration_capture(environment, str(data_directory.resolve()),
            cos_credential_sha256=credential_digest(credential) if credential is not None else None)
        return cls(configuration_validate(value), configuration_bytes(value), credential)

    def export(self):
        # Only the authenticated private root control command may call this.
        return {"configuration": json.loads(self._payload), "revision": self.revision,
                "credential": base64.b64encode(self._credential).decode("ascii") if self._credential is not None else None}

    @classmethod
    def read_worker(cls, path: Path, *, credentials_directory: Path | None, owner=0):
        try:
            value = json.loads(private_bytes(path, owner=owner, maximum=CONFIGURATION_LIMIT, group_read=True))
            revision = configuration_validate(value)
            credential = None
            if value["cos_credential_sha256"] is not None:
                if credentials_directory is None:
                    raise ConfigurationError("Worker storage credential is unavailable")
                credential = private_bytes(credentials_directory / "cos-credentials.json", owner=None, maximum=16384)
                if credential_digest(credential) != value["cos_credential_sha256"]:
                    raise ConfigurationError("Worker storage credential does not match")
            return cls(revision, configuration_bytes(value), credential)
        except (ValueError, TypeError):
            raise ConfigurationError("Worker runtime configuration is invalid") from None

    def apply_worker_environment(self, environment):
        value = json.loads(self._payload)
        configuration_validate(value)
        for key in CONFIGURATION_ENVIRONMENT:
            if value["environment"][key] is None:
                environment.pop(key, None)
            else:
                environment[key] = value["environment"][key]
        for key in list(environment):
            if key.startswith("VANTALINE_PROFILE_"):
                environment.pop(key)
        environment.update(value["profile_environment"])
        # systemd supplies a new credential directory for this service. Never
        # copy a Web process's CREDENTIALS_DIRECTORY into a worker.
        return Path(value["data_directory"])
