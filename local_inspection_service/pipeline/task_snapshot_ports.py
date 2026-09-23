"""Late-resolved collaborators for pipeline task label and name projection."""
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class PipelineTaskSnapshotLinks:
    load_ai_tasks: Callable[[], Callable[[], list[dict[str, Any]]]]
    accessory_lookup: Callable[[], Callable[[dict[str, Any]], dict[str, dict[str, Any]]]]
    label_snapshot: Callable[[], Callable[[dict[str, Any]], dict[str, str]]]