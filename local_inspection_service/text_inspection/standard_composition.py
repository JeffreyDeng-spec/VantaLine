"""Own standard storage/media/revisions and its two background-job services."""
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from fastapi import FastAPI
from ..runtime.training_tasks import TrainingThreadLifecycle
from ..storage.artifacts.runtime import ArtifactRuntime
from .record_store import TextRecordStore
from .file_ports import TextFileRuntime
from .media import TextMedia, TextMediaRecords
from .revisions import TextRevisions, RevisionRecords
from .standard_imports import StandardImports
from .standard_library import StandardLibrary
from .standard_edits import StandardEdits
from .standard_ports import (StandardAccess, StandardRecords, StandardWrites, StandardMedia,
                             StandardRevisions, StandardParsers, StandardClassification,
                             StandardPreparation)
from .document_ports import DocumentAccess, DocumentRecords, DocumentModels
from .document_jobs import DocumentJobs
from .preparation_ports import (PreparationAccess, PreparationRecords, PreparationMedia,
                                PreparationModels, PreparationHistory)
from .preparation_jobs import PreparationJobs
from .standard_api import register as register_standards, StandardRoutes
from .document_api import register as register_documents
from .preparation_api import register as register_preparation

Record = dict[str, Any]


@dataclass(frozen=True)
class StandardPolicy:
    public: Callable[[], Callable[[Record], Record]]
    snapshot: Callable[[list[Record]], list[Record]]
    expected: Callable[[], Callable[[Any], int | None]]
    bounded_text: Callable[[], Callable[[str, int], str]]
    prepare_image: Callable[[bytes], tuple[bytes, str, str, str]]
    preparation_enabled: Callable[[str], bool]


@dataclass(frozen=True)
class StandardMediaStorage:
    directory: Callable[[], Path]
    digest: Callable[[bytes], str]
    data_url: Callable[[bytes, str], str]
    runtime_provider: Callable[[], ArtifactRuntime | None]
    files: TextFileRuntime


@dataclass(frozen=True)
class StandardThreadScope:
    scope: Callable[[], AbstractContextManager]
    clear_repository: Callable[[], None]


