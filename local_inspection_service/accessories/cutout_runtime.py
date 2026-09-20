"""Accessory cutout behavior without application imports."""
from typing import Any
import threading


class RembgSessionRuntime:
    def __init__(self) -> None:
        self._session: Any | None = None
        self.lock = threading.RLock()


    def rembg_session(self) -> Any | None:
        with self.lock:
            if self._session is not None:
                return self._session
            try:
                from rembg import new_session

                self._session = new_session("u2net")
                return self._session
            except Exception:
                self._session = None
                return None
