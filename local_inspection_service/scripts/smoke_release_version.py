from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

try:
    from local_inspection_service.release_version import release_version_status
except ModuleNotFoundError:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from release_version import release_version_status


with tempfile.TemporaryDirectory() as raw:
    root = Path(raw)
    assets = root / "local_inspection_service/frontend/dist-production/assets"
    assets.mkdir(parents=True)
    bundle = assets / "index-test.js"
    bundle.write_text('const protocol="plc-web-serial-v4";', encoding="utf-8")
    document = {
        "release": "test-release",
        "git_commit": "a" * 40,
        "built_at": "2026-08-19T00:00:00Z",
        "backend_protocol": "plc-web-serial-v4",
        "frontend_protocol": "plc-web-serial-v4",
        "frontend_bundle": bundle.name,
        "frontend_bundle_sha256": hashlib.sha256(bundle.read_bytes()).hexdigest(),
    }
    (root / "VERSION.json").write_text(json.dumps(document), encoding="utf-8")
    assert release_version_status(root, "plc-web-serial-v4")["consistent"] is True
    bundle.write_text('const protocol="plc-web-serial-v3";', encoding="utf-8")
    assert release_version_status(root, "plc-web-serial-v4")["consistent"] is False
    document["frontend_protocol"] = "plc-web-serial-v3"
    (root / "VERSION.json").write_text(json.dumps(document), encoding="utf-8")
    assert release_version_status(root, "plc-web-serial-v4")["consistent"] is False

print("release version fail-closed smoke passed")
