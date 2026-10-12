"""Exact global read-only discovery delta over immutable PR #312 sources."""
import hashlib
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
FIXTURE_SHA256="b120c6582e12a1a83242400b742862aa8ee802af4a308425c5c76e9360330054"
def checked_global_fixture():
    raw=(ROOT/"tests/backend_contract/plc_global_protocol_delta.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest()==FIXTURE_SHA256,"Unreviewed global PLC delta"
    fixture=json.loads(raw)
    assert fixture["parent"]=="b7f3c96137c08ed7326e2f86d0bc0c617aa00376" and fixture["schema"]==1
    for path,change in fixture["files"].items():
        assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==change["current_sha256"],"Global PLC owner changed: "+path
    return fixture

def global_parent_bytes(path,actual):
    change=checked_global_fixture()["files"].get(path)
    if change is None:return actual
    digest=hashlib.sha256(actual).hexdigest()
    if digest==change["parent_sha256"]:return actual
    assert digest==change["current_sha256"],"Unknown global PLC source: "+path
    lines=actual.decode().splitlines(keepends=True)
    for region in reversed(change["regions"]):
        assert "".join(lines[region["start"]:region["end"]])==region["expected"]
        lines[region["start"]:region["end"]]=region["original"].splitlines(keepends=True)
    restored="".join(lines).encode()
    assert hashlib.sha256(restored).hexdigest()==change["parent_sha256"],"Global PLC inverse changed: "+path
    return restored
