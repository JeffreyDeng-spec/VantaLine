"""Late-resolved access and catalog capabilities for pipeline accessory routes."""
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class PipelineAccessoryAccess:
    current_user: Callable[[], Callable[[], Any]]
    load_config: Callable[[], Callable[[], dict[str, Any]]]
    scope_config: Callable[[], Callable[..., dict[str, Any]]]
    http_error: Callable[[], Callable[..., Exception]]


@dataclass(frozen=True)
class PipelineAccessoryCatalog:
    resolve: Callable[[], Callable[..., Any]]
    add_id: Callable[[], Callable[[str], Any]]
    aliases: Callable[[], Callable[..., Any]]
    remove_id: Callable[[], Callable[[str], Any]]
    public_payload: Callable[[], Callable[..., dict[str, Any]]]