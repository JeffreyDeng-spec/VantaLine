"""Local root-only client for the fixed label runtime protocol.

The peer verifies root credentials. This client checks the peer's user and never
accepts a socket path, module, command or service name from package metadata.
"""
import json
import math
import re
from pathlib import Path
import socket
import stat
import struct
import time

from local_inspection_service.runtime.configuration_contract import CONFIGURATION_LIMIT

from release_runtime_contract import ContractError, PROTOCOL, WEB, LABEL

SOCKET_NAMES = {WEB: "web-control.sock", LABEL: "label-control.sock"}
CONTROL_DIRECTORY = Path("/opt/vantaline/shared/data/runtime-control")
ALLOWED_COMMANDS = frozenset({"status", "close_admission", "open_admission", "pause", "resume", "configuration"})


def request(service: str, command: str, revision: str, *, uid: int, pid: int,
            directory: Path = CONTROL_DIRECTORY, timeout: float = 5) -> dict:
    if service not in SOCKET_NAMES or command not in ALLOWED_COMMANDS:
        raise ContractError("Unsupported runtime operation")
    if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{32}", revision):
        raise ContractError("Invalid runtime control revision")
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
        raise ContractError("Invalid runtime control timeout")
    if command in ("close_admission", "open_admission", "configuration") and service != WEB:
        raise ContractError("Maintenance belongs to Web admission")
    deadline = time.monotonic() + timeout
    path = directory / SOCKET_NAMES[service]
    try:
        info = path.lstat()
        if not stat.S_ISSOCK(info.st_mode) or info.st_uid != uid or stat.S_IMODE(info.st_mode) != 0o600:
            raise ContractError("Runtime control socket unavailable")
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(timeout)
            connection.connect(str(path))
            peer_pid, peer_uid, _ = struct.unpack("3i", connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
            if peer_uid != uid or peer_pid != pid:
                raise ContractError("Runtime control peer mismatch")
            body = json.dumps({"schema": PROTOCOL, "command": command, "revision": revision}, separators=(",", ":")).encode()
            connection.sendall(body + b"\n")
            limit = CONFIGURATION_LIMIT + 32768 if command == "configuration" else 16384
            received = bytearray()
            while not received.endswith(b"\n"):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ContractError("Runtime control timed out")
                connection.settimeout(remaining)
                part = connection.recv(min(65536, limit + 1 - len(received)))
                if not part or len(received) + len(part) > limit:
                    raise ContractError("Invalid runtime control response")
                received.extend(part)
            value = json.loads(received)
            if not isinstance(value, dict):
                raise ContractError("Invalid runtime control response")
            return value
    except (OSError, ValueError):
        raise ContractError("Runtime control unavailable") from None
