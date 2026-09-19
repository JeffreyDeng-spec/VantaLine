"""Explicit key identity service without application imports."""
from typing import Any
from .key_material_ports import KeyIdentityRuntime


class KeyIdentity:
    def __init__(self, runtime: KeyIdentityRuntime) -> None:
        self._runtime = runtime

    def mask_secret(self, value: str) -> str:
        secret = str(value or "").strip()
        if not secret:
            return ""
        if len(secret) <= 8:
            return f"****{secret[-2:]}"
        return f"{secret[:4]}...{secret[-4:]}"

    def ai_key_id(self, secret: str) -> str:
        digest = self._runtime.sha256()(str(secret or "").encode("utf-8")).hexdigest()[:12]
        return f"key_{digest}"

    def secret_key_item_id(self, env_name: str, secret: str = "") -> str:
        return self._runtime.key_id()(str(env_name or "").strip() or str(secret or "").strip())

    def default_secret_env_name(self, prefix: str, secret: str = "", *, provider: str = "") -> str:
        seed = str(secret or provider or self._runtime.time_ns()()).encode("utf-8")
        digest = self._runtime.sha256()(seed).hexdigest()[:10].upper()
        clean_prefix = self._runtime.substitute()(r"[^A-Z0-9_]+", "_", str(prefix or "VANTALINE_API_KEY").upper()).strip("_")
        if not clean_prefix or not self._runtime.fullmatch()(r"[A-Z_][A-Z0-9_]*", clean_prefix):
            clean_prefix = "VANTALINE_API_KEY"
        return f"{clean_prefix}_{digest}"
