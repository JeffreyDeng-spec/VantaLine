#!/usr/bin/env python3
"""Validate VantaLine's human/agent documentation contract."""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "docs" / "contract.json"
LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")


def fail(errors: list[str], message: str) -> None:
    errors.append(message)


def matches(path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def git_output(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, text=True, encoding="utf-8", errors="replace",
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "git command failed")
    return result.stdout


def changed_files(base_ref: str) -> list[str]:
    changed = {line for line in git_output("diff", "--name-only", base_ref, "--").splitlines() if line}
    changed.update(line for line in git_output("ls-files", "--others", "--exclude-standard").splitlines() if line)
    return sorted(changed)


def server_diff(base_ref: str) -> str:
    return git_output("diff", "--unified=0", base_ref, "--", "local_inspection_service/server.py")


def required_updates(contract: dict, changed: list[str], server_patch: str) -> list[tuple[str, list[str], list[str]]]:
    triggered = []
    for rule in contract["impact_rules"]:
        path_hit = any(matches(path, rule.get("paths", [])) for path in changed)
        regex_hit = bool(rule.get("server_diff_regex") and re.search(rule["server_diff_regex"], server_patch))
        if path_hit or regex_hit:
            triggered.append((rule["name"], rule.get("required_docs", []), rule.get("required_any", [])))
    return triggered


def validate_links(errors: list[str], markdown_path: Path) -> None:
    text = markdown_path.read_text(encoding="utf-8")
    for raw in LINK_RE.findall(text):
        target = raw.strip().split("#", 1)[0]
        if not target or target.startswith(("http://", "https://", "mailto:")):
            continue
        resolved = (markdown_path.parent / target).resolve()
        try:
            resolved.relative_to(ROOT.resolve())
        except ValueError:
            fail(errors, f"{markdown_path.relative_to(ROOT)}: link escapes repository: {raw}")
            continue
        if not resolved.exists():
            fail(errors, f"{markdown_path.relative_to(ROOT)}: broken local link: {raw}")


def validate(base_ref: str | None) -> list[str]:
    errors: list[str] = []
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    protocol = json.loads((ROOT / "release" / "plc-protocol.json").read_text(encoding="utf-8"))["web_serial_protocol"]
    if protocol != contract["protocol"]:
        fail(errors, f"docs protocol {contract['protocol']} != release protocol {protocol}")

    entry_docs = set(contract["entry_docs"])
    authoritative_docs = set(contract["authoritative_docs"])
    historical_docs = set(contract["historical_docs"])
    classified = entry_docs | authoritative_docs | historical_docs
    discovered = {line.replace("\\", "/") for line in git_output("ls-files", "*.md").splitlines() if line}
    discovered.update(line.replace("\\", "/") for line in git_output("ls-files", "--others", "--exclude-standard", "--", "*.md").splitlines() if line)
    for relative in sorted(discovered - classified):
        fail(errors, f"unclassified Markdown document: {relative}")
    for relative in sorted(classified - discovered):
        fail(errors, f"classified Markdown document is missing/untracked: {relative}")

    for relative in sorted(classified):
        if not (ROOT / relative).is_file():
            fail(errors, f"missing classified documentation entry: {relative}")
    for relative in contract["authoritative_docs"]:
        path = ROOT / relative
        if path.is_file() and "**Status: Authoritative" not in path.read_text(encoding="utf-8"):
            fail(errors, f"authoritative status missing: {relative}")
    index_path = ROOT / "docs" / "README.md"
    indexed: set[str] = set()
    if index_path.is_file():
        for raw in LINK_RE.findall(index_path.read_text(encoding="utf-8")):
            target = raw.strip().split("#", 1)[0]
            if not target or target.startswith(("http://", "https://", "mailto:")):
                continue
            resolved = (index_path.parent / target).resolve()
            try:
                indexed.add(resolved.relative_to(ROOT.resolve()).as_posix())
            except ValueError:
                continue
    for relative in sorted(authoritative_docs - {"docs/README.md"} - indexed):
        fail(errors, f"authoritative document missing from docs/README.md index: {relative}")

    for relative, replacement in contract["historical_docs"].items():
        path = ROOT / relative
        if not path.is_file():
            fail(errors, f"historical document missing: {relative}")
            continue
        text = path.read_text(encoding="utf-8")
        if "Historical / Do not implement" not in text or replacement not in text:
            fail(errors, f"historical header/replacement missing: {relative}")

    for relative in sorted(classified):
        path = ROOT / relative
        if path.suffix.lower() == ".md" and path.is_file():
            validate_links(errors, path)

    current_text = "\n".join((ROOT / path).read_text(encoding="utf-8") for path in contract["authoritative_docs"] if (ROOT / path).is_file()).lower()
    forbidden = ["current server-side pyserial dispatcher", "current plc input poller"]
    for phrase in forbidden:
        if phrase in current_text:
            fail(errors, f"authoritative docs describe retired behavior: {phrase}")

    if base_ref:
        changed = changed_files(base_ref)
        changed_set = set(changed)
        patch = server_diff(base_ref) if "local_inspection_service/server.py" in changed_set else ""
        for name, required, required_any in required_updates(contract, changed, patch):
            missing = [doc for doc in required if doc not in changed_set]
            if missing:
                fail(errors, f"{name}: code changed without required docs: {', '.join(missing)}")
            if required_any and not changed_set.intersection(required_any):
                fail(errors, f"{name}: update at least one of: {', '.join(required_any)}")
    return errors


def self_test() -> None:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    cases = [
        (["local_inspection_service/frontend/src/features/plc/x.ts"], "", "PLC and camera dispatch"),
        (["local_inspection_service/storage/repo.py"], "", "PostgreSQL and migrations"),
        (["scripts/bootstrap_release_host.sh"], "", "Release and deployment"),
        (["local_inspection_service/server.py"], "+ permission check", "API authentication permissions and configuration"),
        (["local_inspection_service/frontend/src/features/plc/nested/client.ts"], "", "PLC and camera dispatch"),
        (["local_inspection_service/scripts/smoke_postgres_new.py"], "", "PostgreSQL and migrations"),
        (["local_inspection_service/server.py"], "+ harmless refactor", "API authentication permissions and configuration"),

    ]
    for changed, patch, expected in cases:
        names = {item[0] for item in required_updates(contract, changed, patch)}
        if expected not in names:
            raise AssertionError(f"impact fixture did not trigger {expected}")

    unrelated = required_updates(contract, ["models/README.md"], "")
    if unrelated:
        raise AssertionError("unrelated documentation fixture triggered high-risk impact")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-ref", help="Git ref/SHA used for high-risk change impact checks")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
    errors = validate(args.base_ref)
    if errors:
        print("Documentation contract failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("Documentation contract passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
