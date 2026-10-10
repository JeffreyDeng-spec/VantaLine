"""Owner-scoped read-only manual history projection; never rewrites old decisions."""

import math

PREFIX = "legacy-manual:"


def rows(repo, owner, *, indexed=False):
    standards = {
        s["id"]: s
        for s in repo.legacy(owner, "standards")
        if s.get("standard_type") == "manual"
    }
    sessions = repo.legacy(owner, "sessions")
    pages = repo.legacy(owner, "pages") + [
        r
        for r in repo.legacy(owner, "records")
        if r.get("standard_type") == "manual" or r.get("standard_id") in standards
    ]
    session_map = {s["id"]: s for s in sessions}
    keys = set(standards) | {
        s.get("standard_id") or "orphan-" + s["id"] for s in sessions
    }
    keys |= {
        session_map.get(p.get("session_id"), {}).get("standard_id")
        or p.get("standard_id")
        or "orphan-" + str(p.get("session_id") or p["id"])
        for p in pages
    }
    indexes = _indexes(repo, owner, standards, sessions, pages, keys) if indexed and len(keys) > 1 else None
    output = []
    for key in keys:
        standard = standards.get(key, {})
        selected = indexes[0].get(key, []) if indexes is not None else [
            s for s in sessions if (s.get("standard_id") or "orphan-" + s["id"]) == key
        ]
        ids = {s["id"] for s in selected}
        selected_pages = indexes[1].get(key, []) if indexes is not None else [
            p
            for p in pages
            if p.get("session_id") in ids
            or (p.get("standard_id") or "orphan-" + str(p.get("session_id") or p["id"]))
            == key
        ]
        assets = indexes[2].get(key, []) if indexes is not None else [
            a for a in repo.legacy(owner, "assets") if a.get("standard_id") == key
        ]
        fields = (
            "id",
            "session_id",
            "standard_asset_id",
            "created_at",
            "updated_at",
            "status",
            "decision",
            "message",
            "differences",
            "expected_page_count",
            "missing_asset_ids",
            "observed_asset_order",
            "expected_asset_order",
            "order_matches",
            "duplicate_capture_detected",
            "final_decision",
            "review_reason",
        )
        output.append(
            {
                "id": PREFIX + key,
                "name": standard.get("name") or "原说明书订单缺失",
                "revision": 0,
                "source": {"type": "legacy_manual"},
                "read_only": True,
                "assets": [],
                "runs": [],
                "standard_count": len(assets),
                "created_at": standard.get("created_at", 0),
                "updated_at": max(
                    [standard.get("updated_at", 0)]
                    + [
                        v.get("updated_at", v.get("created_at", 0))
                        for v in selected + selected_pages
                    ]
                ),
                "missing": None if standard else "原订单关联缺失；仅可查阅已保存历史。",
                "manual_history": {
                    "sessions": [{k: v[k] for k in fields if k in v} for v in selected],
                    "pages": [
                        {
                            **{k: v[k] for k in fields if k in v},
                            "has_photo": bool(v.get("media_path")),
                        }
                        for v in selected_pages
                    ],
                    "standards": [
                        {
                            "id": a["id"],
                            "ordinal": a.get("ordinal"),
                            "url": f"/api/text-inspection/assets/{a['id']}/content",
                        }
                        for a in sorted(assets, key=lambda a: a.get("ordinal", 0))
                    ],
                },
            }
        )
    return output


def resolve(repo, owner, identity):
    key = identity.removeprefix(PREFIX)
    for task in rows(repo, owner):
        history = task["manual_history"]
        if task["id"] == identity or any(
            v["id"] == key for v in history["sessions"] + history["pages"]
        ):
            return task
    raise KeyError(identity)


def _number(value):
    # Avoid converting arbitrary-size JSON integers to float during proof.
    return type(value) is int or (type(value) is float and math.isfinite(value))


def _references(value, names):
    return type(value) is dict and type(value.get("id")) is str and all(
        value.get(name) is None or type(value.get(name)) is str for name in names)


def _timestamps(value):
    return _number(value.get("created_at", 0)) and _number(value.get("updated_at", value.get("created_at", 0)))


def _indexes(repo, owner, standards, sessions, pages, keys):
    """Index only proven ordinary rows from the request-cached repository.

    Unsupported shapes use the original projection and its original errors.
    The caller keeps original key discovery and set iteration unchanged.
    """
    if not all(_references(v, ()) and _timestamps(v) for v in standards.values()):
        return None
    if not all(_references(v, ("standard_id",)) and _timestamps(v) for v in sessions):
        return None
    if not all(_references(v, ("standard_id", "session_id")) and _timestamps(v) for v in pages):
        return None
    assets = repo.legacy(owner, "assets")
    if not all(_references(v, ("standard_id",)) and _number(v.get("ordinal", 0)) for v in assets):
        return None
    sessions_by_key, session_keys, pages_by_key, assets_by_key = {}, {}, {}, {}
    for value in sessions:
        key = value.get("standard_id") or "orphan-" + value["id"]
        sessions_by_key.setdefault(key, []).append(value)
        session_keys.setdefault(value["id"], set()).add(key)
    for value in pages:
        fallback = value.get("standard_id") or "orphan-" + str(value.get("session_id") or value["id"])
        destinations = session_keys.get(value.get("session_id"), set()) | {fallback}
        for key in destinations & keys:
            pages_by_key.setdefault(key, []).append(value)
    for value in assets:
        assets_by_key.setdefault(value.get("standard_id"), []).append(value)
    return sessions_by_key, pages_by_key, assets_by_key
