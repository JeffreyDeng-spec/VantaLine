"""Legacy PLC config diagnostics; no configuration write or serial I/O."""
from typing import Any

from .config_diagnostics_ports import (
    ConfigAccess, ConfigDisplay, ConfigErrors, ConfigRuntime, ConfigSources,
)


class ConfigDiagnostics:
    def __init__(self, sources: ConfigSources, display: ConfigDisplay,
                 runtime: ConfigRuntime, access: ConfigAccess, errors: ConfigErrors) -> None:
        self.sources = sources
        self.display = display
        self.runtime = runtime
        self.access = access
        self.errors = errors

    def update(self, request: Any) -> dict[str, Any]:
        self.access.require_permission()("system_settings")
        raise self.errors.http_error()(
            status_code=410,
            detail="legacy_server_serial_config_is_read_only_use_workstation_config",
        )

    def response(self, config: dict[str, Any] | None = None) -> dict[str, Any]:
        current = config if isinstance(config, dict) else self.sources.load()()
        try:
            settings = self.sources.normalize()(self.sources.raw_namespace()(current))
            validation_error = ""
        except self.errors.config_error() as exc:
            settings = dict(self.sources.defaults())
            validation_error = str(exc)
        capability_errors = self.sources.activation_errors()(settings) if not validation_error else []
        if capability_errors:
            validation_error = capability_errors[0]["code"]
        records = list(reversed(self.sources.dispatch_audit()(current)))[:self.runtime.audit_limit()]
        active_attempts = self.runtime.active_attempts()()
        return {
            "config": settings,
            "resolved_addresses": {
                "result_register": self.display.logical_address()(settings["result_register"]),
                "output_control_point": (
                    self.display.logical_address()(settings["output_control_point"])
                    if settings["output_control_point"] else ""
                ),
                "capture_input_register": (
                    self.display.logical_address()(settings["capture_input_register"])
                    if settings["capture_input_register"] else ""
                ),
            },
            "device_profile_verified": self.display.device_verified()(settings),
            "read_profile_verified": self.display.read_verified()(settings),
            "protocol_options": [{"id": self.runtime.protocol_id(), "label": "三菱 FX 编程口（ASCII）"}],
            "recent_dispatches": records,
            "validation_error": validation_error,
            "validation_errors": (
                capability_errors
                if capability_errors
                else ([{"code": "invalid_plc_config", "message": validation_error}] if validation_error else [])
            ),
            "effective_enabled": bool(settings.get("enabled")) if not validation_error else False,
            "control_generation": int(current.get(self.runtime.generation_key()) or 0),
            "in_flight_attempts": active_attempts,
            "disable_notice": "关闭后不会开始新的重试或目标指令；已经进入底层串口调用的单次操作无法被强制撤回。",
            "queue_wait_seconds": self.runtime.queue_wait_seconds(),
            "worker_total_timeout_seconds": self.runtime.worker_total_timeout_seconds(),
        }
