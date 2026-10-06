"""Own the analysis service graph and its shared local persistence guard."""
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
import threading
from ..storage.postgres_runtime_repository import PostgresRuntimeRepository
from .analysis_records import AnalysisNormalization, AnalysisNormalizer
from .analysis_repository import AnalysisStoreDependencies, AnalysisRepository
from .analysis_service import AnalysisAccess, AnalysisRecords
from .analysis_queries import AnalysisPresentation, AnalysisQueries
from .analysis_processing import ProcessingDependencies, ProcessingProjection, image_processing_summary
from .analysis_scope import ScopeDependencies, AnalysisScope
from .analysis_projection import ProjectionDependencies, AnalysisProjection
from .analysis_publication import PublicationDependencies, AnalysisPublisher


@dataclass(frozen=True)
class AnalysisStorage:
    path: Callable[[], Path]
    runtime_repository: Callable[[], PostgresRuntimeRepository | None]
    ensure_dirs: Callable[[], None]


class AnalysisServices:
    def __init__(self, *, normalization: AnalysisNormalization, storage: AnalysisStorage,
                 access: AnalysisAccess, processing: ProcessingDependencies,
                 scope: ScopeDependencies, projection: ProjectionDependencies,
                 publication: PublicationDependencies,
                 cache_scope: Callable[[], AbstractContextManager], batch_limit: int):
        self.lock = threading.RLock()
        self.normalizer = AnalysisNormalizer(normalization)
        self.repository = AnalysisRepository(AnalysisStoreDependencies(
            path=storage.path, runtime_repository=storage.runtime_repository,
            lock=lambda: self.lock, ensure_dirs=storage.ensure_dirs,
        ), self.normalizer.normalize_data_analysis_record)
        self.records = AnalysisRecords(self.repository, access)
        self.processing = ProcessingProjection(processing)
        self.scope = AnalysisScope(scope)
        self.projection = AnalysisProjection(projection, self.processing, self.scope)
        self.publisher = AnalysisPublisher(publication, self.repository, self.processing)
        self.queries = AnalysisQueries(self.records, AnalysisPresentation(
            cache_scope=cache_scope,
            processing_items=self.processing.data_analysis_image_processing_items,
            record=self.projection.public_data_analysis_record,
            task_groups=self.projection.data_analysis_task_groups,
            processing_summary=image_processing_summary,
        ), batch_limit=batch_limit)
