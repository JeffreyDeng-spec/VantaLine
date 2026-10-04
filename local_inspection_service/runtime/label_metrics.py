"""Process-local bounded operational counters; never retain task or exception data."""
import math
import threading
import time

ERRORS = frozenset(("worker_iteration_failed", "worker_cleanup_failed", "heartbeat_failed"))
STATES = frozenset(("ready", "drained", "draining", "failed", "timed_out"))


class LabelRuntimeMetrics:
    def __init__(self):
        self._lock = threading.Lock()
        self._values = {"lock_samples": 0, "lock_wait_ms_total": 0.0, "lock_wait_ms_max": 0.0,
                        "duplicate_submissions": 0, "duplicate_calls": 0, "recent_error": None}

    def lock_wait(self, seconds):
        milliseconds = max(0.0, seconds * 1000)
        with self._lock:
            self._values["lock_samples"] += 1
            self._values["lock_wait_ms_total"] += milliseconds
            self._values["lock_wait_ms_max"] = max(self._values["lock_wait_ms_max"], milliseconds)

    def duplicate(self, *, call=False):
        with self._lock:
            self._values["duplicate_calls" if call else "duplicate_submissions"] += 1

    def error(self, code):
        if code not in ERRORS:
            raise ValueError("Unsupported runtime error code")
        with self._lock:
            self._values["recent_error"] = {"code": code, "at": int(time.time())}

    def snapshot(self):
        with self._lock:
            return {**self._values, "recent_error": dict(self._values["recent_error"]) if self._values["recent_error"] else None}


def valid_metrics(value):
    if not isinstance(value, dict) or value.keys() != {
            "lock_samples", "lock_wait_ms_total", "lock_wait_ms_max", "duplicate_submissions", "duplicate_calls", "recent_error"}:
        return False
    if any(type(value[key]) is not int or value[key] < 0 for key in ("lock_samples", "duplicate_submissions", "duplicate_calls")):
        return False
    if any(type(value[key]) not in (int, float) or not math.isfinite(value[key]) or value[key] < 0
           for key in ("lock_wait_ms_total", "lock_wait_ms_max")):
        return False
    error = value["recent_error"]
    return error is None or (isinstance(error, dict) and error.keys() == {"code", "at"}
        and isinstance(error["code"], str) and error["code"] in ERRORS and type(error["at"]) is int and error["at"] >= 0)
