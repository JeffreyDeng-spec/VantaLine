#!/usr/bin/env python3
from __future__ import annotations
import re
from pathlib import Path
root=Path(__file__).resolve().parents[1]
migrations=sorted((root/"local_inspection_service/storage/migrations").glob("*.sql"))
forbidden=re.compile(r"\b(DROP|TRUNCATE|ALTER|REVOKE|GRANT|CALL|EXECUTE|UPDATE)\b|\bDO\s+\$|\bDELETE\s+FROM\b|\bCREATE\s+OR\s+REPLACE\b",re.I|re.S)

def validate_sql(sql: str, label: str) -> None:
    compact=sql.strip().upper()
    executable=re.sub(r"--[^\n]*", "", sql)
    executable=re.sub(r"'(?:''|[^'])*'", "''", executable)
    if not compact.startswith("BEGIN;") or not compact.endswith("COMMIT;"): raise ValueError(f"migration must be transactional: {label}")
    if forbidden.search(executable): raise ValueError(f"destructive migration is forbidden: {label}")
    if "FEATURE_MIGRATIONS" not in compact: raise ValueError(f"migration must record feature_migrations: {label}")

def main() -> None:
    if not migrations: raise SystemExit("no PostgreSQL migrations found")
    try:
        for path in migrations: validate_sql(path.read_text(encoding="utf-8"), str(path))
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print(f"additive migration policy OK: {len(migrations)} files")

if __name__ == "__main__": main()
