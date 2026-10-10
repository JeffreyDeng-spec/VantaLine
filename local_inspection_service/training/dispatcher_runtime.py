"""Own real-photo dispatcher threads until their actual bounded drain."""
from collections.abc import Callable
from contextlib import AbstractContextManager
import threading
from ..runtime.training_tasks import TrainingThreadLifecycle, TrainingRuntimeClosed


class DispatcherRuntime:
    def __init__(self, *, scope: Callable[[], AbstractContextManager],
                 create_thread: Callable[..., threading.Thread] = threading.Thread):
        if not callable(scope) or not callable(create_thread):
            raise TypeError("Dispatcher scope and thread constructor are required")
        self._stop = threading.Event()
        self._guard = threading.RLock()
        self._started = False
        self._threads = TrainingThreadLifecycle(scope=scope)
        self._create_thread = create_thread

    def start(self, mask: Callable[[], None], training: Callable[[], None] | None) -> None:
        with self._guard:
            if self._stop.is_set():
                raise TrainingRuntimeClosed("Real-photo dispatchers are closing")
            if self._started:
                return
            # A partial start stays owned; do not retry uncertain starts.
            self._started = True
            try:
                self._threads.submit(lambda launch: self._launch(launch, mask, training))
            except BaseException:
                self._stop.set()
                raise

    def _launch(self, launch, mask, training):
        for name, tick in (("real-photo-mask-dispatch", mask),
                           ("real-photo-training-dispatch", training)):
            if tick is None:
                continue
            def loop(tick=tick):
                while not self._stop.wait(2):
                    try:
                        tick()
                    except Exception as exc:
                        print("real-photo training dispatcher failed: " + type(exc).__name__, flush=True)
            launch(lambda wrap, name=name, loop=loop: self._create_thread(
                target=wrap(loop), name=name, daemon=True), lambda thread: None)

    def stop(self) -> None:
        self._stop.set()

    def close(self, timeout: float) -> bool:
        self.stop()
        return self._threads.close(timeout)
