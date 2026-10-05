"""Origin settings and public status visibility capabilities."""
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any
Record = dict[str, Any]
@dataclass(frozen=True)
class OriginPolicy:
    normalize_origin: Callable[[], Callable[[str], str]]
    CORS_ORIGINS: Callable[[], Sequence[str]]
    CORS_ORIGIN_REGEX: Callable[[], str]
@dataclass(frozen=True)
class PublicEndpointPolicy:
    is_private_or_local_host: Callable[[], Callable[[str], bool]]
    masked_url_for_status: Callable[[], Callable[[str], str]]
@dataclass(frozen=True)
class RuntimeDetailAccess:
    user_is_admin: Callable[[], Callable[[Record], bool]]
    user_has_permission: Callable[[], Callable[[Record, str], bool]]
