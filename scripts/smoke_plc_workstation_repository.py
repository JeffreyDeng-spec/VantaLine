"""Original/candidate workstation row and persistence contracts; synthetic state only."""
import ast
from collections.abc import Callable
import copy
import inspect
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
NAMES = {"_plc_web_serial_empty_state", "_plc_web_serial_load_local", "_plc_web_serial_save_local",
         "_plc_web_serial_record", "_plc_workstation_row", "_plc_workstation_lease_row",
         "_plc_web_serial_dispatch_row", "_plc_web_serial_upsert_row", "_plc_web_serial_mutate"}
BASELINE = os.environ.get("VANTALINE_PLC_WORKSTATION_REPOSITORY_BASELINE_SOURCE")


class ConfigError(Exception):
    pass


def load_target():
    source = Path(BASELINE) if BASELINE else Path(__file__).resolve().parents[1] / "local_inspection_service/server.py"
    nodes = []
    raw = source.read_text(encoding="utf-8-sig")
    if not BASELINE:
        from application_integration_source_contract import verify_actual_compositions, restore_delta, PLC_WORKSTATION
        verify_actual_compositions()
        raw = restore_delta(raw, PLC_WORKSTATION)
    for n in ast.parse(raw).body:
        if isinstance(n, ast.FunctionDef) and n.name in NAMES: nodes.append(n)
        elif not BASELINE and isinstance(n, ast.ImportFrom) and n.module in {"plc.workstation_repository", "plc.workstation_repository_ports"}: nodes.append(n)
        elif not BASELINE and isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "_plc_workstation_repository" for t in n.targets): nodes.append(n)
    assert {n.name for n in nodes if isinstance(n, ast.FunctionDef)} == NAMES
    target = types.ModuleType("local_inspection_service._workstation_repository_contract")
    target.__package__ = "local_inspection_service"
    target.__dict__.update(Any=object, Callable=Callable, copy=copy, json=json, os=os, time=time)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), "exec"), target.__dict__)
    return target


