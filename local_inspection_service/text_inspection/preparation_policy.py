"""Existing preparation admission and immutable asset snapshot policy."""
import copy
import os

PROCESSING = {"recognizing", "classifying", "supplementing"}


def enabled(owner):
    return owner in {v.strip() for v in os.getenv("VANTALINE_STANDARD_PREPARATION_ACCOUNTS", "").split(",") if v.strip()}


def snapshot(assets):
    rows = []
    for a in sorted(assets, key=lambda a: int(a.get("ordinal") or 0)):
        if a.get("status") not in {"candidate", "page"}:
            continue
        active = a.get("active_preparation")
        if a.get("preparation_required") and not active:
            if a.get("preparation_previous_snapshot"):
                rows.append(copy.deepcopy(a["preparation_previous_snapshot"]))
            continue
        value = {k: a.get(k, "") for k in ("id", "sha256", "ordinal", "mime_type")}
        value["ordinal"] = int(value["ordinal"] or 0)
        if active:
            value["preparation"] = copy.deepcopy(active)
            value["reference_sha256"] = active["sha256"]
        rows.append(value)
    return rows
