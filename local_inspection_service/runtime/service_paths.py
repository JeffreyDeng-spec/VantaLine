"""Service-relative paths, public path projection and output placement."""
from dataclasses import dataclass
import json
from pathlib import Path, PurePosixPath
import re
import time
import uuid
from typing import Any
from .service_path_ports import ServicePathSettings, PathProjectionPolicy, PathCalls, PathFiles, PathIdentity

@dataclass(frozen=True)
class ServicePaths:
    settings: ServicePathSettings
    policy: PathProjectionPolicy
    calls: PathCalls
    files: PathFiles
    identity: PathIdentity

    def service_rebased_path(self, path: Path) -> Path | None:
        raw = str(path).replace("\\", "/")
        parts = PurePosixPath(raw).parts
        if "assembly_line_optimize" in parts:
            index = parts.index("assembly_line_optimize")
            return self.settings.ROOT().joinpath(*parts[index + 1 :])
        if "local_inspection_service" not in parts:
            return None
        index = parts.index("local_inspection_service")
        return self.settings.ROOT().joinpath(*parts[index:])


    def rebase_stale_local_path_text(self, value: str) -> str:
        text = str(value or "")
        if not text:
            return text
        normalized = text.replace("\\", "/")
        for prefix in self.policy.STALE_REPO_PATH_PREFIXES():
            normalized = normalized.replace(prefix, self.settings.ROOT().as_posix())
        return normalized


    def rebase_stale_local_payload_text(self, text: str) -> str:
        migrated = text
        root_text = self.settings.ROOT().as_posix()
        for prefix in self.policy.STALE_REPO_PATH_PREFIXES():
            normalized_prefix = prefix.replace("\\", "/")
            variants = {
                prefix,
                normalized_prefix,
                normalized_prefix.replace("/", "\\/"),
            }
            if ":" in normalized_prefix:
                variants.add(normalized_prefix.replace("/", "\\\\"))
            for variant in variants:
                replacement = root_text.replace("/", "\\/") if "\\/" in variant else root_text
                migrated = migrated.replace(variant, replacement)
        return migrated


    def public_path_sanitized(self, value: Any) -> Any:
        if isinstance(value, dict):
            value = {k:v for k,v in value.items() if k not in {"model_profiles", "profile_snapshot", "secret_ref", "operational"}}
        if isinstance(value, dict):
            return {
                self.calls.rebase_stale_local_path_text()(key) if isinstance(key, str) else key: self.calls.public_path_sanitized()(item)
                for key, item in value.items()
                if key not in self.policy.REMOVED_PHASE1_PUBLIC_CONFIG_KEYS()
            }
        if isinstance(value, list):
            return [self.calls.public_path_sanitized()(item) for item in value]
        if isinstance(value, str):
            return self.calls.rebase_stale_local_path_text()(value)
        return value


    def migrate_json_file_paths(self, path: Path) -> bool:
        try:
            raw_text = self.files._business_files().read_text(path, encoding="utf-8")
        except OSError:
            return False
        try:
            original = json.loads(raw_text)
        except json.JSONDecodeError:
            migrated_text = self.calls.rebase_stale_local_payload_text()(raw_text)
            if migrated_text == raw_text:
                return False
            try:
                self.files._business_files().write_text(path, migrated_text, encoding="utf-8")
            except OSError:
                return False
            return True
        migrated = self.calls.public_path_sanitized()(original)
        if migrated == original:
            return False
        try:
            self.files._business_files().write_text(path, json.dumps(migrated, indent=2), encoding="utf-8")
        except OSError:
            return False
        return True


    def resolve_service_path(self, value: Any, *, for_write: bool = False) -> Path:
        raw = self.calls.rebase_stale_local_path_text()(str(value or "")).strip()
        if not raw:
            return Path("")
        path = Path(raw).expanduser()
        rebased = self.calls.service_rebased_path()(path)
        if for_write and rebased is not None:
            return rebased

        candidates: list[Path] = []
        if rebased is not None:
            candidates.append(rebased)
        if path.is_absolute():
            candidates.append(path)
        else:
            candidates.extend([self.settings.APP_DIR() / path, self.settings.ROOT() / path, path])

        seen: set[str] = set()
        for candidate in candidates:
            key = str(candidate)
            if key in seen:
                continue
            seen.add(key)
            if self.files._business_files().exists(candidate):
                return candidate.resolve()
        return candidates[0]


    def path_is_under(self, path: Path, root: Path) -> bool:
        try:
            path.resolve().relative_to(root.resolve())
            return True
        except ValueError:
            return False


    def public_output_url(self, path: Path) -> str:
        resolved = self.calls.resolve_service_path()(path, for_write=True)
        try:
            return f"/outputs/{resolved.relative_to(self.settings.OUTPUT_DIR()).as_posix()}"
        except ValueError:
            return ""


    def public_output_url_for_existing(self, path: Path) -> str:
        resolved = self.calls.resolve_service_path()(path)
        return self.calls.public_output_url()(resolved) if self.files._business_files().exists(resolved) and self.calls.path_is_under()(resolved, self.settings.OUTPUT_DIR()) else ""


    def output_write_dir(self, kind: str = "") -> Path:
        user = self.identity._request_user().get()
        return self.calls.output_write_dir_for_owner()(kind, user["id"] if user and not self.identity.user_is_admin()(user) else "")


    def output_write_dir_for_owner(self, kind: str = "", owner_user_id: str = "") -> Path:
        safe_kind = re.sub(r"[^a-zA-Z0-9_.-]+", "_", str(kind or "").strip()).strip("._")
        clean_owner = str(owner_user_id or "").strip()
        if clean_owner and clean_owner not in {self.policy.LEGACY_OWNER_ID(), self.policy.SYSTEM_OWNER_ID()}:
            root = self.settings.OUTPUT_DIR() / "users" / clean_owner
        else:
            root = self.settings.OUTPUT_DIR()
        target = root / safe_kind if safe_kind else root
        target.mkdir(parents=True, exist_ok=True)
        return target


    def output_url(self, path: Path) -> str:
        resolved = self.calls.resolve_service_path()(path, for_write=True)
        try:
            return f"/outputs/{resolved.relative_to(self.settings.OUTPUT_DIR()).as_posix()}"
        except ValueError:
            return ""


def safe_name(filename: str) -> str:
    stem = Path(filename).stem.replace(" ", "_")[:80] or "upload"
    suffix = Path(filename).suffix.lower() or ".bin"
    return f"{int(time.time())}_{uuid.uuid4().hex[:8]}_{stem}{suffix}"
