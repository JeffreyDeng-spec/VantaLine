"""Existing origin admission and public runtime URL/path projection policy."""
from dataclasses import dataclass
import ipaddress
import re
from typing import Any
from urllib.parse import urlsplit
from .public_network_ports import OriginPolicy, PublicEndpointPolicy, RuntimeDetailAccess

@dataclass(frozen=True)
class PublicNetworkPolicy:
    origins: OriginPolicy
    endpoints: PublicEndpointPolicy
    access: RuntimeDetailAccess

    def normalize_origin(self, value: str) -> str:
        parsed = urlsplit(value)
        if not parsed.scheme or not parsed.netloc:
            return ""
        scheme = parsed.scheme.lower()
        hostname = (parsed.hostname or "").lower()
        if not hostname:
            return ""
        port = parsed.port
        default_port = 443 if scheme == "https" else 80
        netloc = hostname if port in (None, default_port) else f"{hostname}:{port}"
        return f"{scheme}://{netloc}"


    def same_origin(self, origin: str, host: str) -> bool:
        parsed_origin = urlsplit(origin)
        if not parsed_origin.scheme or not parsed_origin.netloc:
            return False
        parsed_host = urlsplit(f"{parsed_origin.scheme}://{host}")
        return (parsed_origin.hostname or "").lower() == (parsed_host.hostname or "").lower() and (
            parsed_origin.port or (443 if parsed_origin.scheme == "https" else 80)
        ) == (parsed_host.port or (443 if parsed_origin.scheme == "https" else 80))


    def cors_origin_allowed(self, origin: str) -> bool:
        normalized = self.origins.normalize_origin()(origin)
        if not normalized:
            return False
        if normalized in {self.origins.normalize_origin()(item) for item in self.origins.CORS_ORIGINS()}:
            return True
        return re.match(self.origins.CORS_ORIGIN_REGEX(), normalized) is not None


    def is_private_or_local_host(self, hostname: str) -> bool:
        host = str(hostname or "").strip().lower()
        if not host:
            return False
        if host in {"localhost", "127.0.0.1", "::1"}:
            return True
        try:
            ip_value = ipaddress.ip_address(host)
        except ValueError:
            return host.endswith(".local")
        return any(
            (
                ip_value.is_private,
                ip_value.is_loopback,
                ip_value.is_link_local,
                ip_value.is_reserved,
            )
        )


    def sanitize_url_for_public_user(self, value: Any) -> str:
        raw = str(value or "").strip()
        if not raw:
            return ""
        parsed = urlsplit(raw)
        if not parsed.scheme or not parsed.netloc:
            return ""
        if self.endpoints.is_private_or_local_host()(parsed.hostname or ""):
            return ""
        return self.endpoints.masked_url_for_status()(raw)


    def sanitize_path_for_public_user(self, value: Any) -> str:
        raw = str(value or "").strip()
        if not raw:
            return ""
        if raw.startswith("/"):
            return ""
        normalized = raw.replace("\\", "/")
        if re.match(r"^[A-Za-z]:/", normalized):
            return ""
        return raw


    def include_internal_runtime_details(self, user: dict[str, Any] | None) -> bool:
        viewer = user or {}
        return self.access.user_is_admin()(viewer) or self.access.user_has_permission()(viewer, "system_settings")
