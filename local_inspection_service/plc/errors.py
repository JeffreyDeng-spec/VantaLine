"""Shared PLC dispatch validation errors; no process state or I/O."""
from typing import Any


class PlcDispatchStateConflict(RuntimeError):
    def __init__(self, reason: str, authoritative: dict[str, Any] | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.authoritative = dict(authoritative or {})
