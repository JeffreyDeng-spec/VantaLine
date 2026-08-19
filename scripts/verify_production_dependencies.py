#!/usr/bin/env python3
from __future__ import annotations

import importlib.metadata as metadata
import re
import sys
from pathlib import Path


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: verify_production_dependencies.py LOCK")
    for raw in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)==([^\s]+)", line)
        if not match:
            raise SystemExit(f"unsupported lock entry: {line}")
        name, expected = match.groups()
        try:
            actual = metadata.version(name)
        except metadata.PackageNotFoundError as exc:
            raise SystemExit(f"missing production dependency: {name}") from exc
        if actual != expected:
            raise SystemExit(
                f"production dependency mismatch: {name} expected={expected} actual={actual}"
            )
    print("production dependencies match lock")


if __name__ == "__main__":
    main()
