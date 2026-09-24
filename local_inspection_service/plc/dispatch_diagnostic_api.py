"""Register five existing PLC dispatch/diagnostic routes in original order."""
from typing import Any, Callable


def register_dispatch_diagnostic_routes(
    app: Any,
    *,
    declare_attempt: Callable[..., Any],
    diagnostic_plan: Callable[..., Any],
    diagnostic_receipt: Callable[..., Any],
    diagnostic_confirm: Callable[..., Any],
    record_receipt: Callable[..., Any],
) -> None:
    app.post("/api/plc/workstation/dispatches/{dispatch_id}/attempt")(declare_attempt)
    app.post("/api/plc/workstation/diagnostic-plan")(diagnostic_plan)
    app.post("/api/plc/workstation/diagnostic-receipt")(diagnostic_receipt)
    app.post("/api/plc/workstation/diagnostic-confirm")(diagnostic_confirm)
    app.post("/api/plc/workstation/dispatches/{dispatch_id}/receipt")(record_receipt)
