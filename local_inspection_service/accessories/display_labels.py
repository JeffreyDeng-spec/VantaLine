"""Accessory display naming and size labels."""
from typing import Any
import re
from .display_label_ports import DisplayLabelPolicy, DisplayLabelText

def profile_size_text(size: dict[str, Any] | None) -> str:
    if not isinstance(size, dict):
        return "size=unknown"
    if size.get("kind") == "paper":
        return f"paper {size.get('preset') or 'custom'} {size.get('width_mm', '?')}x{size.get('height_mm', '?')}mm"
    if size.get("kind") == "object":
        return f"object {size.get('length_mm', '?')}x{size.get('width_mm', '?')}x{size.get('height_mm', '?')}mm"
    return "size=unknown"

class AccessoryLabels:
    def __init__(self, policy: DisplayLabelPolicy, text: DisplayLabelText) -> None:
        self._policy = policy
        self._text = text

    def compact_english_accessory_name(self, value: Any, *, max_words: int = 6) -> str:
        text = self._text.bounded()(value, 120)
        if not text or "?" in text or "unknown" in text.lower():
            return ""
        tokens = re.findall(r"[A-Za-z][A-Za-z0-9-]*", text)
        tokens = [token for token in tokens if token.lower() not in self._policy.generic_tokens()]
        if not tokens:
            return ""
        tokens = tokens[: max(1, min(6, int(max_words or 2)))]
        return " ".join(token[:1].upper() + token[1:].lower() for token in tokens)

    def preferred_english_accessory_name(self, item: dict[str, Any]) -> str:
        profiles = [
            item.get("ai_profile") if isinstance(item.get("ai_profile"), dict) else {},
        ]
        for source in [item, *profiles]:
            for key in self._policy.fields():
                name = self._text.compact()(source.get(key) if isinstance(source, dict) else "", max_words=6)
                if name:
                    return name
        for source in [item, *profiles]:
            if not isinstance(source, dict):
                continue
            for key in ("name", "label"):
                name = self._text.compact()(source.get(key), max_words=2)
                if name:
                    return name
        native_name = str(item.get("name") or item.get("label") or "").strip()
        for marker, english_name in self._policy.fallbacks().items():
            if marker and marker in native_name:
                return english_name
        search_parts: list[str] = []
        for source in [item, *profiles]:
            if not isinstance(source, dict):
                continue
            for key in ("description", "visual_signature", "positive_visual_prompt"):
                text = str(source.get(key) or "").strip()
                if text:
                    search_parts.append(text)
            search_parts.extend(self._text.strings()(source.get("tags"), max_items=8))
            search_parts.extend(self._text.strings()(source.get("distinguishing_text"), max_items=8))
        search_text = " ".join(search_parts).lower()
        for phrase, english_name in self._policy.phrases():
            if phrase in search_text:
                return english_name
        for text in search_parts:
            name = self._text.compact()(text, max_words=2)
            if name:
                return name
        return "Accessory"

    def ensure_accessory_english_name(self, item: dict[str, Any]) -> bool:
        english_name = self._text.preferred()(item)
        changed = False
        if item.get("english_name") != english_name:
            item["english_name"] = english_name
            changed = True
        for key in ("ai_profile",):
            profile = item.get(key) if isinstance(item.get(key), dict) else None
            if profile is not None and profile.get("english_name") != english_name:
                profile["english_name"] = english_name
                changed = True
        return changed

    def accessory_display_label(self, item: dict[str, Any]) -> str:
        return self._text.preferred()(item)
