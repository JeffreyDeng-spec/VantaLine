"""One application's shared auto-optimization guard and task-thread registries."""
import threading

class AutoOptimizationRuntimeState:
    def __init__(self):
        self.lock = threading.RLock()
        self.label_threads: dict[str, threading.Thread] = {}
        self.shadow_threads: dict[str, threading.Thread] = {}
