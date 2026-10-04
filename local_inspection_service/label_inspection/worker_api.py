"""Web lifecycle adapter; the consumer itself does not import the Web app."""
from fastapi import FastAPI
from .dependencies import RepositoryLifecycle, ModelProvider
from .worker import LabelWorker
from collections.abc import Callable
from pathlib import Path
import threading

_registration_lock = threading.Lock()


def register(app: FastAPI, repositories: RepositoryLifecycle,
             data_directory: Callable[[], Path], models: ModelProvider) -> LabelWorker:
    with _registration_lock:
        existing = getattr(app.state, "label_worker", None)
        if existing is not None:
            if (existing.repositories is not repositories or existing.data_directory is not data_directory
                    or existing.models is not models):
                raise RuntimeError("Label worker is already registered with different dependencies")
            return existing
        worker = LabelWorker(repositories, data_directory, models)
        app.state.label_worker = worker

        def start():
            worker.start()

        def stop():
            if not worker.drain():
                raise RuntimeError(f"Label worker shutdown {worker.status()}; drain not acknowledged")

        app.on_event("startup")(start)
        app.on_event("shutdown")(stop)
        return worker
