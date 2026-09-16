"""Owner-scoped read-only manual history projection; never rewrites old decisions."""

PREFIX = "legacy-manual:"


def rows(repo, owner):
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
    output = []
    for key in keys:
        standard = standards.get(key, {})
        selected = [
            s for s in sessions if (s.get("standard_id") or "orphan-" + s["id"]) == key
        ]
        ids = {s["id"] for s in selected}
        selected_pages = [
            p
            for p in pages
            if p.get("session_id") in ids
            or (p.get("standard_id") or "orphan-" + str(p.get("session_id") or p["id"]))
            == key
        ]
        assets = [
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
