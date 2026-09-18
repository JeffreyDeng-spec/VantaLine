"""Ordered accessory aliases and first-match lookup through explicit identity policies."""
from collections.abc import Callable
from typing import Any

Record = dict[str, Any]


class AccessoryLookup:
    def __init__(self, uid: Callable[[Record], str], legacy: Callable[[Record], str]):
        self.uid, self.legacy = uid, legacy

    def accessory_lookup_by_id(self, config: dict[str, Any]) -> dict[str, dict[str, Any]]:
        lookup: dict[str, dict[str, Any]] = {}
        for item in config.get("accessories", []):
            for raw_id in (item.get("id"), self.uid(item), self.legacy(item)):
                item_id = str(raw_id or "").strip()
                if item_id and item_id not in lookup:
                    lookup[item_id] = item
        return lookup

    def accessory_id_aliases(self, item: dict[str, Any]) -> list[str]:
        aliases: list[str] = []
        seen: set[str] = set()
        for raw_id in (item.get("id"), self.uid(item), self.legacy(item)):
            item_id = str(raw_id or "").strip()
            if item_id and item_id not in seen:
                seen.add(item_id)
                aliases.append(item_id)
        return aliases
