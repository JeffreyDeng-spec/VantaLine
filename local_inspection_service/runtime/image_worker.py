"""Process-local image admission, thread drain and subprocess registry ownership."""
from collections.abc import Callable
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass
import subprocess
import threading
import time
from typing import Protocol


class WorkerThread(Protocol):
    def is_alive(self) -> bool: ...
    def start(self) -> None: ...
    def join(self, timeout: float | None = None) -> None: ...


class ThreadFactory(Protocol):
    def __call__(self, *, target: Callable[[], None], name: str, daemon: bool) -> WorkerThread: ...


@dataclass(frozen=True)
class ImageWork:
    run: Callable[[], None]
    name: str


class ImageWorkerRuntime:
    def __init__(self, *, target: Callable[[], Callable[[], None]],
                 threads: Callable[[], ThreadFactory],
                 scope: Callable[[], AbstractContextManager] = nullcontext):
        self.target, self.threads, self.scope = target, threads, scope
        self.lock = threading.Lock()
        self._condition = threading.Condition(self.lock)
        self._closing = threading.Event()
        self._starting = False
        self._pending = 0
        self._children: list[WorkerThread] = []
        self._uncertain_starts: list[WorkerThread] = []
        self.thread: WorkerThread | None = None
        self.processes: dict[str, subprocess.Popen] = {}

    @property
    def closing(self) -> bool:
        return self._closing.is_set()

    def wait(self, timeout: float) -> bool:
        return self._closing.wait(timeout)

    def _scoped(self, target: Callable[[], None]):
        entered = False
        cancelled = False
        def run():
            nonlocal entered
            with self._condition:
                if cancelled:
                    return
                entered = True
            try:
                with self.scope():
                    target()
            finally:
                with self._condition:
                    self._condition.notify_all()
        def revoke(thread):
            nonlocal cancelled
            with self._condition:
                if not entered:
                    cancelled = True
                self._uncertain_starts.append(thread)
        return run, revoke

    def start(self) -> bool:
        with self._condition:
            if self.closing or self._starting or (self.thread and self.thread.is_alive()):
                return False
            self._starting = True
            self._pending += 1
        try:
            factory = self.threads()
            run, revoke = self._scoped(self.target())
            thread = factory(target=run, name="image-generation-worker", daemon=True)
            with self._condition:
                self.thread = thread
            try:
                thread.start()
            except BaseException:
                revoke(thread)
                raise
            return True
        finally:
            with self._condition:
                self._starting = False
                self._pending -= 1
                self._condition.notify_all()

    def active_children(self) -> int:
        with self._condition:
            # Starts in progress are owned by _pending and must not be pruned.
            if not self._pending:
                self._children = [t for t in self._children if t.is_alive()]
            return len(self._children)

    def launch(self, prepare: Callable[[], ImageWork | None]) -> bool:
        """Admit before lookup/mark/start; a close waits for the whole admission.

        Already admitted work may still start after closing begins. A failed
        start preserves its stored running evidence; this owner never requeues.
        No store/provider callback runs while holding the lifecycle lock.
        """
        with self._condition:
            if self.closing:
                return False
            self._pending += 1
        thread = None
        try:
            work = prepare()
            if work is None:
                return False
            factory = self.threads()
            run, revoke = self._scoped(work.run)
            thread = factory(target=run, name=work.name, daemon=True)
            with self._condition:
                self._children.append(thread)
            try:
                thread.start()
            except BaseException:
                # An interrupted start can have created an OS thread before
                # is_alive() becomes true. Retain it even across later starts.
                revoke(thread)
                raise
            return True
        finally:
            with self._condition:
                self._pending -= 1
                self._condition.notify_all()

    def close(self, timeout: float) -> bool:
        """Stop admission, then boundedly join owned work including final saves.

        False explicitly means undrained. No thread/process is cancelled, no
        provider call is replayed, and registry emptiness is never used as proof.
        A later close can finish draining, but this owner cannot be restarted.
        """
        deadline = time.monotonic() + max(0.0, timeout)
        with self._condition:
            self._closing.set()
            while self._pending:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._condition.wait(remaining)
            owned = ([self.thread] if self.thread is not None else []) + list(self._children) + list(self._uncertain_starts)
        for thread in owned:
            if thread is threading.current_thread():
                return False
            try:
                thread.join(max(0.0, deadline - time.monotonic()))
            except RuntimeError:
                return False  # no trustworthy started/completed signal yet
            if thread.is_alive():
                return False
        return True
