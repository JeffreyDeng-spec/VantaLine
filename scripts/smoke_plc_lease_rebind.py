"""Accepted-main/candidate browser lease model-rebind state contract."""
import ast
import copy
import os
from pathlib import Path
import sys
import types
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
POSTGRES = "--postgres" in sys.argv
if POSTGRES:
    sys.argv.remove("--postgres")


class ConfigError(Exception):
    pass


def load_target(source, baseline):
    tree = ast.parse(source.read_text(encoding="utf-8-sig"))
    names = {"plc_web_serial_rebind_model", "_plc_web_serial_require_active_lease"}
    nodes = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in names:
            nodes.append(node)
        elif not baseline and isinstance(node, ast.ImportFrom) and node.module in {
            "plc.lease_maintenance", "plc.lease_maintenance_ports"
        }:
            nodes.append(node)
        elif not baseline and isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "_plc_lease_maintenance"
            for target in node.targets
        ):
            nodes.append(node)
    assert names <= {node.name for node in nodes if isinstance(node, ast.FunctionDef)}
    target = types.ModuleType("local_inspection_service._lease_rebind_contract")
    target.__package__ = "local_inspection_service"
    target.__dict__.update(
        Any=object, PlcWorkstationLeaseRebindRequest=object,
        WEB_SERIAL_PROTOCOL_VERSION="v4", WEB_SERIAL_ACTIVE_LEASE_SECONDS=30,
        PlcConfigError=ConfigError,
    )
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), "exec"), target.__dict__)
    return target


class RebindContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = os.environ.get("VANTALINE_PLC_REBIND_BASELINE_SOURCE")
        cls.baseline = bool(source)
        cls.target = load_target(
            Path(source) if source
            else Path(__file__).resolve().parents[1] / "local_inspection_service/server.py",
            cls.baseline,
        )
        cls.active_helper = cls.target._plc_web_serial_require_active_lease

    def setUp(self):
        self.target._plc_web_serial_require_active_lease = type(self).active_helper
        self.calls = []
        self.user = {"id": "owner"}
        self.state = {
            "station": {"raw_json": {
                "id": "station", "config": {"enabled": True}, "config_generation": 3,
            }},
            "lease": {"raw_json": {
                "station_id": "station", "session_id": "session", "lease_epoch": 4,
                "owner_user_id": "owner", "state": "active", "expires_at": 101,
                "config_generation": 3, "bundle_version": "v4",
                "model_id": "old", "heartbeat_at": 90,
                "in_flight_dispatch_id": "", "in_flight_deadline_at": 0,
            }},
            "clock": {"now": 100},
        }
        self.request = types.SimpleNamespace(model_id=" new ", session_id="session", lease_epoch=4)
        self.target.current_auth_user = lambda: self.calls.append("user") or self.user
        self.target.time = types.SimpleNamespace(time=lambda: self.calls.append("clock") or 200)
        self.target.migrate_web_serial_config = (
            lambda config: self.calls.append("config") or config
        )
        self.target._plc_web_serial_record = self.record
        self.target._plc_workstation_lease_row = self.lease_row
        self.target._plc_web_serial_mutate = self.mutate
        self.target.WEB_SERIAL_ACTIVE_LEASE_SECONDS = 30
        self.target.WEB_SERIAL_PROTOCOL_VERSION = "v4"
        self.target.PlcConfigError = ConfigError

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

    def test_rebind_preserves_inflight_evidence_and_ttl(self):
        self.lease().update(in_flight_dispatch_id="plcweb_old", in_flight_deadline_at=100)
        result = self.target.plc_web_serial_rebind_model("station", self.request)
        self.assertEqual((result["model_id"], result["heartbeat_at"], result["expires_at"]),
                         ("new", 100, 130))
        self.assertEqual((result["in_flight_dispatch_id"], result["in_flight_deadline_at"]),
                         ("plcweb_old", 100))
        self.assertEqual(self.calls.count("commit"), 1)

    def test_empty_model_is_rejected_before_transaction(self):
        for value in ("", "   ", None):
            with self.subTest(value=value):
                self.setUp()
                self.request.model_id = value
                with self.assertRaises(ConfigError) as caught:
                    self.target.plc_web_serial_rebind_model("station", self.request)
                self.assertEqual(str(caught.exception), "plc_workstation_model_required")
                self.assertFalse(any(isinstance(x, tuple) and x[0] == "mutate" for x in self.calls))

    def test_shared_active_guard_fencing_and_disabled_config(self):
        cases = (
            ("station", lambda: self.state.update(station=None), "plc_workstation_lease_missing"),
            ("lease", lambda: self.state.update(lease=None), "plc_workstation_lease_missing"),
            ("session", lambda: self.lease().update(session_id="other"), "plc_workstation_lease_fenced"),
            ("owner", lambda: self.lease().update(owner_user_id="other"), "plc_workstation_lease_fenced"),
            ("state", lambda: self.lease().update(state="connecting"), "plc_workstation_lease_fenced"),
            ("expiry", lambda: self.lease().update(expires_at=100), "plc_workstation_lease_fenced"),
            ("generation", lambda: self.lease().update(config_generation=2), "plc_workstation_lease_fenced"),
            ("protocol", lambda: self.lease().update(bundle_version="v3"), "plc_workstation_lease_fenced"),
            ("epoch", lambda: self.lease().update(lease_epoch=5), "plc_workstation_lease_fenced"),
            ("disabled", lambda: self.state["station"]["raw_json"]["config"].update(enabled=False),
             "plc_workstation_disabled"),
        )
        for label, change, error in cases:
            with self.subTest(label=label):
                self.setUp()
                change()
                before = copy.deepcopy(self.state)
                with self.assertRaises(ConfigError) as caught:
                    self.target.plc_web_serial_rebind_model("station", self.request)
                self.assertEqual(str(caught.exception), error)
                self.assertEqual(self.state, before)

    def test_inflight_id_and_strict_deadline_boundary(self):
        for dispatch_id, deadline, blocked in (
            ("plcweb_a", 101, True), ("plcweb_a", 100, False),
            ("plcweb_a", 99, False), ("", 101, False), ("manual", 101, True),
        ):
            with self.subTest(dispatch_id=dispatch_id, deadline=deadline):
                self.setUp()
                self.lease().update(in_flight_dispatch_id=dispatch_id,
                                    in_flight_deadline_at=deadline)
                if blocked:
                    with self.assertRaises(ConfigError) as caught:
                        self.target.plc_web_serial_rebind_model("station", self.request)
                    self.assertEqual(str(caught.exception), "plc_workstation_attempt_in_flight")
                else:
                    self.assertEqual(
                        self.target.plc_web_serial_rebind_model("station", self.request)["model_id"], "new"
                    )

    def test_request_property_and_late_dependency_binding(self):
        class Payload:
            @property
            def model_id(inner):
                self.target._plc_web_serial_mutate = lambda *_: {"lease": {"raw_json": {
                    "selected": "after-model"
                }}}
                return "new"
        self.assertEqual(
            self.target.plc_web_serial_rebind_model("station", Payload()),
            {"selected": "after-model"},
        )
        self.setUp()
        original = self.mutate
        def rebind_inside(sid, did, callback):
            self.target.WEB_SERIAL_ACTIVE_LEASE_SECONDS = 41
            self.target._plc_workstation_lease_row = lambda row: {
                "raw_json": row, "selected": "late-row"
            }
            state = original(sid, did, callback)
            self.target._plc_web_serial_record = lambda row: {"selected": "late-result"}
            return state
        self.target._plc_web_serial_mutate = rebind_inside
        self.assertEqual(self.target.plc_web_serial_rebind_model("station", self.request),
                         {"selected": "late-result"})
        self.assertEqual(self.state["lease"]["selected"], "late-row")
        self.assertEqual(self.state["lease"]["raw_json"]["expires_at"], 141)

    def test_active_guard_selected_before_request_properties(self):
        self.setUp()
        old_guard = self.target._plc_web_serial_require_active_lease
        seen = []
        class Payload:
            model_id = "new"
            @property
            def session_id(inner):
                seen.append("session")
                self.target._plc_web_serial_require_active_lease = lambda *_: (
                    seen.append("too-late"), (_ for _ in ()).throw(AssertionError("late guard"))
                )[1]
                return "session"
            @property
            def lease_epoch(inner):
                seen.append("epoch")
                return 4
        def selected_guard(state, sid, epoch):
            seen.append("selected")
            return old_guard(state, sid, epoch)
        def rebind_at_transaction(sid, did, callback):
            self.target._plc_web_serial_require_active_lease = selected_guard
            return self.mutate(sid, did, callback)
        self.target._plc_web_serial_mutate = rebind_at_transaction
        self.assertEqual(self.target.plc_web_serial_rebind_model("station", Payload())["model_id"], "new")
        self.assertEqual(seen, ["session", "epoch", "selected"])

    def test_partial_failure_original_exception_and_one_mutation(self):
        for failed_port in ("ttl", "row", "mutate"):
            with self.subTest(failed_port=failed_port):
                self.setUp()
                error = RuntimeError(failed_port)
                calls = []
                if failed_port == "ttl":
                    class FailTtl:
                        def __radd__(inner, other):
                            calls.append("ttl")
                            raise error
                    self.target.WEB_SERIAL_ACTIVE_LEASE_SECONDS = FailTtl()
                elif failed_port == "row":
                    self.target._plc_workstation_lease_row = lambda row: (
                        calls.append("row"), (_ for _ in ()).throw(error)
                    )[1]
                else:
                    self.target._plc_web_serial_mutate = lambda sid, did, callback: (
                        calls.append("mutate"), (_ for _ in ()).throw(error)
                    )[1]
                proposed = []
                observed_leases = []
                if failed_port != "mutate":
                    def observe_record(row):
                        projected = self.record(row)
                        if isinstance(projected, dict) and "session_id" in projected:
                            observed_leases.append(projected)
                        return projected
                    self.target._plc_web_serial_record = observe_record
                    original_mutate = self.target._plc_web_serial_mutate
                    def observe(sid, did, callback):
                        calls.append("mutate")
                        def observed_callback(current):
                            calls.append("callback")
                            try:
                                callback(current)
                            finally:
                                proposed.append(copy.deepcopy(current))
                        return original_mutate(sid, did, observed_callback)
                    self.target._plc_web_serial_mutate = observe
                before = copy.deepcopy(self.state)
                with self.assertRaises(RuntimeError) as caught:
                    self.target.plc_web_serial_rebind_model("station", self.request)
                self.assertIs(caught.exception, error)
                if failed_port == "mutate":
                    self.assertEqual(calls, ["mutate"])
                    self.assertEqual(proposed, [])
                else:
                    self.assertEqual(calls, ["mutate", "callback", failed_port])
                    self.assertEqual(len(proposed), 1)
                    self.assertEqual(len(observed_leases), 1)
                    lease = observed_leases[0]
                    self.assertEqual((lease["model_id"], lease["heartbeat_at"]), ("new", 100))
                    self.assertEqual(lease["expires_at"], 101 if failed_port == "ttl" else 130)
                    self.assertEqual(proposed[0]["lease"], before["lease"])
                self.assertEqual(self.state, before)

    def test_transaction_result_empty_is_still_empty(self):
        self.target._plc_web_serial_mutate = lambda sid, did, callback: {"lease": None}
        self.assertEqual(self.target.plc_web_serial_rebind_model("station", self.request), {})

    def test_candidate_service_isolation_and_zero_constructor_reads(self):
        if self.baseline:
            self.skipTest("candidate service only")
        from local_inspection_service.plc.lease_maintenance import LeaseMaintenance
        from local_inspection_service.plc.lease_maintenance_ports import LeaseMaintenancePorts
        reads = []
        def build(label):
            state = copy.deepcopy(self.state)
            def get(name, value):
                return lambda: reads.append((label, name)) or value
            def mutate(sid, did, callback):
                callback(state)
                return state
            ports = LeaseMaintenancePorts(
                mutate=get("mutate", mutate), record=get("record", self.record),
                lease_row=get("row", self.lease_row), current_user=get("user", lambda: self.user),
                clock=get("clock", lambda: 200), active_ttl=get("ttl", 30),
                config_error=get("error", ConfigError),
                require_active_lease=get("active", lambda current, sid, epoch: (
                    current["station"], self.record(current["lease"]), 100
                )),
            )
            return LeaseMaintenance(ports)
        a, b = build("a"), build("b")
        self.assertEqual(reads, [])
        def forbidden(*_args, **_kwargs):
            raise AssertionError("service reached root collaborator")
        for name in ("_plc_web_serial_mutate", "_plc_web_serial_record",
                     "_plc_workstation_lease_row", "_plc_web_serial_require_active_lease",
                     "PlcConfigError"):
            setattr(self.target, name, forbidden)
        for service, label in ((a, "a"), (b, "b"), (a, "a")):
            before = len(reads)
            self.assertEqual(service.rebind_model(label, self.request)["model_id"], "new")
            self.assertEqual(reads[before:], [(label, name) for name in
                ("mutate", "active", "ttl", "row", "record")])
        for service, label in ((a, "a"), (b, "b"), (a, "a")):
            before = len(reads)
            with self.assertRaises(ConfigError):
                service.rebind_model(label, types.SimpleNamespace(model_id=""))
            self.assertEqual(reads[before:], [(label, "error")])

    @unittest.skipUnless(POSTGRES, "isolated PostgreSQL check requested explicitly")
    def test_real_postgres_commit_and_written_rollback(self):
        from local_inspection_service.storage.postgres_schema import postgres_ddl
        from local_inspection_service.storage.postgres_runtime_repository import PostgresRuntimeRepository
        from local_inspection_service.storage.runtime_selector import default_postgres_connector

        dsn = os.environ["VANTALINE_POSTGRES_DSN"]
        schema = "lease_rebind_" + uuid.uuid4().hex[:12]
        connection = default_postgres_connector(dsn)
        try:
            with connection.cursor() as cursor:
                cursor.execute(postgres_ddl(schema))
            connection.commit()
            repo = PostgresRuntimeRepository(connection, "<redacted>", schema_name=schema)
            now = int(__import__("time").time())
            station = {
                "id": "station", "token_hash": "token", "name": "test", "status": "ready",
                "config_generation": 3, "profile_verified": True, "created_by_user_id": "owner",
                "created_at": now, "updated_at": now, "config": {"enabled": True},
            }
            lease = {
                "station_id": "station", "session_id": "session", "state": "active",
                "lease_epoch": 4, "owner_user_id": "owner", "model_id": "old",
                "client_instance_id": "browser", "bundle_version": "v4",
                "config_generation": 3, "heartbeat_at": now, "expires_at": now + 60,
                "in_flight_dispatch_id": "", "in_flight_deadline_at": 0,
            }
            repo.upsert_row("plc_workstations", {
                **{key: station[key] for key in (
                    "id", "token_hash", "name", "status", "config_generation",
                    "profile_verified", "created_by_user_id", "created_at", "updated_at"
                )},
                "raw_json": station,
            })
            def lease_row(row):
                return {**{key: row[key] for key in (
                    "station_id", "session_id", "state", "lease_epoch", "owner_user_id",
                    "model_id", "client_instance_id", "bundle_version", "config_generation",
                    "heartbeat_at", "expires_at",
                )}, "raw_json": row}
            repo.upsert_row("plc_workstation_leases", lease_row(lease))
            self.target._plc_web_serial_record = self.record
            self.target._plc_workstation_lease_row = lease_row
            self.target._plc_web_serial_mutate = repo.mutate_plc_web_serial_rows
            result = self.target.plc_web_serial_rebind_model("station", self.request)
            self.assertEqual(result["model_id"], "new")
            observer = default_postgres_connector(dsn)
            try:
                external = PostgresRuntimeRepository(observer, "<redacted>", schema_name=schema)
                committed = external.fetch_by_primary_key("plc_workstation_leases", {"station_id": "station"})
                self.assertEqual((committed["model_id"], committed["raw_json"]["model_id"]), ("new", "new"))
            finally:
                observer.close()
            self.target._plc_web_serial_mutate = repo.mutate_plc_web_serial_rows
            self.request.model_id = "again"
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
                self.target.plc_web_serial_rebind_model("station", self.request)
            self.assertIs(caught.exception, sentinel)
            status = getattr(getattr(connection, "info", None), "transaction_status", None)
            if status is None:
                status = connection.get_transaction_status()
            self.assertEqual(int(status), 0)
            observer = default_postgres_connector(dsn)
            try:
                external = PostgresRuntimeRepository(observer, "<redacted>", schema_name=schema)
                unchanged = external.fetch_by_primary_key("plc_workstation_leases", {"station_id": "station"})
                self.assertEqual(unchanged["raw_json"], committed["raw_json"])
                self.assertEqual(unchanged["heartbeat_at"], committed["heartbeat_at"])
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
