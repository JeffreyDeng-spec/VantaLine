"""Thin catalog HTTP routes, registered at their original position."""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from fastapi import FastAPI
from .catalog import AccessoryCatalog


@dataclass(frozen=True)
class CatalogRoutes:
    get_accessories: Callable[..., dict[str, Any]]
    get_accessory_detail: Callable[[str], dict[str, Any]]


def register_catalog_api(app: FastAPI, catalog: AccessoryCatalog) -> CatalogRoutes:
    @app.get("/api/accessories")
    def get_accessories(view: str = "summary", summary: bool = True, user_id: str | None = None) -> dict[str, Any]:
        return catalog.get_accessories(view, summary, user_id)

    @app.get("/api/accessories/{accessory_id}/detail")
    def get_accessory_detail(accessory_id: str) -> dict[str, Any]:
        return catalog.get_accessory_detail(accessory_id)

    return CatalogRoutes(get_accessories, get_accessory_detail)
