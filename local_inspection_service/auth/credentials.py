"""Existing PBKDF2 format and temporary password generation, independently testable."""
import binascii
from collections.abc import Callable
import hashlib
import hmac
import secrets
from fastapi import HTTPException

TEMP_PASSWORD_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789!@#$%^*-_"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations_raw, salt_hex, digest_hex = str(stored_hash or "").split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(iterations_raw)
        expected = bytes.fromhex(digest_hex)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), iterations)
        return hmac.compare_digest(actual, expected)
    except (TypeError, ValueError, binascii.Error):
        return False


def generate_temporary_password(length: int = 18) -> str:
    length = max(12, min(48, int(length or 18)))
    return "".join(secrets.choice(TEMP_PASSWORD_ALPHABET) for _ in range(length))


class PasswordHasher:
    def __init__(self, iterations: Callable[[], int]):
        self.iterations = iterations

    def password_hash(self, password: str) -> str:
        if len(password) < 8:
            raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
        salt = secrets.token_hex(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), self.iterations())
        return f"pbkdf2_sha256${self.iterations()}${salt}${digest.hex()}"
