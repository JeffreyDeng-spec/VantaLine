# Frozen full tasks endpoint from fdb3ce9fbe90ff445b5818758a42aa3eb808b9d4.
@app.get(PREFIX + "/tasks")
def tasks(
    q: str = Query("", max_length=200),
    source: str = Query(
        "all", pattern="^(all|word|image|pdf|legacy|legacy_manual|beta)$"
    ),
    result: str = Query("all", pattern="^(all|MATCH|DIFFERENCES|REVIEW_REQUIRED)$"),
    cursor: str = Query("", max_length=512),
    limit: int = Query(20, ge=1, le=100),
):
    owner, repo, _ = context()

    def work():
        filters = {"q": q, "source": source, "result": result}
        if cursor:
            return repo.page(owner, [], filters, limit, cursor)
        current = repo.list(owner, "task")
        standards, records = legacy_data(repo, owner)
        extended = {x.get("legacy_id") for x in current}
        ids = set(standards) | {
            x.get("standard_id") or "orphan-" + x["id"] for x in records
        }
        legacy_records = {}
        for record in records:
            sid = record.get("standard_id") or "orphan-" + record["id"]
            legacy_records.setdefault(sid, []).append(record)
        indexed = standards, records, legacy_records
        current += [
            legacy_task(repo, owner, "legacy:" + sid, indexed) for sid in ids - extended
        ]
        rows = []
        for offset in range(0, len(current), RUN_BATCH_SIZE):
            batch = current[offset : offset + RUN_BATCH_SIZE]
            run_ids = [
                task["id"] for task in batch
                if not task.get("read_only") and task.get("revision") and task.get("id")
            ]
            native_runs = repo.list_run_payloads_for_tasks(owner, run_ids) if run_ids else {}
            for task in batch:
                runs = histories(
                    repo, owner, task,
                    native_runs.get(task["id"], []) if task.get("id") else None,
                    legacy_records,
                )
                latest = runs[0] if runs else {}
                rows.append(
                    {
                        "id": task["id"],
                        "name": task["name"],
                        "source": (
                            "legacy"
                            if task.get("legacy_id")
                            else (task.get("source") or {}).get("type", "word")
                        ),
                        "updated_at": max(
                            task.get("updated_at", 0), latest.get("created_at", 0)
                        ),
                        "standard_count": len(task["assets"]),
                        "run_count": len(runs),
                        "decision": latest.get("decision", "REVIEW_REQUIRED"),
                        "status": latest.get("status", task.get("status", "ready")),
                    }
                )
            del native_runs
        for task in manual_history.rows(repo, owner):
            history = task["manual_history"]
            records = history["pages"]
            latest = max(records, key=lambda v: v.get("created_at", 0), default={})
            rows.append(
                {
                    "id": task["id"],
                    "name": task["name"],
                    "source": "legacy_manual",
                    "updated_at": task["updated_at"],
                    "standard_count": task["standard_count"],
                    "run_count": len(records),
                    "decision": latest.get("decision", "REVIEW_REQUIRED"),
                    "status": "read_only",
                }
            )
        for beta in repo.legacy(owner, "beta"):
            inputs = beta.get("inputs") or {}
            batch = beta.get("report_version") == "label-batch-v3"
            rows.append(
                {
                    "id": "beta:" + beta["id"],
                    "name": inputs.get("standard_name") or "标签检查 Beta",
                    "source": "beta",
                    "updated_at": beta.get("updated_at")
                    or beta.get("created_at", 0),
                    "standard_count": (
                        len(inputs.get("references", {})) if batch else 1
                    ),
                    "run_count": len(beta.get("labels", {})) if batch else 1,
                    "decision": (beta.get("summary") or {}).get(
                        "decision", "REVIEW_REQUIRED"
                    ),
                    "status": beta.get("status", ""),
                    "url": "/workspace/text-compare-codex?"
                    + ("batch=" if batch else "task=")
                    + beta["id"],
                }
            )
        rows = [
            x
            for x in rows
            if q.lower() in x["name"].lower()
            and (source == "all" or source == x["source"])
            and (result == "all" or result == x["decision"])
        ]
        rows.sort(key=lambda x: (x["updated_at"], x["id"]), reverse=True)
        return repo.page(owner, rows, filters, limit)

    return call(work)
