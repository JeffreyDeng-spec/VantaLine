"""Explicit local secret store service without application imports."""
from typing import Any
from .key_material_ports import SecretPaths, SecretCodec, SecretFileOperations, SecretEnvironment, SecretPolicy, SecretStoreAccess


class LocalSecretStore:
    def __init__(self, paths: SecretPaths, codec: SecretCodec, files: SecretFileOperations, environment: SecretEnvironment, policy: SecretPolicy, access: SecretStoreAccess) -> None:
        self._paths = paths
        self._codec = codec
        self._files = files
        self._environment = environment
        self._policy = policy
        self._access = access

    def load_local_secret_env(self) -> dict[str, str]:
        values: dict[str, str] = {}
        if not self._paths.file().exists():
            return values
        try:
            lines = self._paths.file().read_text(encoding="utf-8").splitlines()
        except OSError:
            return values
        for line in lines:
            raw = line.strip()
            if not raw or raw.startswith("#") or "=" not in raw:
                continue
            name, encoded = raw.split("=", 1)
            name = name.strip()
            if not self._policy.fullmatch()(r"[A-Za-z_][A-Za-z0-9_]*", name):
                continue
            try:
                value = self._codec.loads()(encoded.strip())
            except self._codec.decode_error():
                value = encoded.strip().strip("'\"")
            if isinstance(value, str):
                values[name] = value
        return values

    def save_local_secret_env(self, values: dict[str, str]) -> None:
        self._paths.directory().mkdir(parents=True, exist_ok=True)
        clean = {
            name: str(value)
            for name, value in values.items()
            if self._policy.fullmatch()(r"[A-Za-z_][A-Za-z0-9_]*", str(name or "")) and str(value)
        }
        tmp_path = self._paths.file().with_name(f"{self._paths.file().name}.tmp")
        body = "\n".join(f"{name}={self._codec.dumps()(value)}" for name, value in sorted(clean.items()))
        tmp_path.write_text(f"{body}\n" if body else "", encoding="utf-8")
        try:
            self._files.chmod()(tmp_path, 0o600)
        except OSError:
            pass
        self._files.replace()(tmp_path, self._paths.file())
        try:
            self._files.chmod()(self._paths.file(), 0o600)
        except OSError:
            pass

    def local_secret_env_value(self, name: str) -> str:
        env_name = str(name or "").strip()
        if not self._policy.fullmatch()(r"[A-Za-z_][A-Za-z0-9_]*", env_name):
            return ""
        process_value = self._environment.values().get(env_name, "").strip()
        if process_value:
            return process_value
        file_value = self._access.load()().get(env_name, "").strip()
        if file_value:
            self._environment.values()[env_name] = file_value
        return file_value

    def set_local_secret_env(self, name: str, value: str) -> None:
        env_name = self._policy.validate()(name)
        secret = str(value or "").strip()
        if not env_name or not secret:
            return
        values = self._access.load()()
        values[env_name] = secret
        self._access.save()(values)
        self._environment.values()[env_name] = secret

    def delete_local_secret_env(self, name: str) -> None:
        env_name = str(name or "").strip()
        if not self._policy.fullmatch()(r"[A-Za-z_][A-Za-z0-9_]*", env_name):
            return
        values = self._access.load()()
        if env_name in values:
            values.pop(env_name, None)
            self._access.save()(values)
        self._environment.values().pop(env_name, None)

    def persist_secret_key_items(self, items: list[dict[str, str]], default_prefix: str) -> list[dict[str, str]]:
        persisted: list[dict[str, str]] = []
        seen: set[str] = set()
        for item in items:
            secret = str(item.get("key") or "").strip()
            env_name = self._policy.validate()(item.get("env") or item.get("env_name") or item.get("api_key_env"))
            if not env_name and secret:
                env_name = self._policy.default_environment()(default_prefix, secret, provider=str(item.get("provider") or ""))
            if secret and env_name:
                self._access.set()(env_name, secret)
            if not env_name:
                continue
            item_id = str(item.get("id") or self._policy.identity()(env_name, secret)).strip()
            dedupe_key = f"{item.get('provider') or ''}:{item_id}"
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            clean_item = {
                "id": item_id,
                "label": self._policy.text()(item.get("label") or f"API Key {len(persisted) + 1}", 80),
                "env": env_name,
            }
            if item.get("provider"):
                clean_item["provider"] = str(item["provider"])
            persisted.append(clean_item)
        return persisted
