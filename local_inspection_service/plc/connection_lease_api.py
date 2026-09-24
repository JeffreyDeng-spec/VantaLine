"""Register the five existing connection-lease routes in their original order."""
from typing import Any, Callable


def register_connection_lease_routes(
    app: Any,
    *,
    claim: Callable[..., Any],
    activate: Callable[..., Any],
    heartbeat: Callable[..., Any],
    rebind_model: Callable[..., Any],
    disconnect: Callable[..., Any],
) -> None:
    app.post("/api/plc/workstation/connect")(claim)
    app.post("/api/plc/workstation/connect/activate")(activate)
    app.post("/api/plc/workstation/lease/heartbeat")(heartbeat)
    app.post("/api/plc/workstation/lease/rebind-model")(rebind_model)
    app.post("/api/plc/workstation/lease/disconnect")(disconnect)
