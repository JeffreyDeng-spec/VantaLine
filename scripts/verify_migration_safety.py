#!/usr/bin/env python3
from __future__ import annotations
import re
from pathlib import Path
root=Path(__file__).resolve().parents[1]
migrations=sorted((root/"local_inspection_service/storage/migrations").glob("*.sql"))
forbidden=re.compile(r"\b(DROP|TRUNCATE)\b|\bALTER\s+TABLE\b[^;]*\b(DROP|RENAME)\b",re.I|re.S)
if not migrations: raise SystemExit("no PostgreSQL migrations found")
for path in migrations:
    sql=path.read_text(encoding="utf-8"); compact=sql.strip().upper()
    executable=re.sub(r"--[^\n]*", "", sql)
    executable=re.sub(r"'(?:''|[^'])*'", "''", executable)
    if not compact.startswith("BEGIN;") or not compact.endswith("COMMIT;"): raise SystemExit(f"migration must be transactional: {path}")
    if forbidden.search(executable): raise SystemExit(f"destructive migration is forbidden: {path}")
    if "FEATURE_MIGRATIONS" not in compact: raise SystemExit(f"migration must record feature_migrations: {path}")
print(f"additive migration policy OK: {len(migrations)} files")
