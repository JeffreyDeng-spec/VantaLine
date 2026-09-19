"""Explicit legacy settings store service without application imports."""
from typing import Any
from .settings_ports import AgentSettingsDefaults, AgentSettingsPaths, AgentSettingsCodec, AgentSettingsFiles, AgentSettingsPersistence


class LegacyAgentSettingsStore:
    def __init__(self, defaults: AgentSettingsDefaults, paths: AgentSettingsPaths, codec: AgentSettingsCodec, files: AgentSettingsFiles, policy: AgentSettingsPersistence) -> None:
        self._defaults = defaults
        self._paths = paths
        self._codec = codec
        self._files = files
        self._policy = policy

    def _legacy_load_agent_config(self) -> dict[str, Any]:
        merged = dict(self._defaults.config())
        provider_present = False
        if self._paths.file().exists():
            try:
                raw = self._codec.loads()(self._paths.file().read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    provider_present = "provider" in raw
                    merged.update({key: raw[key] for key in self._defaults.config() if key in raw})
            except (OSError, self._codec.decode_error()):
                pass
        if not provider_present:
            merged.pop("provider", None)
        return self._policy.normalize()(merged)

    def save_agent_config(self, config: dict[str, Any]) -> None:
        self._paths.directory().mkdir(parents=True, exist_ok=True)
        config = self._policy.normalize()(config)
        config["api_keys"] = self._policy.persist()(self._policy.keys()(config), "VANTALINE_AGENT_KEY")
        config["api_key"] = ""
        payload = {key: config.get(key, self._defaults.config()[key]) for key in self._defaults.config()}
        payload["api_key"] = ""
        tmp_path = self._paths.file().with_name(f"{self._paths.file().name}.tmp")
        tmp_path.write_text(self._codec.dumps()(payload, indent=2), encoding="utf-8")
        self._files.replace()(tmp_path, self._paths.file())
        try:
            self._files.chmod()(self._paths.file(), 0o600)
        except OSError:
            pass
