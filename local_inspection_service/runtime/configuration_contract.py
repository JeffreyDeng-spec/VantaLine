"""Data-only shared label configuration contract, usable by an isolated installer.

No environment access, imports from the application, filesystem writes or execution.
"""
import hashlib
import json
from pathlib import PurePosixPath
import re

CONFIGURATION_ENVIRONMENT = (
    "VANTALINE_DATA_STORE", "DATABASE_URL", "VANTALINE_LABEL_INSPECTION_ENABLED",
    "VANTALINE_FILE_STORE", "VANTALINE_DATA_ROOT", "VANTALINE_ARTIFACT_WORK_ROOT",
    "VANTALINE_ARTIFACT_CACHE_ROOT", "VANTALINE_ARTIFACT_UPLOAD_ROOT",
    "VANTALINE_ARTIFACT_HARD_LIMITS", "VANTALINE_COS_BUCKET", "TMPDIR",
    "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
    "http_proxy", "https_proxy", "all_proxy", "no_proxy",
    "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE", "SSL_CERT_FILE", "SSL_CERT_DIR",
    "PGHOST", "PGHOSTADDR", "PGPORT", "PGDATABASE", "PGUSER", "PGPASSWORD",
    "PGPASSFILE", "PGSERVICE", "PGSERVICEFILE", "PGOPTIONS", "PGAPPNAME",
    "PGSSLMODE", "PGSSLROOTCERT", "PGSSLCERT", "PGSSLKEY", "PGSSLCRL",
    "PGCONNECT_TIMEOUT", "PGTARGETSESSIONATTRS", "PGGSSENCMODE",
)
CONFIGURATION_LIMIT = 256 * 1024


class ConfigurationError(RuntimeError):
    """Fixed text only: configuration may contain credentials."""


def configuration_bytes(value):
    try:
        raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                         allow_nan=False).encode("ascii")
        if len(raw) > CONFIGURATION_LIMIT:
            raise ValueError()
        return raw
    except (TypeError, ValueError, OverflowError, RecursionError):
        raise ConfigurationError("Runtime configuration is invalid") from None


def configuration_validate(value):
    if (not isinstance(value, dict) or value.keys() != {"schema", "environment", "data_directory",
            "profile_environment", "cos_credential_sha256"}
            or type(value["schema"]) is not int or value["schema"] != 1):
        raise ConfigurationError("Runtime configuration is invalid")
    environment, profiles = value["environment"], value["profile_environment"]
    if not isinstance(environment, dict) or environment.keys() != set(CONFIGURATION_ENVIRONMENT):
        raise ConfigurationError("Runtime configuration environment is invalid")
    if (not isinstance(profiles, dict) or len(profiles) > 1024 or any(
            not isinstance(key, str) or not re.fullmatch(r"VANTALINE_PROFILE_[A-F0-9]{32}", key)
            for key in profiles)):
        raise ConfigurationError("Runtime model-secret references are invalid")
    for item in environment.values():
        if item is not None and (not isinstance(item, str) or "\x00" in item or len(item) > 16384):
            raise ConfigurationError("Runtime configuration environment is invalid")
    for item in profiles.values():
        if not isinstance(item, str) or "\x00" in item or len(item) > 16384:
            raise ConfigurationError("Runtime model-secret references are invalid")
    directory = value["data_directory"]
    if (not isinstance(directory, str) or not directory.startswith("/") or "\x00" in directory
            or len(directory) > 4096 or ".." in PurePosixPath(directory).parts):
        raise ConfigurationError("Runtime data directory is invalid")
    if ((environment["VANTALINE_DATA_STORE"] or "").strip().lower() != "postgres"
            or not (environment["DATABASE_URL"] or "").strip()):
        raise ConfigurationError("Runtime PostgreSQL configuration is required")
    mode = environment["VANTALINE_FILE_STORE"]
    mode = "local" if mode is None else mode
    credential = value["cos_credential_sha256"]
    if mode not in ("local", "hybrid", "cos"):
        raise ConfigurationError("Runtime storage mode is invalid")
    if mode == "local":
        if credential is not None:
            raise ConfigurationError("Unexpected runtime storage credential")
    else:
        if not isinstance(credential, str) or not re.fullmatch("[0-9a-f]{64}", credential):
            raise ConfigurationError("Runtime storage credential is required")
        for key in ("VANTALINE_DATA_ROOT", "VANTALINE_ARTIFACT_WORK_ROOT", "VANTALINE_ARTIFACT_CACHE_ROOT", "VANTALINE_COS_BUCKET"):
            if not environment[key]:
                raise ConfigurationError("Runtime storage configuration is incomplete")
    return hashlib.sha256(configuration_bytes(value)).hexdigest()


def configuration_capture(environment, data_directory, *, cos_credential_sha256=None):
    value = {"schema": 1, "environment": {key: environment.get(key) for key in CONFIGURATION_ENVIRONMENT},
             "data_directory": data_directory,
             "profile_environment": {key: item for key, item in environment.items()
                                     if key.startswith("VANTALINE_PROFILE_")},
             "cos_credential_sha256": cos_credential_sha256}
    configuration_validate(value)
    return value