class TextStandardWorkflows:
    def __init__(self, *, records: TextRecordStore, access: StandardAccess,
                 media: StandardMediaStorage, policy: StandardPolicy,
                 parsers: StandardParsers, documents: DocumentModels,
                 preparation: PreparationModels, runtime: StandardThreadScope,
                 raw_rows: Callable[[list[Record]], list[Record]]):
        self.records = records
        self.access = access
        self.policy = policy
        self.media = TextMedia(directory=media.directory, digest=media.digest,
            runtime_provider=media.runtime_provider,
            records=TextMediaRecords(owned=lambda: self.owned,
                                    save=lambda kind, value: self.save(kind, value)))
        self.revisions = TextRevisions(RevisionRecords(
            load=lambda kind: self.load(kind),
            save=lambda kind, value, insert_only=False: self.save(kind, value, insert_only=insert_only)),
            snapshot=policy.snapshot)
        self.document_records = DocumentRecords(
            repository=lambda: self.records.dependencies.runtime_repository(),
            guard=lambda: self.records.dependencies.guard(),
            owned=lambda kind, identifier, owner: self.owned(kind, identifier, owner),
            load=lambda kind: self.load(kind), save=lambda kind, record: self.save(kind, record),
            public=lambda record: self.policy.public()(record))
        self.document_models = documents
        self.documents = DocumentJobs(self.document_records, documents,
            asset_bytes=lambda asset, owner: self.asset_bytes(asset, owner),
            clear_repository=runtime.clear_repository,
            runtime=TrainingThreadLifecycle(scope=runtime.scope))
        self.preparation_records = PreparationRecords(
            repository=lambda: self.records.dependencies.runtime_repository(),
            guard=lambda: self.records.dependencies.guard(),
            owned=lambda kind, identifier, owner: self.owned(kind, identifier, owner),
            load=lambda kind: self.load(kind), save=lambda kind, value: self.save(kind, value),
            apply_revision=lambda standard, assets, **kwargs: self.apply_revision(standard, assets, **kwargs))
        self.preparation_media = PreparationMedia(
            path=lambda owner, identifier, name: self.media_path(owner, identifier, name),
            write=lambda path, data: self.write(path, data), digest=media.digest,
            asset_bytes=lambda asset, owner: self.asset_bytes(asset, owner), data_url=media.data_url,
            read_verified=lambda path, owner, identifier, **kwargs: self.read_verified(path, owner, identifier, **kwargs))
        self.preparation_models = preparation
        self.preparation = PreparationJobs(self.preparation_records, self.preparation_media, preparation,
            clear_repository=runtime.clear_repository,
            runtime=TrainingThreadLifecycle(scope=runtime.scope))
        self.preparation_history = PreparationHistory(
            record_table=lambda: self.records.dependencies.tables()['records'], raw_rows=raw_rows,
            public=lambda record: self.policy.public()(record), attempt_writer=lambda: self.update_attempt)
        self.standard_records = StandardRecords(
            load=lambda kind: self.load(kind), save=lambda kind, value, **kwargs: self.save(kind, value, **kwargs),
            owned=lambda kind, identifier, owner: self.owned(kind, identifier, owner), public=policy.public)
        self.standard_media = StandardMedia(
            path=lambda owner, standard, name: self.media_path(owner, standard, name),
            write=lambda: self.write, digest=media.digest)
        self.imports = StandardImports(access, self.standard_records, self.standard_media, parsers,
            StandardClassification(start=lambda standard, owner: self.documents.start(standard, owner),
                                   mark_unavailable=lambda: self.documents.mark_unavailable),
            bounded_text=policy.bounded_text)
        self.library = StandardLibrary(access, self.standard_records,
            refresh=lambda standard, owner: self.documents.refresh(standard, owner),
            asset_bytes=lambda asset, owner: self.asset_bytes(asset, owner))
        self.edits = StandardEdits(access, self.standard_records,
            StandardWrites(repository=lambda: self.records.dependencies.runtime_repository(),
                           guard=lambda: self.records.dependencies.guard()),
            self.standard_media,
            StandardRevisions(expected=policy.expected, snapshot=policy.snapshot, apply=lambda: self.apply_revision),
            StandardPreparation(start=lambda standard, owner: self.preparation.start(standard, owner),
                                enabled=policy.preparation_enabled),
            prepare_image=policy.prepare_image, bounded_text=policy.bounded_text, files=media.files)

    def load(self, kind: str) -> list[Record]:
        return self.records.load(kind)

    def save(self, kind: str, value: Record, *, insert_only: bool = False) -> bool:
        return self.records.save(kind, value, insert_only=insert_only)

    def owned(self, kind: str, identifier: str, owner: str) -> Record | None:
        return self.records.owned(kind, identifier, owner)

    def update_attempt(self, kind: str, value: Record, expected_status: str = 'attempting') -> bool:
        return self.records.update_attempt(kind, value, expected_status)

    def media_path(self, owner: str, standard: str, name: str) -> Path:
        return self.media.media_path(owner, standard, name)

    def write(self, path: Path, contents: bytes) -> None:
        return self.media.write(path, contents)

    def read_verified(self, path_value: str, owner: str, standard: str, *,
                      expected_sha256: str = '', max_bytes: int = 120*1024*1024) -> bytes:
        return self.media.read_verified(path_value, owner, standard,
            expected_sha256=expected_sha256, max_bytes=max_bytes)

    def asset_bytes(self, asset: Record, owner: str) -> bytes:
        return self.media.asset_bytes(asset, owner)

    def apply_revision(self, standard: Record, assets: list[Record], *,
                       action: str, asset_id: str, now: int) -> Record:
        return self.revisions.apply(standard, assets, action=action, asset_id=asset_id, now=now)

    def register_standards(self, app: FastAPI) -> StandardRoutes:
        return register_standards(app, self.imports, self.library, self.edits)

    def register_documents(self, app: FastAPI) -> DocumentJobs:
        return register_documents(app, DocumentAccess(self.access.require_permission, self.access.owner),
                                  self.document_records, self.documents)

    def register_preparation(self, app: FastAPI) -> PreparationJobs:
        return register_preparation(app, PreparationAccess(self.access.require_permission, self.access.owner),
            self.preparation_records, self.preparation_history, self.preparation_media, self.preparation)
