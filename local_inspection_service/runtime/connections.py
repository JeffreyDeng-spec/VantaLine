"""One repository selection per execution thread, with explicit release scopes."""
from collections.abc import Callable, Hashable
from contextlib import contextmanager
import threading
from typing import Any


def close_selection(selection: Any) -> None:
    repository = getattr(selection, 'repository', None)
    connection = getattr(repository, 'connection', None)
    close = getattr(connection, 'close', None)
    if callable(close):
        try:
            close()
        except Exception:
            pass


def selection_is_usable(selection: Any) -> bool:
    repository = getattr(selection, 'repository', None)
    connection = getattr(repository, 'connection', None)
    closed = getattr(connection, 'closed', None)
    if closed is None:
        return True
    try:
        return not bool(closed)
    except Exception:
        return True


class ThreadRepositoryFactory:
    def __init__(self, create: Callable[[], Any], cache_key: Callable[[], Hashable]):
        self._create = create
        self._cache_key = cache_key
        self._lock = threading.RLock()
        self._generation = 0
        self._local = threading.local()

    def generation(self) -> int:
        with self._lock:
            return self._generation

    def reset(self) -> None:
        with self._lock:
            self._generation += 1
        self.clear()

    def clear(self) -> None:
        selection = getattr(self._local, 'selection', None)
        if selection is not None:
            close_selection(selection)
        for attr in ('key', 'selection', 'generation'):
            try:
                delattr(self._local, attr)
            except AttributeError:
                pass

    def selection(self) -> Any:
        while True:
            key, generation = self._cache_key(), self.generation()
            cached = getattr(self._local, 'selection', None)
            if (cached is not None and getattr(self._local, 'key', None) == key
                    and getattr(self._local, 'generation', None) == generation
                    and selection_is_usable(cached)):
                return cached
            if cached is not None:
                self.clear()
            selection = self._create()
            # Invalidation during connect must not publish a stale connection.
            if self.generation() != generation or self._cache_key() != key:
                close_selection(selection)
                continue
            self._local.key = key
            self._local.selection = selection
            self._local.generation = generation
            return selection

    @contextmanager
    def thread_scope(self):
        """Enter/exit on the same thread; nested work releases at its outer edge.

        Async callers wrap the synchronous function sent to the thread pool.
        Do not hold this scope across an await or close another thread's state.
        """
        depth = getattr(self._local, 'scope_depth', 0)
        self._local.scope_depth = depth + 1
        try:
            yield self
        finally:
            self._local.scope_depth = depth
            if depth == 0:
                self.clear()
