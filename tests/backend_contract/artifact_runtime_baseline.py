_lock = threading.Lock()
_runtime = None
_signature = None


def get_runtime() -> ArtifactRuntime | None:
    mode = os.environ.get("VANTALINE_FILE_STORE", "local")
    if mode == "local":
        return None
    if mode not in {"hybrid", "cos"}:
        raise ValueError("VANTALINE_FILE_STORE must be local, hybrid or cos")
    required = ("VANTALINE_DATA_ROOT", "VANTALINE_ARTIFACT_WORK_ROOT", "VANTALINE_ARTIFACT_CACHE_ROOT",
                "VANTALINE_COS_BUCKET", "DATABASE_URL", "CREDENTIALS_DIRECTORY")
    values = tuple(os.environ.get(key, "") for key in required)
    if not all(values):
        raise ValueError("COS storage requires data, work, cache, database and systemd credential configuration")
    hard_limits = os.environ.get("VANTALINE_ARTIFACT_HARD_LIMITS", "0")
    upload_root = os.environ.get("VANTALINE_ARTIFACT_UPLOAD_ROOT", "")
    if hard_limits not in {"0", "1"}:
        raise ValueError("invalid temporary hard-limit setting")
    signature = (mode, *values, hard_limits, upload_root)
    global _runtime, _signature
    with _lock:
        if _runtime is not None:
            if _signature != signature:
                raise RuntimeError("storage configuration changed; restart is required")
            return _runtime
        _runtime = build_runtime(mode, *values, hard_limits=hard_limits == "1", upload_root=upload_root)
        _signature = signature
        return _runtime
