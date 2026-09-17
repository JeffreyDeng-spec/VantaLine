"""Process-local ownership of training threads, deletion markers and their shared guard."""
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
import threading
from typing import Any

Record = dict[str, Any]


class TrainingTaskRuntime:
    def __init__(self):
        self.lock = threading.RLock()
        self.threads: dict[str, threading.Thread] = {}
        self.tombstones: dict[str, Record] = {}


@dataclass(frozen=True)
class TrainingTaskState:
    guard: Callable[[], AbstractContextManager]
    threads: Callable[[], dict[str, threading.Thread]]
    tombstones: Callable[[], dict[str, Record]]
