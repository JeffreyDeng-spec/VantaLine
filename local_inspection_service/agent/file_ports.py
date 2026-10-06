"""Narrow file capabilities for Agent source evidence."""
from pathlib import Path
from typing import Protocol


class ExistingAgentFiles(Protocol):
    def exists(self, path: Path) -> bool: ...


class AgentReferenceFiles(ExistingAgentFiles, Protocol):
    def read_bytes(self, path: Path) -> bytes: ...
