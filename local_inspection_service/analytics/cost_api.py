"""Administrator-only cost route, mounted explicitly at its original position."""
from collections.abc import Callable
from typing import Any
from fastapi import FastAPI
from .costs import CostLedger


def register_cost_api(app: FastAPI, require_admin: Callable[[], Any], ledger: CostLedger):
    @app.get("/api/admin/api-cost-ledger")
    def get_api_cost_ledger() -> dict[str, Any]:
        require_admin()
        return ledger.summary(ledger.collect_records())

    return get_api_cost_ledger
