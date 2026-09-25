"""Replay accepted-main PLC diagnostic receipt behavior against the extracted service."""
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
POSTGRES = '--postgres' in sys.argv
if POSTGRES:
    sys.argv.remove('--postgres')


class ConfigError(Exception):
    pass


def baseline_function():
    path = Path(os.environ["VANTALINE_PLC_FINISH_BASELINE_SOURCE"])
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    node = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                and node.name == "plc_web_serial_finish_diagnostic")
    namespace = {"Any": object, "PlcWebSerialDiagnosticReceiptRequest": object,
                 "PlcConfigError": ConfigError, "hmac": hmac}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), namespace)
    return namespace


class FinishContract:
    def setUp(self):
        self.state = {"lease": {"raw_json": {
            "station_id": "station", "session_id": "session", "lease_epoch": 4,
            "owner_user_id": "owner", "state": "active", "expires_at": 101,
            "in_flight_dispatch_id": "plcdiag_id", "in_flight_deadline_at": 101,
            "diagnostic_token_hash": "hash:token", "other": "retained",
        }}}
        self.request = types.SimpleNamespace(session_id="session", lease_epoch=4,
            diagnostic_id="plcdiag_id", attempt_token="token", outcome="success")
        self.calls = []
        self.error_class = ConfigError

    def record(self, row):
        self.calls.append("record")
        return dict(row["raw_json"]) if row else None

    def auth(self):
        self.calls.append("auth")
        return {"id": "owner"}

    def token_hash(self, value):
        self.calls.append("hash")
        return "hash:" + value

    def compare(self, a, b):
        self.calls.append("compare")
        return a == b

    def lease_row(self, lease):
        self.calls.append("row")
        return {"raw_json": dict(lease)}

    def mutate(self, station_id, dispatch_id, callback):
        self.calls.append(("mutate", station_id, dispatch_id))
        proposed = copy.deepcopy(self.state)
        callback(proposed)
        self.state = proposed
        self.calls.append("commit")

    def invoke(self):
        raise NotImplementedError

    def set_dep(self, name, value):
        raise NotImplementedError

    def test_success_and_draining(self):
        for state in ("active", "draining"):
            with self.subTest(state=state):
                self.setUp()
                self.state["lease"]["raw_json"]["state"] = state
                self.assertEqual(self.invoke(), {"released": True, "diagnostic_id": "plcdiag_id"})
                lease = self.state["lease"]["raw_json"]
                self.assertEqual(lease["other"], "retained")
                self.assertFalse(any(k in lease for k in (
                    "in_flight_dispatch_id", "in_flight_deadline_at", "diagnostic_token_hash")))
                self.assertEqual(self.calls, [
                    ("mutate", "station", None), "record", "auth", "hash",
                    "compare", "row", "commit",
                ])

    def test_error_priority_and_rollback(self):
        cases = (
            ("missing", lambda: self.state.update(lease=None), "plc_workstation_lease_fenced"),
            ("owner", lambda: self.state["lease"]["raw_json"].update(owner_user_id="other"), "plc_workstation_lease_fenced"),
            ("epoch", lambda: self.state["lease"]["raw_json"].update(lease_epoch=5), "plc_workstation_lease_fenced"),
            ("state", lambda: self.state["lease"]["raw_json"].update(state="expired"), "plc_workstation_lease_fenced"),
            ("dispatch", lambda: self.state["lease"]["raw_json"].update(in_flight_dispatch_id="other"), "plc_diagnostic_not_in_flight"),
            ("empty_hash", lambda: self.state["lease"]["raw_json"].update(diagnostic_token_hash=""), "plc_diagnostic_token_invalid"),
            ("bad_token", lambda: setattr(self.request, "attempt_token", "wrong"), "plc_diagnostic_token_invalid"),
            ("outcome", lambda: setattr(self.request, "outcome", "unknown"), "plc_diagnostic_outcome_invalid"),
        )
        for label, change, expected in cases:
            with self.subTest(label=label):
                self.setUp()
                change()
                before = copy.deepcopy(self.state)
                with self.assertRaises(ConfigError) as caught:
                    self.invoke()
                self.assertEqual(str(caught.exception), expected)
                self.assertEqual(self.state, before)
                self.assertNotIn("commit", self.calls)

    def test_all_outcomes_and_repeat(self):
        for outcome in ("success", "failed", "uncertain"):
            with self.subTest(outcome=outcome):
                self.setUp()
                self.request.outcome = outcome
                self.assertTrue(self.invoke()["released"])
                with self.assertRaises(ConfigError) as caught:
                    self.invoke()
                self.assertEqual(str(caught.exception), "plc_diagnostic_not_in_flight")

    def test_empty_hash_does_not_read_token(self):
        self.state["lease"]["raw_json"]["diagnostic_token_hash"] = ""
        class Payload:
            session_id = "session"
            lease_epoch = 4
            diagnostic_id = "plcdiag_id"
            outcome = "success"
            @property
            def attempt_token(inner):
                raise AssertionError("token read on empty hash")
        self.request = Payload()
        with self.assertRaises(ConfigError) as caught:
            self.invoke()
        self.assertEqual(str(caught.exception), "plc_diagnostic_token_invalid")
        self.assertNotIn("hash", self.calls)
    def test_record_can_rebind_user_before_identity_check(self):
        original_record = self.record
        def record_then_rebind(row):
            self.set_dep("auth", lambda: self.calls.append("rebound_auth") or {"id": "owner"})
            return original_record(row)
        self.set_dep("auth", lambda: {"id": "other"})
        self.set_dep("record", record_then_rebind)
        self.assertTrue(self.invoke()["released"])
        self.assertEqual(self.calls[:3], [("mutate", "station", None), "record", "rebound_auth"])

    def test_token_property_cannot_rebind_selected_hash_or_compare(self):
        seen = []
        self.set_dep("token_hash", lambda token: seen.append("old_hash") or "hash:" + token)
        self.set_dep("compare", lambda left, right: seen.append("old_compare") or left == right)
        outer = self
        class Payload:
            session_id = "session"
            lease_epoch = 4
            diagnostic_id = "plcdiag_id"
            outcome = "success"
            @property
            def attempt_token(inner):
                seen.append("token")
                outer.set_dep("token_hash", lambda *_: (_ for _ in ()).throw(AssertionError("late hash")))
                outer.set_dep("compare", lambda *_: (_ for _ in ()).throw(AssertionError("late compare")))
                return "token"
        self.request = Payload()
        self.assertTrue(self.invoke()["released"])
        self.assertEqual(seen, ["token", "old_hash", "old_compare"])

    def test_error_class_is_selected_after_bad_id_property(self):
        class ChangedError(Exception):
            pass
        outer = self
        class Payload:
            session_id = "session"
            lease_epoch = 4
            attempt_token = "token"
            outcome = "success"
            @property
            def diagnostic_id(inner):
                outer.set_dep("error_class", ChangedError)
                return "wrong"
        self.request = Payload()
        with self.assertRaises(ChangedError) as caught:
            self.invoke()
        self.assertEqual(str(caught.exception), "plc_diagnostic_not_in_flight")

    def test_detached_copy_on_row_failure(self):
        observed = []
        original_record = type(self).record.__get__(self)
        sentinel = RuntimeError("row")
        def copy_record(row):
            copied = original_record(row)
            observed.append((row["raw_json"], copied))
            return copied
        def fail_row(lease):
            observed.append(lease)
            raise sentinel
        def mutate_without_commit(station, dispatch, callback):
            self.calls.append(("mutate", station, dispatch))
            proposed = copy.deepcopy(self.state)
            with self.assertRaises(RuntimeError) as caught:
                callback(proposed)
            self.assertIs(caught.exception, sentinel)
            self.assertEqual(proposed, self.state)
            raise caught.exception
        self.set_dep("record", copy_record)
        self.set_dep("lease_row", fail_row)
        self.set_dep("mutate", mutate_without_commit)
        before = copy.deepcopy(self.state)
        with self.assertRaises(RuntimeError) as caught:
            self.invoke()
        self.assertIs(caught.exception, sentinel)
        self.assertEqual(self.state, before)
        self.assertEqual(len(observed), 2)
        original_row, copied = observed[0]
        self.assertIs(observed[1], copied)
        self.assertIsNot(original_row, copied)
        self.assertTrue(all(key in original_row for key in (
            "in_flight_dispatch_id", "in_flight_deadline_at", "diagnostic_token_hash")))
        self.assertFalse(any(key in copied for key in (
            "in_flight_dispatch_id", "in_flight_deadline_at", "diagnostic_token_hash")))
        self.assertNotIn("commit", self.calls)

    def test_post_commit_second_id_read(self):
        reads = []
        class Payload:
            session_id = "session"
            lease_epoch = 4
            attempt_token = "token"
            outcome = "success"
            @property
            def diagnostic_id(inner):
                reads.append("id")
                return "plcdiag_id" if len(reads) == 1 else "late_id"
        self.request = Payload()
        self.assertEqual(self.invoke()["diagnostic_id"], "late_id")
        self.assertEqual(reads, ["id", "id"])
        self.assertEqual(self.calls.count("commit"), 1)

    def test_post_commit_second_id_exception(self):
        sentinel = RuntimeError("return id")
        reads = []
        class Payload:
            session_id = "session"
            lease_epoch = 4
            attempt_token = "token"
            outcome = "success"
            @property
            def diagnostic_id(inner):
                reads.append("id")
                if len(reads) == 2:
                    raise sentinel
                return "plcdiag_id"
        self.request = Payload()
        with self.assertRaises(RuntimeError) as caught:
            self.invoke()
        self.assertIs(caught.exception, sentinel)
        self.assertEqual(reads, ["id", "id"])
        self.assertEqual(self.calls.count("commit"), 1)
        self.assertNotIn("diagnostic_token_hash", self.state["lease"]["raw_json"])
    def test_deadline_expiry_does_not_block_receipt(self):
        self.state["lease"]["raw_json"]["in_flight_deadline_at"] = 1
        self.assertTrue(self.invoke()["released"])


