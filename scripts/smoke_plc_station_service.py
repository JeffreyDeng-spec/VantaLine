"""Original/candidate workstation transaction and projection behavior without I/O."""
import ast
import copy
from contextlib import nullcontext
import hashlib
import os
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from canonical_application_source_contract import read_checked_application_source
NAMES = {
    "_plc_web_serial_token_hash", "plc_web_serial_station_from_request",
    "require_plc_web_serial_station", "plc_web_serial_current_lease",
    "plc_web_serial_recent_dispatches", "plc_web_serial_ensure_current_station_contract",
    "plc_web_serial_station_payload", "plc_web_serial_unpaired_payload",
    "plc_web_serial_list_workstations", "plc_web_serial_pair",
    "plc_web_serial_update_config", "plc_web_serial_set_verified",
}
BASELINE = os.environ.get("VANTALINE_PLC_STATION_SERVICE_BASELINE_SOURCE")


class ConfigError(Exception):
    pass


class HttpError(Exception):
    def __init__(self, status_code, detail):
        self.status_code, self.detail = status_code, detail


def load_target():
    source = Path(BASELINE) if BASELINE else Path(__file__).resolve().parents[1] / "local_inspection_service/server.py"
    raw = read_checked_application_source(source, encoding='utf-8-sig')
    if not BASELINE:
        from application_integration_source_contract import restore_plc_domain_root
        raw = restore_plc_domain_root(raw)
    tree = ast.parse(raw)
    nodes = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in NAMES:
            nodes.append(node)
        elif not BASELINE and isinstance(node, ast.ImportFrom) and node.module in {"plc.station_service", "plc.station_ports"}:
            nodes.append(node)
        elif not BASELINE and isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "_plc_station_service" for t in node.targets):
            nodes.append(node)
    assert {n.name for n in nodes if isinstance(n, ast.FunctionDef)} == NAMES
    target = types.ModuleType("local_inspection_service._station_contract")
    target.__package__ = "local_inspection_service"
    import hmac, secrets, time, uuid
    target.__dict__.update(Any=object, Request=object, Response=object, hashlib=hashlib,
                          hmac=hmac, secrets=secrets, time=time, uuid=uuid)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), "exec"), target.__dict__)
    return target


