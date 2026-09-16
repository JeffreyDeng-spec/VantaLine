"""Request identity follows async context, including native thread-pool dispatch."""
from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Any

User = dict[str, Any]


class RequestIdentity:
    def __init__(self):
        self._user: ContextVar[User | None] = ContextVar('vantaline_request_user', default=None)

    def get(self) -> User | None:
        return self._user.get()

    def set(self, user: User | None) -> Token:
        return self._user.set(user)

    def reset(self, token: Token) -> None:
        self._user.reset(token)

    @contextmanager
    def bind(self, user: User | None):
        token = self.set(user)
        try:
            yield
        finally:
            self.reset(token)
