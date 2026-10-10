"""Authenticated self-service and real ASGI lease verification; no physical PLC I/O."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local_inspection_service.scripts import smoke_plc_web_serial_v3 as fixture
from local_inspection_service.plc_web_serial import build_connection_check, validate_connection_check
import time

server, Client, check = fixture.server, fixture.TestClient, fixture.assert_status
admin = Client(server.app, base_url="https://testserver")
check(admin.post("/api/auth/bootstrap", json={"username": "admin", "password": "admin-password-123", "display_name": "Admin"}), 200, "bootstrap")
clients = []
for name, permissions in (("operator", ["inspection"]), ("aioperator", ["ai_detection"]), ("viewer", [])):
    check(admin.post("/api/auth/users", json={"username": name, "password": "operator-password-123", "display_name": name, "role": "user", "permissions": permissions, "active": True}), 200, "create operator")
    client = Client(server.app, base_url="https://testserver")
    check(client.post("/api/auth/login", json={"username": name, "password": "operator-password-123"}), 200, "login")
    clients.append(client)
a, b, denied = clients
outsider = Client(server.app, base_url="https://testserver")
check(outsider.post("/api/plc/workstation/self-pair", json={}), 401, "unauthenticated")
check(denied.post("/api/plc/workstation/self-pair", json={}), 403, "permission denied")
paired = a.post("/api/plc/workstation/self-pair", json={})
check(paired, 200, "self pair")
sid = paired.json()["station"]["id"]
cookie = a.cookies.get(server.PLC_WORKSTATION_COOKIE)
check(a.post("/api/plc/workstation/self-pair", json={"station_id": sid}), 422, "cannot take over station")
check(a.post("/api/plc/workstation/self-pair", json={}), 200, "idempotent existing pair")
assert a.cookies.get(server.PLC_WORKSTATION_COOKIE) == cookie
check(a.post("/api/plc/workstation/self-pair", json={"name": "一号产线"}), 200, "rename without rotating cookie")
assert a.cookies.get(server.PLC_WORKSTATION_COOKIE) == cookie
config = {**fixture.DEFAULT_WEB_SERIAL_CONFIG, "enabled": True, "capture_trigger_enabled": True}
check(a.post("/api/plc/workstation/self-config", json=config), 200, "configure locally")
check(a.post("/api/plc/workstation/config", json=config), 403, "global admin config still denied")
check(a.post("/api/plc/workstation/self-config", json={**config, "capture_input_register": "D206"}), 400, "conflicting addresses")
check(a.post("/api/plc/workstation/self-config", json={**config, "station_id": sid}), 422, "cannot configure other station")
check(b.post("/api/plc/workstation/self-pair", json={}), 200, "AI operator pair without selecting model")
check(b.post("/api/plc/workstation/self-config", json={**config, "result_register": "D207"}), 200, "second line config")
assert b.get("/api/plc/workstation").json()["station"]["id"] != sid
assert a.get("/api/plc/workstation").json()["config"]["result_register"] == "D206"
check(a.post("/api/auth/logout"), 200, "logout")
assert a.cookies.get(server.PLC_WORKSTATION_COOKIE) == cookie
check(a.post("/api/auth/login", json={"username": "operator", "password": "operator-password-123"}), 200, "relogin")
assert a.get("/api/plc/workstation").json()["station"]["id"] == sid

lease = a.post("/api/plc/workstation/connect", json={"client_instance_id": "browser_self_test", "model_id": "", "bundle_version": "plc-web-serial-v4"})
check(lease, 200, "claim before model selection")
l = lease.json()
plan = l["connection_check"]
assert [f["target"] for f in plan["frames"]] == ["D205", "D206"]
base = {"session_id": l["session_id"], "lease_epoch": l["lease_epoch"]}
check(a.post("/api/plc/workstation/connect/activate", json=base), 409, "old browser must reload")
reads = [{"target": f["target"], "response_hex": "0230303030034333"} for f in plan["frames"]]
activation = {**base, "connection_check_id": plan["id"], "connection_reads": reads}
check(a.post("/api/plc/workstation/connect/activate", json={**activation, "connection_reads": [{**reads[0], "response_hex": "0230303030030000"}, reads[1]]}), 409, "bad checksum")
check(a.post("/api/plc/workstation/connect/activate", json={**activation, "connection_reads": reads[:1]}), 409, "missing read")
check(a.post("/api/plc/workstation/connect/activate", json={**activation, "connection_reads": [{**reads[0], "response_hex": "00"}, reads[1]]}), 422, "bounded response")
check(a.post("/api/plc/workstation/connect/activate", json=activation), 200, "verified activation")
assert a.get("/api/plc/workstation").json()["effective_enabled"]
assert not a.get("/api/plc/workstation").json()["station"]["profile_verified"]
check(a.post("/api/plc/workstation/self-config", json=config), 409, "must disconnect before editing")
check(a.post("/api/plc/workstation/lease/heartbeat", json=base), 200, "verified heartbeat")

def remove_verification(state):
    lease = server._plc_web_serial_record(state["lease"])
    lease.pop("communication_verified", None)
    state["lease"] = server._plc_workstation_lease_row(lease)
server._plc_web_serial_mutate(sid, None, remove_verification)
check(a.post("/api/plc/workstation/lease/heartbeat", json=base), 409, "old active lease fenced")
assert not a.get("/api/plc/workstation").json()["effective_enabled"]
check(a.post("/api/plc/workstation/lease/disconnect", json=base), 200, "release")
check(a.post("/api/plc/workstation/self-config", json=config), 200, "edit after release")

for kind in ("expired", "generation"):
    l = a.post("/api/plc/workstation/connect", json={"client_instance_id": "browser_self_test", "model_id": "", "bundle_version": "plc-web-serial-v4"}).json()
    activation = {"session_id": l["session_id"], "lease_epoch": l["lease_epoch"], "connection_check_id": l["connection_check"]["id"], "connection_reads": reads}
    def fence(state):
        if kind == "expired":
            record = server._plc_web_serial_record(state["lease"])
            record["connection_check"]["deadline_at"] = int(time.time()) - 1
            state["lease"] = server._plc_workstation_lease_row(record)
        else:
            record = server._plc_web_serial_record(state["station"])
            record["config_generation"] += 1
            state["station"] = server._plc_workstation_row(record)
    server._plc_web_serial_mutate(sid, None, fence)
    check(a.post("/api/plc/workstation/connect/activate", json=activation), 409, kind)
    check(a.post("/api/plc/workstation/lease/disconnect", json={"session_id": l["session_id"], "lease_epoch": l["lease_epoch"]}), 200, "release failed check")
print("smoke_plc_self_service: ok")
