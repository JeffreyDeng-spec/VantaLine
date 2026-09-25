"""Accepted-main/candidate PLC browser diagnostic reservation contract."""
import ast
import copy
import hashlib
import math
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
    names = {"plc_web_serial_diagnostic_plan", "_plc_web_serial_require_active_lease", "_plc_web_serial_token_hash"}
    nodes = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in names:
            nodes.append(node)
        elif not baseline and isinstance(node, ast.ImportFrom) and node.module in {
            "plc.diagnostic_state", "plc.diagnostic_state_ports"
        }:
            nodes.append(node)
        elif not baseline and isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "_plc_diagnostic_state"
            for target in node.targets
        ):
            nodes.append(node)
    assert names <= {node.name for node in nodes if isinstance(node, ast.FunctionDef)}
    target = types.ModuleType("local_inspection_service._diagnostic_state_contract")
    target.__package__ = "local_inspection_service"
    target.__dict__.update(
        Any=object, PlcWebSerialAttemptRequest=object, PlcConfigError=ConfigError,
        hashlib=__import__("hashlib"),
    )
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), "exec"), target.__dict__)
    return target


class DiagnosticStateContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = os.environ.get("VANTALINE_PLC_DIAGNOSTIC_BASELINE_SOURCE")
        cls.baseline = bool(source)
        cls.target = load_target(
            Path(source) if source else
            Path(__file__).resolve().parents[1] / "local_inspection_service/server.py",
            cls.baseline,
        )
        cls.real_active = cls.target._plc_web_serial_require_active_lease
        cls.real_hash = cls.target._plc_web_serial_token_hash

    def setUp(self):
        self.calls = []
        self.state = {
            "station": {"raw_json": {"config_generation": 3, "config": {"enabled": True}}},
            "lease": {"raw_json": {
                "station_id": "station", "session_id": "session", "lease_epoch": 4,
                "owner_user_id": "owner", "state": "active", "expires_at": 101,
                "config_generation": 3, "bundle_version": "v4",
                "model_id": "model", "heartbeat_at": 90,
                "in_flight_dispatch_id": "", "in_flight_deadline_at": 0,
            }},
            "clock": {"now": 100},
        }
        self.request = types.SimpleNamespace(session_id="session", lease_epoch=4, config_generation=3)
        self.frames = [{"frame": "test"}]
        self.target.secrets = types.SimpleNamespace(
            token_hex=lambda n: self.calls.append(("hex", n)) or "id",
            token_urlsafe=lambda n: self.calls.append(("url", n)) or "token",
        )
        self.target.time = types.SimpleNamespace(time=lambda: self.calls.append("clock") or 100.125)
        self.target.math = types.SimpleNamespace(ceil=lambda n: self.calls.append(("ceil", n)) or math.ceil(n))
        self.target.WEB_SERIAL_PROTOCOL_VERSION = "v4"
        self.target.PlcConfigError = ConfigError
        self.target._plc_web_serial_require_active_lease = self.active
        self.target._plc_web_serial_token_hash = lambda token: self.calls.append(("hash", token)) or "hash:" + token
        self.target._plc_workstation_lease_row = self.lease_row
        self.target.build_web_serial_diagnostic_plan = lambda: self.calls.append("frames") or self.frames
        self.target._plc_web_serial_mutate = self.mutate

    def record(self, row):
        return dict(row["raw_json"]) if row else None

    def active(self, state, session, epoch):
        self.calls.append(("active", session, epoch))
        station, lease = self.record(state.get("station")), self.record(state.get("lease"))
        if not station or not lease:
            raise ConfigError("plc_workstation_lease_missing")
        if session != lease["session_id"] or epoch != lease["lease_epoch"] or lease["expires_at"] <= 100:
            raise ConfigError("plc_workstation_lease_fenced")
        return station, lease, 100

    def lease_row(self, row):
        self.calls.append("row")
        return {"raw_json": row, "model_id": row["model_id"]}

    def mutate(self, station, dispatch, callback):
        self.calls.append(("mutate", station, dispatch))
        proposed = copy.deepcopy(self.state)
        callback(proposed)
        self.state = proposed
        self.calls.append("commit")
        return proposed

    def lease(self):
        return self.state["lease"]["raw_json"]

    def test_success_order_dual_clock_and_plaintext_boundary(self):
        original_expiry = self.lease()["expires_at"]
        result = self.target.plc_web_serial_diagnostic_plan("station", self.request)
        self.assertEqual(self.calls, [
            ("hex", 16), ("url", 32), ("mutate", "station", None),
            ("active", "session", 4), "clock", ("ceil", 102.125),
            ("hash", "token"), "row", "frames", "commit"
        ])
        self.assertEqual(result, {
            "diagnostic_id": "plcdiag_id", "attempt_token": "token",
            "protocol_version": "v4", "register": "D206", "write_value": 6,
            "issued_at": 100, "deadline_at_ms": 102125,
            "execution_window_ms": 2000, "ack_timeout_ms": 500,
            "read_timeout_ms": 500, "frames": self.frames,
        })
        self.assertIs(result["frames"], self.frames)
        self.assertEqual(
            (self.lease()["in_flight_dispatch_id"], self.lease()["in_flight_deadline_at"],
             self.lease()["diagnostic_token_hash"], self.lease()["expires_at"]),
            ("plcdiag_id", 103, "hash:token", original_expiry),
        )
        self.assertNotIn("attempt_token", self.lease())

    def test_generation_and_inflight_guards_consume_random_before_transaction(self):
        cases = (
            ("generation", lambda: setattr(self.request, "config_generation", 2),
             "plc_workstation_generation_changed"),
            ("inflight", lambda: self.lease().update(in_flight_dispatch_id="plcweb_other",
                                                     in_flight_deadline_at=101),
             "plc_workstation_dispatch_in_flight"),
        )
        for label, change, expected in cases:
            with self.subTest(label=label):
                self.setUp()
                change()
                before = copy.deepcopy(self.state)
                with self.assertRaises(ConfigError) as caught:
                    self.target.plc_web_serial_diagnostic_plan("station", self.request)
                self.assertEqual(str(caught.exception), expected)
                self.assertEqual(self.calls[:4], [
                    ("hex", 16), ("url", 32), ("mutate", "station", None),
                    ("active", "session", 4),
                ])
                self.assertEqual(self.state, before)
                self.assertNotIn("commit", self.calls)

    def test_strict_inflight_deadline_and_empty_id(self):
        for dispatch_id, deadline, blocked in (
            ("plcweb_x", 101, True), ("plcweb_x", 100, False),
            ("plcweb_x", 99, False), ("", 101, False), ("manual", 101, True),
        ):
            with self.subTest(dispatch_id=dispatch_id, deadline=deadline):
                self.setUp()
                self.lease().update(in_flight_dispatch_id=dispatch_id,
                                    in_flight_deadline_at=deadline)
                if blocked:
                    with self.assertRaises(ConfigError):
                        self.target.plc_web_serial_diagnostic_plan("station", self.request)
                else:
                    self.assertEqual(
                        self.target.plc_web_serial_diagnostic_plan("station", self.request)["diagnostic_id"],
                        "plcdiag_id",
                    )

    def test_distinct_db_and_host_clocks_with_submillisecond_truncation(self):
        self.target._plc_web_serial_require_active_lease = lambda state, session, epoch: (
            self.record(state["station"]), self.record(state["lease"]), 73
        )
        self.target.time.time = lambda: 100.1259
        result = self.target.plc_web_serial_diagnostic_plan("station", self.request)
        self.assertEqual((result["issued_at"], result["deadline_at_ms"]), (73, 102125))
        self.assertEqual(self.lease()["in_flight_deadline_at"], 103)

    def test_late_rebinding_chain_preserves_evaluation_order(self):
        seen = []
        def hex_then_rebind(n):
            seen.append("hex")
            self.target.secrets.token_urlsafe = lambda count: seen.append("new-url") or "late-token"
            self.target._plc_web_serial_mutate = lambda sid, did, cb: (
                seen.append("new-mutate"), self.mutate(sid, did, cb)
            )[1]
            return "id"
        def hash_then_rebind(token):
            seen.append("hash")
            self.target._plc_workstation_lease_row = row_then_rebind
            return "hash:" + token
        def row_then_rebind(row):
            seen.append("row")
            self.target.WEB_SERIAL_PROTOCOL_VERSION = "row-version"
            self.target.build_web_serial_diagnostic_plan = frames_then_rebind
            return self.lease_row(row)
        def frames_then_rebind():
            seen.append("frames")
            self.target.WEB_SERIAL_PROTOCOL_VERSION = "too-late"
            return self.frames
        self.target.secrets.token_hex = hex_then_rebind
        self.target._plc_web_serial_token_hash = hash_then_rebind
        result = self.target.plc_web_serial_diagnostic_plan("station", self.request)
        self.assertEqual(seen, ["hex", "new-url", "new-mutate", "hash", "row", "frames"])
        self.assertEqual(result["attempt_token"], "late-token")
        self.assertEqual(result["protocol_version"], "row-version")

    def test_random_failure_order_and_no_retry(self):
        for port in ("hex", "url"):
            with self.subTest(port=port):
                self.setUp()
                error = RuntimeError(port)
                failures = []
                def fail(n):
                    failures.append(port)
                    raise error
                if port == "hex":
                    self.target.secrets.token_hex = fail
                else:
                    self.target.secrets.token_urlsafe = fail
                with self.assertRaises(RuntimeError) as caught:
                    self.target.plc_web_serial_diagnostic_plan("station", self.request)
                self.assertIs(caught.exception, error)
                self.assertEqual(failures, [port])
                self.assertFalse(any(isinstance(x, tuple) and x[0] == "mutate" for x in self.calls))

    def test_active_guard_selected_before_request_properties(self):
        seen = []
        class Payload:
            config_generation = 3
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
        def selected(state, session, epoch):
            seen.append("selected")
            return self.active(state, session, epoch)
        def mutate(station, dispatch, callback):
            self.target._plc_web_serial_require_active_lease = selected
            return self.mutate(station, dispatch, callback)
        self.target._plc_web_serial_mutate = mutate
        self.target.plc_web_serial_diagnostic_plan("station", Payload())
        self.assertEqual(seen, ["session", "epoch", "selected"])

    def test_partial_failure_order_and_detached_lease(self):
        for port in ("hash", "row", "frames"):
            with self.subTest(port=port):
                self.setUp()
                error = RuntimeError(port)
                lease_copies = []
                proposed = []
                failures = []
                callbacks = []
                def fail(*args):
                    failures.append(port)
                    raise error
                original_active = self.target._plc_web_serial_require_active_lease
                def active(state, session, epoch):
                    station, lease, now = original_active(state, session, epoch)
                    lease_copies.append(lease)
                    return station, lease, now
                self.target._plc_web_serial_require_active_lease = active
                if port == "hash":
                    self.target._plc_web_serial_token_hash = fail
                elif port == "row":
                    self.target._plc_workstation_lease_row = fail
                else:
                    self.target.build_web_serial_diagnostic_plan = fail
                def mutate(station, dispatch, callback):
                    self.calls.append(("mutate", station, dispatch))
                    current = copy.deepcopy(self.state)
                    try:
                        callbacks.append("callback")
                        callback(current)
                    finally:
                        proposed.append(current)
                self.target._plc_web_serial_mutate = mutate
                before = copy.deepcopy(self.state)
                with self.assertRaises(RuntimeError) as caught:
                    self.target.plc_web_serial_diagnostic_plan("station", self.request)
                self.assertIs(caught.exception, error)
                self.assertEqual(failures, [port])
                self.assertEqual(callbacks, ["callback"])
                self.assertEqual(len(lease_copies), 1)
                self.assertEqual(len(proposed), 1)
                self.assertEqual(self.calls.count(("mutate", "station", None)), 1)
                lease = lease_copies[0]
                self.assertEqual((lease["in_flight_dispatch_id"], lease["in_flight_deadline_at"]),
                                 ("plcdiag_id", 103))
                self.assertEqual(lease.get("diagnostic_token_hash"),
                                 None if port == "hash" else "hash:token")
                if port == "frames":
                    self.assertEqual(proposed[0]["lease"]["raw_json"], lease)
                else:
                    self.assertEqual(proposed[0]["lease"], before["lease"])
                self.assertEqual(self.state, before)

    def test_no_callback_returns_empty_plan(self):
        self.target._plc_web_serial_mutate = lambda *_: None
        self.assertEqual(self.target.plc_web_serial_diagnostic_plan("station", self.request), {})

    def test_candidate_service_isolation_and_zero_constructor_reads(self):
        if self.baseline:
            self.skipTest("candidate service only")
        from local_inspection_service.plc.diagnostic_state import DiagnosticState
        from local_inspection_service.plc.diagnostic_state_ports import DiagnosticStatePorts
        reads = []
        def build(label):
            state = copy.deepcopy(self.state)
            def get(name, value):
                return lambda: reads.append((label, name)) or value
            def active(current, session, epoch):
                return self.record(current["station"]), self.record(current["lease"]), 100
            def mutate(station, dispatch, callback):
                callback(state)
                return state
            ports = DiagnosticStatePorts(
                token_hex=get("hex", lambda n: "id"),
                token_urlsafe=get("url", lambda n: "token"),
                active_lease=get("active", active),
                config_error=get("error", ConfigError),
                clock=get("clock", lambda: 100.125),
                ceil=get("ceil", math.ceil),
                token_hash=get("hash", lambda token: "hash:" + token),
                lease_row=get("row", self.lease_row),
                protocol_version=get("version", "v4"),
                frames=get("frames", lambda: self.frames),
                mutate=get("mutate", mutate),
                compare_digest=get("compare", lambda left, right: left == right),
                record=get('record', lambda row: row),
                current_user=get('user', lambda: {'id': 'owner'}),
            )
            return DiagnosticState(ports)
        a, b = build("a"), build("b")
        self.assertEqual(reads, [])
        def forbidden(*_args, **_kwargs):
            raise AssertionError("service reached root collaborator")
        for name in ("_plc_web_serial_mutate", "_plc_web_serial_require_active_lease",
                     "_plc_web_serial_token_hash", "_plc_workstation_lease_row",
                     "build_web_serial_diagnostic_plan", "PlcConfigError"):
            setattr(self.target, name, forbidden)
        self.target.secrets = types.SimpleNamespace(
            token_hex=forbidden, token_urlsafe=forbidden,
        )
        for service, label in ((a, "a"), (b, "b")):
            before = len(reads)
            self.assertEqual(service.plan(label, self.request)["diagnostic_id"], "plcdiag_id")
            self.assertEqual(reads[before:], [(label, name) for name in
                ("hex", "url", "mutate", "active", "clock", "ceil", "hash", "row", "version", "frames")])
        before = len(reads)
        with self.assertRaises(ConfigError):
            a.plan("a", self.request)
        self.assertEqual(reads[before:], [("a", name) for name in
            ("hex", "url", "mutate", "active", "error")])


    @unittest.skipUnless(POSTGRES, "isolated PostgreSQL check requested explicitly")
    def test_real_postgres_commit_and_written_rollback(self):
        from local_inspection_service.storage.postgres_schema import postgres_ddl
        from local_inspection_service.storage.postgres_runtime_repository import PostgresRuntimeRepository
        from local_inspection_service.storage.runtime_selector import default_postgres_connector

        dsn = os.environ["VANTALINE_POSTGRES_DSN"]
        schema = "diagnostic_state_" + uuid.uuid4().hex[:12]
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
                "lease_epoch": 4, "owner_user_id": "owner", "model_id": "model",
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
            self.target._plc_workstation_lease_row = lease_row
            self.target._plc_web_serial_record = self.record
            self.target.current_auth_user = lambda: {"id": "owner"}
            self.target.migrate_web_serial_config = lambda config: config
            self.target._plc_web_serial_require_active_lease = type(self).real_active
            self.target._plc_web_serial_token_hash = type(self).real_hash
            self.target.time = types.SimpleNamespace(time=__import__("time").time)
            self.target._plc_web_serial_mutate = repo.mutate_plc_web_serial_rows
            result = self.target.plc_web_serial_diagnostic_plan("station", self.request)
            self.assertEqual(result["attempt_token"], "token")
            observer = default_postgres_connector(dsn)
            try:
                external = PostgresRuntimeRepository(observer, "<redacted>", schema_name=schema)
                committed = external.fetch_by_primary_key(
                    "plc_workstation_leases", {"station_id": "station"}
                )
                self.assertEqual(
                    committed["raw_json"]["diagnostic_token_hash"],
                    hashlib.sha256(result["attempt_token"].encode("utf-8")).hexdigest(),
                )
                self.assertNotIn("attempt_token", committed["raw_json"])
                self.assertEqual(committed["raw_json"]["in_flight_dispatch_id"], result["diagnostic_id"])
                self.assertEqual(committed["raw_json"]["in_flight_deadline_at"],
                                 math.ceil(result["deadline_at_ms"] / 1000))
                self.assertEqual(
                    (committed["raw_json"]["expires_at"], committed["raw_json"]["heartbeat_at"]),
                    (lease["expires_at"], lease["heartbeat_at"]),
                )
                self.assertLessEqual(now, result["issued_at"])
                self.assertGreater(result["deadline_at_ms"], result["issued_at"] * 1000)
            finally:
                observer.close()
            ready = dict(committed["raw_json"])
            ready["in_flight_dispatch_id"] = ""
            ready["in_flight_deadline_at"] = 0
            repo.upsert_row("plc_workstation_leases", lease_row(ready))
            ready_row = repo.fetch_by_primary_key(
                "plc_workstation_leases", {"station_id": "station"}
            )
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
                self.target.plc_web_serial_diagnostic_plan("station", self.request)
            self.assertIs(caught.exception, sentinel)
            status = getattr(getattr(connection, "info", None), "transaction_status", None)
            if status is None:
                status = connection.get_transaction_status()
            self.assertEqual(int(status), 0)
            observer = default_postgres_connector(dsn)
            try:
                external = PostgresRuntimeRepository(observer, "<redacted>", schema_name=schema)
                unchanged = external.fetch_by_primary_key(
                    "plc_workstation_leases", {"station_id": "station"}
                )
                self.assertEqual(unchanged["raw_json"], ready_row["raw_json"])
                self.assertEqual(unchanged["heartbeat_at"], ready_row["heartbeat_at"])
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
