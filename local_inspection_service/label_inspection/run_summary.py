"""Conservative proof of the fields consumed by native label list histories.

Version must change when projection semantics, validation, or consumed fields
change. A rejected proof leaves the original payload as the read fallback.
"""
import json
import math
from .projection import public

VERSION = 1
MAX_BYTES = 256 * 1024
MAX_DEPTH = 64
DISCARDED = ("model", "prompt_hash", "layout", "transformations", "profile_snapshot")


def _integer(token):
    # Python permits configured decoder limits as low as 640 digits. A cached
    # row must remain decodable on every supported Web/worker process.
    if len(token.lstrip("-")) > 512:
        raise ValueError("Integer outside summary proof bound")
    return int(token)


def _float(token):
    value = float(token)
    if not math.isfinite(value):
        raise ValueError("Nonfinite summary value")
    return value


def _constant(token):
    raise ValueError("Nonfinite summary constant")


def project(text, identity, owner, task_id):
    if not isinstance(text, str) or len(text) > MAX_BYTES:
        return None
    try:
        value = json.loads(text, parse_int=_integer, parse_float=_float, parse_constant=_constant)
        if (not isinstance(value, dict) or value.get("kind") != "run"
                or value.get("id") != identity or value.get("owner_user_id") != owner
                or value.get("task_id") != task_id):
            return None
        stack = [(value, 0)]
        while stack:
            item, depth = stack.pop()
            if depth > MAX_DEPTH:
                return None
            if isinstance(item, dict):
                stack.extend((child, depth + 1) for child in item.values())
            elif isinstance(item, list):
                stack.extend((child, depth + 1) for child in item)
        visible = public(value)  # Includes validation of non-summary import fields.
        stamp = visible["created_at"]
        if (type(stamp) not in (int, float) or not math.isfinite(stamp)
                or abs(stamp) > 2**53 or not isinstance(identity, str) or len(identity) > 256):
            return None
        for key in ("status", "decision"):
            if key in visible and visible[key] is not None:
                if not isinstance(visible[key], str) or len(visible[key]) > 256:
                    return None
        return {key: visible[key] for key in ("id", "created_at", "status", "decision") if key in visible}
    except (ValueError, TypeError, AttributeError, KeyError, RecursionError, OverflowError):
        return None
