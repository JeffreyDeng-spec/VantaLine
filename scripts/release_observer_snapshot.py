"""Copy only controller-authorized bytes before any privileged observer import."""
from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import stat
import tempfile

from release_runtime_contract import ContractError


OBSERVER_EXECUTION_FILES = {}  # Replaced with reviewed hashes by the deterministic renderer.


@contextmanager
def observer_snapshot(target, storage, expected):
    if not isinstance(expected, dict) or not expected or len(expected) > 1000:
        raise ContractError('Missing observation source authorization')
    # The caller verifies storage and every ancestor; no application-owned code
    # is imported while reading the candidate files as untrusted data.
    with tempfile.TemporaryDirectory(prefix='.observer-', dir=storage) as folder:
        snapshot = Path(folder)
        for name, digest in expected.items():
            parts = Path(name).parts
            if (not parts or Path(name).is_absolute() or '..' in parts
                    or Path(name).as_posix() != name or '\\' in name
                    or not isinstance(digest, str) or len(digest) != 64):
                raise ContractError('Invalid observation source authorization')
            source = target / name
            descriptor = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(descriptor, 'rb') as handle:
                info = os.fstat(handle.fileno())
                if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0
                        or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) & 0o022):
                    raise ContractError('Untrusted observation source data')
                data = handle.read(20 * 1024 * 1024 + 1)
            if len(data) > 20 * 1024 * 1024 or hashlib.sha256(data).hexdigest() != digest:
                raise ContractError('Observation source authorization mismatch')
            destination = snapshot / name
            destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with destination.open('xb') as handle:
                os.fchmod(handle.fileno(), 0o600)
                handle.write(data)
        yield snapshot
