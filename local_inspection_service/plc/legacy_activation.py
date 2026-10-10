"""Retained server-serial readiness policy; never opens transport or starts workers."""
from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass
import hashlib
import hmac
from typing import Any

Record = dict[str, Any]


@dataclass(frozen=True)
class LegacyActivationSources:
    repository: Callable[[], Callable[[], object | None]]
    transport: Callable[[], Callable[..., Any] | None]
    identity: Callable[[], ContextVar[Record | None]]
    getenv: Callable[[], Callable[[str], str | None]]
    canonical: Callable[[], Callable[[Record], str]]


@dataclass(frozen=True)
class LegacyActivationChecks:
    coordination: Callable[[], Callable[[], bool]]
    fingerprint: Callable[[], Callable[..., str]]
    device: Callable[[], Callable[[Record | None], bool]]
    read: Callable[[], Callable[[Record | None], bool]]
    serial: Callable[[], Callable[[], bool]]


@dataclass(frozen=True)
class LegacyActivationPolicy:
    sources: LegacyActivationSources
    checks: LegacyActivationChecks

    def plc_pg_coordination_available(self) -> bool:
        repository = self.sources.repository()()
        # Generic namespace CAS is not enough to fence physical I/O across hosts.
        # Production stays closed until the repository supplies a DB-clock, atomic
        # owner+attempt transition primitive reviewed against the real deployment.
        return repository is not None and callable(
            getattr(repository, "mutate_plc_fenced_attempt_with_db_time", None)
        )

    def plc_profile_fingerprint(self, settings: dict[str, Any], *, include_read: bool) -> str:
        fields = [
            "protocol", "checksum_mode", "serial_port", "baudrate", "parity",
            "data_bits", "stop_bits", "result_register", "output_control_point",
        ]
        if include_read:
            fields.extend(["capture_input_register", "capture_trigger_value"])
        material = {field: settings.get(field) for field in fields}
        return hashlib.sha256(self.sources.canonical()(material).encode("ascii")).hexdigest()

    def plc_device_profile_verified(self, settings: dict[str, Any] | None = None) -> bool:
        if self.sources.transport() is not None:
            return True
        expected = str(self.sources.getenv()("VANTALINE_PLC_DEVICE_PROFILE_FINGERPRINT") or "").strip().lower()
        return bool(settings is not None and expected and hmac.compare_digest(expected, self.checks.fingerprint()(settings, include_read=False)))

    def plc_read_profile_verified(self, settings: dict[str, Any] | None = None) -> bool:
        if self.sources.transport() is not None:
            return True
        expected = str(self.sources.getenv()("VANTALINE_PLC_READ_PROFILE_FINGERPRINT") or "").strip().lower()
        return bool(settings is not None and expected and hmac.compare_digest(expected, self.checks.fingerprint()(settings, include_read=True)))

    def plc_serial_dependency_available(self) -> bool:
        if self.sources.transport() is not None and self.sources.identity().get() is not None:
            return True
        try:
            import serial  # type: ignore[import-not-found]  # noqa: F401
        except ImportError:
            return False
        return True

    def plc_activation_errors(self, settings: dict[str, Any]) -> list[dict[str, str]]:
        if not settings.get("enabled"):
            return []
        errors: list[dict[str, str]] = []
        if not self.checks.coordination()():
            errors.append({"code": "plc_pg_coordination_unavailable", "message": "PostgreSQL PLC 多实例协调不可用"})
        if not self.checks.serial()():
            errors.append({"code": "plc_serial_dependency_missing", "message": "生产部署未安装锁定版本的 pyserial"})
        if not self.checks.device()(settings):
            errors.append({"code": "plc_device_profile_unverified", "message": "现场 PLC 型号、地址范围和写协议尚未验证"})
        if settings.get("capture_trigger_enabled") and not self.checks.read()(settings):
            errors.append({"code": "plc_read_profile_unverified", "message": "现场 PLC 输入寄存器读取帧和字节序尚未验证"})
        return errors
