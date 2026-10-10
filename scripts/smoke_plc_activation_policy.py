"""Retained readiness policy uses synthetic repositories, profiles and import stubs."""
import ast
import builtins
from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar
import hashlib
import hmac
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace, ModuleType
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from canonical_application_source_contract import read_checked_application_source
BASELINE = os.environ.get("VANTALINE_PLC_ACTIVATION_BASELINE_SOURCE")
NAMES = {"plc_pg_coordination_available", "plc_profile_fingerprint", "plc_device_profile_verified",
         "plc_read_profile_verified", "plc_serial_dependency_available", "plc_activation_errors"}


def build():
    source = Path(BASELINE) if BASELINE else ROOT / "local_inspection_service/server.py"
    nodes = []
    for node in ast.parse(read_checked_application_source(source, encoding='utf-8-sig')).body:
        if isinstance(node, ast.FunctionDef) and node.name in NAMES:
            nodes.append(node)
        elif not BASELINE and isinstance(node, ast.ImportFrom) and node.module == "plc.legacy_activation":
            nodes.append(node)
        elif not BASELINE and isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id in NAMES | {"_legacy_plc_activation"} for t in node.targets
        ):
            nodes.append(node)
    target = ModuleType("local_inspection_service._activation_contract")
    target.__package__ = "local_inspection_service"
    target.__dict__.update(Any=object, hashlib=hashlib, hmac=hmac)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), "exec"), target.__dict__)
    return target


