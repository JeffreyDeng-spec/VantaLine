"""Narrow late-bound capabilities for a browser diagnostic reservation."""
from dataclasses import dataclass
from typing import Any, Callable

Getter = Callable[[], Callable[..., Any]]


@dataclass(frozen=True)
class DiagnosticStatePorts:
    token_hex: Getter
    token_urlsafe: Getter
    active_lease: Getter
    config_error: Callable[[], type[Exception]]
    clock: Getter
    ceil: Getter
    token_hash: Getter
    lease_row: Getter
    protocol_version: Callable[[], str]
    frames: Getter
    mutate: Getter
    compare_digest: Getter
    record: Getter
    current_user: Getter
