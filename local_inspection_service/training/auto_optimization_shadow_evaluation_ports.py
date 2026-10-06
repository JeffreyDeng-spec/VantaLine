"""Capabilities for shadow comparison, promotion and existing retirement cleanup."""
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from threading import Thread
from typing import Any, Protocol
import numpy as np
from .auto_optimization_label_generation_ports import ImageFiles
Record = dict[str, Any]

class Analyze(Protocol):
    def __call__(self, image: np.ndarray, record_id: str, model_id: str, *, image_path: Path) -> Record: ...

class DeleteTrainingRecord(Protocol):
    def __call__(self, job_id: str, user: Record, *, missing_ok: bool) -> Any: ...

class CleanupRetired(Protocol):
    def __call__(self, state: Record, model_id: str, *, keep_model_id: str) -> None: ...

class RetirementFiles(Protocol):
    def exists(self, path: Path) -> bool: ...
    def is_dir(self, path: Path) -> bool: ...
    def rmtree(self, path: Path) -> Any: ...

@dataclass(frozen=True)
class ShadowState:
    sanitize_ai_detection_task_id: Callable[[], Callable[[str], str]]
    _auto_optimize_lock: Callable[[], AbstractContextManager[Any]]
    _auto_optimize_shadow_threads: Callable[[], dict[str, Thread]]
    auto_optimize_shadow_worker: Callable[[], Callable[[str, str], None]]
    load_auto_optimize_state: Callable[[], Callable[[str], Record]]
    save_auto_optimize_state: Callable[[], Callable[[Record], None]]
    bounded_text: Callable[[], Callable[[Any, int], str]]

@dataclass(frozen=True)
class ShadowObservation:
    resolve_service_path: Callable[[], Callable[[Any], Path]]
    _image_files: Callable[[], ImageFiles]
    analyze_bgr: Callable[[], Analyze]
    safe_record_id: Callable[[], Callable[[str], str]]

@dataclass(frozen=True)
class ShadowPromotion:
    maybe_promote_auto_optimize_model_locked: Callable[[], Callable[[Record], None]]
    default_auto_optimize_settings: Callable[[], Record]
    cleanup_auto_optimize_retired_candidate_locked: Callable[[], CleanupRetired]
    LEGACY_OWNER_ID: Callable[[], str]
    delete_training_task_record: Callable[[], DeleteTrainingRecord]
    training_run_roots: Callable[[], Callable[[], list[Path]]]
    _business_files: Callable[[], RetirementFiles]
