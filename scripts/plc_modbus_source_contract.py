"""Owner-approved exact feature inverse for immutable pre-Modbus oracles.

Every changed and added product source is checked before restoring historical
source locations. Product code never imports this test helper. Unknown source
or fixture edits fail; actual protocol/state behavior has independent tests.
"""
import hashlib
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
FIXTURE_SHA256 = "d88c65e5d464217e080bdd020e70a1c1f3811e4863ed8075abb7d280df2f3056"

def checked_fixture():
    raw = (ROOT / "tests/backend_contract/modbus_auto_delta.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == FIXTURE_SHA256, "Unreviewed Modbus delta"
    fixture = json.loads(raw)
    assert fixture["schema"] == 1 and fixture["parent"] == "25c96812dfaaa14144432850455b6d1d708a44af"
    for path, change in fixture["files"].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == change["current_sha256"], "Modbus descendant changed: " + path
    for path, expected in fixture["added_sources"].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == expected, "Modbus adapter changed: " + path
    return fixture

def restore_modbus_business(path, actual):
    change = checked_fixture()["files"].get(path)
    if change is None:
        return actual
    assert hashlib.sha256(actual).hexdigest() == change["current_sha256"], "Modbus descendant changed: " + path
    lines = actual.decode().splitlines(keepends=True)
    for region in reversed(change["regions"]):
        assert "".join(lines[region["start"]:region["end"]]) == region["expected"]
        lines[region["start"]:region["end"]] = region["original"].splitlines(keepends=True)
    restored = "".join(lines).encode()
    assert hashlib.sha256(restored).hexdigest() == change["parent_sha256"], "Modbus inverse changed: " + path
    return restored
