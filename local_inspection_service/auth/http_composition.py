"""Application-bound authentication HTTP composition with explicit external policy."""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from fastapi import FastAPI
from ..runtime.identity import RequestIdentity
from .api import register_auth_api, register_user_api
from .composition import AuthenticationServices
from .docs_api import DocumentationAccess, register_documentation_api
from .middleware import SecurityDependencies, register_security_middleware
from .policy import user_is_admin

Record = dict[str, Any]


@dataclass(frozen=True)
class AuthenticationHttpPolicy:
    output_visible: Callable[[str, Record], bool]
    same_origin: Callable[[str, str], bool]
    cors_origin_allowed: Callable[[str], bool]


class AuthenticationHttp:
    """Build inert dependencies; register each boundary at the application's chosen position."""

    def __init__(self, services: AuthenticationServices, identity: RequestIdentity,
                 policy: AuthenticationHttpPolicy):
        if services.access.identity is not identity:
            raise ValueError('Authentication HTTP identity must belong to its service graph')
        self.services = services
        self.security = SecurityDependencies(
            services.sessions.authenticate_request, services.accounts.users_exist, identity,
            policy.output_visible, policy.same_origin, policy.cors_origin_allowed,
        )
        self.documentation = DocumentationAccess(
            self.security.authenticate, self.security.users_exist, user_is_admin,
        )

    def register_security(self, app: FastAPI):
        return register_security_middleware(app, self.security)

    def register_auth(self, app: FastAPI):
        return register_auth_api(app, self.services.flows, self.services.sessions, self.services.users)

    def register_documentation(self, app: FastAPI):
        return register_documentation_api(app, self.documentation.require_docs_admin)

    def register_users(self, app: FastAPI):
        return register_user_api(app, self.services.sessions, self.services.users)
