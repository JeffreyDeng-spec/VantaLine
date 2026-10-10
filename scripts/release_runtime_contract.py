"""Strict label runtime protocol used by the release controller.

Topology and transition contracts read data only; they do not run candidate
validators. The separate read-only database observer runs only verified root-owned
code with isolated imports. Paths, service names and roles are controller-owned.
"""
from dataclasses import dataclass
import json
import math
import os
import stat
from pathlib import Path
import re
from typing import Mapping

WEB = "vantaline"
LABEL = "vantaline-label-worker"
PROTOCOL = 1
MAX_HEARTBEAT_AGE = 10.0
HEX40 = re.compile(r"[0-9a-f]{40}\Z")
RELEASE = re.compile(r"v[0-9]{4}\.[0-9]{2}\.[0-9]+\Z")
INSTANCE = re.compile(r"[0-9a-f]{32}\Z")


class ContractError(RuntimeError):
    """A safe fixed message; never include untrusted runtime content."""


@dataclass(frozen=True)
class Topology:
    commit: str
    mode: str
    runtime_protocol: int | None = None

    @property
    def services(self) -> tuple[str, ...]:
        return (WEB,) if self.mode == "embedded" else (WEB, LABEL)

    @property
    def consumer_service(self) -> str:
        return WEB if self.mode == "embedded" else LABEL

    @classmethod
    def parse(cls, value: Mapping, commit: str) -> "Topology":
        if not isinstance(commit, str) or not HEX40.fullmatch(commit):
            raise ContractError("Invalid release commit")
        if not isinstance(value, dict) or type(value.get("schema")) is not int:
            raise ContractError("Invalid runtime topology")
        common = {"schema": 1, "git_commit": commit,
                  "worker_mode": "embedded", "services": [WEB]}
        if value == common:
            return cls(commit, "embedded")
        for mode, services in (("embedded", [WEB]), ("external", [WEB, LABEL])):
            expected = {"schema": 2, "git_commit": commit, "worker_mode": mode,
                        "services": services, "runtime_protocol": PROTOCOL}
            if value == expected and type(value.get("runtime_protocol")) is int:
                return cls(commit, mode, PROTOCOL)
        raise ContractError("Unsupported runtime topology")


def read_object(path: Path, *, limit: int = 16384) -> dict:
    """Bounded regular-file read; errors do not leak internal paths or content."""
    try:
        # O_NOFOLLOW closes the final-component check/open race on Linux. A
        # bounded descriptor read also rejects file growth after the size check.
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        if path.is_symlink():
            raise ContractError("Runtime state file unavailable")
        with os.fdopen(os.open(path, flags), "rb") as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode):
                raise ContractError("Runtime state file unavailable")
            data = handle.read(limit+1)
        if len(data) > limit:
            raise ContractError("Runtime state file unavailable")
        value = json.loads(data.decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError()
        return value
    except (OSError, ValueError, UnicodeError):
        raise ContractError("Runtime state file unavailable") from None


@dataclass(frozen=True)
class ConsumerState:
    instance: str
    pid: int
    state: str
    control_revision: str
    active_iterations: int
    queued_runs: int
    active_runs: int
    maintenance: bool
    config_revision: str | None

    @classmethod
    def verify(cls, value: dict, *, topology: Topology, release: str,
               pid: int, now: float, service: str = WEB, expected_instance: str | None = None,
               control_revision: str | None = None) -> "ConsumerState":
        if topology.runtime_protocol != PROTOCOL:
            raise ContractError("Consumer runtime protocol unavailable")
        if not isinstance(release, str) or not RELEASE.fullmatch(release):
            raise ContractError("Invalid release identity")
        required = {"schema", "git_commit", "release", "role", "instance", "pid",
                    "heartbeat", "state", "control_revision", "active_iterations",
                    "worker_mode", "queued_runs", "active_runs", "maintenance", "config_revision"}
        if not isinstance(value, dict) or value.keys() != required:
            raise ContractError("Invalid consumer state")
        if (type(value["schema"]) is not int or value["schema"] != PROTOCOL
                or value["git_commit"] != topology.commit or value["release"] != release
                or value["worker_mode"] != topology.mode
                or service not in topology.services
                or value["role"] != ("web" if service == WEB else "label")):
            raise ContractError("Consumer build or role mismatch")
        if type(pid) is not int or pid <= 0 or type(value["pid"]) is not int or value["pid"] != pid:
            raise ContractError("Consumer process mismatch")
        instance = value["instance"]
        if not isinstance(instance, str) or not INSTANCE.fullmatch(instance):
            raise ContractError("Invalid consumer instance")
        if expected_instance is not None and instance != expected_instance:
            raise ContractError("Consumer instance changed during transition")
        heartbeat = value["heartbeat"]
        if (type(heartbeat) not in (int, float) or not math.isfinite(heartbeat)
                or not math.isfinite(now) or not -1 <= now - heartbeat <= MAX_HEARTBEAT_AGE):
            raise ContractError("Consumer heartbeat expired")
        revision = value["control_revision"]
        if not isinstance(revision, str) or not INSTANCE.fullmatch(revision):
            raise ContractError("Invalid consumer control revision")
        if control_revision is not None and revision != control_revision:
            raise ContractError("Consumer has not acknowledged control revision")
        state = value["state"]
        if state not in ("ready", "draining", "drained", "failed", "timed_out"):
            raise ContractError("Invalid consumer lifecycle state")
        active = value["active_iterations"]
        if type(active) is not int or not 0 <= active <= 2 or (state == "drained" and active):
            raise ContractError("Invalid consumer drain evidence")
        for key in ('queued_runs', 'active_runs'):
            if type(value[key]) is not int or value[key] < 0:
                raise ContractError('Invalid queue evidence')
        if type(value['maintenance']) is not bool:
            raise ContractError('Invalid maintenance evidence')
        configuration = value['config_revision']
        if configuration is not None and (not isinstance(configuration, str)
                or not re.fullmatch(r'[0-9a-f]{64}', configuration)):
            raise ContractError('Invalid runtime configuration revision')
        if topology.mode == 'external' and configuration is None:
            raise ContractError('Shared runtime configuration missing')
        return cls(instance, pid, state, revision, active, value['queued_runs'],
                   value['active_runs'], value['maintenance'], configuration)

    def require_available(self) -> None:
        if self.state not in ("ready", "drained"):
            raise ContractError("Consumer is not available")

    def require_ready(self) -> None:
        if self.state != "ready":
            raise ContractError("Consumer is not ready")

    def require_drained(self) -> None:
        if self.state != "drained" or self.active_iterations:
            raise ContractError("Consumer has not drained")


def sync_directory(directory: Path) -> None:
    descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
