"""Register the five original workstation-management routes in place."""
from typing import Any, Callable


def register_workstation_management_routes(
    app: Any,
    *,
    get_workstation: Callable[..., Any],
    list_workstations: Callable[..., Any],
    pair_workstation: Callable[..., Any],
    update_config: Callable[..., Any],
    verify_profile: Callable[..., Any],
) -> None:
    app.get("/api/plc/workstation")(get_workstation)
    app.get("/api/plc/workstations")(list_workstations)
    app.post("/api/plc/workstations/pair")(pair_workstation)
    app.post("/api/plc/workstation/config")(update_config)
    app.post("/api/plc/workstation/profile-verification")(verify_profile)
