"""Provider configuration policy without application state."""
from typing import Any
from .configuration_ports import PublicUrlCapabilities

class PublicProviderURLs:
    def __init__(self, capabilities: PublicUrlCapabilities) -> None:
        self._capabilities = capabilities

    def public_ai_base_url(self, value: Any) -> str:
        base_url = str(value or "").strip()
        parsed = self._capabilities.split_url()(base_url)
        if not parsed.scheme or not parsed.netloc:
            return self._capabilities.text()(base_url.split("?", 1)[0].split("#", 1)[0], 300)
        host = parsed.hostname or ""
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        try:
            port = f":{parsed.port}" if parsed.port else ""
        except ValueError:
            port = ""
        return self._capabilities.join_url()((parsed.scheme, f"{host}{port}", parsed.path, "", ""))

    def masked_url_for_status(self, value: Any) -> str:
        raw = str(value or "").strip()
        parsed = self._capabilities.split_url()(raw)
        if not parsed.scheme or not parsed.netloc:
            return self._capabilities.text()(raw.split("?", 1)[0].split("#", 1)[0], 300)
        host = parsed.hostname or ""
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        try:
            port = f":{parsed.port}" if parsed.port else ""
        except ValueError:
            port = ""
        username = "****@" if parsed.username or parsed.password else ""
        return self._capabilities.join_url()((parsed.scheme, f"{username}{host}{port}", parsed.path, "", ""))
