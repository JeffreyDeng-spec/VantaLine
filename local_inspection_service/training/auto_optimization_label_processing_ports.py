"""Explicit state, artifact and executor capabilities for automatic mask batches."""
from collections.abc import Callable, Iterable, Iterator
from concurrent.futures import Future
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from threading import Thread
from typing import Any, Protocol
from .auto_optimization_status_ports import StopCapture
Record = dict[str, Any]

class LabelGenerator(Protocol):
    def __call__(self, sample: Record, settings: Record, model: str, directory: Path) -> tuple[list[Record], list[Record], Record]: ...

class LabelExecutor(Protocol):
    def __enter__(self) -> 'LabelExecutor': ...
    def __exit__(self, *args: Any) -> Any: ...
    def submit(self, function: Callable[[str, Record, Record, str], Record], task_id: str, sample: Record, settings: Record, model: str) -> Future[Record]: ...

class ExecutorFactory(Protocol):
    def __call__(self, *, max_workers: int, thread_name_prefix: str) -> LabelExecutor: ...

@dataclass(frozen=True)
class ProcessingState:
    sanitize_ai_detection_task_id: Callable[[], Callable[[str], str]]
    _auto_optimize_lock: Callable[[], AbstractContextManager[Any]]
    _auto_optimize_label_threads: Callable[[], dict[str, Thread]]
    auto_optimize_label_worker: Callable[[], Callable[[str], None]]
    load_auto_optimize_state: Callable[[], Callable[[str], Record]]
    save_auto_optimize_state: Callable[[], Callable[[Record], None]]
    auto_optimize_completed_model_id: Callable[[], Callable[[Record], str]]
    auto_optimize_stop_capture_for_model_locked: Callable[[], StopCapture]
    default_auto_optimize_settings: Callable[[], Callable[[], Record]]
    maybe_start_auto_optimize_training_locked: Callable[[], Callable[[Record], None]]

@dataclass(frozen=True)
class ProcessingArtifacts:
    output_write_dir_for_owner: Callable[[], Callable[[str, str], Path]]
    safe_record_id: Callable[[], Callable[[str], str]]
    auto_optimize_generate_labels_for_sample: Callable[[], LabelGenerator]
    bounded_text: Callable[[], Callable[[Any, int], str]]
    auto_optimize_generate_synthetic_batch_for_sample: Callable[[], Callable[[str, Record, Record], list[Record]]]

@dataclass(frozen=True)
class ProcessingExecution:
    image_generation_settings: Callable[[], Callable[[], Record]]
    AUTO_OPTIMIZE_MASK_MAX_PARALLEL: Callable[[], int]
    ThreadPoolExecutor: Callable[[], ExecutorFactory]
    as_completed: Callable[[], Callable[[Iterable[Future[Record]]], Iterator[Future[Record]]]]
    auto_optimize_process_label_sample: Callable[[], Callable[[str, Record, Record, str], Record]]
