"""Accepted-main/candidate browser diagnostic confirmation contract."""
import ast
import copy
import hashlib
import hmac
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
    names = {
        "plc_web_serial_confirm_diagnostic",
        "_plc_web_serial_require_active_lease",
        "_plc_web_serial_token_hash",
    }
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
    target = types.ModuleType("local_inspection_service._diagnostic_confirm_contract")
    target.__package__ = "local_inspection_service"
    target.__dict__.update(
        Any=object, PlcWebSerialDiagnosticConfirmRequest=object,
        PlcConfigError=ConfigError, hashlib=hashlib, hmac=hmac,
    )
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), "exec"), target.__dict__)
    return target


class ConfirmContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = os.environ.get("VANTALINE_PLC_CONFIRM_BASELINE_SOURCE")
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
                "in_flight_dispatch_id": "plcdiag_id", "in_flight_deadline_at": 101,
                "diagnostic_token_hash": "hash:token",
            }},
            "clock": {"now": 100},
        }
        self.request = types.SimpleNamespace(
            session_id="session", lease_epoch=4,
            diagnostic_id="plcdiag_id", attempt_token="token",
        )
        self.target._plc_web_serial_require_active_lease = self.active
        self.target._plc_web_serial_token_hash = lambda token: self.calls.append(("hash", token)) or "hash:" + token
        self.target.hmac = types.SimpleNamespace(
            compare_digest=lambda a, b: self.calls.append(("compare", a, b)) or a == b
        )
        self.target.PlcConfigError = ConfigError
        self.target._plc_web_serial_mutate = self.mutate

    def record(self, row):
        return dict(row["raw_json"]) if row else None

    def active(self, state, session, epoch):
        self.calls.append(("active", session, epoch))
        lease = self.record(state.get("lease"))
        if not lease or session != lease["session_id"] or epoch != lease["lease_epoch"]:
            raise ConfigError("plc_workstation_lease_fenced")
        return self.record(state.get("station")), lease, 100

    def mutate(self, station, dispatch, callback):
        self.calls.append(("mutate", station, dispatch))
        proposed = copy.deepcopy(self.state)
        callback(proposed)
        self.state = proposed
        self.calls.append("commit")
        return {"ignored": True}

    def lease(self):
        return self.state["lease"]["raw_json"]

    def test_success_repeat_no_evidence_consumption(self):
        before = copy.deepcopy(self.state)
        for _ in range(2):
            result = self.target.plc_web_serial_confirm_diagnostic("station", self.request)
            self.assertEqual(result, {"confirmed": True, "diagnostic_id": "plcdiag_id"})
            self.assertEqual(self.state, before)
        self.assertEqual(self.calls, [
            ("mutate", "station", None), ("active", "session", 4),
            ("hash", "token"), ("compare", "hash:token", "hash:token"), "commit",
        ] * 2)

    def test_error_priority_deadline_boundary(self):
        for label, change, expected in (
            ("id", lambda: self.lease().update(in_flight_dispatch_id="other"),
             "plc_diagnostic_not_in_flight"),
            ("deadline_equal", lambda: self.lease().update(in_flight_deadline_at=100),
             "plc_diagnostic_deadline_expired"),
            ("deadline_past", lambda: self.lease().update(in_flight_deadline_at=99),
             "plc_diagnostic_deadline_expired"),
            ("token", lambda: setattr(self.request, "attempt_token", "wrong"),
             "plc_diagnostic_token_invalid"),
            ("missing_hash", lambda: self.lease().pop("diagnostic_token_hash"),
             "plc_diagnostic_token_invalid"),
        ):
            with self.subTest(label=label):
                self.setUp()
                change()
                before = copy.deepcopy(self.state)
                with self.assertRaises(ConfigError) as caught:
                    self.target.plc_web_serial_confirm_diagnostic("station", self.request)
                self.assertEqual(str(caught.exception), expected)
                self.assertEqual(self.state, before)
                self.assertNotIn("commit", self.calls)
                if label in {"id", "deadline_equal", "deadline_past", "missing_hash"}:
                    self.assertFalse(any(isinstance(x, tuple) and x[0] == "hash" for x in self.calls))

    def test_empty_hash_short_circuits_token_property_and_compare(self):
        self.lease()["diagnostic_token_hash"] = ""
        class Payload:
            session_id = "session"
            lease_epoch = 4
            diagnostic_id = "plcdiag_id"
            @property
            def attempt_token(inner):
                raise AssertionError("token read on empty hash")
        with self.assertRaises(ConfigError) as caught:
            self.target.plc_web_serial_confirm_diagnostic("station", Payload())
        self.assertEqual(str(caught.exception), "plc_diagnostic_token_invalid")
        self.assertFalse(any(isinstance(x, tuple) and x[0] == "compare" for x in self.calls))

    def test_compare_callee_selected_before_hash_and_token(self):
        seen = []
        def chosen(a, b):
            seen.append("chosen")
            return True
        def hash_then_rebind(token):
            seen.append("hash")
            return "hash:token"
        class Payload:
            session_id = "session"
            lease_epoch = 4
            diagnostic_id = "plcdiag_id"
            @property
            def attempt_token(inner):
                seen.append("token")
                self.target.hmac.compare_digest = lambda *_: (
                    seen.append("too-late-compare"), False
                )[1]
                self.target._plc_web_serial_token_hash = lambda *_: (
                    seen.append("too-late-hash"), "wrong"
                )[1]
                return "token"
        self.target.hmac.compare_digest = chosen
        self.target._plc_web_serial_token_hash = hash_then_rebind
        self.target.plc_web_serial_confirm_diagnostic("station", Payload())
        self.assertEqual(seen, ["token", "hash", "chosen"])

    def test_return_id_re_read_and_mutate_result_ignored(self):
        reads = []
        class Payload:
            session_id = "session"
            lease_epoch = 4
            attempt_token = "token"
            @property
            def diagnostic_id(inner):
                reads.append("id")
                return "plcdiag_id" if len(reads) == 1 else "returned-late-id"
        self.assertEqual(
            self.target.plc_web_serial_confirm_diagnostic("station", Payload()),
            {"confirmed": True, "diagnostic_id": "returned-late-id"},
        )
        self.assertEqual(reads, ["id", "id"])
        self.setUp()
        class FailsAfterCommit:
            session_id = "session"
            lease_epoch = 4
            attempt_token = "token"
            calls = 0
            @property
            def diagnostic_id(inner):
                inner.calls += 1
                if inner.calls == 2:
                    raise RuntimeError("return id failed")
                return "plcdiag_id"
        with self.assertRaisesRegex(RuntimeError, "return id failed"):
            self.target.plc_web_serial_confirm_diagnostic("station", FailsAfterCommit())
        self.assertEqual(self.calls.count("commit"), 1)

    def test_guard_and_error_class_late_binding(self):
        seen = []
        original_guard = self.target._plc_web_serial_require_active_lease
        def selected(state, session, epoch):
            seen.append("selected")
            return original_guard(state, session, epoch)
        class Payload:
            lease_epoch = 4
            attempt_token = "token"
            diagnostic_id = "plcdiag_id"
            @property
            def session_id(inner):
                seen.append("session")
                self.target._plc_web_serial_require_active_lease = lambda *_: (
                    seen.append("too-late"), (_ for _ in ()).throw(AssertionError("late guard"))
                )[1]
                return "session"
        def mutate(sid, did, callback):
            self.target._plc_web_serial_require_active_lease = selected
            return self.mutate(sid, did, callback)
        self.target._plc_web_serial_mutate = mutate
        self.target.plc_web_serial_confirm_diagnostic("station", Payload())
        self.assertEqual(seen, ["session", "selected"])
        self.setUp()
        class ChangedError(Exception):
            pass
        class WrongId:
            session_id = "session"
            lease_epoch = 4
            attempt_token = "token"
            @property
            def diagnostic_id(inner):
                self.target.PlcConfigError = ChangedError
                return "wrong"
        with self.assertRaises(ChangedError) as caught:
            self.target.plc_web_serial_confirm_diagnostic("station", WrongId())
        self.assertEqual(str(caught.exception), "plc_diagnostic_not_in_flight")

    def test_failure_same_exception_and_single_mutation(self):
        for port in ("guard", "hash", "compare"):
            with self.subTest(port=port):
                self.setUp()
                error = RuntimeError(port)
                failures = []
                def fail(*_):
                    failures.append(port)
                    raise error
                if port == "guard":
                    self.target._plc_web_serial_require_active_lease = fail
                elif port == "hash":
                    self.target._plc_web_serial_token_hash = fail
                else:
                    self.target.hmac.compare_digest = fail
                before = copy.deepcopy(self.state)
                with self.assertRaises(RuntimeError) as caught:
                    self.target.plc_web_serial_confirm_diagnostic("station", self.request)
                self.assertIs(caught.exception, error)
                self.assertEqual(failures, [port])
                self.assertEqual(self.calls.count(("mutate", "station", None)), 1)
                self.assertEqual(self.state, before)

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
            def mutate(sid, did, callback):
                callback(state)
                return {"ignored": True}
            ports = DiagnosticStatePorts(
                token_hex=get("hex", lambda n: "id"),
                token_urlsafe=get("url", lambda n: "token"),
                active_lease=get("active", active),
                config_error=get("error", ConfigError),
                clock=get("clock", lambda: 100.125),
                ceil=get("ceil", __import__("math").ceil),
                token_hash=get("hash", lambda token: "hash:" + token),
                lease_row=get("row", lambda row: row),
                protocol_version=get("version", "v4"),
                frames=get("frames", lambda: []),
                mutate=get("mutate", mutate),
                compare_digest=get("compare", lambda a, b: a == b),
            )
            return DiagnosticState(ports)
        a, b = build("a"), build("b")
        self.assertEqual(reads, [])
        def forbidden(*_args, **_kwargs):
            raise AssertionError("service reached root collaborator")
        self.target._plc_web_serial_mutate = forbidden
        self.target._plc_web_serial_require_active_lease = forbidden
        self.target._plc_web_serial_token_hash = forbidden
        self.target.PlcConfigError = forbidden
        self.target.hmac = types.SimpleNamespace(compare_digest=forbidden)
        for service, label in ((a, "a"), (b, "b"), (a, "a")):
            before = len(reads)
            self.assertEqual(service.confirm(label, self.request)["confirmed"], True)
            self.assertEqual(reads[before:], [(label, name) for name in
                ("mutate", "active", "compare", "hash")])
        before = len(reads)
        bad = types.SimpleNamespace(
            session_id="session", lease_epoch=4, diagnostic_id="other",
            attempt_token="token",
        )
        with self.assertRaises(ConfigError):
            a.confirm("a", bad)
        self.assertEqual(reads[before:], [("a", name) for name in
            ("mutate", "active", "error")])


    @unittest.skipUnless(POSTGRES, "isolated PostgreSQL check requested explicitly")
    def test_real_postgres_confirmation_and_written_rollback(self):
        from local_inspection_service.storage.postgres_schema import postgres_ddl
        from local_inspection_service.storage.postgres_runtime_repository import PostgresRuntimeRepository
        from local_inspection_service.storage.runtime_selector import default_postgres_connector

        dsn = os.environ["VANTALINE_POSTGRES_DSN"]
        schema = "diagnostic_confirm_" + uuid.uuid4().hex[:12]
        connection = default_postgres_connector(dsn)
        try:
            with connection.cursor() as cursor:
                cursor.execute(postgres_ddl(schema))
            connection.commit()
            repo = PostgresRuntimeRepository(connection, "<redacted>", schema_name=schema)
            now = int(__import__("time").time())
            station = {
                "id": "station", "token_hash": "station-token", "name": "test", "status": "ready",
                "config_generation": 3, "profile_verified": True, "created_by_user_id": "owner",
                "created_at": now, "updated_at": now, "config": {"enabled": True},
            }
            lease = {
                "station_id": "station", "session_id": "session", "state": "active",
                "lease_epoch": 4, "owner_user_id": "owner", "model_id": "model",
                "client_instance_id": "browser", "bundle_version": "v4",
                "config_generation": 3, "heartbeat_at": now, "expires_at": now + 7200,
                "in_flight_dispatch_id": "plcdiag_id", "in_flight_deadline_at": now + 3600,
                "diagnostic_token_hash": hashlib.sha256(b"token").hexdigest(),
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
            self.target.current_auth_user = lambda: {"id": "owner"}
            self.target.migrate_web_serial_config = lambda config: config
            self.target.time = types.SimpleNamespace(time=__import__("time").time)
            self.target.WEB_SERIAL_PROTOCOL_VERSION = "v4"
            self.target._plc_web_serial_require_active_lease = type(self).real_active
            self.target._plc_web_serial_token_hash = type(self).real_hash
            self.target.hmac = hmac
            self.target._plc_web_serial_mutate = repo.mutate_plc_web_serial_rows
            def assert_idle():
                status = getattr(getattr(connection, "info", None), "transaction_status", None)
                if status is None:
                    status = connection.get_transaction_status()
                self.assertEqual(int(status), 0)
            self.assertEqual(
                self.target.plc_web_serial_confirm_diagnostic("station", self.request),
                {"confirmed": True, "diagnostic_id": "plcdiag_id"},
            )
            assert_idle()
            self.assertEqual(
                self.target.plc_web_serial_confirm_diagnostic("station", self.request)["confirmed"],
                True,
            )
            assert_idle()
            observer = default_postgres_connector(dsn)
            try:
                external = PostgresRuntimeRepository(observer, "<redacted>", schema_name=schema)
                committed = external.fetch_by_primary_key(
                    "plc_workstation_leases", {"station_id": "station"}
                )
                self.assertEqual(committed["raw_json"], lease)
                self.assertEqual((committed["expires_at"], committed["heartbeat_at"]),
                                 (lease["expires_at"], lease["heartbeat_at"]))
            finally:
                observer.close()
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
                self.target.plc_web_serial_confirm_diagnostic("station", self.request)
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
