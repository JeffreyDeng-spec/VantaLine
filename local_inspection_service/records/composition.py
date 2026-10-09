"""Explicit record identity, ownership and audit composition."""
from collections.abc import Callable
from typing import Any
from ..runtime.identity import RequestIdentity
from .access import RecordAccess
from .audit import RecordAudit
from .ownership import RecordOwnership


class RecordServices:
    def __init__(self, *, identity: RequestIdentity, legacy_owner: str, system_owner: str,
                 current_user: Callable[[], dict[str, Any]],
                 find_user: Callable[[str], dict[str, Any] | None]):
        self.ownership = RecordOwnership(legacy_owner, system_owner)
        self.audit = RecordAudit(self.ownership)
        self.access = RecordAccess(identity, self.ownership, current_user, find_user)
