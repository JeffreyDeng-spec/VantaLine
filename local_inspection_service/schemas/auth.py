"""Auth request shapes; defaults and coercion match the existing API."""
from pydantic import BaseModel, Field


class AuthBootstrapRequest(BaseModel):
    username: str
    password: str
    display_name: str | None = None


class AuthLoginRequest(BaseModel):
    username: str
    password: str


class UserCreateRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=300)
    username: str
    password: str
    display_name: str | None = None
    role: str = "user"
    permissions: list[str] = []
    active: bool = True


class UserUpdateRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=300)
    display_name: str | None = None
    password: str | None = None
    role: str | None = None
    permissions: list[str] | None = None
    active: bool | None = None


class UserPasswordResetRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=300)
    password: str | None = None
    generate: bool = False
    revoke_sessions: bool = True


class TaskNavigationPreferencesRequest(BaseModel):
    pinned_task_ids: list[str] = []
    archived_task_ids: list[str] = []
