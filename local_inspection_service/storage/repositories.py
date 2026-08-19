"""Minimal insert helpers for migration scripts.

These helpers are intentionally not imported by the FastAPI runtime. They keep
SQL construction centralized for the dry-run migrator and smoke tests.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from typing import Any

from .schema import columns_for_table


def insert_rows(conn: sqlite3.Connection, table_name: str, rows: Iterable[dict[str, Any]]) -> int:
    columns = columns_for_table(table_name)
    placeholders = ", ".join("?" for _ in columns)
    column_sql = ", ".join(columns)
    sql = f"INSERT INTO {table_name} ({column_sql}) VALUES ({placeholders})"
    count = 0
    for row in rows:
        values = [row.get(column) for column in columns]
        conn.execute(sql, values)
        count += 1
    return count


def insert_row(conn: sqlite3.Connection, table_name: str, row: dict[str, Any]) -> None:
    insert_rows(conn, table_name, [row])
