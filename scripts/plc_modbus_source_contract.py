"""Owner-approved exact feature inverse for immutable pre-Modbus oracles.

Every changed and added product source is checked before restoring historical
source locations. Product code never imports this test helper. Unknown source
or fixture edits fail; actual protocol/state behavior has independent tests.
"""
from admin_user_data_source_contract import checkpoint_bytes
import hashlib
import json
from pathlib import Path
from plc_global_protocol_source_contract import global_parent_bytes
ROOT = Path(__file__).resolve().parents[1]
FIXTURE_SHA256 = "9731e314bda530aa9efdbd2e11f6a4627d89dd274ab4d0e1bd353bfc4b982916"

def checked_fixture():
    raw = (ROOT / "tests/backend_contract/modbus_auto_delta.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == FIXTURE_SHA256, "Unreviewed Modbus delta"
    fixture = json.loads(raw)
    assert fixture["schema"] == 1 and fixture["parent"] == "25c96812dfaaa14144432850455b6d1d708a44af"
    for path, change in fixture["files"].items():
        assert hashlib.sha256(checkpoint_bytes(path, global_parent_bytes(path,(ROOT / path).read_bytes()))).hexdigest() == change["current_sha256"], "Modbus descendant changed: " + path
    for path, expected in fixture["added_sources"].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == expected, "Modbus adapter changed: " + path
    return fixture

def restore_modbus_business(path, actual):
    actual = global_parent_bytes(path, actual)
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
