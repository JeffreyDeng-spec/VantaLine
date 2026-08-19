"""SQLite dry-run connection helpers for the VantaLine data-layer migration."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from .schema import SCHEMA_VERSION, TABLES


def connect_sqlite(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def apply_schema(conn: sqlite3.Connection) -> None:
    for table in TABLES:
        conn.execute(table.ddl)
        for index in table.indexes:
            conn.execute(index)
    conn.execute(
        """
        INSERT OR REPLACE INTO schema_migrations (version, applied_at, metadata_json)
        VALUES (?, ?, ?)
        """,
        (
            SCHEMA_VERSION,
            int(time.time()),
            json.dumps({"schema_version": SCHEMA_VERSION}, sort_keys=True),
        ),
    )
    conn.commit()


def table_counts(conn: sqlite3.Connection) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table in TABLES:
        row = conn.execute(f"SELECT COUNT(*) AS count FROM {table.name}").fetchone()
        counts[table.name] = int(row["count"] if row else 0)
    return counts


def fetch_all(conn: sqlite3.Connection, table_name: str) -> list[dict[str, Any]]:
    rows = conn.execute(f"SELECT * FROM {table_name}").fetchall()
    return [dict(row) for row in rows]
