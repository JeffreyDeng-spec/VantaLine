"""Original-versus-extracted PLC browser lease state contract."""
import ast
import copy
import os
from pathlib import Path
import sys
import types
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

NAMES = {"plc_web_serial_heartbeat", "plc_web_serial_release_lease"}
POSTGRES = "--postgres" in sys.argv
if POSTGRES:
    sys.argv.remove("--postgres")


class ConfigError(Exception):
    pass


def load_target(source: Path) -> types.ModuleType:
    tree = ast.parse(source.read_text(encoding="utf-8-sig"))
    nodes = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in NAMES:
            nodes.append(node)
        elif isinstance(node, ast.ImportFrom) and node.module in {
            "plc.lease_maintenance", "plc.lease_maintenance_ports"
        }:
            nodes.append(node)
        elif isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "_plc_lease_maintenance"
            for target in node.targets
        ):
            nodes.append(node)
    assert NAMES <= {node.name for node in nodes if isinstance(node, ast.FunctionDef)}
    target = types.ModuleType("local_inspection_service._lease_maintenance_contract")
    target.__package__ = "local_inspection_service"
    target.__dict__.update(
        Any=object, PlcWorkstationLeaseHeartbeatRequest=object,
        WEB_SERIAL_ACTIVE_LEASE_SECONDS=30, PlcConfigError=ConfigError,
    )
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), "exec"), target.__dict__)
    return target


class LeaseStateContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        baseline = os.environ.get("VANTALINE_PLC_LEASE_BASELINE_SOURCE")
        cls.target = load_target(
            Path(baseline) if baseline
            else Path(__file__).resolve().parents[1] / "local_inspection_service/server.py"
        )
        cls.baseline = bool(baseline)

    def setUp(self):
        self.target.WEB_SERIAL_ACTIVE_LEASE_SECONDS = 30
        self.calls = []
        self.user = {"id": "owner"}
        self.state = {
            "station": {"raw_json": {"id": "station", "config_generation": 3}},
            "lease": {
                "raw_json": {
                    "station_id": "station", "session_id": "session", "lease_epoch": 4,
                    "owner_user_id": "owner", "state": "active", "config_generation": 3,
                    "expires_at": 101, "heartbeat_at": 90, "in_flight_dispatch_id": "plcweb_a",
                    "in_flight_deadline_at": 105,
                }
            },
            "clock": {"now": 100},
        }
        self.request = types.SimpleNamespace(session_id="session", lease_epoch=4)
        self.target.current_auth_user = lambda: self.calls.append("user") or self.user
        self.target.time = types.SimpleNamespace(time=lambda: self.calls.append("clock") or 200)
        self.target._plc_web_serial_record = self.record
        self.target._plc_workstation_lease_row = self.lease_row
        self.target._plc_web_serial_mutate = self.mutate
        self.target.PlcConfigError = ConfigError

    def record(self, row):
        self.calls.append("record")
        if not isinstance(row, dict):
            return None
        raw = row.get("raw_json")
        return dict(raw) if isinstance(raw, dict) else dict(row)

    def lease_row(self, record):
        self.calls.append("row")
        return {"raw_json": record, "state": record["state"]}

    def mutate(self, station_id, dispatch_id, callback):
        self.calls.append(("mutate", station_id, dispatch_id))
        proposed = copy.deepcopy(self.state)
        callback(proposed)
        self.state = proposed
        self.calls.append("commit")
        return proposed

    def lease(self):
        return self.state["lease"]["raw_json"] if self.state["lease"] else None

    def test_heartbeat_extends_plcweb_attempt_and_keeps_dispatch(self):
        before = copy.deepcopy(self.state)
        result = self.target.plc_web_serial_heartbeat("station", self.request)
        self.assertEqual(result["expires_at"], 130)
        self.assertEqual(result["heartbeat_at"], 100)
        self.assertEqual(result["in_flight_deadline_at"], 130)
        self.assertEqual(self.state["station"], before["station"])
        self.assertEqual(self.calls.count("commit"), 1)
        self.assertEqual(self.calls[0], "user")

    def test_non_plcweb_attempt_deadline_is_not_extended(self):
        for dispatch_id in ("", "manual", "plcweb"):
            with self.subTest(dispatch_id=dispatch_id):
                self.setUp()
                self.lease()["in_flight_dispatch_id"] = dispatch_id
                result = self.target.plc_web_serial_heartbeat("station", self.request)
                self.assertEqual(result["in_flight_deadline_at"], 105)

    def test_all_heartbeat_fences_and_missing_rows_roll_back(self):
        changes = (
            ("session", lambda: setattr(self.request, "session_id", "other"), "fenced"),
            ("epoch", lambda: setattr(self.request, "lease_epoch", 5), "fenced"),
            ("owner", lambda: self.user.update(id="other"), "fenced"),
            ("state", lambda: self.lease().update(state="connecting"), "fenced"),
            ("expiry", lambda: self.lease().update(expires_at=100), "fenced"),
            ("generation", lambda: self.state["station"]["raw_json"].update(config_generation=2), "fenced"),
            ("lease missing", lambda: self.state.update(lease=None), "missing"),
            ("station missing", lambda: self.state.update(station=None), "missing"),
        )
        for label, change, expected in changes:
            with self.subTest(label=label):
                self.setUp()
                change()
                before = copy.deepcopy(self.state)
                with self.assertRaises(ConfigError) as caught:
                    self.target.plc_web_serial_heartbeat("station", self.request)
                self.assertIn(expected, str(caught.exception))
                self.assertEqual(self.state, before)
                self.assertNotIn("commit", self.calls)

    def test_database_zero_clock_uses_host_fallback(self):
        self.state["clock"]["now"] = 0
        self.lease()["expires_at"] = 201
        result = self.target.plc_web_serial_heartbeat("station", self.request)
        self.assertEqual(result["heartbeat_at"], 200)
        self.assertIn("clock", self.calls)

    def test_release_missing_and_stale_identity_are_idempotent(self):
        self.state["lease"] = None
        self.assertEqual(self.target.plc_web_serial_release_lease("station", self.request), {"state": "released"})
        self.assertEqual(self.calls.count("commit"), 1)
        for change in (
            lambda: setattr(self.request, "session_id", "other"),
            lambda: setattr(self.request, "lease_epoch", 5),
            lambda: self.user.update(id="other"),
        ):
            self.setUp()
            change()
            before = copy.deepcopy(self.state["lease"])
            result = self.target.plc_web_serial_release_lease("station", self.request)
            self.assertEqual(result, before["raw_json"])
            self.assertEqual(self.state["lease"], before)
            self.assertEqual(self.calls.count("commit"), 1)

    def test_release_draining_and_deadline_boundary(self):
        for deadline, expected in ((101, "draining"), (100, "released"), (99, "released")):
            with self.subTest(deadline=deadline):
                self.setUp()
                self.lease()["in_flight_deadline_at"] = deadline
                result = self.target.plc_web_serial_release_lease("station", self.request)
                self.assertEqual(result["state"], expected)
                self.assertEqual(result["expires_at"], max(100, deadline))
                self.assertEqual(result["in_flight_dispatch_id"], "plcweb_a")
                self.assertEqual(result["in_flight_deadline_at"], deadline)

    def test_release_does_not_apply_heartbeat_fences(self):
        self.state["station"] = None
        self.lease().update(state="revoked", expires_at=1, config_generation=99,
                            in_flight_deadline_at=101)
        result = self.target.plc_web_serial_release_lease("station", self.request)
        self.assertEqual(result["state"], "draining")
        self.assertEqual(result["expires_at"], 101)

    def test_mutator_callback_and_result_rebind_at_original_times(self):
        original = self.mutate
        def rebind_inside(station_id, dispatch_id, callback):
            self.target.WEB_SERIAL_ACTIVE_LEASE_SECONDS = 41
            self.target._plc_workstation_lease_row = lambda record: {
                "raw_json": record, "selected": "late-row"
            }
            return original(station_id, dispatch_id, callback)
        self.target._plc_web_serial_mutate = rebind_inside
        result = self.target.plc_web_serial_heartbeat("station", self.request)
        self.assertEqual(result["expires_at"], 141)
        self.assertEqual(self.state["lease"]["selected"], "late-row")
        self.setUp()
        def rebind_after_callback(station_id, dispatch_id, callback):
            state = original(station_id, dispatch_id, callback)
            self.target._plc_web_serial_record = lambda row: {"selected": "late-result"}
            return state
        self.target._plc_web_serial_mutate = rebind_after_callback
        self.assertEqual(
            self.target.plc_web_serial_release_lease("station", self.request),
            {"selected": "late-result"},
        )

    def test_late_mutator_binding_and_partial_failure_no_retry(self):
        selected = []
        original = self.mutate
        def auth():
            self.target._plc_web_serial_mutate = lambda *args: selected.append("late") or original(*args)
            return self.user
        self.target.current_auth_user = auth
        self.target.plc_web_serial_heartbeat("station", self.request)
        self.assertEqual(selected, ["late"])
        self.setUp()
        error = RuntimeError("after mutation")
        def failing_mutate(station_id, dispatch_id, callback):
            proposed = copy.deepcopy(self.state)
            callback(proposed)
            raise error
        self.target._plc_web_serial_mutate = failing_mutate
        before = copy.deepcopy(self.state)
        with self.assertRaises(RuntimeError) as caught:
            self.target.plc_web_serial_release_lease("station", self.request)
        self.assertIs(caught.exception, error)
        self.assertEqual(self.state, before)

    def test_two_instance_isolation_and_zero_constructor_reads(self):
        if self.baseline:
            self.skipTest("candidate service only")
        from local_inspection_service.plc.lease_maintenance import LeaseMaintenance
        from local_inspection_service.plc.lease_maintenance_ports import LeaseMaintenancePorts
        reads = []
        def build(label):
            lease = copy.deepcopy(self.lease())
            lease["expires_at"] = 301
            state = {"station": {"raw_json": {"config_generation": 3}},
                     "lease": {"raw_json": lease}, "clock": {"now": 0}}
            def get(name, value):
                return lambda: reads.append((label, name)) or value
            def mutate(sid, did, callback):
                callback(state)
                return state
            ports = LeaseMaintenancePorts(
                mutate=get("mutate", mutate), record=get("record", self.record),
                lease_row=get("row", self.lease_row), current_user=get("user", lambda: {"id": "owner"}),
                clock=get("clock", lambda: 200), active_ttl=get("ttl", 30),
                config_error=get("error", ConfigError),
            )
            return LeaseMaintenance(ports)
        for method in ("heartbeat", "release"):
            reads.clear()
            a, b = build("a"), build("b")
            self.assertEqual(reads, [])
            def forbidden(*_args, **_kwargs):
                raise AssertionError("service reached root collaborator")
            for name in ("_plc_web_serial_mutate", "_plc_web_serial_record",
                         "_plc_workstation_lease_row", "current_auth_user", "PlcConfigError"):
                setattr(self.target, name, forbidden)
            for service, label in ((a, "a"), (b, "b"), (a, "a")):
                before = len(reads)
                result = getattr(service, method)(label, self.request)
                self.assertEqual(result["state"], "active" if method == "heartbeat" else "released")
                used = reads[before:]
                expected = (
                    ("user", "mutate", "record", "record", "clock", "ttl", "row", "record")
                    if method == "heartbeat"
                    else ("user", "mutate", "record", "clock", "row", "record")
                )
                self.assertEqual(used, [(label, name) for name in expected])
                if method == "heartbeat":
                    bad_request = types.SimpleNamespace(session_id="fenced", lease_epoch=4)
                    with self.assertRaises(ConfigError):
                        service.heartbeat(label, bad_request)
                    self.assertEqual(
                        reads[before + len(expected):],
                        [(label, name) for name in
                         ("user", "mutate", "record", "record", "clock", "error")],
                    )


    @unittest.skipUnless(POSTGRES, "isolated PostgreSQL check requested explicitly")
    def test_real_postgres_commit_and_fenced_rollback(self):
        from local_inspection_service.storage.postgres_schema import postgres_ddl
        from local_inspection_service.storage.postgres_runtime_repository import PostgresRuntimeRepository
        from local_inspection_service.storage.runtime_selector import default_postgres_connector

        dsn = os.environ["VANTALINE_POSTGRES_DSN"]
        schema = "lease_smoke_" + uuid.uuid4().hex[:12]
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
                "created_at": now, "updated_at": now,
            }
            lease = {
                "station_id": "station", "session_id": "session", "state": "active",
                "lease_epoch": 4, "owner_user_id": "owner", "model_id": "model",
                "client_instance_id": "browser", "bundle_version": "v4",
                "config_generation": 3, "heartbeat_at": now, "expires_at": now + 60,
                "in_flight_dispatch_id": "plcweb_a", "in_flight_deadline_at": now + 60,
            }
            repo.upsert_row("plc_workstations", {**station, "raw_json": station})
            repo.upsert_row("plc_workstation_leases", {**lease, "raw_json": lease})
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
            result = self.target.plc_web_serial_heartbeat("station", self.request)
            committed = repo.fetch_by_primary_key("plc_workstation_leases", {"station_id": "station"})
            self.assertEqual(committed["raw_json"]["expires_at"], result["expires_at"])
            self.assertEqual(committed["raw_json"]["in_flight_deadline_at"], result["expires_at"])
            self.request.session_id = "fenced"
            with self.assertRaises(ConfigError):
                self.target.plc_web_serial_heartbeat("station", self.request)
            unchanged = repo.fetch_by_primary_key("plc_workstation_leases", {"station_id": "station"})
            self.assertEqual(unchanged["raw_json"], committed["raw_json"])
            self.request.session_id = "session"
            sentinel = RuntimeError("after SQL write")
            def write_then_fail(station_id, dispatch_id, callback):
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
                return repo.mutate_plc_web_serial_rows(station_id, dispatch_id, wrapped)
            self.target._plc_web_serial_mutate = write_then_fail
            with self.assertRaises(RuntimeError) as caught:
                self.target.plc_web_serial_heartbeat("station", self.request)
            self.assertIs(caught.exception, sentinel)
            status = getattr(getattr(connection, "info", None), "transaction_status", None)
            if status is None:
                status = connection.get_transaction_status()
            self.assertEqual(int(status), 0, "failed mutation left the SQL transaction open")
            observer = default_postgres_connector(dsn)
            try:
                external = PostgresRuntimeRepository(observer, "<redacted>", schema_name=schema)
                self.assertEqual(
                    external.fetch_by_primary_key("plc_workstation_leases", {"station_id": "station"})["raw_json"],
                    committed["raw_json"],
                )
                self.assertEqual(
                    external.fetch_by_primary_key("plc_workstation_leases", {"station_id": "station"})["heartbeat_at"],
                    committed["heartbeat_at"],
                )
            finally:
                observer.close()
            self.target._plc_web_serial_mutate = repo.mutate_plc_web_serial_rows
            released = self.target.plc_web_serial_release_lease("station", self.request)
            self.assertEqual(released["state"], "draining")
            self.assertEqual(
                repo.fetch_by_primary_key("plc_workstation_leases", {"station_id": "station"})["raw_json"]["state"],
                "draining",
            )
        finally:
            connection.rollback()
            with connection.cursor() as cursor:
                cursor.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
            connection.commit()
            connection.close()


if __name__ == "__main__":
    unittest.main()
