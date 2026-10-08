"""Process-local ownership of training threads, deletion markers and their shared guard."""
from collections.abc import Callable
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass
import threading
import time
from typing import Any, TypeVar

Record = dict[str, Any]


Result = TypeVar("Result")
ThreadTarget = Callable[..., Any]
ThreadWrapper = Callable[[ThreadTarget], ThreadTarget]
ThreadConstructor = Callable[[ThreadWrapper], threading.Thread]
ThreadRegistration = Callable[[threading.Thread], None]
ThreadLaunch = Callable[[ThreadConstructor, ThreadRegistration], None]


class TrainingRuntimeClosed(RuntimeError):
    """New work cannot be admitted after the owner starts draining."""


class TrainingThreadLifecycle:
    def __init__(self, *, scope: Callable[[], AbstractContextManager] = nullcontext):
        self.scope = scope
        self._condition = threading.Condition()
        self._closing = False
        self._pending = 0
        self._owned: list[threading.Thread] = []
        self._uncertain: list[threading.Thread] = []

    def submit(self, prepare: Callable[[ThreadLaunch], Result]) -> Result:
        """Reserve before persistence; keep admitted preparation valid during close."""
        with self._condition:
            if self._closing:
                raise TrainingRuntimeClosed("Training runtime is closing")
            if not self._pending:
                self._owned = [thread for thread in self._owned if thread.is_alive()]
            self._pending += 1
        submitting_thread = threading.get_ident()
        active = True
        def launch(construct: ThreadConstructor, register: ThreadRegistration) -> None:
            with self._condition:
                if not active or threading.get_ident() != submitting_thread:
                    raise RuntimeError("Training launch must run inside its synchronous submission")
            self._launch(construct, register)
        try:
            return prepare(launch)
        finally:
            with self._condition:
                active = False
                self._pending -= 1
                self._condition.notify_all()

    def _launch(self, construct: ThreadConstructor, register: ThreadRegistration) -> None:
        entered = False
        cancelled = False
        def wrap(target: ThreadTarget) -> ThreadTarget:
            def run(*args, **kwargs):
                nonlocal entered
                with self._condition:
                    if cancelled:
                        return
                    entered = True
                with self.scope():
                    return target(*args, **kwargs)
            return run
        thread = construct(wrap)
        with self._condition:
            self._owned.append(thread)
        try:
            register(thread)
            thread.start()
        except BaseException:
            with self._condition:
                if not entered:
                    cancelled = True
                self._uncertain.append(thread)
            raise

    def close(self, timeout: float) -> bool:
        """Stop admission and wait for preparation, owned threads and scope exit.

        A timeout does not cancel, restart or settle a task. Uncertain starts stay
        owned even if public records are replaced or the native bootstrap has
        not yet set Python's started event. An unjoinable handle fails closed.
        """
        deadline = time.monotonic() + max(0.0, timeout)
        with self._condition:
            self._closing = True
            while self._pending:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._condition.wait(remaining)
            threads = list(self._owned) + list(self._uncertain)
        for thread in threads:
            if thread is threading.current_thread():
                return False
            try:
                thread.join(max(0.0, deadline - time.monotonic()))
            except RuntimeError:
                return False
            if thread.is_alive():
                return False
        return True


class TrainingTaskRuntime(TrainingThreadLifecycle):
    def __init__(self, *, scope: Callable[[], AbstractContextManager] = nullcontext):
        self.lock = threading.RLock()
        self.threads: dict[str, threading.Thread] = {}
        self.tombstones: dict[str, Record] = {}
        super().__init__(scope=scope)


@dataclass(frozen=True)
class TrainingTaskState:
    guard: Callable[[], AbstractContextManager]
    threads: Callable[[], dict[str, threading.Thread]]
    tombstones: Callable[[], dict[str, Record]]
