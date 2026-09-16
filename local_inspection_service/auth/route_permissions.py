"""Pure HTTP route permission policy; endpoint-local guards remain authoritative."""


def route_required_permission(path: str, method: str) -> str | None:
    clean_path = path.rstrip("/") or "/"
    # Discovery and account-owned operation recovery require authentication,
    # not the administrator's provider-configuration permission.
    if clean_path == "/api/agent/capabilities" or clean_path.startswith("/api/operations/"):
        return None
    plc_admin_routes = {
        ("/api/plc/config", "GET"),
        ("/api/plc/config", "POST"),
        ("/api/plc/workstations/pair", "POST"),
        ("/api/plc/workstations", "GET"),
        ("/api/plc/workstation/config", "POST"),
        ("/api/plc/workstation/profile-verification", "POST"),
    }
    plc_runtime_routes = {
        ("/api/plc/workstation/connect", "POST"),
        ("/api/plc/workstation/connect/activate", "POST"),
        ("/api/plc/workstation/lease/heartbeat", "POST"),
        ("/api/plc/workstation/lease/rebind-model", "POST"),
        ("/api/plc/workstation/lease/disconnect", "POST"),
    }
    if (clean_path, method) in plc_admin_routes:
        return "system_settings"
    if clean_path == "/api/plc/workstation" and method == "GET":
        return "inspection"
    if (clean_path, method) in plc_runtime_routes:
        return "inspection"
    if clean_path.startswith("/api/plc/workstation/dispatches/") and method == "POST":
        suffix = clean_path.rsplit("/", 1)[-1]
        if suffix in {"attempt", "receipt"}:
            return "inspection"
    if clean_path == "/api/docs" or clean_path.startswith("/api/auth/users"):
        return "user_management"
    if clean_path.startswith("/api/windows-worker"):
        return "worker_settings"
    if clean_path.startswith("/api/text-compare-codex"):
        return "inspection"
    if clean_path.startswith("/api/agent"):
        return "agent_config"
    if clean_path.startswith("/api/admin"):
        return "ai_config"
    if clean_path.startswith("/api/ai/config"):
        return "ai_config"
    if clean_path.startswith("/api/stream/config"):
        return "system_settings"
    if clean_path.startswith("/api/plc/capture-"):
        return "inspection"
    if clean_path.startswith("/api/plc"):
        return "system_settings"
    if clean_path.startswith("/api/data-analysis"):
        return "ai_detection"
    if clean_path.startswith("/api/incoming-text/tasks") and (clean_path.endswith("/references") or method in {"PUT", "PATCH", "DELETE"}):
        return "incoming_material_config"
    if clean_path.startswith("/api/incoming-text/references"):
        return "incoming_material_config"
    if clean_path.startswith("/api/incoming-text"):
        return "inspection"
    if clean_path.startswith("/api/text-inspection"):
        return "inspection"
    if clean_path.startswith("/api/text-compare-beta"):
        return "inspection"
    if clean_path.startswith("/api/locateanything") or clean_path.startswith("/api/label-sheets") or clean_path.startswith("/api/experimental/label-inspector"):
        return "system_settings"
    if clean_path.startswith("/api/ai/tasks"):
        return "ai_detection"
    if clean_path == "/api/config" or clean_path.startswith("/api/config/"):
        return "system_settings" if method != "GET" or clean_path == "/api/config" else None
    if clean_path.startswith("/api/accessories"):
        return "accessory_library"
    if clean_path.startswith("/api/training/resources"):
        return "model_library"
    if clean_path.startswith("/api/training") or clean_path.startswith("/api/pipeline") or clean_path.startswith("/api/image-jobs") or clean_path.startswith("/api/image-job-candidates"):
        return "training_pipeline"
    if clean_path.startswith("/api/backgrounds"):
        return "training_pipeline"
    if clean_path.startswith("/api/models"):
        return "inspection"
    if clean_path.startswith("/api/analyze"):
        return "inspection"
    return None


def route_allowed_permissions(path: str, method: str) -> tuple[str, ...]:
    clean_path = path.rstrip("/") or "/"
    permission = route_required_permission(path, method)
    if clean_path.startswith("/api/training/resources"):
        return ("model_library", "training_pipeline")
    if clean_path.startswith("/api/analyze"):
        return ("inspection", "ai_detection")
    if clean_path.startswith("/api/plc/capture-"):
        return ("inspection", "ai_detection")
    if clean_path == "/api/pipeline/tasks" and method == "GET":
        return ("training_pipeline", "incoming_material_config", "inspection")
    if clean_path == "/api/pipeline/tasks" and method == "POST":
        return ("training_pipeline", "incoming_material_config")
    if clean_path.startswith("/api/pipeline/tasks/") and method == "PATCH":
        return ("training_pipeline", "incoming_material_config")
    if clean_path.startswith("/api/pipeline/tasks/") and method == "DELETE":
        return ("training_pipeline", "incoming_material_config")
    if clean_path.startswith("/api/incoming-text/tasks") and method == "GET":
        return ("inspection", "incoming_material_config")
    if clean_path == "/api/plc/workstation" and method == "GET":
        return ("inspection", "ai_detection", "system_settings")
    plc_runtime_routes = {
        ("/api/plc/workstation/connect", "POST"),
        ("/api/plc/workstation/connect/activate", "POST"),
        ("/api/plc/workstation/lease/heartbeat", "POST"),
        ("/api/plc/workstation/lease/rebind-model", "POST"),
        ("/api/plc/workstation/lease/disconnect", "POST"),
    }
    if (clean_path, method) in plc_runtime_routes:
        return ("inspection", "ai_detection")
    if clean_path.startswith("/api/plc/workstation/dispatches/") and method == "POST" and clean_path.rsplit("/", 1)[-1] in {"attempt", "receipt"}:
        return ("inspection", "ai_detection")
    return (permission,) if permission else ()