class StationContracts(unittest.TestCase):
    def setUp(self):
        self.api = load_target()
        self.events = []
        self.state = {"station": {"id": "s", "name": "Station", "config": {"enabled": True, "profile": "a"}, "config_generation": 3},
                      "lease": None, "clock": {"now": 100}}
        self.local = {"workstations": {}, "leases": {}, "dispatches": {}}
        def mutate(station_id, dispatch_id, callback):
            self.events.append(("transaction", station_id, dispatch_id))
            draft = copy.deepcopy(self.state)
            callback(draft)
            self.state = draft
            return draft
        self.api.__dict__.update(
            PlcConfigError=ConfigError, HTTPException=HttpError,
            PLC_WORKSTATION_COOKIE="station", PLC_WORKSTATION_COOKIE_TTL_SECONDS=3600,
            SYSTEM_OWNER_ID="system", WEB_SERIAL_PROTOCOL_VERSION="v4",
            WEB_SERIAL_HEARTBEAT_SECONDS=5, WEB_SERIAL_ACTIVE_LEASE_SECONDS=30,
            DEFAULT_WEB_SERIAL_CONFIG={"enabled": False, "profile": "a"},
            _config_io_lock=nullcontext(), runtime_postgres_repository_or_none=lambda: None,
            _plc_web_serial_load_local=lambda: self.local,
            _plc_web_serial_record=lambda row: row,
            _plc_workstation_row=lambda row: row,
            _plc_workstation_lease_row=lambda row: row,
            _plc_web_serial_dispatch_row=lambda row: row,
            _plc_web_serial_mutate=mutate,
            _plc_web_serial_upsert_row=lambda *args: self.events.append(("upsert", args)),
            current_auth_user=lambda: {"id": "account"}, request_is_https=lambda request: True,
            normalize_web_serial_config=lambda config: dict(config),
            migrate_web_serial_config=lambda config: {"enabled": False, "profile": "migrated"},
            web_serial_profile_fingerprint=lambda config: config["profile"],
            current_release_version=lambda: {"consistent": True},
            web_serial_resolved_addresses=lambda config: {"D": "206"},
            build_web_serial_capture_read_plan=lambda config, generation: {"generation": generation},
        )
        self.clock = patch("time.time", return_value=100)
        self.clock.start()
        self.addCleanup(self.clock.stop)

    def test_token_empty_request_and_falsey_repository(self):
        self.assertEqual(self.api._plc_web_serial_token_hash(" t "), hashlib.sha256(b" t ").hexdigest())
        request = types.SimpleNamespace(cookies={})
        self.api.runtime_postgres_repository_or_none = lambda: self.fail("empty cookie reached database")
        self.assertIsNone(self.api.plc_web_serial_station_from_request(request))
        with self.assertRaises(HttpError) as caught:
            self.api.require_plc_web_serial_station(request)
        self.assertEqual((caught.exception.status_code, caught.exception.detail), (409, "plc_workstation_not_paired"))
        calls = []
        class Repository:
            def __bool__(self): return False
            def fetch_one_by_columns(inner, *args): calls.append(args); return {"id": "r"}
            def fetch_by_primary_key(inner, *args): calls.append(args); return {"id": "lease"}
        self.api.runtime_postgres_repository_or_none = lambda: Repository()
        self.assertEqual(self.api.plc_web_serial_station_from_request(types.SimpleNamespace(cookies={"station": " x "})), {"id": "r"})
        self.assertEqual(calls[0], ("plc_workstations", {"token_hash": hashlib.sha256(b"x").hexdigest()}))
        self.assertEqual(self.api.plc_web_serial_current_lease("s"), {"id": "lease"})

    def test_payload_deadline_generation_and_release_gates(self):
        station = self.state["station"]
        station.update(profile_verified=True, profile_verified_fingerprint="a")
        lease = {"state": "active", "communication_verified": True, "expires_at": 101, "config_generation": 3, "bundle_version": "v4"}
        self.api.plc_web_serial_current_lease = lambda station_id: lease
        self.api.plc_web_serial_recent_dispatches = lambda station_id: ["history"]
        result = self.api.plc_web_serial_station_payload(station)
        self.assertIs(result["lease"], lease)
        self.assertTrue(result["production_ready"])
        self.assertEqual(result["recent_dispatches"], ["history"])
        lease["expires_at"] = 100
        self.assertIsNone(self.api.plc_web_serial_station_payload(station)["lease"])
        lease["expires_at"] = 101
        self.api.current_release_version = lambda: {"consistent": False}
        self.assertFalse(self.api.plc_web_serial_station_payload(station)["effective_enabled"])
        self.assertFalse(self.api.plc_web_serial_unpaired_payload()["production_ready"])

    def test_config_migration_and_transaction_failure_preserve_state(self):
        station = self.state["station"]
        station["config"] = {"legacy": True}
        self.state["lease"] = {"state": "active", "communication_verified": True, "in_flight_deadline_at": 120}
        def normalize(config):
            if config.get("legacy"): raise ConfigError("legacy")
            return dict(config)
        self.api.normalize_web_serial_config = normalize
        result = self.api.plc_web_serial_ensure_current_station_contract(station)
        self.assertEqual(result["config_generation"], 4)
        self.assertFalse(result["profile_verified"])
        self.assertEqual(self.state["lease"]["state"], "draining")
        self.assertEqual(self.state["lease"]["expires_at"], 120)
        before = copy.deepcopy(self.state)
        self.api._plc_workstation_row = lambda row: (_ for _ in ()).throw(ValueError("store"))
        with self.assertRaisesRegex(ValueError, "store"):
            self.api.plc_web_serial_update_config("s", {"enabled": True, "profile": "a"})
        self.assertEqual(self.state, before)

    def test_unchanged_config_still_drains_and_profile_changes_reset(self):
        station = self.state["station"]
        station.update(profile_verified=True, profile_verified_fingerprint="a")
        self.state["lease"] = {"state": "active", "communication_verified": True, "in_flight_deadline_at": 120}
        self.api.plc_web_serial_station_payload = lambda row: row
        result = self.api.plc_web_serial_update_config("s", dict(station["config"]))
        self.assertEqual(result["config_generation"], 3)
        self.assertTrue(result["profile_verified"])
        self.assertEqual(self.state["lease"]["state"], "draining")
        result = self.api.plc_web_serial_update_config("s", {"enabled": True, "profile": "b"})
        self.assertEqual(result["config_generation"], 4)
        self.assertFalse(result["profile_verified"])
        self.assertEqual(self.state["lease"]["expires_at"], 120)

    def test_recent_projection_settles_missing_receipt_in_transaction(self):
        record = {"dispatch_id": "d", "station_id": "s", "status": "browser_attempt_declared", "deadline_at": 100, "updated_at": 90}
        self.local["dispatches"]["d"] = record
        self.state["dispatch"] = copy.deepcopy(record)
        self.state["lease"] = {"state": "draining", "in_flight_dispatch_id": "d", "in_flight_deadline_at": 100}
        result = self.api.plc_web_serial_recent_dispatches("s")
        self.assertEqual(result[0]["outcome"], "uncertain")
        self.assertEqual(result[0]["error_code"], "browser_receipt_missing_after_deadline")
        self.assertEqual(self.state["lease"], {"state": "released", "expires_at": 100})
        self.assertEqual(self.events, [("transaction", "s", "d")])

    def test_pair_validation_rebind_and_cookie_failure_effect_order(self):
        request = types.SimpleNamespace(cookies={})
        self.api.current_auth_user = lambda: self.fail("invalid name reached auth")
        with self.assertRaises(ConfigError): self.api.plc_web_serial_pair(request, object(), "  ")
        self.api.current_auth_user = lambda: {"id": "account"}
        self.api.plc_web_serial_station_from_request = lambda request: self.state["station"]
        self.state["lease"] = {"state": "active", "communication_verified": True, "in_flight_deadline_at": 120}
        cookies = []
        def cookie(*args, **kwargs):
            cookies.append((args, kwargs))
            raise ValueError("cookie")
        with patch("secrets.token_urlsafe", return_value="new-token"):
            with self.assertRaisesRegex(ValueError, "cookie"):
                self.api.plc_web_serial_pair(request, types.SimpleNamespace(set_cookie=cookie), " New  Station ")
        self.assertEqual(self.state["station"]["name"], "New Station")
        self.assertEqual(self.state["lease"]["state"], "draining")
        self.assertEqual(cookies[0][0], ("station", "new-token"))
        self.assertEqual(cookies[0][1], dict(max_age=3600, httponly=True, secure=True, samesite="lax", path="/"))

    def test_verification_and_list_casefold_stability(self):
        self.api.plc_web_serial_station_payload = lambda row: row
        self.api.migrate_web_serial_config = lambda config: dict(config)
        result = self.api.plc_web_serial_set_verified("s", True)
        self.assertEqual((result["profile_verified_fingerprint"], result["verified_by_user_id"], result["verified_at"]), ("a", "account", 100))
        self.api.current_auth_user = lambda: self.fail("false verification fetched identity")
        result = self.api.plc_web_serial_set_verified("s", False)
        self.assertEqual((result["verified_at"], result["verified_by_user_id"]), (0, ""))
        self.local["workstations"] = {"a": dict(result, id="a", name="A"), "b": dict(result, id="b", name="a")}
        self.assertEqual([row["id"] for row in self.api.plc_web_serial_list_workstations()], ["a", "b"])

    @unittest.skipIf(BASELINE, "candidate assembly only")
    def test_all_32_ports_are_lazy_and_root_forwarders_preserve_identity(self):
        service = self.api._plc_station_service
        count = 0
        for group in (service.storage, service.identity, service.policy, service.projection):
            for name in group.__dataclass_fields__:
                if name == "clock":
                    continue
                a, b = object(), object()
                setattr(self.api, name, a)
                self.assertIs(getattr(group, name)(), a)
                setattr(self.api, name, b)
                self.assertIs(getattr(group, name)(), b)
                setattr(self.api, name, a)
                self.assertIs(getattr(group, name)(), a)
                count += 1
        self.assertEqual(count, 32)
        a, b = object(), object()
        for value in (a, b, a):
            self.api.time = types.SimpleNamespace(time=value)
            self.assertIs(service.policy.clock(), value)
        self.assertEqual(sum(len(group.__dataclass_fields__) for group in
                             (service.storage, service.identity, service.policy, service.projection)), 33)
        api = load_target()
        calls = []
        class Fake:
            def __getattr__(self, name):
                return lambda *args, **kwargs: calls.append((name, args, kwargs)) or token
        token = object()
        api._plc_station_service = Fake()
        import inspect
        for name in NAMES:
            fn = getattr(api, name)
            args = [object() for _ in inspect.signature(fn).parameters]
            self.assertIs(fn(*args), token)
            self.assertEqual(calls[-1], (name, tuple(args), {}))


if __name__ == "__main__":
    unittest.main()
