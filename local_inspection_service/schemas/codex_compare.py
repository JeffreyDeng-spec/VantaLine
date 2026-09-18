"""Existing Codex single-label and batch HTTP request contracts."""
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal
from ..codex_compare.batch_contracts import MAX_LABELS


class Retry(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: str = Field(pattern=r'^[A-Za-z0-9_.-]{8,128}$')


class Review(Retry):
    decision: Literal['MATCH', 'DIFFERENCES', 'REVIEW_REQUIRED']
    note: str = Field(max_length=4000)


class SelectOrder(Retry):
    standard_id: str = Field(max_length=100)


class Rename(Retry):
    name: str = Field(min_length=1, max_length=120)


class Rerun(Retry):
    label_ids: list[str] = Field(min_length=1, max_length=MAX_LABELS)
    # Optional manual correspondence is frozen into the new batch only.
    matches: dict[str, dict] = Field(default_factory=dict)
