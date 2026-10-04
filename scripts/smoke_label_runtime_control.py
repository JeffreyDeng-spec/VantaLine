"""Real PostgreSQL, threads and Unix socket control; no model/provider or PLC calls."""
import json
from dataclasses import replace
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
import uuid
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local_inspection_service.runtime.connections import ThreadRepositoryFactory
from local_inspection_service.runtime.label_identity import LabelRuntimeIdentity, RuntimeUnavailable
from local_inspection_service.runtime.configuration import ConfigurationSnapshot
from local_inspection_service.label_inspection.runtime_control import LabelRuntimeControl
from local_inspection_service.label_inspection.worker import LabelWorker
from local_inspection_service.label_inspection.dependencies import RepositoryLifecycle
from local_inspection_service.storage.postgres_runtime_repository import PostgresRuntimeRepository
from local_inspection_service.storage.postgres_schema import postgres_ddl
from local_inspection_service.storage.runtime_selector import default_postgres_connector


def main():
    dsn = os.environ["VANTALINE_POSTGRES_DSN"]
    schema = "label_socket_" + uuid.uuid4().hex[:12]
    setup = default_postgres_connector(dsn)
    closed = []
    failing = [False]
    blocked = [False]
    connecting, release_connect = threading.Event(), threading.Event()
    def create():
        if blocked[0] and threading.current_thread().name == "label-runtime-control":
            connecting.set()
            assert release_connect.wait(10)
        if failing[0]:
            raise RuntimeError("synthetic-secret-and-customer-path")
        connection = default_postgres_connector(dsn)
        return SimpleNamespace(repository=PostgresRuntimeRepository(connection, "<synthetic>", schema_name=schema))
    factory = ThreadRepositoryFactory(create, lambda: schema)
    def clear():
        import threading
        closed.append(threading.current_thread().name)
        factory.clear()
    repositories = RepositoryLifecycle(lambda: factory.selection().repository, clear)
    identity = LabelRuntimeIdentity("a"*40, "v2026.10.1", "embedded")
    controls, workers = [], []
    try:
        with setup.cursor() as cursor:
            cursor.execute(postgres_ddl(schema))
        setup.commit()
        with tempfile.TemporaryDirectory(prefix="label-control-") as temporary:
            directory = Path(temporary) / "control"
            def launch(selected=identity, allowed_uid=None, configuration=None, tick_seconds=5):
                worker = LabelWorker(repositories, lambda: Path(temporary), lambda: None)
                worker._iteration = lambda: False
                control = LabelRuntimeControl(selected, repositories, worker, directory=directory,
                    allowed_uid=os.getuid() if allowed_uid is None else allowed_uid, configuration=configuration)
                control.socket.tick_seconds = tick_seconds
                workers.append(worker)
                controls.append(control)
                control.start()
                return worker, control
            def request(command, *, revision="b"*32, raw=None, timeout=3):
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                    client.settimeout(timeout)
                    client.connect(str(directory / "web-control.sock"))
                    body = raw if raw is not None else json.dumps({"schema": 1, "command": command, "revision": revision}).encode() + b"\n"
                    client.sendall(body)
                    result = bytearray()
                    while not result.endswith(b"\n"):
                        part = client.recv(16384)
                        if not part:
                            return None
                        result.extend(part)
                    return json.loads(result)
            failing[0] = True
            try:
                launch()
            except RuntimeUnavailable as error:
                assert str(error) == "Label runtime startup failed"
            else:
                raise AssertionError("unavailable database allowed startup")
            assert not (directory / "web-control.sock").exists()
            failing[0] = False
            worker, control = launch()
            original_threads = tuple(worker._threads)
            original_instance = control.instance
            control.start()
            assert tuple(worker._threads) == original_threads and control.instance == original_instance
            state = request("status")
            keys = {"schema", "git_commit", "release", "worker_mode", "role", "instance", "pid", "heartbeat",
                    "control_revision", "maintenance", "config_revision", "queued_runs", "active_runs", "state", "active_iterations"}
            assert state.keys() == keys and state["state"] == "drained" and state["maintenance"]
            assert state["pid"] == os.getpid() and state["instance"] == control.instance
            assert 0 <= time.monotonic() - state["heartbeat"] < 2
            assert request("resume")["state"] == "ready"
            assert request("open_admission")["maintenance"] is False
            assert request("close_admission")["maintenance"] is True
            assert request("pause")["state"] in ("draining", "drained")
            assert request("status")["control_revision"] == "b"*32
            assert request("pause", revision="invalid") == {"error": "runtime_control_unavailable"}
            assert request("invalid") == {"error": "runtime_control_unavailable"}
            assert request("status", raw=b'{"schema":1,"synthetic-secret":"bad"}\n') == {"error": "runtime_control_unavailable"}
            assert request("status", raw=b"x"*1100+b"\n") == {"error": "runtime_control_unavailable"}
            # The existing process lock rejects a second build before it can change DB state.
            try:
                launch(LabelRuntimeIdentity("c"*40, "v2026.10.2", "embedded"))
            except RuntimeUnavailable:
                pass
            else:
                raise AssertionError("duplicate role was allowed")
            assert request("status")["git_commit"] == identity.commit
            # Database errors are bounded/redacted; the next request can reconnect.
            failing[0] = True
            assert request("status") == {"error": "runtime_control_unavailable"}
            failing[0] = False
            assert request("status")["state"] == "drained"
            request("resume")
            request("open_admission")
            assert worker.drain(3)
            control.close()
            control.start()  # A second lifespan of the same application/controller.
            assert tuple(worker._threads) != original_threads and control.instance != original_instance
            assert request("status")["state"] == "ready"
            assert worker.drain(3)
            control.close()
            new_worker, new_control = launch()
            restarted = request("status")
            assert restarted["state"] == "ready" and not restarted["maintenance"]
            assert restarted["instance"] != state["instance"]
            assert new_worker.drain(3)
            new_control.close()
            # Another release always starts paused/closed, even after an active predecessor.
            next_worker, next_control = launch(LabelRuntimeIdentity("c"*40, "v2026.10.2", "embedded"))
            next_state = request("status")
            assert next_state["state"] == "drained" and next_state["maintenance"]
            assert next_worker.drain(3)
            next_control.close()
            # SO_PEERCRED rejects an unauthorized peer before the handler receives input.
            denied_worker, denied = launch(LabelRuntimeIdentity("c"*40, "v2026.10.2", "embedded"), os.getuid()+1)
            denied_calls = []
            original_handler = denied.socket.handler
            def observe_denied_command(value):
                denied_calls.append(value)
                return original_handler(value)
            denied.socket.handler = observe_denied_command
            with denied.store() as store:
                denied_before = store.snapshot(denied.identity)
            assert denied_before[0]["maintenance"] is True
            try:
                assert request("open_admission") is None
            except (ConnectionResetError, BrokenPipeError):
                pass  # A denied peer may close before send, during send, or at recv.
            # Observe the rejection before sending to deterministically cover EPIPE.
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.settimeout(3)
                client.connect(str(denied.socket.path))
                assert client.recv(1) == b""
                try:
                    client.sendall(b'{"schema":1,"command":"open_admission","revision":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"}\n')
                except BrokenPipeError:
                    pass
                else:
                    raise AssertionError("denied peer accepted input after observed EOF")
            assert denied_calls == []
            with denied.store() as store:
                assert store.snapshot(denied.identity) == denied_before
            assert denied_worker.drain(3)
            denied.close()
            hung_worker, hung_control = launch(LabelRuntimeIdentity("c"*40, "v2026.10.2", "embedded"))
            blocked[0] = True
            try:
                request("status", timeout=.2)
            except socket.timeout:
                pass
            else:
                raise AssertionError("unacknowledged blocked connection was reported successful")
            assert connecting.is_set()
            try:
                hung_control.close()
            except RuntimeUnavailable as error:
                assert str(error) == "Runtime control thread did not stop"
            else:
                raise AssertionError("live control thread was acknowledged stopped")
            assert hung_control.socket.lock_handle is not None
            try:
                hung_control.start()
            except RuntimeUnavailable:
                pass
            else:
                raise AssertionError("timed-out controller generation restarted")
            try:
                launch(LabelRuntimeIdentity("d"*40, "v2026.10.4", "embedded"))
            except RuntimeUnavailable:
                pass
            else:
                raise AssertionError("role lock released while a command was still running")
            blocked[0] = False
            release_connect.set()
            hung_control.socket.thread.join(2)
            assert not hung_control.socket.thread.is_alive()
            assert hung_worker.drain(3)
            hung_control.close()
            configuration = ConfigurationSnapshot.capture({"VANTALINE_DATA_STORE": "postgres",
                "DATABASE_URL": "fixture-dsn", "VANTALINE_PROFILE_" + "A"*32: "synthetic-secret"}, Path(temporary))
            configured_identity = LabelRuntimeIdentity("e"*40, "v2026.10.5", "embedded", configuration.revision)
            configured_worker, configured = launch(configured_identity, configuration=configuration, tick_seconds=.05)
            exported = request("configuration")
            assert exported.keys() == {"state", "snapshot"}
            assert exported["state"]["config_revision"] == configuration.revision
            assert exported["snapshot"] == configuration.export()
            assert request("status").keys() == keys and "snapshot" not in request("status")
            # Periodic heartbeat runs without a control request and has the same
            # shutdown/role-lock protection when its connection creation stalls.
            first_samples = configured.monitor()["roles"]["web"]["metrics"]["lock_samples"]
            deadline = time.monotonic() + 3
            while configured.monitor()["roles"]["web"]["metrics"]["lock_samples"] <= first_samples:
                assert time.monotonic() < deadline
                time.sleep(.05)
            release_connect.clear(); connecting.clear(); blocked[0] = True
            assert connecting.wait(2), "periodic heartbeat did not run"
            try:
                configured.close()
            except RuntimeUnavailable:
                pass
            else:
                raise AssertionError("blocked heartbeat released role lock")
            assert configured.socket.lock_handle is not None
            blocked[0] = False; release_connect.set()
            configured.socket.thread.join(2)
            assert not configured.socket.thread.is_alive()
            assert configured_worker.drain(3)
            configured.close()
            assert "label-runtime-control" in closed
        print("label control: real sockets, peer denial, exclusive roles, SQL failures, restart and build activation passed")
    finally:
        blocked[0] = False
        release_connect.set()
        failing[0] = False
        for worker in workers:
            assert worker.drain(3)
        for control in controls:
            control.close()
        factory.clear()
        setup.rollback()
        with setup.cursor() as cursor:
            cursor.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        setup.commit()
        setup.close()


if __name__ == "__main__":
    main()
