"""Register the existing legacy PLC config endpoints in original order."""
from typing import Any, Callable


def register_config_diagnostics_routes(
    app: Any,
    *,
    get_config: Callable[..., Any],
    update_config: Callable[..., Any],
) -> None:
    app.get("/api/plc/config")(get_config)
    app.post("/api/plc/config")(update_config)
