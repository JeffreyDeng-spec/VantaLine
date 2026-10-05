"""Compose the authentication domain without retaining request or DB state."""
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
import threading
from ..runtime.identity import RequestIdentity
from ..storage.postgres_runtime_repository import PostgresRuntimeRepository
from .access import AccessControl
from .accounts import AccountDependencies, AccountService
from .credentials import PasswordHasher
from .flows import AuthFlows
from .login_limits import LoginLimitSettings, LoginRateLimiter
from .repository import AuthRepository, AuthStoreDependencies
from .sessions import SessionDependencies, SessionService, SessionSettings
from .users import UserService


@dataclass(frozen=True)
class AuthenticationStorage:
    directory: Callable[[], Path]
    path: Callable[[], Path]
    repository: Callable[[], PostgresRuntimeRepository | None]


@dataclass(frozen=True)
class AuthenticationSettings:
    password_iterations: Callable[[], int]
    sessions: Callable[[], SessionSettings]
    login_limits: Callable[[], LoginLimitSettings]
    legacy_owner: Callable[[], str]


class AuthenticationServices:
    def __init__(self, *, storage: AuthenticationStorage,
                 settings: AuthenticationSettings, identity: RequestIdentity):
        self.write_lock = threading.RLock()
        self.hasher = PasswordHasher(settings.password_iterations)
        self.repository = AuthRepository(AuthStoreDependencies(
            storage.directory, storage.path, storage.repository, lambda: self.write_lock,
        ))
        self.accounts = AccountService(AccountDependencies(
            self.repository.load_auth_store, self.repository.save_auth_store,
            self.hasher.password_hash,
        ))
        self.sessions = SessionService(settings.sessions, SessionDependencies(
            storage.repository, self.repository.load_auth_store,
            self.accounts.bootstrap_admin_from_env,
            self.repository.save_auth_session_touch_or_prune,
        ))
        self.access = AccessControl(identity)
        self.limits = LoginRateLimiter(settings.login_limits)
        postgres = lambda: storage.repository() is not None
        self.users = UserService(self.repository, self.accounts, self.access,
                                 postgres=postgres, write_lock=lambda: self.write_lock)
        self.flows = AuthFlows(self.repository, self.accounts, self.sessions, self.limits,
                               postgres=postgres, legacy_owner=settings.legacy_owner)
