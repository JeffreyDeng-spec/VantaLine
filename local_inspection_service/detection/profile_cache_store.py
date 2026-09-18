"""Profile-cache JSON file persistence with explicit paths and filesystem operations."""
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol
import json


class CacheFiles(Protocol):
    def chmod(self, path: Path, mode: int) -> None: ...
    def replace(self, source: Path, destination: Path) -> None: ...


class ProfileCacheStore:
    def __init__(self, data_dir: Callable[[], Path], path: Callable[[], Path], files: Callable[[], CacheFiles]):
        self.data_dir, self.path, self.files = data_dir, path, files

    def load_ai_profile_cache(self) -> dict[str, Any]:
        if not self.path().exists():
            return {"entries": {}}
        try:
            raw = json.loads(self.path().read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raw = {}
        if not isinstance(raw, dict):
            raw = {}
        entries = raw.get("entries") if isinstance(raw.get("entries"), dict) else {}
        return {"entries": entries}

    def save_ai_profile_cache(self, cache: dict[str, Any]) -> None:
        self.data_dir().mkdir(parents=True, exist_ok=True)
        payload = {"entries": cache.get("entries") if isinstance(cache.get("entries"), dict) else {}}
        tmp_path = self.path().with_name(f"{self.path().name}.tmp")
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            self.files().chmod(tmp_path, 0o600)
        except OSError:
            pass
        self.files().replace(tmp_path, self.path())
        try:
            self.files().chmod(self.path(), 0o600)
        except OSError:
            pass