class ActivationContract(unittest.TestCase):
    def setUp(self):
        self.api = build()
        self.events = []
        self.env = {}
        self.identity = ContextVar("synthetic_activation_user", default=None)
        self.api._request_user = self.identity
        self.api._plc_transport_factory = None
        self.api.runtime_postgres_repository_or_none = lambda: None
        self.api.os = SimpleNamespace(getenv=lambda name: self.events.append(name) or self.env.get(name))
        self.api._plc_canonical = lambda value: json.dumps(value, sort_keys=True, ensure_ascii=True)

    def test_repository_requires_atomic_primitive_even_if_falsey(self):
        class Repository:
            def __bool__(self):
                raise AssertionError("repository truthiness must not be consulted")
            def mutate_plc_fenced_attempt_with_db_time(self):
                raise AssertionError("primitive must not be invoked")
        self.assertFalse(self.api.plc_pg_coordination_available())
        self.api.runtime_postgres_repository_or_none = Repository
        self.assertTrue(self.api.plc_pg_coordination_available())
        self.api.runtime_postgres_repository_or_none = lambda: SimpleNamespace(mutate_plc_fenced_attempt_with_db_time=False)
        self.assertFalse(self.api.plc_pg_coordination_available())

    def test_fingerprint_field_order_and_read_extension(self):
        settings = {"protocol": "fixture", "capture_input_register": "D1", "unrelated": "ignored"}
        calls = []
        self.api._plc_canonical = lambda material: calls.append(material) or "canonical"
        expected = hashlib.sha256(b"canonical").hexdigest()
        for include in (False, True):
            self.assertEqual(self.api.plc_profile_fingerprint(settings, include_read=include), expected)
        self.assertEqual(list(calls[0]), ["protocol", "checksum_mode", "serial_port", "baudrate", "parity",
                         "data_bits", "stop_bits", "result_register", "output_control_point"])
        self.assertEqual(list(calls[1])[-2:], ["capture_input_register", "capture_trigger_value"])
        self.assertNotIn("unrelated", calls[0])
        self.api._plc_canonical = lambda _: "中"
        with self.assertRaises(UnicodeEncodeError):
            self.api.plc_profile_fingerprint({}, include_read=False)

    def test_profile_override_missing_config_and_normalized_environment(self):
        for name, env_name, include in (("plc_device_profile_verified", "VANTALINE_PLC_DEVICE_PROFILE_FINGERPRINT", False),
                                       ("plc_read_profile_verified", "VANTALINE_PLC_READ_PROFILE_FINGERPRINT", True)):
            with self.subTest(name=name):
                self.setUp()
                fn = getattr(self.api, name)
                self.assertFalse(fn())
                self.env[env_name] = " AbC "
                self.api.plc_profile_fingerprint = lambda settings, **kw: self.events.append(kw) or "abc"
                self.assertTrue(fn({}))
                self.assertEqual(self.events[-1], {"include_read": include})
                self.api._plc_transport_factory = False
                self.events.clear()
                self.assertTrue(fn(None))
                self.assertEqual(self.events, [])

    def test_serial_import_only_when_override_and_identity_do_not_both_exist(self):
        original = builtins.__import__
        def missing(name, *args, **kwargs):
            if name == "serial":
                self.events.append("import")
                raise ImportError("synthetic missing")
            return original(name, *args, **kwargs)
        with patch("builtins.__import__", side_effect=missing):
            self.assertFalse(self.api.plc_serial_dependency_available())
            self.api._plc_transport_factory = False
            self.assertFalse(self.api.plc_serial_dependency_available())
            token = self.identity.set({})
            try:
                self.assertTrue(self.api.plc_serial_dependency_available())
            finally:
                self.identity.reset(token)
        self.assertEqual(self.events, ["import", "import"])
        with patch.dict(sys.modules, {"serial": ModuleType("serial")}):
            self.assertTrue(self.api.plc_serial_dependency_available())

    def test_other_import_errors_propagate_and_user_is_thread_local(self):
        original = builtins.__import__
        def broken(name, *args, **kwargs):
            if name == "serial":
                raise RuntimeError("synthetic import failure")
            return original(name, *args, **kwargs)
        with patch("builtins.__import__", side_effect=broken):
            with self.assertRaisesRegex(RuntimeError, "synthetic import failure"):
                self.api.plc_serial_dependency_available()
        self.api._plc_transport_factory = False
        with patch.dict(sys.modules, {"serial": None}):
            def probe(user):
                token = self.identity.set(user)
                try:
                    return self.api.plc_serial_dependency_available()
                finally:
                    self.identity.reset(token)
            with ThreadPoolExecutor(max_workers=2) as executor:
                results = list(executor.map(probe, [{"id": "a"}, None, {}, None]))
            self.assertEqual(results, [True, False, True, False])
        self.assertIsNone(self.identity.get())

    def test_errors_disabled_order_and_capture_gate(self):
        for name in ("plc_pg_coordination_available", "plc_serial_dependency_available",
                     "plc_device_profile_verified", "plc_read_profile_verified"):
            setattr(self.api, name, lambda *args, name=name: self.events.append(name) or False)
        self.assertEqual(self.api.plc_activation_errors({"enabled": False}), [])
        self.assertEqual(self.events, [])
        result = self.api.plc_activation_errors({"enabled": True, "capture_trigger_enabled": True})
        self.assertEqual([r["code"] for r in result], ["plc_pg_coordination_unavailable", "plc_serial_dependency_missing",
                                                     "plc_device_profile_unverified", "plc_read_profile_unverified"])
        self.assertEqual(self.events, ["plc_pg_coordination_available", "plc_serial_dependency_available",
                                      "plc_device_profile_verified", "plc_read_profile_verified"])
        self.events.clear()
        self.assertEqual(len(self.api.plc_activation_errors({"enabled": True})), 3)
        self.assertNotIn("plc_read_profile_verified", self.events)

    def test_late_helper_selection_and_error_identity(self):
        def coordination():
            self.api.plc_serial_dependency_available = lambda: True
            return True
        self.api.plc_pg_coordination_available = coordination
        self.api.plc_serial_dependency_available = lambda: self.fail("old serial helper")
        self.api.plc_device_profile_verified = lambda _: True
        self.assertEqual(self.api.plc_activation_errors({"enabled": True}), [])
        sentinel = RuntimeError("repository")
        self.api.runtime_postgres_repository_or_none = lambda: (_ for _ in ()).throw(sentinel)
        # Use original owned callable to avoid the intentionally replaced helper.
        if BASELINE:
            target = build()
            target.runtime_postgres_repository_or_none = self.api.runtime_postgres_repository_or_none
            callback = target.plc_pg_coordination_available
        else:
            callback = self.api._legacy_plc_activation.plc_pg_coordination_available
        with self.assertRaises(RuntimeError) as caught:
            callback()
        self.assertIs(caught.exception, sentinel)

    @unittest.skipIf(BASELINE, "candidate binding and dormant startup")
    def test_root_bindings_and_no_constructor_work_or_worker_activation(self):
        self.assertEqual(self.events, [])
        for name in NAMES:
            self.assertIs(getattr(self.api, name).__self__, self.api._legacy_plc_activation)
        other = build()
        self.assertIsNot(other._legacy_plc_activation, self.api._legacy_plc_activation)
        tree = ast.parse(read_checked_application_source(ROOT / 'local_inspection_service/server.py'))
        startup = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "start_plc_runtime_workers")
        self.assertEqual(len(startup.body), 1)
        self.assertIsInstance(startup.body[0], ast.Return)
        self.assertIsNone(startup.body[0].value.value)


if __name__ == "__main__":
    unittest.main()
