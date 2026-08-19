#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


contract = json.loads((ROOT / "release/plc-protocol.json").read_text(encoding="utf-8"))
protocol = contract["web_serial_protocol"]
schema = contract["web_serial_config_schema"]
profile = contract["web_serial_profile"]
backend = (ROOT / "local_inspection_service/plc_web_serial.py").read_text(encoding="utf-8")
client = (ROOT / "local_inspection_service/frontend/src/features/plc/webSerialClient.ts").read_text(encoding="utf-8")
types = (ROOT / "local_inspection_service/frontend/src/api/types.ts").read_text(encoding="utf-8")
require(f'WEB_SERIAL_PROTOCOL_VERSION = "{protocol}"' in backend, "backend protocol differs from contract")
require(f'PLC_WEB_SERIAL_VERSION = "{protocol}"' in client, "frontend protocol differs from contract")
require(f'protocol_version: "{protocol}"' in types, "frontend API type differs from contract")
require(re.search(rf"schema_version:\s*{schema};", types) is not None, "frontend schema differs from contract")
require(f'profile_id: "{profile}"' in types, "frontend profile differs from contract")
dist = ROOT / "local_inspection_service/frontend/dist-production"
if dist.is_dir():
    index = (dist / "index.html").read_text(encoding="utf-8")
    scripts = re.findall(r'<script[^>]+src="[^"]*/assets/([^"?]+\.js)', index)
    require(bool(scripts), "production index does not reference a JavaScript bundle")
    payload = "\n".join((dist / "assets" / item).read_text(encoding="utf-8") for item in scripts)
    require(protocol in payload, "built frontend bundle does not contain current protocol")
    require("plc-web-serial-v3" not in payload, "built frontend bundle contains active legacy protocol")
print(f"release contract OK: {protocol}, schema {schema}, profile {profile}")
