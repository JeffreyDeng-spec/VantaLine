"""Ordered Web teardown; failed producers keep their dependencies available."""
from collections.abc import Callable
from dataclasses import dataclass
import inspect
import math
import re
import threading
import time

from fastapi import FastAPI


@dataclass(frozen=True)
class ShutdownStep:
    name: str
    close: Callable[[float], bool]


class WebShutdown:
    """Own a fixed teardown order and retain completed work across drain attempts.

    Call after HTTP request admission and request processing have stopped. Each
    native close must honor its remaining budget and preserve uncertain work.
    Existing synchronous stop hooks retain their original timeout semantics;
    time spent in them reduces the budget available to later native owners.
    No callback is interrupted, no task is settled, and no model call is retried.
    """
    def __init__(self, hooks: tuple[Callable[[], None], ...], steps: tuple[ShutdownStep, ...]):
        names = [step.name for step in steps]
        if len(names) != len(set(names)) or any(not re.fullmatch(r"[a-z][a-z0-9_-]*", name) for name in names):
            raise ValueError("Shutdown component names must be unique identifiers")
        if any(inspect.iscoroutinefunction(hook) for hook in hooks):
            raise ValueError("Web shutdown requires synchronous legacy stop hooks")
        self.hooks, self.steps = hooks, steps
        self._lock = threading.RLock()
        self._active = False
        self._hook_index = self._step_index = 0
        self.failed_component: str | None = None

    def close(self, timeout: float) -> bool:
        if not math.isfinite(timeout) or not 0 <= timeout <= threading.TIMEOUT_MAX:
            raise ValueError("Shutdown timeout must be finite and nonnegative")
        deadline = time.monotonic() + timeout
        if not self._lock.acquire(timeout=timeout):
            return False
        try:
            if self._active:
                return False
            self._active = True
            try:
                while self._hook_index < len(self.hooks):
                    self.failed_component = f"legacy-stop-{self._hook_index}"
                    self.hooks[self._hook_index]()
                    self._hook_index += 1
                while self._step_index < len(self.steps):
                    step = self.steps[self._step_index]
                    self.failed_component = step.name
                    if step.close(max(0.0, deadline - time.monotonic())) is not True:
                        return False
                    self._step_index += 1
                self.failed_component = None
                return True
            except Exception:
                # Do not log or expose provider messages, paths or credentials.
                return False
            finally:
                self._active = False
        finally:
            self._lock.release()

    def shutdown_application(self) -> None:
        if not self.close(480.0):
            raise RuntimeError(f"Web shutdown not drained: {self.failed_component or 'busy'}")


def register_web_shutdown(app: FastAPI, steps: tuple[ShutdownStep, ...]) -> WebShutdown:
    """Final composition operation, after all domain lifecycle registrations."""
    if getattr(app.state, "web_shutdown", None) is not None:
        raise RuntimeError("Web shutdown is already registered")
    owner = WebShutdown(tuple(app.router.on_shutdown), steps)
    app.state.web_shutdown = owner
    app.router.on_shutdown[:] = [owner.shutdown_application]
    return owner
