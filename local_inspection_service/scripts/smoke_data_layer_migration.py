#!/usr/bin/env python3
"""Smoke test for the PR1 JSON-to-SQLite dry-run migrator."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "local_inspection_service" / "scripts" / "migrate_json_to_sqlite.py"


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def run_migrator(source: Path, db_path: Path, report_path: Path, *, allow_repair: bool) -> dict:
    cmd = [
        sys.executable,
        str(SCRIPT_PATH),
        "--source",
        str(source),
        "--db",
        str(db_path),
        "--report",
        str(report_path),
        "--dry-run",
    ]
    if allow_repair:
        cmd.append("--allow-legacy-id-repair")
    result = subprocess.run(cmd, cwd=REPO_ROOT, text=True, capture_output=True, check=True)
    summary = json.loads(result.stdout.strip())
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if summary["report_path"] != str(report_path):
        raise AssertionError("migrator summary reported the wrong report path")
    return report


def build_source(root: Path) -> Path:
    service_root = root / "local_inspection_service"
    data_dir = service_root / "data"
    (data_dir / "uploads").mkdir(parents=True)
    (data_dir / "normalized_assets" / "acc_demo").mkdir(parents=True)
    (data_dir / "uploads" / "source.png").write_bytes(b"not-a-real-png")
    (data_dir / "normalized_assets" / "acc_demo" / "canonical.png").write_bytes(b"not-a-real-png")
    secret_token = "raw-session-token-should-not-leak"
    password_hash = "sha256$public-smoke-password-hash"
    write_json(
        data_dir / "auth.json",
        {
            "users": [
                {
                    "id": "user_demo",
                    "username": "demo",
                    "display_name": "Demo",
                    "role": "admin",
                    "permissions": ["accessories", "ai_detection"],
                    "password_hash": password_hash,
                    "active": True,
                    "created_at": 100,
                    "updated_at": 101,
                }
            ],
            "sessions": {
                secret_token: {
                    "user_id": "user_demo",
                    "created_at": 110,
                    "last_seen_at": 111,
                    "expires_at": 9999999999,
                }
            },
        },
    )
    write_json(
        data_dir / "config.json",
        {
            "active_model_id": "demo-model",
            "image_size": 640,
            "confidence_threshold": 0.4,
            "required_classes": [0],
            "min_counts": {"0": 1},
            "training": {"status": "idle"},
            "accessories": [
                {
                    "class_id": 0,
                    "name": "legacy accessory without id",
                    "status": "active",
                    "material_type": "metal",
                    "owner_user_id": "user_demo",
                    "owner_username": "demo",
                    "source_files": ["uploads/source.png"],
                    "normalized_assets": ["normalized_assets/acc_demo/canonical.png"],
                    "created_at": 120,
                    "updated_at": 121,
                }
            ],
        },
    )
    write_json(
        data_dir / "ai_detection_tasks.json",
        {
            "tasks": [
                {
                    "id": "aitask_demo",
                    "name": "Demo AI",
                    "status": "active",
                    "source": "smoke",
                    "owner_user_id": "user_demo",
                    "owner_username": "demo",
                    "created_at": 130,
                    "updated_at": 131,
                }
            ]
        },
    )
    write_json(
        data_dir / "data_analysis_records.json",
        {
            "records": [
                {
                    "record_id": "record_demo",
                    "owner_user_id": "user_demo",
                    "owner_username": "demo",
                    "created_at": 140,
                    "updated_at": 141,
                    "task": {"id": "aitask_demo"},
                    "source_image": {"path": "uploads/source.png"},
                    "ai_detection_result": {},
                }
            ]
        },
    )
    write_json(data_dir / "pipeline_state.json", {"accessory_ids": [], "pending_candidate_ids": ["cand_demo"]})
    write_json(
        data_dir / "pipeline_tasks.json",
        [
            {
                "id": "pipe_demo",
                "name": "Demo pipeline",
                "status": "queued",
                "stage": "samples",
                "owner_user_id": "user_demo",
                "owner_username": "demo",
                "created_at": 150,
                "updated_at": 151,
            }
        ],
    )
    write_json(
        data_dir / "accessory_candidates" / "cand_demo.json",
        {
            "id": "cand_demo",
            "name": "Candidate",
            "class_id": 0,
            "status": "pending",
            "owner_user_id": "user_demo",
            "owner_username": "demo",
            "source_files": ["uploads/source.png"],
            "normalized_assets": ["normalized_assets/acc_demo/canonical.png"],
            "created_at": 160,
            "updated_at": 161,
        },
    )
    write_json(
        data_dir / "training_tasks" / "train_demo.json",
        {
            "task_id": "train_demo",
            "job_id": "job_demo",
            "action": "train",
            "status": "queued",
            "queue_kind": "training",
            "owner_user_id": "user_demo",
            "owner_username": "demo",
            "created_at": 170,
            "updated_at": 171,
        },
    )
    write_json(
        data_dir / "auto_optimize" / "aitask_demo.json",
        {
            "task_id": "aitask_demo",
            "status": "running",
            "owner_user_id": "user_demo",
            "owner_username": "demo",
            "created_at": 180,
            "updated_at": 181,
        },
    )
    write_json(data_dir / "ai_config.local.json", {"api_key": "provider-key-should-not-leak"})
    write_json(data_dir / "agent_config.local.json", {"token": "agent-token-should-not-leak"})
    (data_dir / "runtime_secrets.local.env").write_text("INSPECTION_AI_API_KEY=env-secret-should-not-leak\n", encoding="utf-8")
    return service_root


def assert_blocker(report: dict, code: str) -> None:
    if not any(error.get("code") == code for error in report.get("blocking_errors", [])):
        raise AssertionError(f"expected blocker {code}, got {report.get('blocking_errors')}")


def assert_warning(report: dict, code: str) -> None:
    if not any(warning.get("code") == code for warning in report.get("warnings", [])):
        raise AssertionError(f"expected warning {code}, got {report.get('warnings')}")


def assert_no_blockers(report: dict) -> None:
    if report.get("blocking_errors"):
        raise AssertionError(f"expected no blockers, got {report['blocking_errors']}")


def make_active_orphan_source(root: Path) -> Path:
    source = build_source(root)
    data_dir = source / "data"
    tasks = read_json(data_dir / "ai_detection_tasks.json")
    if not isinstance(tasks, dict):
        raise AssertionError("AI task fixture root should be a dict")
    tasks["tasks"][0]["selected_accessory_ids"] = ["missing_active_accessory"]
    tasks["tasks"][0]["status"] = "active"
    write_json(data_dir / "ai_detection_tasks.json", tasks)
    records = read_json(data_dir / "data_analysis_records.json")
    if not isinstance(records, dict):
        raise AssertionError("data-analysis fixture root should be a dict")
    records["records"].append(
        {
            "record_id": "record_active_orphan",
            "status": "active",
            "owner_user_id": "user_demo",
            "owner_username": "demo",
            "created_at": 190,
            "updated_at": 191,
            "task": {"id": "missing_active_ai_task"},
            "source_image": {"path": "uploads/source.png"},
        }
    )
    write_json(data_dir / "data_analysis_records.json", records)
    return source


def make_active_missing_path_source(root: Path) -> Path:
    source = build_source(root)
    data_dir = source / "data"
    config = read_json(data_dir / "config.json")
    if not isinstance(config, dict):
        raise AssertionError("config fixture root should be a dict")
    config["accessories"][0]["status"] = "active"
    config["accessories"][0]["source_files"] = ["uploads/missing-active-source.png"]
    write_json(data_dir / "config.json", config)
    return source


def make_historical_warning_source(root: Path) -> Path:
    source = build_source(root)
    data_dir = source / "data"
    records = read_json(data_dir / "data_analysis_records.json")
    if not isinstance(records, dict):
        raise AssertionError("data-analysis fixture root should be a dict")
    records["records"].append(
        {
            "record_id": "record_historical_missing",
            "status": "completed",
            "owner_user_id": "user_demo",
            "owner_username": "demo",
            "created_at": 200,
            "updated_at": 201,
            "task": {"id": "missing_historical_ai_task"},
            "source_image": {"path": "uploads/missing-historical-source.png"},
        }
    )
    write_json(data_dir / "data_analysis_records.json", records)
    return source


def make_recoverable_extra_data_source(root: Path) -> Path:
    source = build_source(root)
    candidate_path = source / "data" / "accessory_candidates" / "cand_demo.json"
    candidate_path.write_text(candidate_path.read_text(encoding="utf-8") + "\n" + '{"partial": true}', encoding="utf-8")
    return source


def assert_report_safe(report_path: Path, db_path: Path) -> None:
    report_text = report_path.read_text(encoding="utf-8")
    db_text = db_path.read_bytes().decode("utf-8", errors="ignore")
    forbidden_report_values = [
        "raw-session-token-should-not-leak",
        "sha256$public-smoke-password-hash",
        "provider-key-should-not-leak",
        "agent-token-should-not-leak",
        "env-secret-should-not-leak",
    ]
    forbidden_db_values = [
        "raw-session-token-should-not-leak",
        "provider-key-should-not-leak",
        "agent-token-should-not-leak",
        "env-secret-should-not-leak",
    ]
    for value in forbidden_report_values:
        if value in report_text:
            raise AssertionError(f"redacted report leaked sensitive value: {value}")
    for value in forbidden_db_values:
        if value in db_text:
            raise AssertionError(f"database leaked sensitive value: {value}")


def assert_db_shape(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute("SELECT password_hash FROM users WHERE id = 'user_demo'").fetchone()
        if not row or row[0] != "sha256$public-smoke-password-hash":
            raise AssertionError("user password_hash did not migrate to users table")
        session = conn.execute("SELECT id_hash, raw_json FROM auth_sessions").fetchone()
        if not session or len(session[0]) != 64 or "raw-session-token-should-not-leak" in session[1]:
            raise AssertionError("auth session token was not stored as hash-only")
        config_rows = conn.execute("SELECT COUNT(*) FROM app_config").fetchone()[0]
        if config_rows < 5:
            raise AssertionError("app_config rows were not populated from config.json")
    finally:
        conn.close()


def main() -> int:
    real_default_db = REPO_ROOT / "local_inspection_service" / "data" / "vantaline.sqlite3"
    real_default_db_existed = real_default_db.exists()
    with tempfile.TemporaryDirectory(prefix="vantaline_data_layer_smoke_") as tmp_raw:
        root = Path(tmp_raw)
        source = build_source(root)
        blocked_report = root / "blocked_report.json"
        blocked_db = root / "blocked.sqlite3"
        blocked = run_migrator(source, blocked_db, blocked_report, allow_repair=False)
        if not any(error["code"] == "legacy_id_repair_required" for error in blocked["blocking_errors"]):
            raise AssertionError("missing legacy accessory id did not produce a code-defined blocker")

        active_orphan = run_migrator(
            make_active_orphan_source(root / "active_orphan"),
            root / "active_orphan.sqlite3",
            root / "active_orphan_report.json",
            allow_repair=True,
        )
        assert_blocker(active_orphan, "active_orphan_reference")
        if not active_orphan["orphan_counts"]:
            raise AssertionError("active orphan link was not counted")

        active_missing_path = run_migrator(
            make_active_missing_path_source(root / "active_missing_path"),
            root / "active_missing_path.sqlite3",
            root / "active_missing_path_report.json",
            allow_repair=True,
        )
        assert_blocker(active_missing_path, "active_missing_path")
        if not active_missing_path["missing_path_counts"]:
            raise AssertionError("active missing path was not counted")

        historical_warning = run_migrator(
            make_historical_warning_source(root / "historical_warning"),
            root / "historical_warning.sqlite3",
            root / "historical_warning_report.json",
            allow_repair=True,
        )
        assert_no_blockers(historical_warning)
        assert_warning(historical_warning, "historical_orphan_reference")
        assert_warning(historical_warning, "historical_missing_path")

        recovered_extra = run_migrator(
            make_recoverable_extra_data_source(root / "recoverable_extra"),
            root / "recoverable_extra.sqlite3",
            root / "recoverable_extra_report.json",
            allow_repair=True,
        )
        if recovered_extra.get("source_errors"):
            raise AssertionError(f"recoverable accessory candidate extra data should not be a source error: {recovered_extra['source_errors']}")
        if not any(item.get("warning") == "recovered_accessory_candidate_extra_data" for item in recovered_extra.get("source_warnings", [])):
            raise AssertionError(f"recoverable extra data was not reported as a source warning: {recovered_extra.get('source_warnings')}")

        report_a = root / "report_a.json"
        report_b = root / "report_b.json"
        db_a = root / "dry_run_a.sqlite3"
        db_b = root / "dry_run_b.sqlite3"
        migrated_a = run_migrator(source, db_a, report_a, allow_repair=True)
        migrated_b = run_migrator(source, db_b, report_b, allow_repair=True)
        if migrated_a["blocking_errors"] or migrated_a["source_errors"]:
            raise AssertionError(f"dry-run should be clean after legacy repair: {migrated_a['blocking_errors']} {migrated_a['source_errors']}")
        if sha256(report_a) != sha256(report_b):
            raise AssertionError("migration reports are not deterministic across identical dry-runs")
        if migrated_a["row_counts"]["app_config"] < 5:
            raise AssertionError("app_config table was not populated")
        if migrated_a["row_counts"]["auth_sessions"] != 1:
            raise AssertionError("auth_sessions table count mismatch")
        if migrated_a["row_counts"]["accessories"] != 1 or not migrated_a["legacy_repairs"]:
            raise AssertionError("legacy accessory id repair did not migrate exactly one accessory")
        assert_report_safe(report_a, db_a)
        assert_db_shape(db_a)
    if not real_default_db_existed and real_default_db.exists():
        raise AssertionError("smoke test created the real local default SQLite DB")
    print("data-layer migration smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
