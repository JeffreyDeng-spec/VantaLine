"""Request-scoped identity and explicit permission checks."""
from typing import Any
from fastapi import HTTPException
from ..runtime.identity import RequestIdentity
from .policy import user_has_permission, user_is_admin


class AccessControl:
    def __init__(self, identity: RequestIdentity):
        self.identity = identity


    def current_auth_user(self) -> dict[str, Any]:
        user = self.identity.get()
        if not user:
            raise HTTPException(status_code=401, detail="Authentication required")
        return user


    def require_admin_role(self, detail: str = "Admin role required") -> dict[str, Any]:
        user = self.current_auth_user()
        if not user_is_admin(user):
            raise HTTPException(status_code=403, detail=detail)
        return user


    def require_permission(self, permission: str, *, detail: str = "Permission denied") -> None:
        if not user_has_permission(self.current_auth_user(), permission):
            raise HTTPException(status_code=403, detail=detail)
