"""Immutable label runtime identity; no Web import or environment-based mode switch."""
from dataclasses import dataclass
import json
from pathlib import Path
import re


class RuntimeUnavailable(RuntimeError):
    """Fixed operational error; never include database or filesystem details."""


@dataclass(frozen=True)
class LabelRuntimeIdentity:
    commit: str
    release: str
    mode: str
    config_revision: str | None = None

    def __post_init__(self):
        if (not isinstance(self.commit, str) or not re.fullmatch(r"[0-9a-f]{40}", self.commit)
                or not isinstance(self.release, str) or not re.fullmatch(r"v[0-9]{4}\.[0-9]{2}\.[0-9]+", self.release)
                or self.mode not in ("embedded", "external")
                or (self.config_revision is not None and (not isinstance(self.config_revision, str)
                    or not re.fullmatch(r"[0-9a-f]{64}", self.config_revision)))
                or (self.mode == "external" and self.config_revision is None)):
            raise RuntimeUnavailable("Invalid label runtime identity")


def read_identity(root: Path) -> LabelRuntimeIdentity | None:
    path = root / "RUNTIME_TOPOLOGY.json"
    if not path.exists():
        # Source checkout; managed production packages always contain the manifest.
        return None
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        version = json.loads((root / "VERSION.json").read_text(encoding="utf-8"))
        commit = version["git_commit"]
        embedded = {"schema": 1, "git_commit": commit, "worker_mode": "embedded", "services": ["vantaline"]}
        if manifest == embedded and type(manifest.get("schema")) is int:
            return None
        expected = {**embedded, "schema": 2, "runtime_protocol": 1}
        if manifest != expected or type(manifest.get("schema")) is not int or type(manifest.get("runtime_protocol")) is not int:
            raise RuntimeUnavailable("Unsupported label runtime topology")
        return LabelRuntimeIdentity(commit, version["release"], "embedded")
    except (OSError, ValueError, KeyError, TypeError):
        raise RuntimeUnavailable("Label runtime identity unavailable") from None
