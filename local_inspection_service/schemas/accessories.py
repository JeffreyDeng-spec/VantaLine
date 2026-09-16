"""Accessories request shapes; defaults and coercion match the existing API."""
from pydantic import BaseModel


class AccessoryFileDeleteRequest(BaseModel):
    source_path: str


class AccessoryAiReferenceRequest(BaseModel):
    source_path: str


class AccessoryTextCropRequest(BaseModel):
    source_path: str
    corners: list[dict[str, float]]


class AccessoryRouteRequest(BaseModel):
    route: str
    apply: bool = True
