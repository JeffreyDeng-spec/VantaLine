"""Direct detection rule capabilities; identity and config are read per call."""
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol
Record = dict[str, Any]
class Clock(Protocol):
    def time(self) -> float: ...
@dataclass(frozen=True)
class RulePolicy:
    task_rule_id: Callable[[Any], str]
    CLASS_NAMES: Mapping[int, str]
@dataclass(frozen=True)
class RuleStore:
    load_config: Callable[[], Record]
    save_config: Callable[[Record], None]
    list_trained_model_specs: Callable[[Record], list[Record]]
    time: Clock
@dataclass(frozen=True)
class RuleAccess:
    current_auth_user: Callable[[], Record]
    record_visible_to_user: Callable[[Record, Record], bool]