class BaselineFinish(FinishContract, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.module = baseline_function()
        self.module.update(
            _plc_web_serial_record=self.record,
            current_auth_user=self.auth,
            _plc_web_serial_token_hash=self.token_hash,
            _plc_workstation_lease_row=self.lease_row,
            _plc_web_serial_mutate=self.mutate,
            hmac=types.SimpleNamespace(compare_digest=self.compare),
        )

    def invoke(self):
        return self.module["plc_web_serial_finish_diagnostic"]("station", self.request)

    def set_dep(self, name, value):
        names = {
            "record": "_plc_web_serial_record", "auth": "current_auth_user",
            "token_hash": "_plc_web_serial_token_hash",
            "lease_row": "_plc_workstation_lease_row",
            "mutate": "_plc_web_serial_mutate",
            "error_class": "PlcConfigError",
        }
        if name == "compare":
            self.module["hmac"].compare_digest = value
        else:
            self.module[names[name]] = value


class CandidateFinish(FinishContract, unittest.TestCase):
    def setUp(self):
        super().setUp()
        from local_inspection_service.plc.diagnostic_state import DiagnosticState
        from local_inspection_service.plc.diagnostic_state_ports import DiagnosticStatePorts
        self.service = DiagnosticState(DiagnosticStatePorts(
            token_hex=lambda: lambda n: "id", token_urlsafe=lambda: lambda n: "token",
            active_lease=lambda: lambda *_: None, config_error=lambda: self.error_class,
            clock=lambda: lambda: 100, ceil=lambda: lambda value: value,
            token_hash=lambda: self.token_hash, lease_row=lambda: self.lease_row,
            protocol_version=lambda: "v4", frames=lambda: lambda: [],
            mutate=lambda: self.mutate, compare_digest=lambda: self.compare,
            record=lambda: self.record, current_user=lambda: self.auth,
        ))

    def invoke(self):
        return self.service.finish("station", self.request)

    def set_dep(self, name, value):
        setattr(self, name, value)
    def test_independent_instances_zero_constructor_reads_and_root_adapter(self):
        from local_inspection_service.plc.diagnostic_state import DiagnosticState
        from local_inspection_service.plc.diagnostic_state_ports import DiagnosticStatePorts
        reads = []
        def build(label):
            state = copy.deepcopy(self.state)
            def get(name, value):
                return lambda: reads.append((label, name)) or value
            def record(row):
                return dict(row["raw_json"]) if row else None
            def row(lease):
                return {"raw_json": dict(lease)}
            def mutate(station, dispatch, callback):
                proposed = copy.deepcopy(state)
                callback(proposed)
                state.clear()
                state.update(proposed)
            ports = DiagnosticStatePorts(
                token_hex=get("hex", lambda n: "id"),
                token_urlsafe=get("url", lambda n: "token"),
                active_lease=get("active", lambda *_: None),
                config_error=get("error", ConfigError),
                clock=get("clock", lambda: 100),
                ceil=get("ceil", lambda n: n),
                token_hash=get("hash", lambda token: "hash:" + token),
                lease_row=get("row", row),
                protocol_version=get("version", "v4"),
                frames=get("frames", lambda: []),
                mutate=get("mutate", mutate),
                compare_digest=get("compare", lambda left, right: left == right),
                record=get("record", record),
                current_user=get("user", lambda: {"id": "owner"}),
            )
            return DiagnosticState(ports), state
        self.assertEqual(self.state["lease"]["raw_json"].get("in_flight_dispatch_id"), "plcdiag_id")
        a, state_a = build("a")
        b, state_b = build("b")
        self.assertEqual(reads, [])
        for service, state, label in ((a, state_a, "a"), (b, state_b, "b"),
                                      (a, state_a, "a")):
            if label == "a" and reads:
                state["lease"] = copy.deepcopy(self.state["lease"])
            before = len(reads)
            self.assertTrue(service.finish("station", self.request)["released"])
            self.assertEqual(reads[before:], [(label, key) for key in (
                "mutate", "record", "user", "compare", "hash", "row")])
            self.assertNotIn("diagnostic_token_hash", state["lease"]["raw_json"])
        self.assertNotIn("diagnostic_token_hash", state_b["lease"]["raw_json"])

        original_lease = copy.deepcopy(self.state["lease"])
        from local_inspection_service.plc.diagnostic_state import DiagnosticState
        from local_inspection_service.plc.diagnostic_state_ports import DiagnosticStatePorts
        path = Path(__file__).resolve().parents[1] / "local_inspection_service/server.py"
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        nodes = [node for node in tree.body if (
            isinstance(node, ast.Assign) and any(
                isinstance(item, ast.Name) and item.id == "_plc_diagnostic_state"
                for item in node.targets)
        ) or (isinstance(node, ast.FunctionDef)
              and node.name == "plc_web_serial_finish_diagnostic")]
        self.assertEqual(len(nodes), 2)
        target = {
            "_PlcDiagnosticState": DiagnosticState,
            "_PlcDiagnosticStatePorts": DiagnosticStatePorts,
            "Any": object, "PlcWebSerialDiagnosticReceiptRequest": object,
            "_plc_web_serial_record": self.record,
            "current_auth_user": self.auth,
            "_plc_web_serial_mutate": self.mutate,
            "_plc_web_serial_token_hash": self.token_hash,
            "_plc_workstation_lease_row": self.lease_row,
            "PlcConfigError": ConfigError,
            "hmac": hmac,
        }
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), target)
        self.assertEqual(
            target["plc_web_serial_finish_diagnostic"]("station", self.request),
            {"released": True, "diagnostic_id": "plcdiag_id"},
        )
        def forbidden(*_args, **_kwargs):
            raise AssertionError("root collaborator reached")
        target["_plc_diagnostic_state"] = a
        for name in ("_plc_web_serial_record", "current_auth_user",
                     "_plc_web_serial_mutate", "_plc_web_serial_token_hash",
                     "_plc_workstation_lease_row", "PlcConfigError"):
            target[name] = forbidden
        target["hmac"] = types.SimpleNamespace(compare_digest=forbidden)
        state_a["lease"] = copy.deepcopy(original_lease)
        self.assertEqual(
            target["plc_web_serial_finish_diagnostic"]("station", self.request),
            {"released": True, "diagnostic_id": "plcdiag_id"},
        )
    @unittest.skipUnless(POSTGRES, "isolated PostgreSQL check requested")
    def test_real_postgres_commit_and_rollback(self):
        from local_inspection_service.storage.postgres_schema import postgres_ddl
        from local_inspection_service.storage.postgres_runtime_repository import PostgresRuntimeRepository
        from local_inspection_service.storage.runtime_selector import default_postgres_connector
        import time

        dsn = os.environ["VANTALINE_POSTGRES_DSN"]
        schema = "diagnostic_finish_" + uuid.uuid4().hex[:12]
        connection = default_postgres_connector(dsn)
        try:
            with connection.cursor() as cursor:
                cursor.execute(postgres_ddl(schema))
            connection.commit()
            repo = PostgresRuntimeRepository(connection, "<redacted>", schema_name=schema)
            now = int(time.time())
            station = {
                "id": "station", "token_hash": "station-token", "name": "test",
                "status": "ready", "config_generation": 3, "profile_verified": True,
                "created_by_user_id": "owner", "created_at": now, "updated_at": now,
                "config": {"enabled": True},
            }
            lease = {
                "station_id": "station", "session_id": "session", "state": "draining",
                "lease_epoch": 4, "owner_user_id": "owner", "model_id": "model",
                "client_instance_id": "browser", "bundle_version": "v4",
                "config_generation": 3, "heartbeat_at": now - 50,
                "expires_at": now - 1, "in_flight_dispatch_id": "plcdiag_id",
                "in_flight_deadline_at": now - 2,
                "diagnostic_token_hash": hashlib.sha256(b"token").hexdigest(),
            }
            repo.upsert_row("plc_workstations", {
                **{key: station[key] for key in (
                    "id", "token_hash", "name", "status", "config_generation",
                    "profile_verified", "created_by_user_id", "created_at", "updated_at")},
                "raw_json": station,
            })
            def lease_row(row):
                return {**{key: row[key] for key in (
                    "station_id", "session_id", "state", "lease_epoch", "owner_user_id",
                    "model_id", "client_instance_id", "bundle_version", "config_generation",
                    "heartbeat_at", "expires_at")}, "raw_json": row}
            repo.upsert_row("plc_workstation_leases", lease_row(lease))
            self.record = lambda row: dict(row["raw_json"]) if row else None
            self.token_hash = lambda token: hashlib.sha256(token.encode()).hexdigest()
            self.compare = hmac.compare_digest
            self.lease_row = lease_row
            self.mutate = repo.mutate_plc_web_serial_rows
            def idle():
                status = getattr(getattr(connection, "info", None), "transaction_status", None)
                if status is None:
                    status = connection.get_transaction_status()
                self.assertEqual(int(status), 0)
            self.assertTrue(self.invoke()["released"])
            idle()
            observer = default_postgres_connector(dsn)
            try:
                external = PostgresRuntimeRepository(observer, "<redacted>", schema_name=schema)
                committed = external.fetch_by_primary_key(
                    "plc_workstation_leases", {"station_id": "station"})
                clean = committed["raw_json"]
                self.assertEqual(clean["state"], "draining")
                self.assertEqual(clean["expires_at"], now - 1)
                self.assertEqual(clean["heartbeat_at"], now - 50)
                self.assertFalse(any(key in clean for key in (
                    "in_flight_dispatch_id", "in_flight_deadline_at", "diagnostic_token_hash")))
                with self.assertRaises(ConfigError) as caught:
                    self.invoke()
                self.assertEqual(str(caught.exception), "plc_diagnostic_not_in_flight")
                idle()
                sentinel = RuntimeError("after SQL write")
                def write_then_fail(sid, did, callback):
                    def wrapped(state):
                        callback(state)
                        with connection.cursor() as cursor:
                            cursor.execute(
                                f'UPDATE "{schema}"."plc_workstation_leases" '
                                'SET heartbeat_at = %s WHERE station_id = %s',
                                (now - 99, "station"),
                            )
                            self.assertEqual(cursor.rowcount, 1)
                        raise sentinel
                    return repo.mutate_plc_web_serial_rows(sid, did, wrapped)
                self.mutate = write_then_fail
                # Restore evidence to exercise rollback after a successful callback and SQL write.
                repo.upsert_row("plc_workstation_leases", lease_row(lease))
                with self.assertRaises(RuntimeError) as caught:
                    self.invoke()
                self.assertIs(caught.exception, sentinel)
                idle()
                after = external.fetch_by_primary_key(
                    "plc_workstation_leases", {"station_id": "station"})
                self.assertEqual(after["raw_json"], lease)
                self.assertEqual(after["heartbeat_at"], now - 50)
            finally:
                observer.close()
        finally:
            connection.rollback()
            with connection.cursor() as cursor:
                cursor.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
            connection.commit()
            connection.close()


def load_tests(loader, tests, pattern):
    suite = unittest.TestSuite()
    if os.environ.get("VANTALINE_PLC_FINISH_BASELINE_SOURCE"):
        suite.addTests(loader.loadTestsFromTestCase(BaselineFinish))
    suite.addTests(loader.loadTestsFromTestCase(CandidateFinish))
    return suite

if __name__ == "__main__":
    unittest.main()
