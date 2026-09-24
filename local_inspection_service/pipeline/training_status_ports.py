"""Late-resolved collaborators for pipeline training-job status views."""
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

Record = dict[str, Any]
JobLoader = Callable[[Path], Record | None]


@dataclass(frozen=True)
class TrainingJobLookup:
    load: Callable[[], JobLoader]
    path: Callable[[], Callable[[str], Path]]
    public: Callable[[], Callable[[Record], Record]]
    linked: Callable[[], Callable[[Record, JobLoader | None], Record | None]]


@dataclass(frozen=True)
class TrainingStatusEffects:
    orchestration: Callable[[], Callable[[Record], Record]]
    set_stage: Callable[[], Callable[[Record, str, str, int], Any]]