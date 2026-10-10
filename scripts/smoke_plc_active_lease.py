"""Original/owned active browser lease checks with synthetic state and identity."""
import ast
import copy
import os
from pathlib import Path
import sys
import types
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from canonical_application_source_contract import read_checked_application_source
BASELINE = os.environ.get("VANTALINE_PLC_ACTIVE_LEASE_BASELINE_SOURCE")
NAME = "_plc_web_serial_require_active_lease"


class ConfigError(Exception):
    pass


def load_target():
    source = Path(BASELINE) if BASELINE else Path(__file__).resolve().parents[1] / "local_inspection_service/server.py"
    nodes = []
    raw = read_checked_application_source(source, encoding='utf-8-sig')
    if not BASELINE:
        from application_integration_source_contract import restore_plc_domain_root
        raw = restore_plc_domain_root(raw)
    for node in ast.parse(raw).body:
        if isinstance(node, ast.FunctionDef) and node.name == NAME:
            nodes.append(node)
        elif not BASELINE and isinstance(node, ast.ImportFrom) and node.module in {"plc.station_service", "plc.station_ports"}:
            nodes.append(node)
        elif not BASELINE and isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id in {"_plc_station_service", NAME} for t in node.targets
        ):
            nodes.append(node)
    target = types.ModuleType("local_inspection_service._active_lease_contract")
    target.__package__ = "local_inspection_service"
    target.Any = object
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), "exec"), target.__dict__)
    return target


class ActiveLeaseContract(unittest.TestCase):
    def setUp(self):
        self.api = load_target()
        self.events = []
        self.state = {
            "station": {"id": "station", "config_generation": 3, "config": {"enabled": True}},
            "lease": {"session_id": "session", "owner_user_id": "owner", "state": "active",
                      "expires_at": 101, "config_generation": 3, "bundle_version": "v4", "lease_epoch": 4},
            "clock": {"now": 100},
        }
        self.api.PlcConfigError = ConfigError
        self.api.WEB_SERIAL_PROTOCOL_VERSION = "v4"
        self.api._plc_web_serial_record = lambda value: self.events.append("record") or value
        self.api.current_auth_user = lambda: self.events.append("user") or {"id": "owner"}
        self.api.time = types.SimpleNamespace(time=lambda: self.events.append("clock") or 90)
        self.api.migrate_web_serial_config = lambda value: self.events.append("config") or value

    def invoke(self, epoch=4):
        return getattr(self.api, NAME)(self.state, "session", epoch)

    def test_valid_aliases_order_and_no_state_change(self):
        before = copy.deepcopy(self.state)
        station, lease, now = self.invoke()
        self.assertIs(station, self.state["station"])
        self.assertIs(lease, self.state["lease"])
        self.assertEqual(now, 100)
        self.assertEqual(self.events, ["record", "record", "user", "config"])
        self.assertEqual(self.state, before)

    def test_missing_still_reads_clock_and_identity(self):
        self.state.update(station=None, lease=None, clock={"now": 0})
        with self.assertRaisesRegex(ConfigError, "lease_missing"):
            self.invoke()
        self.assertEqual(self.events, ["record", "record", "clock", "user"])
        self.api.current_auth_user = lambda: (_ for _ in ()).throw(LookupError("identity"))
        with self.assertRaisesRegex(LookupError, "identity"):
            self.invoke()
        self.state["clock"] = {"now": "bad"}
        with self.assertRaises(ValueError):
            self.invoke()

    def test_each_fence_and_strict_deadline(self):
        for key, value in (("session_id", "other"), ("owner_user_id", "other"),
                           ("state", "draining"), ("expires_at", 100),
                           ("config_generation", 0), ("bundle_version", "old"), ("lease_epoch", 0)):
            with self.subTest(key=key):
                self.setUp()
                self.state["lease"][key] = value
                with self.assertRaisesRegex(ConfigError, "lease_fenced"):
                    self.invoke()
                self.assertNotIn("config", self.events)

    def test_short_circuit_and_optional_epoch(self):
        self.state["lease"].update(session_id="other", expires_at="bad", lease_epoch="bad")
        with self.assertRaisesRegex(ConfigError, "lease_fenced"):
            self.invoke("bad")
        self.state["lease"].update(session_id="session", expires_at=101)
        self.assertEqual(self.invoke(None)[2], 100)
        with self.assertRaises(ValueError):
            self.invoke()
        self.state["lease"]["lease_epoch"] = 4
        self.state["station"]["config_generation"] = 0
        self.state["lease"]["config_generation"] = 0
        with self.assertRaisesRegex(ConfigError, "lease_fenced"):
            self.invoke()

    def test_config_after_fences_and_failure_identity(self):
        self.state["station"]["config"] = "legacy"
        values = []
        self.api.migrate_web_serial_config = lambda value: values.append(value) or {"enabled": False}
        with self.assertRaisesRegex(ConfigError, "workstation_disabled"):
            self.invoke()
        self.assertEqual(values, [{}])
        sentinel = RuntimeError("migration")
        def fail(value):
            raise sentinel
        self.api.migrate_web_serial_config = fail
        with self.assertRaises(RuntimeError) as caught:
            self.invoke()
        self.assertIs(caught.exception, sentinel)

    def test_zero_clock_uses_fresh_supplier_and_identity(self):
        self.state["clock"]["now"] = 0
        self.assertEqual(self.invoke()[2], 90)
        self.api.time = types.SimpleNamespace(time=lambda: 91)
        self.assertEqual(self.invoke()[2], 91)
        self.api.current_auth_user = lambda: {"id": "other"}
        with self.assertRaisesRegex(ConfigError, "lease_fenced"):
            self.invoke()

    def test_migration_receives_original_config_and_retains_partial_effect(self):
        config = self.state["station"]["config"]
        def fail(value):
            self.assertIs(value, config)
            value["seen"] = True
            raise RuntimeError("after mutation")
        self.api.migrate_web_serial_config = fail
        with self.assertRaisesRegex(RuntimeError, "after mutation"):
            self.invoke()
        self.assertTrue(config["seen"])

    @unittest.skipIf(BASELINE, "candidate owned method binding")
    def test_owner_binding_two_instances_and_no_constructor_io(self):
        owner = self.api._plc_station_service
        self.assertIs(getattr(self.api, NAME).__self__, owner)
        other = load_target()
        self.assertIsNot(other._plc_station_service, owner)
        self.assertEqual(self.events, [])
        self.assertEqual(self.invoke()[2], 100)
        self.assertIs(getattr(self.api, NAME).__func__, type(owner)._plc_web_serial_require_active_lease)


if __name__ == "__main__":
    unittest.main()
