"""Web lifecycle adapter; the consumer itself does not import the Web app."""
from fastapi import FastAPI
from dataclasses import dataclass
import os
from .dependencies import RepositoryLifecycle, ModelProvider
from .worker import LabelWorker
from ..runtime.label_identity import LabelRuntimeIdentity, read_identity
from ..runtime.control_connections import create_control_factory
from ..runtime.configuration import ConfigurationSnapshot
from .runtime_control import LabelRuntimeControl
from .readiness import verify_summary_reads
from collections.abc import Callable
from pathlib import Path
import threading

@dataclass(frozen=True)
class WebLabelRuntime:
    """External-mode Web owns admission/control only; no consumer is constructed."""
    repositories: RepositoryLifecycle
    data_directory: Callable[[], Path]
    models: ModelProvider
    runtime_identity: LabelRuntimeIdentity
    runtime_control: LabelRuntimeControl


_registration_lock = threading.Lock()


def register(app: FastAPI, repositories: RepositoryLifecycle,
             data_directory: Callable[[], Path], models: ModelProvider) -> LabelWorker | WebLabelRuntime:
    with _registration_lock:
        existing = getattr(app.state, "label_worker", None)
        if existing is not None:
            if (existing.repositories is not repositories or existing.data_directory is not data_directory
                    or existing.models is not models):
                raise RuntimeError("Label worker is already registered with different dependencies")
            return existing
        configuration = None
        def configuration_revision():
            nonlocal configuration
            configuration = ConfigurationSnapshot.capture(os.environ, data_directory())
            return configuration.revision
        identity = read_identity(Path(__file__).resolve().parents[2], current=Path("/opt/vantaline/current"),
                                 configuration_revision=configuration_revision)
        worker = None if identity is not None and identity.mode == "external" else LabelWorker(repositories, data_directory, models)
        control = None
        if identity is not None:
            control_factory = create_control_factory()
            control_repositories = RepositoryLifecycle(
                lambda: control_factory.selection().repository, control_factory.clear)
            control = LabelRuntimeControl(identity, control_repositories, worker, configuration=configuration)
        if worker is None:
            handle = WebLabelRuntime(repositories, data_directory, models, identity, control)
        else:
            worker.runtime_identity = identity
            worker.runtime_control = control
            handle = worker
        app.state.label_worker = handle

        def start():
            if control is None:
                worker.start()
            else:
                control.start()

        def stop():
            if worker is not None and not worker.drain():
                raise RuntimeError(f"Label worker shutdown {worker.status()}; drain not acknowledged")
            if control is not None:
                control.close()

        def verify_label_list_database():
            verify_summary_reads(repositories, required=identity is not None)

        # Before startup side effects, consumer/control readiness, or HTTP serving.
        app.router.on_startup.insert(0, verify_label_list_database)
        app.on_event("startup")(start)
        app.on_event("shutdown")(stop)
        return handle
