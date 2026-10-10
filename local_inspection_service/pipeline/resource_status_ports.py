"""Late-resolved resource readers for pipeline availability projection."""
from dataclasses import dataclass
from typing import Any, Callable, Protocol
from pathlib import Path


@dataclass(frozen=True)
class PipelineResourceStatusLinks:
    find_dataset: Callable[[], Callable[[str], tuple[Any, Any]]]
    load_ai_tasks: Callable[[], Callable[[], list[dict[str, Any]]]]
    list_trained_specs: Callable[[], Callable[[], list[dict[str, Any]]]]

class PipelineResourceFiles(Protocol):
    def exists(self, path: Path) -> bool: ...
