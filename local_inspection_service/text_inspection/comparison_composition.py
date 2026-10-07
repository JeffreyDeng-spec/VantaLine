"""Own comparison submission, reviews, history and extraction lifecycles."""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from fastapi import FastAPI
from ..runtime.training_tasks import TrainingThreadLifecycle
from .comparison_runtime import ComparisonRuntime
from .comparison_jobs import submit
from .comparison_ports import ComparisonRecords, ComparisonMedia, ComparisonModels, EnvironmentReader
from .comparison_submission import ComparisonSubmission
from .inspection_reviews import InspectionReviews
from .inspection_ports import (InspectionAccess, InspectionRecords, SubmissionImages,
    SubmissionModels, SubmissionPolicy, SubmissionDiagnostics, SubmissionMedia,
    PrepareImage)
from .standard_composition import TextStandardWorkflows, StandardThreadScope
from .history import register as register_history, display_snapshot
from .history_ports import HistoryAccess, HistoryRecords, HistoryMedia
from .extraction_api import register as register_extraction
from .extraction_ports import ExtractionAccess, ExtractionRecords, ExtractionMedia, ExtractionModels
from .file_ports import ExtractionCleanupFiles
from .inspection_api import register as register_inspections

Record = dict[str, Any]
ExtractionResolver = Callable[[str, str, str, Record], Record]


@dataclass(frozen=True)
class ComparisonImages:
    prepare: Callable[[], PrepareImage]
    provider_copy: Callable[[bytes, str], tuple[bytes, str, str]]
    annotate: Callable[[], Callable[[bytes, list[Record]], bytes]]
    data_url: Callable[[bytes, str], str]


@dataclass(frozen=True)
class ComparisonAudit:
    append: Callable[[], Callable[[Record], None]]
    bounded_text: Callable[[], Callable[[str, int], str]]


class TextComparisonWorkflows:
    def __init__(self, *, standards: TextStandardWorkflows,
                 access: InspectionAccess, images: ComparisonImages,
                 models: SubmissionModels, policy: SubmissionPolicy,
                 diagnostics: SubmissionDiagnostics, extraction: ExtractionModels,
                 prepared_models: Callable[[], ComparisonModels],
                 digest: Callable[[], Callable[[bytes], str]],
                 environment: Callable[[], EnvironmentReader],
                 prepared_cleanup: Callable[[], Callable[[], None]], audit: ComparisonAudit,
                 runtime: StandardThreadScope, files: ExtractionCleanupFiles):
        self.standards = standards
        self.access = access
        self.images = images
        self.prepared_models = prepared_models
        self.digest = digest
        self.environment = environment
        self.prepared_cleanup = prepared_cleanup
        self.clear_repository = runtime.clear_repository
        self.files = files
        self.extraction_models = extraction
        self.extraction_runtime = TrainingThreadLifecycle(scope=runtime.scope)
        self.comparison_runtime = ComparisonRuntime(scope=runtime.scope)
        self._extraction_resolver: ExtractionResolver | None = None
        self.history_records = HistoryRecords(
            repository=lambda: self.standards.records.dependencies.runtime_repository(),
            load=lambda kind: self.standards.load(kind),
            owned=lambda kind, identifier, owner: self.standards.owned(kind, identifier, owner),
            public=lambda record: self.standards.policy.public()(record))
        self.history_media = HistoryMedia(
            path=lambda owner, standard, name: self.standards.media_path(owner, standard, name),
            read_verified=lambda path, owner, standard, **kwargs:
                self.standards.read_verified(path, owner, standard, **kwargs))
        self.extraction_records = ExtractionRecords(
            repository=lambda: self.standards.records.dependencies.runtime_repository(),
            owned=lambda kind, identifier, owner: self.standards.owned(kind, identifier, owner),
            load=lambda kind: self.standards.load(kind),
            save=lambda kind, value, **kwargs: self.standards.save(kind, value, **kwargs))
        self.extraction_media = ExtractionMedia(
            path=lambda owner, identifier, name: self.standards.media_path(owner, identifier, name),
            write=lambda path, data: self.standards.write(path, data),
            read_verified=lambda path, owner, identifier, **kwargs:
                self.standards.read_verified(path, owner, identifier, **kwargs),
            digest=standards.standard_media.digest, data_url=images.data_url)
        self.inspection_records = InspectionRecords(
            owned=lambda: self.owned,
            save=lambda kind, record, **kwargs: self.standards.save(kind, record, **kwargs),
            public=lambda record: self.standards.policy.public()(record))
        self.submission = ComparisonSubmission(
            access, self.inspection_records, load=lambda kind: self.standards.load(kind),
            media=SubmissionMedia(path=lambda: self.media_path,
                write=lambda path, data: self.standards.write(path, data),
                digest=digest),
            images=SubmissionImages(prepare=images.prepare, provider_copy=images.provider_copy,
                asset_bytes=lambda asset, owner: self.standards.asset_bytes(asset, owner),
                annotate=images.annotate, data_url=images.data_url),
            models=models, policy=policy, diagnostics=diagnostics,
            prepared_submit=lambda *args: self.submit_prepared(*args),
            resolve_extraction=lambda *args: self.resolve_extraction(*args),
            display_snapshot=display_snapshot)
        self.reviews = InspectionReviews(access, self.inspection_records,
            read_verified=lambda: self.read_verified,
            audit=audit.append, bounded_text=audit.bounded_text)

    def owned(self, kind, identifier, owner):
        return self.standards.owned(kind, identifier, owner)

    def media_path(self, owner, standard, name):
        return self.standards.media_path(owner, standard, name)

    def read_verified(self, path, owner, standard, **kwargs):
        return self.standards.read_verified(path, owner, standard, **kwargs)

    def submit_prepared(self, owner, username, standard, asset, snapshot,
                        captured, comparison_id, extraction):
        return submit(
            ComparisonRecords(self.standards.load, self.standards.save, self.standards.owned,
                self.standards.update_attempt, self.standards.policy.public()),
            ComparisonMedia(self.standards.media_path, self.standards.write,
                            self.digest()),
            self.prepared_models(), self.prepared_cleanup(), self.environment(),
            self.standards.preparation, owner, username, standard, asset, snapshot,
            captured, comparison_id, extraction, execution=self.comparison_runtime)

    def resolve_extraction(self, identifier, owner, asset_id, standard):
        resolver = self._extraction_resolver
        if resolver is None:
            raise RuntimeError('Text extraction routes must be assembled before admission')
        return resolver(identifier, owner, asset_id, standard)

    def register_history(self, app: FastAPI) -> None:
        register_history(app, HistoryAccess(self.access.require_permission, self.access.owner),
                         self.history_records, self.history_media)

    def register_extraction(self, app: FastAPI) -> ExtractionResolver:
        self._extraction_resolver = register_extraction(app,
            ExtractionAccess(self.access.require_permission, self.access.owner),
            self.extraction_records, self.extraction_media, self.extraction_models,
            clear_repository=self.clear_repository, runtime=self.extraction_runtime, files=self.files)
        return self.resolve_extraction

    def register_inspections(self, app: FastAPI):
        return register_inspections(app, self.submission, self.reviews, self.access)
