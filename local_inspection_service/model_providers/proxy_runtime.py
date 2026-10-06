"""Proxy resolution and provider URL transport, without application imports."""
from dataclasses import dataclass
from typing import Any
import urllib.request
from urllib.parse import urlsplit
from fastapi import HTTPException
from .proxy_runtime_ports import ProxySettings, ProxyCalls, ProxyTransports

AI_LOCAL_PROXY_URL = "http://127.0.0.1:17890"

@dataclass(frozen=True)
class ProviderProxyRuntime:
    settings: ProxySettings
    calls: ProxyCalls
    transports: ProxyTransports

    def ai_proxy_url_from_environment(self) -> tuple[str, str]:
        for name in self.settings.AI_PROXY_ENV_NAMES():
            value = self.transports.os().environ.get(name, "").strip()
            if not value:
                continue
            try:
                return self.calls.validate_ai_proxy_url()(value), name
            except HTTPException:
                return "", name
        return "", ""


    def local_proxy_available(self, proxy_url: str = AI_LOCAL_PROXY_URL) -> bool:
        parsed = urlsplit(str(proxy_url or "").strip())
        host = parsed.hostname or ""
        port = parsed.port
        if not host or not port:
            return False
        try:
            with self.transports.socket().create_connection((host, port), timeout=0.15):
                return True
        except OSError:
            return False


    def env_flag_enabled(self, name: str, default: bool = True) -> bool:
        raw = self.transports.os().environ.get(name)
        if raw is None:
            return default
        return str(raw).strip().lower() not in {"0", "false", "no", "off", "disabled"}


    def ai_proxy_url_from_config(self, local: dict[str, Any], provider: str) -> tuple[str, str, bool]:
        proxy_url, proxy_source_name = self.calls.ai_proxy_url_from_environment()()
        if proxy_url:
            return proxy_url, proxy_source_name, False
        configured_proxy = str(local.get("proxy_url") or "").strip()
        if configured_proxy:
            try:
                return self.calls.validate_ai_proxy_url()(configured_proxy), "ai_config.local.proxy_url", False
            except HTTPException:
                return "", "ai_config.local.proxy_url_invalid", False
        auto_local_enabled = bool(local.get("auto_local_proxy", True)) and self.calls.env_flag_enabled()(self.settings.AI_AUTO_LOCAL_PROXY_ENV(), True)
        if provider == "gemini" and auto_local_enabled and self.calls.local_proxy_available()(self.settings.AI_LOCAL_PROXY_URL()):
            return self.settings.AI_LOCAL_PROXY_URL(), "auto_local_mihomo", True
        return "", "", False


    def ai_urlopen(self, request: urllib.request.Request, settings: dict[str, Any], *, timeout: float):
        proxy_url = str(settings.get("proxy_url_raw") or settings.get("proxy_url") or "").strip()
        if not proxy_url:
            return self.transports.urllib().request.urlopen(request, timeout=timeout)
        opener = self.transports.urllib().request.build_opener(self.transports.urllib().request.ProxyHandler({"http": proxy_url, "https": proxy_url}))
        return opener.open(request, timeout=timeout)
