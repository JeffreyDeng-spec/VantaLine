"""Auth request shapes; defaults and coercion match the existing API."""
from pydantic import BaseModel


class AuthBootstrapRequest(BaseModel):
    username: str
    password: str
    display_name: str | None = None


class AuthLoginRequest(BaseModel):
    username: str
    password: str


class UserCreateRequest(BaseModel):
    username: str
    password: str
    display_name: str | None = None
    role: str = "user"
    permissions: list[str] = []
    active: bool = True


class UserUpdateRequest(BaseModel):
    display_name: str | None = None
    password: str | None = None
    role: str | None = None
    permissions: list[str] | None = None
    active: bool | None = None


class UserPasswordResetRequest(BaseModel):
    password: str | None = None
    generate: bool = False
    revoke_sessions: bool = True


class TaskNavigationPreferencesRequest(BaseModel):
    pinned_task_ids: list[str] = []
    archived_task_ids: list[str] = []
