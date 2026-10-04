"""Real PG/control sockets/consumer lifespans against the installed-controller code.

Only systemd and HTTP acceptance are substituted. No providers or physical PLC.
"""
from functools import partial
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from release_runtime_client import request
from release_runtime_contract import ContractError, WEB, LABEL
from release_runtime_transition import RuntimeTransition
from local_inspection_service.runtime.connections import ThreadRepositoryFactory
from local_inspection_service.runtime.label_identity import read_identity
from local_inspection_service.label_inspection.runtime_control import LabelRuntimeControl
from local_inspection_service.label_inspection.worker import LabelWorker
from local_inspection_service.label_inspection.dependencies import RepositoryLifecycle
from local_inspection_service.storage.postgres_runtime_repository import PostgresRuntimeRepository
from local_inspection_service.storage.postgres_schema import postgres_ddl
from local_inspection_service.storage.runtime_selector import default_postgres_connector


class RuntimeHarness:
    def __init__(self, root, repositories):
        self.root, self.repositories = root, repositories
        self.current = root / "current"
        self.old = self.release("v2026.10.1", "a" * 40)
        self.new = self.release("v2026.10.2", "b" * 40)
        self.current.symlink_to(self.old, target_is_directory=True)
        self.control = self.worker = None
        self.events = []
        self.directory = root / "control"
        self.journal = root / "journal.json"
        self.transition = RuntimeTransition(self.journal, commands=self, units=self,
            client=partial(request, directory=self.directory), uid=os.getuid(),
            backgrounds=root / "backgrounds")
        self.run("start", WEB)
        self.control.command({"schema": 1, "command": "resume", "revision": "d" * 32})
        self.control.command({"schema": 1, "command": "open_admission", "revision": "d" * 32})
        self.events.clear()

    def release(self, name, commit):
        path = self.root / name
        path.mkdir()
        (path / "VERSION.json").write_text(json.dumps({"git_commit": commit, "release": name}))
        (path / "RUNTIME_TOPOLOGY.json").write_text(json.dumps({"schema": 2, "git_commit": commit,
            "worker_mode": "embedded", "services": [WEB], "runtime_protocol": 1}))
        return path

    def property(self, service, name, **options):
        live = service == WEB and self.control is not None
        if name == "MainPID":
            return str(os.getpid()) if live else "0"
        if name == "LoadState":
            return "loaded" if service == WEB else "not-found"
        if name == "ActiveState":
            return "active" if live else "inactive"
        raise AssertionError(name)

    def run(self, command, *services, **options):
        self.events.append((command, *services))
        assert command == "start" and services == (WEB,)
        if self.control is not None:
            return
        identity = read_identity(self.current.resolve(), current=self.current)
        self.worker = LabelWorker(self.repositories, lambda: self.root, lambda: None)
        self.worker._iteration = lambda: False  # The paid workflow is not exercised here.
        self.control = LabelRuntimeControl(identity, self.repositories, self.worker,
            directory=self.directory, allowed_uid=os.getuid())
        self.control.start()

    def stop_all(self, services, *, deadline):
        self.events.append(("stop", *services))
        assert services == (WEB,)
        self.close()

    def capture(self):
        return {"fixture": True}

    def install(self, topology, **options):
        self.events.append(("install", topology.mode))
        assert topology.mode == "embedded"

    def restore(self, snapshot):
        assert snapshot == {"fixture": True}
        self.events.append(("restore",))

    def switch(self):
        temporary = self.root / "next"
        temporary.symlink_to(self.new, target_is_directory=True)
        os.replace(temporary, self.current)

    def close(self):
        if self.worker is not None:
            assert self.worker.drain(3)
        if self.control is not None:
            self.control.close()
        self.worker = self.control = None