class RepositoryContracts(unittest.TestCase):
    def setUp(self):
        self.api = load_target()
        self.events = []
        self.directory = tempfile.TemporaryDirectory(prefix="plc-repository-contract-")
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "state.json"
        events = self.events
        class Lock:
            def __enter__(self): events.append("lock")
            def __exit__(self, *args): events.append("unlock")
        self.api.__dict__.update(PlcConfigError=ConfigError, SYSTEM_OWNER_ID="system",
            PLC_WEB_SERIAL_JSON_TEST_ENV="VANTALINE_SYNTHETIC_STATION_JSON", PLC_WEB_SERIAL_STATE_PATH=self.path,
            DATA_DIR=self.path.parent, _config_io_lock=Lock(), runtime_postgres_repository_or_none=lambda: None,
            _business_files=types.SimpleNamespace(read_text=lambda path, **kw: path.read_text(**kw),
                                                write_text=lambda path, content, **kw: path.write_text(content, **kw)))
        environment = patch.dict(os.environ, {"VANTALINE_SYNTHETIC_STATION_JSON": "0"})
        environment.start(); self.addCleanup(environment.stop)

    def test_local_missing_malformed_and_normalized_records(self):
        empty = {"workstations": {}, "leases": {}, "dispatches": {}}
        self.assertEqual(self.api._plc_web_serial_load_local(), empty)
        for text in ("{", "[]", '"string"', "null"):
            self.path.write_text(text)
            self.assertEqual(self.api._plc_web_serial_load_local(), empty)
        self.path.write_text(json.dumps({"workstations": {"a": {"nested": [1]}, "invalid": 3}, "leases": [], "unknown": {}}))
        self.assertEqual(self.api._plc_web_serial_load_local(), {"workstations": {"a": {"nested": [1]}}, "leases": {}, "dispatches": {}})
        self.api._business_files = types.SimpleNamespace(read_text=lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("adapter")))
        with self.assertRaisesRegex(ValueError, "adapter"): self.api._plc_web_serial_load_local()

    def test_save_bytes_atomic_replace_and_failed_replace_keeps_previous(self):
        state = {"workstations": {"s": {"name": "检测"}}, "leases": {}, "dispatches": {}}
        self.api._plc_web_serial_save_local(state)
        expected = json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True).replace("\n", os.linesep).encode("utf-8")
        self.assertEqual(self.path.read_bytes(), expected)
        self.assertFalse(self.path.with_suffix(".tmp").exists())
        with patch("os.replace", side_effect=OSError("replace")):
            with self.assertRaisesRegex(OSError, "replace"): self.api._plc_web_serial_save_local({"new": {}})
        self.assertEqual(self.path.read_bytes(), expected)
        self.assertEqual(json.loads(self.path.with_suffix(".tmp").read_text()), {"new": {}})

    def test_mapping_shallow_identity_defaults_and_required_fields(self):
        nested = []; raw = {"nested": nested}
        result = self.api._plc_web_serial_record({"raw_json": raw})
        self.assertIsNot(result, raw); self.assertIs(result["nested"], nested)
        self.assertIsNone(self.api._plc_web_serial_record([]))
        record = {"id": "s", "token_hash": "hash", "name": "Station"}
        row = self.api._plc_workstation_row(record)
        self.assertIs(row["raw_json"], record)
        self.assertEqual((row["status"], row["config_generation"], row["created_by_user_id"]), ("commissioning", 0, "system"))
        lease = dict(station_id="s", session_id="session", state="active", lease_epoch="7", owner_user_id="account",
                     client_instance_id="browser", bundle_version="v4", config_generation="3", heartbeat_at="100", expires_at="130")
        row = self.api._plc_workstation_lease_row(lease)
        self.assertIs(row["raw_json"], lease); self.assertEqual(row["lease_epoch"], 7)
        dispatch = dict(dispatch_id="d", station_id="s", detection_request_id="r", session_id="session", lease_epoch="7",
                        config_generation="3", status="planned", created_at="100", updated_at="101", passed="nonempty")
        row = self.api._plc_web_serial_dispatch_row(dispatch)
        self.assertIs(row["raw_json"], dispatch); self.assertEqual(row["id"], "d"); self.assertTrue(row["passed"])
        with self.assertRaises(KeyError) as caught: self.api._plc_web_serial_dispatch_row({})
        self.assertEqual(caught.exception.args, ("dispatch_id",))

    def test_falsey_postgres_remains_authoritative_and_preserves_callback(self):
        calls = []; returned = {"result": "postgres"}; callback = lambda state: self.fail("local callback")
        class Repository:
            def __bool__(self): return False
            def upsert_row(self, *args): calls.append(("upsert", args))
            def mutate_plc_web_serial_rows(self, *args): calls.append(("mutate", args)); return returned
        self.api.runtime_postgres_repository_or_none = lambda: Repository()
        row = {"id": "s"}
        self.api._plc_web_serial_upsert_row("table", row, "workstations", "s")
        self.assertIs(self.api._plc_web_serial_mutate("s", "d", callback), returned)
        self.assertEqual(calls, [("upsert", ("table", row)), ("mutate", ("s", "d", callback))])
        self.assertEqual(self.events, [])

    def test_local_write_gate_precedes_lock_and_callback(self):
        for action in (lambda: self.api._plc_web_serial_upsert_row("t", {}, "workstations", "s"),
                       lambda: self.api._plc_web_serial_mutate("s", "d", lambda state: self.fail("callback"))):
            with self.assertRaisesRegex(ConfigError, "postgres_coordination_unavailable"): action()
        self.assertEqual(self.events, [])
        os.environ["VANTALINE_SYNTHETIC_STATION_JSON"] = " YeS "
        self.api._plc_web_serial_upsert_row("table", {"id": "s"}, "workstations", "s")
        self.assertEqual(self.events, ["lock", "unlock"])
        self.assertEqual(json.loads(self.path.read_text())["workstations"], {"s": {"id": "s"}})

    def test_mutation_isolation_none_rows_and_exception_releases_lock(self):
        os.environ["VANTALINE_SYNTHETIC_STATION_JSON"] = "1"
        initial = {"workstations": {"s": {"nested": [1]}}, "leases": {"s": {"id": "lease"}}, "dispatches": {"d": {"id": "d"}}}
        self.path.write_text(json.dumps(initial))
        def fail(state):
            state["station"]["nested"].append(2)
            raise ValueError("abort")
        with self.assertRaisesRegex(ValueError, "abort"): self.api._plc_web_serial_mutate("s", "d", fail)
        self.assertEqual(json.loads(self.path.read_text()), initial)
        self.assertEqual(self.events, ["lock", "unlock"])
        def change(state):
            self.assertEqual(state["clock"], {"now": 100})
            state["station"]["nested"].append(3)
            state["lease"] = None
            state["dispatch"] = {}
        with patch("time.time", return_value=100.75): result = self.api._plc_web_serial_mutate("s", "d", change)
        stored = json.loads(self.path.read_text())
        self.assertEqual(stored["leases"], initial["leases"])
        self.assertEqual(stored["dispatches"], {"d": {}})
        self.assertEqual(result["station"], {"nested": [1, 3]})

    @unittest.skipIf(BASELINE, "candidate assembly only")
    def test_eleven_lazy_ports_and_nine_forwarders(self):
        service = self.api._plc_workstation_repository; count = 0
        for group in (service.files, service.policy, service.storage):
            for name in group.__dataclass_fields__:
                a, b = object(), object()
                for value in (a, b, a):
                    setattr(self.api, name, value); self.assertIs(getattr(group, name)(), value)
                count += 1
        self.assertEqual(count, 11)
        api = load_target(); calls = []; result = object()
        class Fake:
            def __getattr__(self, name): return lambda *args, **kwargs: calls.append((name, args, kwargs)) or result
        api._plc_workstation_repository = Fake()
        for name in NAMES:
            fn = getattr(api, name); args = [object() for _ in inspect.signature(fn).parameters]
            self.assertIs(fn(*args), result); self.assertEqual(calls[-1], (name, tuple(args), {}))


if __name__ == "__main__":
    unittest.main()
