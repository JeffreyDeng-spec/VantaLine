"""Account-scoped status query; settlement belongs to the injected projection service."""
from collections.abc import Callable
from typing import Any

Record = dict[str, Any]


class TrainingStatusQuery:
    def __init__(self, current: Callable[[], Record], is_admin: Callable[[Record], bool],
                 load: Callable[[], Record], scope: Callable[[], Callable[[Record, Record, str | None], Record]],
                 filtered: Callable[[Record, Record, str | None], Record]):
        self.current, self.is_admin, self.load = current, is_admin, load
        self.scope, self.filtered = scope, filtered

    def training_status(self, user_id: str | None = None) -> dict[str, Any]:
        user = self.current()
        target_user_id = user_id if self.is_admin(user) else None
        config = self.scope()(self.load(), user, target_user_id)
        return self.filtered(config, user, target_user_id)
