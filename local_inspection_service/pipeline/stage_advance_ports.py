"""Late-resolved collaborators for one pipeline stage transition."""
from dataclasses import dataclass
from typing import Any, Callable

Record = dict[str, Any]
Getter = Callable[[], Callable[..., Any]]


@dataclass(frozen=True)
class StageAdvancePolicy:
    detection_method: Getter
    consume_recommendation: Getter
    recommend: Getter
    canonical_accessories: Getter
    orchestration: Getter
    pause: Getter
    training_quality: Getter
    link_model: Getter
    http_error: Callable[[], type[Exception]]
    cancelled_error: Callable[[], type[Exception]]


@dataclass(frozen=True)
class StageAdvanceAssets:
    load_config: Getter
    save_config: Getter
    activate_ai: Getter
    prepare: Getter
    materialize: Getter
    normalize: Getter


@dataclass(frozen=True)
class StageAdvanceJobs:
    request_type: Getter
    sample_generation: Getter
    training: Getter
    task_name: Getter
    log_samples: Getter
    log_training: Getter


@dataclass(frozen=True)
class StageAdvanceRuntime:
    persist_progress: Getter
    monotonic: Getter
    clock: Getter
    print: Getter
