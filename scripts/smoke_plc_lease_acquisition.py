"""Accepted-main/candidate PLC workstation lease claim and activation contract."""
import ast
import copy
import os
from pathlib import Path
import re
import sys
import types
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
NAMES = {"plc_web_serial_claim_connecting_lease", "plc_web_serial_activate_lease"}
POSTGRES = "--postgres" in sys.argv
if POSTGRES:
    sys.argv.remove("--postgres")


class ConfigError(Exception):
    pass


def load_target(source):
    tree = ast.parse(source.read_text(encoding="utf-8-sig"))
    nodes = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in NAMES:
            nodes.append(node)
        elif isinstance(node, ast.ImportFrom) and node.module in {
            "plc.lease_acquisition", "plc.lease_acquisition_ports"
        }:
            nodes.append(node)
        elif isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "_plc_lease_acquisition"
            for target in node.targets
        ):
            nodes.append(node)
    assert NAMES <= {node.name for node in nodes if isinstance(node, ast.FunctionDef)}
    target = types.ModuleType("local_inspection_service._lease_acquisition_contract")
    target.__package__ = "local_inspection_service"
    target.__dict__.update(
        Any=object, PlcWorkstationLeaseRequest=object, PlcWorkstationLeaseActivateRequest=object,
        PlcConfigError=ConfigError, WEB_SERIAL_PROTOCOL_VERSION="v4",
        WEB_SERIAL_CONNECTING_LEASE_SECONDS=20, WEB_SERIAL_ACTIVE_LEASE_SECONDS=30,
    )
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), "exec"), target.__dict__)
    return target


class LeaseAcquisitionContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = os.environ.get("VANTALINE_PLC_ACQUIRE_BASELINE_SOURCE")
        cls.baseline = bool(source)
        cls.target = load_target(
            Path(source) if source
            else Path(__file__).resolve().parents[1] / "local_inspection_service/server.py"
        )

    def setUp(self):
        self.calls = []
        self.user = {"id": "owner"}
        self.state = {
            "station": {"raw_json": {"id": "station", "config": {"enabled": True},
                                     "config_generation": 3}},
            "lease": None,
            "clock": {"now": 100},
        }
        self.claim_request = types.SimpleNamespace(
            client_instance_id="browser-123", model_id="model-1", bundle_version="v4"
        )
        self.activate_request = types.SimpleNamespace(
            session_id="session", lease_epoch=4, usb_vendor_id=1000, usb_product_id=2000
        )
        self.target.current_auth_user = lambda: self.calls.append("user") or self.user
        self.target.current_release_version = lambda: self.calls.append("release") or {"consistent": True}
        self.target.re = types.SimpleNamespace(
            fullmatch=lambda pattern, value: self.calls.append("regex") or re.fullmatch(pattern, value)
        )
        self.target.require_analyze_model_permission = (
            lambda model: self.calls.append(("permission", model))
        )
        self.target.migrate_web_serial_config = (
            lambda config: self.calls.append("config") or config
        )
        self.target.time = types.SimpleNamespace(time=lambda: self.calls.append("clock") or 200)
        self.target.uuid = types.SimpleNamespace(
            uuid4=lambda: self.calls.append("uuid") or types.SimpleNamespace(hex="fixed")
        )
        self.target.WEB_SERIAL_PROTOCOL_VERSION = "v4"
        self.target.WEB_SERIAL_CONNECTING_LEASE_SECONDS = 20
        self.target.WEB_SERIAL_ACTIVE_LEASE_SECONDS = 30
        self.target.PlcConfigError = ConfigError
        self.target._plc_web_serial_record = self.record
        self.target._plc_workstation_lease_row = self.lease_row
        self.target._plc_web_serial_mutate = self.mutate

    def record(self, row):
        self.calls.append("record")
        if not isinstance(row, dict):
            return None
        raw = row.get("raw_json")
        return dict(raw) if isinstance(raw, dict) else dict(row)

    def lease_row(self, row):
        self.calls.append("row")
        return {"raw_json": row, "state": row["state"]}

    def mutate(self, station_id, dispatch_id, callback):
        self.calls.append(("mutate", station_id, dispatch_id))
        proposed = copy.deepcopy(self.state)
        callback(proposed)
        self.state = proposed
        self.calls.append("commit")
        return proposed

    def lease(self):
        return self.state["lease"]["raw_json"] if self.state["lease"] else None

    def seed_lease(self, **changes):
        lease = {
            "station_id": "station", "session_id": "session", "state": "connecting",
            "lease_epoch": 4, "owner_user_id": "owner", "model_id": "model-1",
            "client_instance_id": "browser-123", "bundle_version": "v4",
            "config_generation": 3, "heartbeat_at": 90, "expires_at": 101,
            "serial_info": {},
        }
        lease.update(changes)
        self.state["lease"] = {"raw_json": lease}

    def test_claim_then_activate_state_and_return(self):
        claim = self.target.plc_web_serial_claim_connecting_lease("station", self.claim_request)
        self.assertEqual(claim["session_id"], "plcwsess_fixed")
        self.assertEqual((claim["lease_epoch"], claim["expires_at"]), (1, 120))
        self.assertEqual((claim["owner_user_id"], claim["model_id"]), ("owner", "model-1"))
        self.assertEqual(self.calls[:4], ["user", "release", "regex", ("permission", "model-1")])
        self.assertEqual(self.calls.count("commit"), 1)
        self.setUp()
        self.seed_lease()
        active = self.target.plc_web_serial_activate_lease("station", self.activate_request)
        self.assertEqual((active["state"], active["expires_at"]), ("active", 130))
        self.assertEqual(active["serial_info"], {"usb_vendor_id": 1000, "usb_product_id": 2000})
        self.assertEqual(self.calls[0], "user")
        self.assertEqual(self.calls.count("commit"), 1)

    def test_claim_preflight_priority_before_transaction(self):
        cases = (
            ("release", lambda: setattr(self.target, "current_release_version",
                                        lambda: {"consistent": False}), "plc_release_version_mismatch"),
            ("client", lambda: setattr(self.claim_request, "client_instance_id", "bad"),
             "invalid_client_instance_id"),
            ("protocol", lambda: setattr(self.claim_request, "bundle_version", "v3"),
             "plc_browser_protocol_version_mismatch"),
        )
        for label, change, error in cases:
            with self.subTest(label=label):
                self.setUp()
                change()
                with self.assertRaises(ConfigError) as caught:
                    self.target.plc_web_serial_claim_connecting_lease("station", self.claim_request)
                self.assertEqual(str(caught.exception), error)
                self.assertNotIn("commit", self.calls)
                self.assertFalse(any(isinstance(x, tuple) and x[0] == "mutate" for x in self.calls))
        self.setUp()
        denial = RuntimeError("model denied")
        self.target.require_analyze_model_permission = lambda model: (_ for _ in ()).throw(denial)
        with self.assertRaises(RuntimeError) as caught:
            self.target.plc_web_serial_claim_connecting_lease("station", self.claim_request)
        self.assertIs(caught.exception, denial)
        self.assertNotIn("commit", self.calls)

    def test_claim_station_disabled_and_expiry_boundary(self):
        for label, change, expected in (
            ("missing", lambda: self.state.update(station=None), "plc_workstation_not_found"),
            ("disabled", lambda: self.state["station"]["raw_json"]["config"].update(enabled=False),
             "plc_workstation_disabled"),
            ("occupied", lambda: self.seed_lease(state="active", expires_at=101),
             "plc_workstation_in_use"),
        ):
            with self.subTest(label=label):
                self.setUp()
                change()
                before = copy.deepcopy(self.state)
                with self.assertRaises(ConfigError) as caught:
                    self.target.plc_web_serial_claim_connecting_lease("station", self.claim_request)
                self.assertEqual(str(caught.exception), expected)
                self.assertEqual(self.state, before)
        for expiry in (100, 99):
            self.setUp()
            self.seed_lease(state="draining", expires_at=expiry)
            claimed = self.target.plc_web_serial_claim_connecting_lease("station", self.claim_request)
            self.assertEqual(claimed["lease_epoch"], 5)
            self.assertEqual(claimed["state"], "connecting")

    def test_activation_error_priority_and_repeat_fails(self):
        cases = (
            ("missing lease", lambda: None, "plc_workstation_lease_missing"),
            ("missing station", lambda: self.state.update(station=None), "plc_workstation_lease_missing"),
            ("session", lambda: self.lease().update(session_id="other"), "plc_workstation_lease_fenced"),
            ("epoch", lambda: self.lease().update(lease_epoch=5), "plc_workstation_lease_fenced"),
            ("owner", lambda: self.lease().update(owner_user_id="other"), "plc_workstation_lease_expired"),
            ("active", lambda: self.lease().update(state="active"), "plc_workstation_lease_expired"),
            ("expiry equality", lambda: self.lease().update(expires_at=100),
             "plc_workstation_lease_expired"),
            ("generation", lambda: self.lease().update(config_generation=2),
             "plc_workstation_generation_changed"),
        )
        for label, change, error in cases:
            with self.subTest(label=label):
                self.setUp()
                if label != "missing lease":
                    self.seed_lease()
                change()
                before = copy.deepcopy(self.state)
                with self.assertRaises(ConfigError) as caught:
                    self.target.plc_web_serial_activate_lease("station", self.activate_request)
                self.assertEqual(str(caught.exception), error)
                self.assertEqual(self.state, before)
        self.setUp()
        self.seed_lease()
        self.target.plc_web_serial_activate_lease("station", self.activate_request)
        with self.assertRaises(ConfigError) as caught:
            self.target.plc_web_serial_activate_lease("station", self.activate_request)
        self.assertEqual(str(caught.exception), "plc_workstation_lease_expired")

    def test_claim_persist_error_but_activation_empty_result(self):
        self.target._plc_web_serial_mutate = lambda sid, did, callback: {"lease": None}
        with self.assertRaises(ConfigError) as caught:
            self.target.plc_web_serial_claim_connecting_lease("station", self.claim_request)
        self.assertEqual(str(caught.exception), "plc_lease_persist_failed")
        self.assertEqual(
            self.target.plc_web_serial_activate_lease("station", self.activate_request), {}
        )

    def test_request_read_order_user_capture_and_late_callbacks(self):
        events = []
        user = {"id": "first"}
        self.target.current_auth_user = lambda: events.append("user") or user
        class Payload:
            @property
            def client_instance_id(inner):
                events.append("client")
                user["id"] = "second"
                return "browser-123"
            @property
            def model_id(inner):
                events.append("model")
                return "model-1"
            @property
            def bundle_version(inner):
                events.append("bundle")
                return "v4"
        result = self.target.plc_web_serial_claim_connecting_lease("station", Payload())
        self.assertEqual(events, ["user", "client", "model", "bundle"])
        self.assertEqual(result["owner_user_id"], "second")
        self.setUp()
        original = self.mutate
        def rebind(sid, did, callback):
            self.target.uuid.uuid4 = lambda: types.SimpleNamespace(hex="late")
            self.target.WEB_SERIAL_CONNECTING_LEASE_SECONDS = 41
            self.target._plc_workstation_lease_row = lambda row: {"raw_json": row, "selected": "late"}
            state = original(sid, did, callback)
            self.target._plc_web_serial_record = lambda row: {"result": "late"}
            return state
        self.target._plc_web_serial_mutate = rebind
        self.assertEqual(self.target.plc_web_serial_claim_connecting_lease(
            "station", self.claim_request), {"result": "late"})
        self.assertEqual(self.state["lease"]["selected"], "late")
        self.assertEqual(self.state["lease"]["raw_json"]["session_id"], "plcwsess_late")
        self.assertEqual(self.state["lease"]["raw_json"]["expires_at"], 141)

    def test_config_and_usb_late_binding_order(self):
        selected = []
        def early(config):
            selected.append("early")
            return config
        self.target.migrate_web_serial_config = early
        original_record = self.record
        target = self.target
        class Station(dict):
            def get(inner, key, default=None):
                if key == "config":
                    target.migrate_web_serial_config = lambda config: selected.append("late") or config
                return super().get(key, default)
        def station_record(row):
            value = original_record(row)
            return Station(value) if value and value.get("id") == "station" else value
        self.target._plc_web_serial_record = station_record
        self.target.plc_web_serial_claim_connecting_lease("station", self.claim_request)
        self.assertEqual(selected, ["early"])

        self.setUp()
        class NewConfigError(Exception):
            pass
        def disable(config):
            self.target.PlcConfigError = NewConfigError
            return {"enabled": False}
        self.target.migrate_web_serial_config = disable
        with self.assertRaises(NewConfigError) as caught:
            self.target.plc_web_serial_claim_connecting_lease("station", self.claim_request)
        self.assertEqual(str(caught.exception), "plc_workstation_disabled")

        self.setUp()
        self.seed_lease()
        class RebindUsb:
            session_id, lease_epoch = "session", 4
            @property
            def usb_vendor_id(inner):
                self.target._plc_workstation_lease_row = lambda row: {
                    "raw_json": row, "selected": "usb-rebound"
                }
                return 1000
            @property
            def usb_product_id(inner):
                return 2000
        self.target.plc_web_serial_activate_lease("station", RebindUsb())
        self.assertEqual(self.state["lease"]["selected"], "usb-rebound")

        self.setUp()
        self.seed_lease()
        captured = []
        sentinel = RuntimeError("USB property failed")
        def tracking_record(row):
            result = self.record(row)
            if result and result.get("session_id") == "session":
                captured.append(result)
            return result
        self.target._plc_web_serial_record = tracking_record
        self.target._plc_workstation_lease_row = lambda row: (_ for _ in ()).throw(
            AssertionError("lease row selected before USB fields")
        )
        class FailingUsb:
            session_id, lease_epoch = "session", 4
            usb_vendor_id = 1000
            @property
            def usb_product_id(inner):
                raise sentinel
        before = copy.deepcopy(self.state)
        with self.assertRaises(RuntimeError) as caught:
            self.target.plc_web_serial_activate_lease("station", FailingUsb())
        self.assertIs(caught.exception, sentinel)
        self.assertEqual(self.state, before)
        self.assertEqual(len(captured), 1)
        self.assertEqual((captured[0]["state"], captured[0]["heartbeat_at"],
                          captured[0]["expires_at"]), ("active", 100, 130))
        self.assertEqual(captured[0]["serial_info"], {})

    def test_callback_failure_identity_and_no_retry(self):
        for method, request, expected_state in (
            ("plc_web_serial_claim_connecting_lease", self.claim_request, "connecting"),
            ("plc_web_serial_activate_lease", self.activate_request, "active"),
        ):
            with self.subTest(method=method):
                self.setUp()
                if expected_state == "active":
                    self.seed_lease()
                calls = []
                error = RuntimeError("after mutation")
                def failing(sid, did, callback):
                    calls.append("mutate")
                    proposed = copy.deepcopy(self.state)
                    callback(proposed)
                    self.assertEqual(proposed["lease"]["raw_json"]["state"], expected_state)
                    calls.append("callback")
                    raise error
                self.target._plc_web_serial_mutate = failing
                before = copy.deepcopy(self.state)
                with self.assertRaises(RuntimeError) as caught:
                    getattr(self.target, method)("station", request)
                self.assertIs(caught.exception, error)
                self.assertEqual(calls, ["mutate", "callback"])
                self.assertEqual(self.state, before)

    def test_two_instance_isolation_zero_constructor_reads(self):
        if self.baseline:
            self.skipTest("candidate service only")
        from local_inspection_service.plc.lease_acquisition import LeaseAcquisition
        from local_inspection_service.plc.lease_acquisition_ports import LeaseAcquisitionPorts
        reads = []
        def build(label, method):
            state = copy.deepcopy(self.state)
            state["clock"] = {"now": 0}
            if method == "activate":
                state["lease"] = {"raw_json": {
                    "station_id": label, "session_id": "session", "state": "connecting",
                    "lease_epoch": 4, "owner_user_id": label,
                    "model_id": "model-1", "client_instance_id": "browser-123",
                    "bundle_version": "v4", "config_generation": 3,
                    "heartbeat_at": 190, "expires_at": 201, "serial_info": {},
                }}
            def get(name, value):
                return lambda: reads.append((label, name)) or value
            def mutate(sid, did, callback):
                if method == "claim" and state.get("lease"):
                    state["clock"]["now"] = 220
                if method == "activate" and state["lease"]["raw_json"]["state"] == "active":
                    state["lease"]["raw_json"].update(state="connecting", expires_at=201)
                callback(state)
                return state
            return LeaseAcquisition(LeaseAcquisitionPorts(
                current_user=get("user", lambda: {"id": label}),
                release_version=get("release", lambda: {"consistent": True}),
                fullmatch=get("regex", re.fullmatch),
                protocol_version=get("protocol", "v4"),
                require_model_permission=get("permission", lambda model: None),
                mutate=get("mutate", mutate),
                record=get("record", self.record),
                migrate_config=get("config", lambda config: config),
                clock=get("clock", lambda: 200),
                uuid4=get("uuid", lambda: types.SimpleNamespace(hex=label)),
                connecting_ttl=get("connecting_ttl", 20),
                active_ttl=get("active_ttl", 30),
                lease_row=get("row", self.lease_row),
                config_error=get("error", ConfigError),
            ))
        def forbidden(*args, **kwargs):
            raise AssertionError("service reached root collaborator")
        for name in ("current_auth_user", "current_release_version", "_plc_web_serial_mutate",
                     "_plc_web_serial_record", "_plc_workstation_lease_row",
                     "require_analyze_model_permission", "migrate_web_serial_config", "PlcConfigError"):
            setattr(self.target, name, forbidden)
        for method in ("claim", "activate"):
            reads.clear()
            a, b = build("a", method), build("b", method)
            self.assertEqual(reads, [])
            for index, (service, label) in enumerate(((a, "a"), (b, "b"), (a, "a"))):
                before = len(reads)
                request = self.claim_request if method == "claim" else self.activate_request
                result = getattr(service, method)(label, request)
                self.assertEqual(result["state"], "connecting" if method == "claim" else "active")
                used = reads[before:]
                if method == "claim":
                    expected = ["user", "release", "regex", "protocol", "permission",
                                "mutate", "record", "config"]
                    if index == 0 or label == "b":
                        expected += ["clock"]
                    expected += ["record", "uuid", "connecting_ttl", "row", "record"]
                    self.assertEqual(result["session_id"], "plcwsess_" + label)
                    invalid = types.SimpleNamespace(
                        client_instance_id="bad", model_id="model-1", bundle_version="v4"
                    )
                    with self.assertRaises(ConfigError):
                        service.claim(label, invalid)
                    self.assertEqual(
                        reads[before + len(used):],
                        [(label, name) for name in ("user", "release", "regex", "error")],
                    )
                else:
                    expected = ["user", "mutate", "record", "record", "clock",
                                "active_ttl", "row", "record"]
                    invalid = types.SimpleNamespace(
                        session_id="wrong", lease_epoch=4, usb_vendor_id=1, usb_product_id=2
                    )
                    with self.assertRaises(ConfigError):
                        service.activate(label, invalid)
                    self.assertEqual(
                        reads[before + len(used):],
                        [(label, name) for name in
                         ("user", "mutate", "record", "record", "clock", "error")],
                    )
                self.assertEqual(used, [(label, name) for name in expected])


    @unittest.skipUnless(POSTGRES, "isolated PostgreSQL check requested explicitly")
    def test_real_postgres_claim_activate_and_written_rollback(self):
        from local_inspection_service.storage.postgres_schema import postgres_ddl
        from local_inspection_service.storage.postgres_runtime_repository import PostgresRuntimeRepository
        from local_inspection_service.storage.runtime_selector import default_postgres_connector

        dsn = os.environ["VANTALINE_POSTGRES_DSN"]
        schema = "lease_acquire_" + uuid.uuid4().hex[:12]
        connection = default_postgres_connector(dsn)
        try:
            with connection.cursor() as cursor:
                cursor.execute(postgres_ddl(schema))
            connection.commit()
            repo = PostgresRuntimeRepository(connection, "<redacted>", schema_name=schema)
            now = int(__import__("time").time())
            station = {
                "id": "station", "token_hash": "token", "name": "test", "status": "ready",
                "config_generation": 3, "profile_verified": True,
                "created_by_user_id": "owner", "created_at": now, "updated_at": now,
                "config": {"enabled": True},
            }
            repo.upsert_row("plc_workstations", {
                **{key: station[key] for key in (
                    "id", "token_hash", "name", "status", "config_generation",
                    "profile_verified", "created_by_user_id", "created_at", "updated_at"
                )},
                "raw_json": station,
            })
            self.target._plc_web_serial_mutate = repo.mutate_plc_web_serial_rows
            self.target._plc_web_serial_record = self.record
            self.target._plc_workstation_lease_row = lambda row: {
                **{key: row[key] for key in (
                    "station_id", "session_id", "state", "lease_epoch", "owner_user_id",
                    "model_id", "client_instance_id", "bundle_version", "config_generation",
                    "heartbeat_at", "expires_at",
                )},
                "raw_json": row,
            }
            claim = self.target.plc_web_serial_claim_connecting_lease("station", self.claim_request)
            committed = repo.fetch_by_primary_key("plc_workstation_leases", {"station_id": "station"})
            self.assertEqual(committed["raw_json"]["session_id"], claim["session_id"])
            self.activate_request.session_id = claim["session_id"]
            self.activate_request.lease_epoch = claim["lease_epoch"]
            active = self.target.plc_web_serial_activate_lease("station", self.activate_request)
            self.assertEqual(active["state"], "active")
            observer = default_postgres_connector(dsn)
            try:
                external = PostgresRuntimeRepository(observer, "<redacted>", schema_name=schema)
                observed = external.fetch_by_primary_key("plc_workstation_leases", {"station_id": "station"})
                self.assertEqual((observed["state"], observed["raw_json"]["state"]), ("active", "active"))
                self.assertEqual(observed["raw_json"]["session_id"], claim["session_id"])
            finally:
                observer.close()
            with self.assertRaises(ConfigError) as caught:
                self.target.plc_web_serial_claim_connecting_lease("station", self.claim_request)
            self.assertEqual(str(caught.exception), "plc_workstation_in_use")
            committed = repo.fetch_by_primary_key("plc_workstation_leases", {"station_id": "station"})
            reseeded = dict(committed["raw_json"])
            reseeded["state"] = "connecting"
            reseeded["expires_at"] = now + 60
            repo.upsert_row("plc_workstation_leases", {
                **{key: reseeded[key] for key in (
                    "station_id", "session_id", "state", "lease_epoch", "owner_user_id",
                    "model_id", "client_instance_id", "bundle_version", "config_generation",
                    "heartbeat_at", "expires_at",
                )},
                "raw_json": reseeded,
            })
            committed = repo.fetch_by_primary_key("plc_workstation_leases", {"station_id": "station"})
            sentinel = RuntimeError("after SQL write")
            def write_then_fail(sid, did, callback):
                def wrapped(state):
                    callback(state)
                    with connection.cursor() as cursor:
                        cursor.execute(
                            f'UPDATE "{schema}"."plc_workstation_leases" '
                            'SET heartbeat_at = %s WHERE station_id = %s',
                            (now - 50, "station"),
                        )
                        self.assertEqual(cursor.rowcount, 1)
                    raise sentinel
                return repo.mutate_plc_web_serial_rows(sid, did, wrapped)
            self.target._plc_web_serial_mutate = write_then_fail
            with self.assertRaises(RuntimeError) as caught:
                self.target.plc_web_serial_activate_lease("station", self.activate_request)
            self.assertIs(caught.exception, sentinel)
            status = getattr(getattr(connection, "info", None), "transaction_status", None)
            if status is None:
                status = connection.get_transaction_status()
            self.assertEqual(int(status), 0)
            observer = default_postgres_connector(dsn)
            try:
                external = PostgresRuntimeRepository(observer, "<redacted>", schema_name=schema)
                observed = external.fetch_by_primary_key("plc_workstation_leases", {"station_id": "station"})
                self.assertEqual(observed["raw_json"], committed["raw_json"])
                self.assertEqual(observed["heartbeat_at"], committed["heartbeat_at"])
            finally:
                observer.close()
        finally:
            connection.rollback()
            with connection.cursor() as cursor:
                cursor.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
            connection.commit()
            connection.close()


if __name__ == "__main__":
    unittest.main()
