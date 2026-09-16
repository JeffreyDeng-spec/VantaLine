"""Thin HTTP registrars, preserving the existing documentation-route position."""
from dataclasses import dataclass
from collections.abc import Callable
from typing import Any
from fastapi import FastAPI, Request, Response
from .flows import AuthFlows
from .sessions import SessionService
from .users import UserService
from ..schemas.auth import AuthBootstrapRequest, AuthLoginRequest, TaskNavigationPreferencesRequest, UserCreateRequest, UserUpdateRequest, UserPasswordResetRequest


@dataclass(frozen=True)
class AuthRoutes:
    auth_status: Callable[..., dict[str, Any]]
    auth_bootstrap: Callable[..., dict[str, Any]]
    auth_login: Callable[..., dict[str, Any]]
    auth_logout: Callable[..., dict[str, Any]]
    get_task_navigation_preferences: Callable[..., dict[str, Any]]
    update_task_navigation_preferences: Callable[..., dict[str, Any]]


@dataclass(frozen=True)
class UserRoutes:
    list_users: Callable[..., dict[str, Any]]
    create_user: Callable[..., dict[str, Any]]
    update_user: Callable[..., dict[str, Any]]
    reset_user_password: Callable[..., dict[str, Any]]
    delete_user: Callable[..., dict[str, Any]]


def register_auth_api(app: FastAPI, flows: AuthFlows, sessions: SessionService, users: UserService) -> AuthRoutes:
    @app.get("/api/auth/status")
    def auth_status(request: Request) -> dict[str, Any]:
        return flows.auth_status(request)

    @app.post("/api/auth/bootstrap")
    def auth_bootstrap(request: Request, response: Response, payload: AuthBootstrapRequest) -> dict[str, Any]:
        result, session_id = flows.auth_bootstrap(payload)
        sessions.set_session_cookie(response, request, session_id)
        return result

    @app.post("/api/auth/login")
    def auth_login(request: Request, response: Response, payload: AuthLoginRequest) -> dict[str, Any]:
        result, session_id = flows.auth_login(request, payload)
        sessions.set_session_cookie(response, request, session_id)
        return result

    @app.post("/api/auth/logout")
    def auth_logout(request: Request, response: Response) -> dict[str, Any]:
        result = flows.auth_logout(request.cookies.get(sessions.settings().cookie, ""))
        sessions.clear_session_cookie(response, request)
        return result

    @app.get("/api/user/preferences/tasks")
    def get_task_navigation_preferences() -> dict[str, Any]:
        return users.get_task_navigation_preferences()

    @app.post("/api/user/preferences/tasks")
    def update_task_navigation_preferences(payload: TaskNavigationPreferencesRequest) -> dict[str, Any]:
        return users.update_task_navigation_preferences(payload)

    return AuthRoutes(auth_status, auth_bootstrap, auth_login, auth_logout, get_task_navigation_preferences, update_task_navigation_preferences)


def register_user_api(app: FastAPI, sessions: SessionService, users: UserService) -> UserRoutes:
    @app.get("/api/auth/users")
    def list_users() -> dict[str, Any]:
        return users.list_users()

    @app.post("/api/auth/users")
    def create_user(payload: UserCreateRequest) -> dict[str, Any]:
        return users.create_user(payload)

    @app.patch("/api/auth/users/{user_id}")
    def update_user(user_id: str, payload: UserUpdateRequest, request: Request) -> dict[str, Any]:
        return users.update_user(user_id, payload, request.cookies.get(sessions.settings().cookie, ""))

    @app.post("/api/auth/users/{user_id}/password")
    def reset_user_password(user_id: str, payload: UserPasswordResetRequest, request: Request) -> dict[str, Any]:
        return users.reset_user_password(user_id, payload, request.cookies.get(sessions.settings().cookie, ""))

    @app.delete("/api/auth/users/{user_id}")
    def delete_user(user_id: str) -> dict[str, Any]:
        return users.delete_user(user_id)

    return UserRoutes(list_users, create_user, update_user, reset_user_password, delete_user)
