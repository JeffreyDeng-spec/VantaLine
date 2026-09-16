"""Per-process login throttling isolated per composition."""
from collections.abc import Callable
from dataclasses import dataclass
import math
import threading
import time
from fastapi import HTTPException, Request

@dataclass(frozen=True)
class LoginLimitSettings:
    window: int
    max_attempts: int
    lockout: int

def request_client_ip(request: Request) -> str:
    forwarded = str(request.headers.get("x-forwarded-for") or "").split(",", 1)[0].strip()
    if forwarded:
        return forwarded
    return str((request.client.host if request.client else "") or "unknown")

def login_rate_limit_keys(request: Request, username: str) -> list[str]:
    normalized_username = str(username or "").strip().casefold() or "<empty>"
    return [f"user:{normalized_username}", f"ip:{request_client_ip(request)}"]

class LoginRateLimiter:
    def __init__(self, settings: Callable[[], LoginLimitSettings]):
        self.settings = settings
        self.lock = threading.RLock()
        self.failures: dict[str, list[float]] = {}
        self.blocked_until: dict[str, float] = {}

    def prune_login_rate_limit_state(self, now: float) -> None:
        window_start = now - self.settings().window
        for key, attempts in list(self.failures.items()):
            kept = [stamp for stamp in attempts if stamp >= window_start]
            if kept:
                self.failures[key] = kept
            else:
                self.failures.pop(key, None)
        for key, blocked_until in list(self.blocked_until.items()):
            if blocked_until <= now:
                self.blocked_until.pop(key, None)

    def enforce_login_rate_limit(self, request: Request, username: str) -> None:
        now = time.time()
        with self.lock:
            self.prune_login_rate_limit_state(now)
            retry_after = 0
            for key in login_rate_limit_keys(request, username):
                blocked_until = float(self.blocked_until.get(key) or 0.0)
                if blocked_until > now:
                    retry_after = max(retry_after, int(math.ceil(blocked_until - now)))
            if retry_after > 0:
                raise HTTPException(
                    status_code=429,
                    detail="Too many login attempts. Please try again later.",
                    headers={"Retry-After": str(retry_after)},
                )

    def record_failed_login_attempt(self, request: Request, username: str) -> None:
        now = time.time()
        with self.lock:
            self.prune_login_rate_limit_state(now)
            for key in login_rate_limit_keys(request, username):
                attempts = self.failures.setdefault(key, [])
                attempts.append(now)
                attempts[:] = [stamp for stamp in attempts if stamp >= now - self.settings().window]
                if len(attempts) >= self.settings().max_attempts:
                    self.blocked_until[key] = max(float(self.blocked_until.get(key) or 0.0), now + self.settings().lockout)

    def clear_failed_login_attempts(self, request: Request, username: str) -> None:
        with self.lock:
            for key in login_rate_limit_keys(request, username):
                self.failures.pop(key, None)
                self.blocked_until.pop(key, None)
