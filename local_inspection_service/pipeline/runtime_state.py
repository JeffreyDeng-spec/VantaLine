"""One application's pipeline guards, in-flight registries and reconciliation clock."""
import threading

class PipelineRuntimeState:
    def __init__(self):
        self.task_lock = threading.Lock()
        self.state_lock = threading.RLock()
        self.auto_agent_lock = threading.Lock()
        self.auto_agent_inflight: set[str] = set()
        self.recommendation_lock = threading.Lock()
        self.recommendation_inflight: set[str] = set()
        self.advance_registry_lock = threading.Lock()
        self.advance_inflight: set[str] = set()
        self.advance_cancel: dict[str, threading.Event] = {}
        self.last_sync_at = 0.0

    def set_last_sync_at(self, value: float) -> None:
        self.last_sync_at = value
