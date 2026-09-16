"""Text inspection request shapes; defaults and coercion match the existing API."""
from typing import Any
from pydantic import BaseModel


class IncomingTextRulesRequest(BaseModel):
    rules: list[dict[str, Any]]
    activate: bool = False


class IncomingTextReviewRequest(BaseModel):
    decision: str
    reason: str
