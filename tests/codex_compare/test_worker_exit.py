"""Deterministic process/reader scheduling around the actual worker.execute path."""
import io
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from local_inspection_service.codex_compare import worker


@pytest.mark.parametrize("exit_timing,reader_delay,exit_code,events,control,expected", [
    ("before", 0, 0, "complete", "running", "completed"),
    ("during_pulse", 0, 0, "complete", "running", "completed"),
    ("during_pulse", 1, 0, "complete", "running", "completed"),
    ("reader_during_pulse", 1, 0, "complete", "running", "completed"),
    ("during_pulse", 0, 1, "complete", "running", "failed"),
    ("during_pulse", 0, 0, "failed", "running", "failed"),
    ("during_pulse", 0, 0, "missing", "running", "failed"),
    ("before", 0, 0, "complete", "cancel_requested", "cancelled"),
    ("before", 0, 0, "complete", "expired", "timed_out"),
    ("during_pulse", 99, 0, "complete", "expire_waiting", "timed_out"),
])
def test_exit_drains_reader_before_settling(tmp_path, exit_timing, reader_delay, exit_code, events, control, expected):
    task = {"id": "cc_synthetic", "owner_user_id": "fixture", "attempt_id": "attempt",
            "deadline": 100, "inputs": {side: {"image": "synthetic"} for side in ("reference", "actual")}}
    auth = tmp_path / "auth"
    auth.mkdir()
    (auth / "auth.json").write_text("{}")
    payload = [{"type": "thread.started", "thread_id": "synthetic-session"}]
    if events != "missing":
        payload.append({"type": "turn.completed", "usage": {"input_tokens": 11, "output_tokens": 7}})
    if events == "failed":
        payload.append({"type": "turn.failed"})
    process = SimpleNamespace(
        stdin=io.BytesIO(), stdout=io.BytesIO(b"".join(json.dumps(event).encode() + b"\n" for event in payload)),
        returncode=exit_code if exit_timing in {"before", "reader_during_pulse"} else None,
    )
    process.poll = lambda: process.returncode
    calls = []
    clock = [100 if control == "expired" else 10]
    readers = []

    class ControlledThread:
        def __init__(self, target, **kwargs):
            self.target = target
            self.alive = True
            self.joins = 0
            if target.__name__ == "read_events":
                readers.append(self)

        def start(self):
            pass  # The test controls scheduling, never sleeps or launches a process.

        def join(self, timeout):
            self.joins += 1
            if self.joins > reader_delay and self.alive:
                self.target()  # Execute the actual JSON reader, including its bounded queue.
                self.alive = False

        def is_alive(self):
            return self.alive

    def pulse(owner, identity, attempt, metadata):
        calls.append(("pulse", dict(metadata)))
        process.returncode = exit_code
        if exit_timing == "reader_during_pulse" and readers[0].alive:
            readers[0].target()
            readers[0].alive = False
        if control == "expire_waiting" and len(calls) >= 3:
            clock[0] = 100
        assert len(calls) < 8, "worker did not settle after bounded controlled iterations"
        return {"status": control if control == "cancel_requested" else "running"}

    def settle(owner, identity, attempt, status, error):
        calls.append(("settle", status))

    repository = SimpleNamespace(pulse=pulse, settle=settle)
    broker = SimpleNamespace(serve_forever=lambda: None, shutdown=lambda: None, server_close=lambda: None)
    with patch.object(worker, "broker", return_value=broker), \
         patch.object(worker, "sandbox_command", return_value=["synthetic-command"]), \
         patch.object(worker.subprocess, "Popen", return_value=process), \
         patch.object(worker.threading, "Thread", ControlledThread), \
         patch.object(worker, "time", SimpleNamespace(time=lambda: clock[0], monotonic=lambda: 10, sleep=lambda _: None)), \
         patch.object(worker, "stop_process", return_value=None), \
         patch.object(worker, "with_repo", side_effect=lambda fn: fn(repository)):
        worker.execute(task, "synthetic-token", {"work_root": str(tmp_path / "work"),
            "auth_home": str(auth), "model": "fixture", "binary": "unused"},
            SimpleNamespace(read=lambda *args: b"synthetic-media"))
    assert calls[-1] == ("settle", expected)
    if expected == "completed":
        assert not readers[0].alive
        assert calls[-2] == ("pulse", {"session_id": "synthetic-session",
                                      "usage": {"input_tokens": 11, "output_tokens": 7}})
    assert list((tmp_path / "work").iterdir()) == []