def main():
    dsn = os.environ["VANTALINE_POSTGRES_DSN"]
    schema = "label_deploy_" + uuid.uuid4().hex[:12]
    setup = default_postgres_connector(dsn)
    unavailable = [False]
    def create():
        if unavailable[0]:
            raise RuntimeError("synthetic-private-value")
        return SimpleNamespace(repository=PostgresRuntimeRepository(default_postgres_connector(dsn),
            "<synthetic>", schema_name=schema))
    factory = ThreadRepositoryFactory(create, lambda: schema)
    repositories = RepositoryLifecycle(lambda: factory.selection().repository, factory.clear)
    harness = None
    try:
        with setup.cursor() as cursor:
            cursor.execute(postgres_ddl(schema))
        setup.commit()
        for case in ("accept", "rollback", "retry_rollback", "db_failure", "preserve_pause"):
            with tempfile.TemporaryDirectory(prefix="label-deploy-") as temporary:
                harness = RuntimeHarness(Path(temporary), repositories)
                transition = harness.transition
                if case == "preserve_pause":
                    harness.control.command({"schema": 1, "command": "close_admission", "revision": "d" * 32})
                    harness.control.command({"schema": 1, "command": "pause", "revision": "d" * 32})
                    deadline = time.monotonic() + 2
                    while harness.worker.runtime_status()["state"] != "drained":
                        assert time.monotonic() < deadline
                        time.sleep(.01)
                original_instance = harness.control.instance
                if case == "db_failure":
                    # Reach the admission mutation, then fail its DB operation.
                    real_pause = transition.pause
                    def fail_pause(*args, **kwargs):
                        unavailable[0] = True
                        return real_pause(*args, **kwargs)
                    transition.pause = fail_pause
                    try:
                        transition.begin(harness.old, harness.new)
                    except ContractError:
                        pass
                    else:
                        raise AssertionError("unavailable DB allowed transition")
                    unavailable[0] = False
                    transition.rollback(harness.current)
                    assert harness.control.instance == original_instance
                    assert not any(e[0] in ("stop", "install") for e in harness.events)
                else:
                    transition.begin(harness.old, harness.new)
                    assert harness.control is None and transition.data["phase"] == "stopped"
                    harness.switch()
                    transition.start()
                    assert harness.worker.runtime_status()["state"] == "drained"
                    assert transition.state(transition.data["new"], WEB).maintenance
                    if case in ("accept", "preserve_pause"):
                        transition.accept()
                        state = transition.state(transition.data["new"], WEB)
                        assert state.maintenance == (case == "preserve_pause")
                        assert state.state == ("drained" if case == "preserve_pause" else "ready")
                    else:
                        # Simulate the shell rejecting public HTTP/assets after startup.
                        real_save = transition.save
                        interrupted = [False]
                        def save():
                            if case == "retry_rollback" and transition.data["phase"] == "rolled_back" and not interrupted[0]:
                                interrupted[0] = True
                                raise RuntimeError("synthetic interruption after admission")
                            real_save()
                        transition.save = save
                        try:
                            transition.rollback(harness.current)
                        except RuntimeError:
                            assert case == "retry_rollback" and interrupted[0]
                            restored_instance = harness.control.instance
                            stops = len([e for e in harness.events if e[0] == "stop"])
                            transition.rollback(harness.current)
                            assert harness.control.instance == restored_instance
                            assert len([e for e in harness.events if e[0] == "stop"]) == stops
                        assert harness.current.resolve() == harness.old
                        state = transition.state(transition.data["old"], WEB)
                        assert not state.maintenance and state.state == "ready"
                        assert state.instance != original_instance
                harness.close()
                harness = None
        print("label deployment: real controller/client + PG + Unix sockets accept, rollback, retry, DB failure and intent passed")
    finally:
        unavailable[0] = False
        if harness is not None:
            harness.close()
        factory.clear()
        setup.rollback()
        with setup.cursor() as cursor:
            cursor.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        setup.commit()
        setup.close()


if __name__ == "__main__":
    main()
