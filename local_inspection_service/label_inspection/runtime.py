"""Standalone label process. No application import, routes or legacy migration."""
import argparse
import logging
import os
from pathlib import Path
from collections.abc import Callable
from ..storage.artifacts.runtime import ArtifactRuntime
import signal
import threading

from ..runtime.configuration import ConfigurationSnapshot
from ..runtime.connections import ThreadRepositoryFactory
from ..runtime.control_connections import create_control_factory
from ..runtime.label_identity import RuntimeUnavailable, read_identity
from ..storage.runtime_selector import build_runtime_repository
from ..storage.artifacts.runtime import get_runtime as artifact_runtime
from .dependencies import RepositoryLifecycle
from .runtime_control import LabelRuntimeControl
from .runtime_models import create_models
from .worker import LabelWorker


class LabelProcess:
    def __init__(self, identity, configuration, data_directory, repositories, control_repositories,
                 *, runtime_provider: Callable[[], ArtifactRuntime | None], models=None, control_directory=Path("/opt/vantaline/shared/data/runtime-control"), allowed_uid=0):
        if runtime_provider is None:
            raise TypeError("runtime_provider is required")
        if identity.mode != "external" or configuration.revision != identity.config_revision:
            raise RuntimeUnavailable("Standalone label runtime identity mismatch")
        self._stop_requested = False
        self.repositories = repositories
        self.models = models if models is not None else create_models(repositories, data_directory)
        self.worker = LabelWorker(repositories, lambda: data_directory, lambda: self.models,
                                  stopping=lambda: self._stop_requested, runtime_provider=runtime_provider)
        self.control = LabelRuntimeControl(identity, control_repositories, self.worker, role="label",
            directory=control_directory, allowed_uid=allowed_uid, configuration=configuration)
        self.stopping = threading.Event()

    def start(self):
        if self._stop_requested:
            return False
        try:
            self.models.initialize()  # Existing registry is required; no legacy migration.
        finally:
            self.repositories.clear()
        if self._stop_requested:
            return False
        self.control.start()
        if self._stop_requested:
            self.worker.request_stop()
            return False
        return True

    def request_stop(self, *unused):
        # Python signal handlers can interrupt the main thread while it owns a
        # worker/Event lock. Only assign a monotonic latch here; no locking/I/O.
        self._stop_requested = True

    def close(self):
        self._stop_requested = True
        self.stopping.set()
        if not self.worker.drain():
            raise RuntimeUnavailable("Standalone label drain was not acknowledged")
        self.control.close()

    def run(self):
        try:
            if not self.start():
                return
            while not self.stopping.wait(.5):
                if self._stop_requested:
                    break
                failed = (self.worker.runtime_status()["state"] in ("failed", "timed_out")
                          or self.control.socket.thread is None or not self.control.socket.thread.is_alive())
                if failed and not self._stop_requested:
                    raise RuntimeUnavailable("Standalone label runtime failed")
        finally:
            self.close()


def bootstrap(config: Path, *, root=None, current=Path("/opt/vantaline/current")):
    configuration = ConfigurationSnapshot.read_worker(config,
        credentials_directory=Path(os.environ["CREDENTIALS_DIRECTORY"]) if os.environ.get("CREDENTIALS_DIRECTORY") else None)
    data_directory = configuration.apply_worker_environment(os.environ)
    identity = read_identity(root or Path(__file__).resolve().parents[2], current=current,
                             configuration_revision=lambda: configuration.revision)
    if identity is None or identity.mode != "external":
        raise RuntimeUnavailable("Standalone label worker requires the active external release")
    # Fail startup on local storage/credential/mount errors; this builds no Web routes.
    artifact_runtime()
    environment = {key: os.environ[key] for key in ("VANTALINE_DATA_STORE", "DATABASE_URL")}
    factory = ThreadRepositoryFactory(lambda: build_runtime_repository(env=environment),
        lambda: (environment["VANTALINE_DATA_STORE"], environment["DATABASE_URL"]))
    controls = create_control_factory()
    return LabelProcess(identity, configuration, data_directory,
        RepositoryLifecycle(lambda: factory.selection().repository, factory.clear),
        RepositoryLifecycle(lambda: controls.selection().repository, controls.clear), runtime_provider=artifact_runtime)


def main():
    parser = argparse.ArgumentParser(description="VantaLine label consumer")
    parser.add_argument("--config", required=True, type=Path)
    arguments = parser.parse_args()
    try:
        process = bootstrap(arguments.config)
        signal.signal(signal.SIGTERM, process.request_stop)
        signal.signal(signal.SIGINT, process.request_stop)
        process.run()
    except Exception:
        # No exceptions, DSNs, paths, payloads or credentials enter worker logs.
        logging.getLogger(__name__).error('{"event":"label_runtime_failed"}')
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
