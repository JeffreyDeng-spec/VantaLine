"""Per-application startup admission and ordered bounded shutdown."""
from functools import wraps
import inspect
import math
import threading
import time
from collections.abc import Callable
from fastapi import FastAPI
from .connections import ThreadRepositoryFactory
from .shutdown import WebShutdown


class ApplicationLifetime:
    """Run each native startup once; a drained application cannot restart.

    Failed startup uses the existing ordered drain. Failure to drain leaves the
    instance stopping and permits another close attempt without restarting work.
    Connections continue to release on their owning execution thread.
    """
    def __init__(self, shutdown: WebShutdown, repositories: ThreadRepositoryFactory):
        self.shutdown = shutdown
        self.repositories = repositories
        self._lock = threading.RLock()
        self._completed: set[int] = set()
        self._stopping = threading.Event()
        self._closed = False

    @property
    def closed(self) -> bool:
        with self._lock:
            return self._closed

    def startup_hook(self, index: int, hook: Callable[[], None]) -> Callable[[], None]:
        if inspect.iscoroutinefunction(hook):
            raise TypeError('Application startup requires synchronous native hooks')

        @wraps(hook)
        def start() -> None:
            with self._lock:
                if self._stopping.is_set() or self._closed:
                    raise RuntimeError('Application is stopping or closed')
                if index in self._completed:
                    return
                if index != len(self._completed):
                    raise RuntimeError('Application startup order is invalid')
                try:
                    hook()
                except BaseException:
                    try:
                        self.close(480.0)
                    except BaseException:
                        # Keep the original startup error; admission stays shut
                        # and a later bounded close may finish interrupted cleanup.
                        pass
                    raise
                self._completed.add(index)
        return start

    def close(self, timeout: float = 480.0) -> bool:
        if not math.isfinite(timeout) or not 0 <= timeout <= threading.TIMEOUT_MAX:
            raise ValueError('Shutdown timeout must be finite and nonnegative')
        deadline = time.monotonic() + timeout
        self._stopping.set()
        if not self._lock.acquire(timeout=timeout):
            return False
        try:
            if self._closed:
                return True
            if not self.shutdown.close(max(0.0, deadline - time.monotonic())):
                return False
            self.repositories.reset()
            self._closed = True
            return True
        finally:
            self._lock.release()


def register_application_lifetime(app: FastAPI, shutdown: WebShutdown, repositories: ThreadRepositoryFactory) -> ApplicationLifetime:
    if getattr(app.state, 'application_lifetime', None) is not None:
        raise RuntimeError('Application lifetime is already registered')
    owner = ApplicationLifetime(shutdown, repositories)
    startup = [owner.startup_hook(index, hook) for index, hook in enumerate(app.router.on_startup)]
    if app.router.on_shutdown != [shutdown.shutdown_application]:
        raise RuntimeError('Application lifetime must follow final Web shutdown registration')

    @wraps(shutdown.shutdown_application)
    def shutdown_application() -> None:
        if not owner.close():
            raise RuntimeError(f'Web shutdown not drained: {shutdown.failed_component or "busy"}')

    app.router.on_startup[:] = startup
    app.router.on_shutdown[:] = [shutdown_application]
    app.state.application_lifetime = owner
    return owner
