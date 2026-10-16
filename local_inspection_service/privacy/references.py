"""Deterministic authenticated public references, independent of authorization.

The shared runtime key survives immutable releases and worker restarts. A reference
is never an access grant: decoded values still enter the original owner/lease checks.
"""
import base64
import os
from pathlib import Path
from collections.abc import Callable


def runtime_key(directory: Path) -> bytes:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "model-reference.key"
    # Publish a complete key atomically; concurrent workers must never read a
    # partially written file or overwrite the winning worker's key.
    if not path.exists():
        temporary = directory / (".model-reference-" + os.urandom(12).hex())
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(os.urandom(64))
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, path)
            except FileExistsError:
                pass
        finally:
            temporary.unlink(missing_ok=True)
    key = path.read_bytes()
    if len(key) != 64:
        raise ValueError("Public reference key unavailable")
    return key


class References:
    PREFIX = "ref1_"

    def __init__(self, key: Callable[[], bytes]):
        self.key = key
        self._material: bytes | None = None

    def material(self) -> bytes:
        if self._material is None:
            self._material = self.key()
        return self._material

    def encode(self, value: str) -> str:
        from Crypto.Cipher import AES
        cipher = AES.new(self.material(), AES.MODE_SIV)
        cipher.update(b"vantaline-public-reference-v1")
        encrypted, tag = cipher.encrypt_and_digest(value.encode("utf-8"))
        return self.PREFIX + base64.urlsafe_b64encode(tag + encrypted).decode().rstrip("=")

    def decode(self, value: str) -> str:
        if not value.startswith(self.PREFIX):
            return value
        if len(value) > 8192:
            raise ValueError("Invalid public reference")
        try:
            from Crypto.Cipher import AES
            raw = base64.b64decode(value[len(self.PREFIX):] + "=" * (-len(value[len(self.PREFIX):]) % 4), altchars=b"-_", validate=True)
            cipher = AES.new(self.material(), AES.MODE_SIV)
            cipher.update(b"vantaline-public-reference-v1")
            return cipher.decrypt_and_verify(raw[16:], raw[:16]).decode("utf-8")
        except (ValueError, UnicodeError) as error:
            raise ValueError("Invalid public reference") from error
