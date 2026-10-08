"""Build one incoming-text workflow graph around its own storage and file ports."""
from collections.abc import Callable
from typing import Protocol
from fastapi import FastAPI
from ..storage.artifacts.http import ResponseFiles
from .incoming_api import CatalogRoutes, InspectionRoutes, register_catalog, register_inspections

from .incoming_catalog import IncomingCatalog
from .incoming_duplicates import lookup_duplicate
from .incoming_execution import IncomingExecution
from .incoming_ports import (
    IncomingAccess, IncomingTasks, IncomingMedia, IncomingOCR, IncomingImaging,
    IncomingReferences, IncomingInspections, IncomingWrites, IncomingJSON,
    IncomingReferenceFiles, IncomingRetentionFiles, IncomingEvidenceImages, Record,
)
from .incoming_retention import IncomingRetention
from .incoming_reviews import IncomingReviews
from .storage_composition import TextStorage


class IncomingFiles(IncomingReferenceFiles, IncomingRetentionFiles, ResponseFiles, Protocol):
    """The capabilities shared by this domain's workflows."""


class IncomingWorkflows:
    """Construction is inert; identities and repositories are resolved per operation.

    There is no review/inspection construction cycle: both admission and reviews
    use the same duplicate lookup implementation. Store methods remain selected
    at operation time, allowing replacement of this owner's explicit adapters.
    """
    def __init__(
        self, *, storage: TextStorage, access: IncomingAccess, tasks: IncomingTasks,
        media: IncomingMedia, ocr: IncomingOCR, imaging: IncomingImaging,
        files: IncomingFiles, images: IncomingEvidenceImages,
        public: Callable[[Record], Record], verified: Callable[[], bool],
        decode_rows: Callable[[], Callable[[list[Record]], list[Record]]],
        capacity: Callable[[], Callable[[int], None]],
        audit: Callable[[], Callable[[Record], None]], system_owner: Callable[[], str],
    ):
        self.storage = storage
        self.files = files
        store = storage.incoming
        self.references = IncomingReferences(
            all=lambda: store.load_incoming_text_references(),
            load=lambda identity: store.load_incoming_text_reference(identity),
            save=lambda record, **kwargs: store.save_incoming_text_reference(record, **kwargs),
        )
        self.writes = IncomingWrites(repository=lambda: store.repository(), guard=lambda: storage.lock)
        self.json = IncomingJSON(
            paths=store.paths,
            read=lambda path: store.read_json(path),
            write=lambda path, values: store.write_json(path, values),
        )
        self.inspections = IncomingInspections(
            all=lambda: store.load_incoming_text_inspections(),
            load=lambda identity: store.load_incoming_text_inspection(identity),
            save=lambda record, **kwargs: store.save_incoming_text_inspection(record, **kwargs),
            duplicate=lambda owner, task, capture: lookup_duplicate(
                self.writes, decode_rows, lambda: store.load_incoming_text_inspections(),
                owner, task, capture,
            ),
        )
        self.catalog = IncomingCatalog(
            access, self.references, tasks, media, self.writes, self.json,
            public, verified, files=files, images=images,
        )
        self.reviews = IncomingReviews(
            access, self.inspections, tasks, media, self.writes, self.json,
            decode_rows, public, files=files,
        )
        self.execution = IncomingExecution(
            access, self.references, self.inspections, media, ocr, imaging,
            capacity, verified, public, files=files, images=images,
        )
        self.retention = IncomingRetention(
            self.inspections, media, self.writes, self.json,
            audit, system_owner, files=files,
        )

    def register_catalog(self, app: FastAPI) -> CatalogRoutes:
        """Register this owner's catalog at its preserved application position."""
        return register_catalog(app, self.catalog, files=lambda: self.files)

    def register_inspections(self, app: FastAPI) -> InspectionRoutes:
        """Register this owner's inspection group without relocating other routes."""
        return register_inspections(app, self.execution, self.reviews, files=lambda: self.files)
