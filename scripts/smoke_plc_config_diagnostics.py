"""Accepted-main/candidate contract for legacy PLC config diagnostics."""
import ast
from collections.abc import Mapping
from contextlib import ExitStack
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from typing import Any
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
NAMES = ("plc_config_response", "get_plc_config", "update_plc_config")


class ConfigError(Exception):
    pass


class HttpError(Exception):
    def __init__(self, status_code, detail):
        self.status_code, self.detail = status_code, detail


class ConfigDiagnosticsContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lifetime = ExitStack()
        cls.lifetime.enter_context(patch.dict(os.environ))
        root = Path(cls.lifetime.enter_context(tempfile.TemporaryDirectory(prefix="plc-config-diag-")))
        (root / "local_inspection_service/static").mkdir(parents=True)
        for key in ("DATABASE_URL", "VANTALINE_POSTGRES_DSN", "PGDSN"):
            os.environ.pop(key, None)
        os.environ.update(LOCAL_INSPECTION_ROOT=str(root), VANTALINE_DATA_STORE="json",
                          LOCAL_INSPECTION_AUTO_RESUME_WORKER="0", VANTALINE_LABEL_INSPECTION_ENABLED="false",
                          YOLO_AUTOINSTALL="false")
        for name in ("requests.sessions.Session.request", "urllib.request.urlopen", "subprocess.Popen", "os.kill"):
            cls.lifetime.enter_context(patch(name, side_effect=AssertionError("external operation forbidden")))
        baseline = os.environ.get("VANTALINE_PLC_CONFIG_DIAG_BASELINE_SOURCE")
        if baseline:
            tree = ast.parse(Path(baseline).read_text(encoding="utf-8-sig"))
            functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in NAMES]
            assert {node.name for node in functions} == set(NAMES)
            for node in functions:
                node.decorator_list = []
            cls.api = types.ModuleType("accepted_main_plc_config_diags")
            cls.api.__dict__.update(Any=Any, PlcConfigRequest=object)
            exec(compile(ast.Module(body=functions, type_ignores=[]), baseline, "exec"), cls.api.__dict__)
        else:
            from local_inspection_service import server
            cls.api = server

    @classmethod
    def tearDownClass(cls):
        cls.lifetime.close()

    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.events = []
        self.config = {"plc": {"enabled": True}, "generation": 7}
        self.settings = {
            "enabled": True, "result_register": "D206", "output_control_point": "Y04",
            "capture_input_register": "D100",
        }
        self.defaults = {**self.settings, "enabled": False}
        self.audits = [{"id": "old"}, {"id": "middle"}, {"id": "new"}]
        self.attempt = {"id": "attempt", "nested": {"state": "live"}}
        self.active = {"key": self.attempt}
        self.invalid = False
        self.capability = []
        self.replace("PlcConfigError", ConfigError)
        self.replace("HTTPException", HttpError)
        self.replace("require_permission", lambda role: self.events.append(("permission", role)))
        self.replace("load_config", lambda: self.events.append("load") or self.config)
        self.replace("raw_plc_namespace", lambda current: self.events.append(("raw", current)) or current.get("plc"))
        def normalize(raw):
            self.events.append(("normalize", raw))
            if self.invalid:
                raise ConfigError("bad configuration")
            return self.settings
        self.replace("normalize_plc_config", normalize)
        self.replace("DEFAULT_PLC_CONFIG", self.defaults)
        self.replace("plc_activation_errors", lambda settings: self.events.append(("capability", settings)) or self.capability)
        self.replace("plc_dispatch_audit_records", lambda current: self.events.append(("audit", current)) or self.audits)
        self.replace("PLC_DISPATCH_AUDIT_LIMIT", 2)
        events = self.events
        class Lock:
            def __enter__(inner):
                events.append("lock-enter")
            def __exit__(inner, *_):
                events.append("lock-exit")
        self.replace("_config_io_lock", Lock())
        self.replace("_plc_active_attempts", self.active)
        self.replace("logical_device_address", lambda value: self.events.append(("address", value)) or "logical:" + value)
        self.replace("plc_device_profile_verified", lambda settings: self.events.append("device-verify") or True)
        self.replace("plc_read_profile_verified", lambda settings: self.events.append("read-verify") or False)
        self.replace("PLC_PROTOCOL_ID", "protocol-v4")
        self.replace("PLC_CONTROL_GENERATION_KEY", "generation")
        self.replace("PLC_QUEUE_WAIT_SECONDS", 2.25)
        self.replace("PLC_WORKER_TOTAL_TIMEOUT_SECONDS", 422.5)

    def replace(self, name, value):
        self.stack.enter_context(patch.object(self.api, name, value, create=True))

    def test_get_and_supplied_config_preserve_projection(self):
        result = self.api.get_plc_config()
        self.assertIs(result["config"], self.settings)
        self.assertEqual(result["recent_dispatches"], [{"id": "new"}, {"id": "middle"}])
        self.assertEqual(result["resolved_addresses"], {
            "result_register": "logical:D206", "output_control_point": "logical:Y04",
            "capture_input_register": "logical:D100"})
        self.assertEqual((result["device_profile_verified"], result["read_profile_verified"]), (True, False))
        self.assertEqual((result["validation_error"], result["validation_errors"]), ("", []))
        self.assertEqual((result["effective_enabled"], result["control_generation"]), (True, 7))
        self.assertEqual((result["protocol_options"], result["queue_wait_seconds"],
                          result["worker_total_timeout_seconds"]),
                         ([{"id": "protocol-v4", "label": "三菱 FX 编程口（ASCII）"}], 2.25, 422.5))
        self.assertEqual(result["in_flight_attempts"], [self.attempt])
        self.assertIsNot(result["in_flight_attempts"][0], self.attempt)
        self.assertIs(result["in_flight_attempts"][0]["nested"], self.attempt["nested"])
        self.assertLess(self.events.index("lock-enter"), self.events.index("lock-exit"))
        self.events.clear()
        direct = self.api.plc_config_response({})
        self.assertNotIn("load", self.events)
        self.assertEqual(direct["control_generation"], 0)

    def test_get_late_resolves_root_response(self):
        marker = object()
        self.replace("plc_config_response", lambda: marker)
        self.assertIs(self.api.get_plc_config(), marker)

    def test_nondict_config_loads_and_invalid_skips_capability(self):
        self.invalid = True
        for value in (None, [], 0, ""):
            self.events.clear()
            result = self.api.plc_config_response(value)
            self.assertEqual(self.events[0], "load")
            self.assertEqual(result["config"], self.defaults)
            self.assertEqual(result["validation_error"], "bad configuration")
            self.assertEqual(result["validation_errors"],
                             [{"code": "invalid_plc_config", "message": "bad configuration"}])
            self.assertFalse(result["effective_enabled"])
            self.assertFalse(any(isinstance(event, tuple) and event[0] == "capability"
                                 for event in self.events))

    def test_capability_first_error_and_empty_addresses(self):
        self.settings["output_control_point"] = ""
        self.settings["capture_input_register"] = ""
        self.capability = [{"code": "first"}, {"code": "second"}]
        result = self.api.plc_config_response(self.config)
        self.assertEqual(result["validation_error"], "first")
        self.assertIs(result["validation_errors"], self.capability)
        self.assertFalse(result["effective_enabled"])
        self.assertEqual(result["resolved_addresses"],
                         {"result_register": "logical:D206", "output_control_point": "",
                          "capture_input_register": ""})
        self.assertEqual([e for e in self.events if isinstance(e, tuple) and e[0] == "address"],
                         [("address", "D206")])

    def test_active_snapshot_is_shallow_and_only_copy_is_locked(self):
        state = {"locked": False}
        class Lock:
            def __enter__(inner):
                self.assertFalse(state["locked"])
                state["locked"] = True
            def __exit__(inner, *_):
                state["locked"] = False
        class Item(Mapping):
            def __iter__(inner):
                self.assertTrue(state["locked"])
                return iter(("id", "nested"))
            def __len__(inner):
                return 2
            def __getitem__(inner, key):
                self.assertTrue(state["locked"])
                return {"id": "item", "nested": self.attempt["nested"]}[key]
        class Attempts:
            def values(inner):
                self.assertTrue(state["locked"])
                return [Item()]
        self.replace("_config_io_lock", Lock())
        self.replace("_plc_active_attempts", Attempts())
        self.replace("logical_device_address",
                     lambda value: self.assertFalse(state["locked"]) or value)
        result = self.api.plc_config_response(self.config)
        self.assertFalse(state["locked"])
        self.assertEqual(result["in_flight_attempts"][0]["id"], "item")
        self.assertIs(result["in_flight_attempts"][0]["nested"], self.attempt["nested"])

    def test_snapshot_copy_exception_releases_lock(self):
        state = {"locked": False}
        error = ValueError("copy failed")
        class Lock:
            def __enter__(inner):
                state["locked"] = True
            def __exit__(inner, *_):
                state["locked"] = False
        class Item(Mapping):
            def __iter__(inner):
                self.assertTrue(state["locked"])
                raise error
            def __len__(inner):
                return 1
            def __getitem__(inner, key):
                raise AssertionError("unexpected item access")
        class Attempts:
            def values(inner):
                self.assertTrue(state["locked"])
                return [Item()]
        self.replace("_config_io_lock", Lock())
        self.replace("_plc_active_attempts", Attempts())
        with self.assertRaises(ValueError) as caught:
            self.api.plc_config_response(self.config)
        self.assertIs(caught.exception, error)
        self.assertFalse(state["locked"])

    def test_dynamic_normalizer_error_defaults_and_http_binding(self):
        early = lambda raw: self.settings
        late = lambda raw: {"wrong": True}
        self.replace("normalize_plc_config", early)
        self.replace("raw_plc_namespace",
                     lambda current: setattr(self.api, "normalize_plc_config", late) or current["plc"])
        self.assertIs(self.api.plc_config_response(self.config)["config"], self.settings)
        class NewConfigError(Exception):
            def __str__(inner):
                setattr(self.api, "DEFAULT_PLC_CONFIG", {"wrong": True})
                return "new error"
        fresh_defaults = {**self.settings, "enabled": False}
        error = NewConfigError()
        def raw(current):
            setattr(self.api, "PlcConfigError", NewConfigError)
            setattr(self.api, "DEFAULT_PLC_CONFIG", fresh_defaults)
            raise error
        self.replace("raw_plc_namespace", raw)
        self.replace("PlcConfigError", ConfigError)
        result = self.api.plc_config_response(self.config)
        self.assertEqual(result["config"], fresh_defaults)
        self.assertIsNot(result["config"], fresh_defaults)
        self.assertEqual(result["validation_error"], "new error")
        class LateHttpError(HttpError):
            pass
        self.replace("HTTPException", HttpError)
        self.replace("require_permission",
                     lambda role: setattr(self.api, "HTTPException", LateHttpError))
        with self.assertRaises(LateHttpError) as caught:
            self.api.update_plc_config(object())
        self.assertEqual(caught.exception.status_code, 410)

    def test_post_permission_then_fixed_410_without_mutation(self):
        denied = HttpError(403, "denied")
        self.replace("require_permission", lambda role: (_ for _ in ()).throw(denied))
        with self.assertRaises(HttpError) as caught:
            self.api.update_plc_config(object())
        self.assertIs(caught.exception, denied)
        self.replace("require_permission", lambda role: self.events.append(("permission", role)))
        for name in ("plc_config_request_payload", "mutate_app_config_atomically", "plc_config_response"):
            self.replace(name, lambda *_args: (_ for _ in ()).throw(AssertionError("obsolete mutation reached")))
        with self.assertRaises(HttpError) as caught:
            self.api.update_plc_config(object())
        self.assertEqual((caught.exception.status_code, caught.exception.detail),
                         (410, "legacy_server_serial_config_is_read_only_use_workstation_config"))
        self.assertEqual(self.events, [("permission", "system_settings")])


    def test_candidate_instances_isolate_all_capabilities(self):
        if os.environ.get("VANTALINE_PLC_CONFIG_DIAG_BASELINE_SOURCE"):
            self.skipTest("candidate composition only")
        from local_inspection_service.plc.config_diagnostics import ConfigDiagnostics
        from local_inspection_service.plc.config_diagnostics_ports import (
            ConfigAccess, ConfigDisplay, ConfigErrors, ConfigRuntime, ConfigSources)
        reads = []
        invalid = {"a": False, "b": False}
        def getter(label, name, callback):
            return lambda: reads.append((label, name)) or callback
        def constant(label, name, value):
            return lambda: reads.append((label, name)) or value
        def build(label):
            settings = {"enabled": True, "result_register": "D206",
                        "output_control_point": "", "capture_input_register": ""}
            config = {"plc": {"label": label}, "generation": 3}
            def normalize(raw):
                if invalid[label]:
                    raise ConfigError(label)
                return settings
            sources = ConfigSources(
                getter(label, "load", lambda: config),
                getter(label, "raw", lambda current: current.get("plc")),
                getter(label, "normalize", normalize),
                constant(label, "defaults", settings),
                getter(label, "activation", lambda settings: []),
                getter(label, "audit", lambda current: []))
            display = ConfigDisplay(
                getter(label, "address", lambda value: value),
                getter(label, "device", lambda settings: True),
                getter(label, "read", lambda settings: False))
            runtime = ConfigRuntime(
                getter(label, "attempts", lambda: [{"id": label}]),
                constant(label, "limit", 20),
                constant(label, "protocol", label),
                constant(label, "generation", "generation"),
                constant(label, "queue", 2.25),
                constant(label, "timeout", 422.5))
            access = ConfigAccess(getter(label, "permission", lambda role: None))
            errors = ConfigErrors(constant(label, "config-error", ConfigError),
                                  constant(label, "http-error", HttpError))
            return ConfigDiagnostics(sources, display, runtime, access, errors)
        a, b = build("a"), build("b")
        self.assertEqual(reads, [])
        def forbidden(*_args, **_kwargs):
            raise AssertionError("config service reached root collaborator")
        for name in ("load_config", "raw_plc_namespace", "normalize_plc_config",
                     "plc_activation_errors", "plc_dispatch_audit_records",
                     "logical_device_address", "plc_device_profile_verified",
                     "plc_read_profile_verified", "_plc_active_attempts_snapshot",
                     "require_permission", "PlcConfigError", "HTTPException"):
            self.replace(name, forbidden)
        for service, label in ((a, "a"), (b, "b"), (a, "a")):
            before = len(reads)
            result = service.response()
            self.assertEqual(result["protocol_options"][0]["id"], label)
            self.assertEqual(result["in_flight_attempts"], [{"id": label}])
            expected = ("load", "normalize", "raw", "activation", "audit", "limit",
                        "attempts", "address", "device", "read", "protocol",
                        "generation", "queue", "timeout")
            self.assertEqual(reads[before:], [(label, port) for port in expected])
            before = len(reads)
            with self.assertRaises(HttpError) as caught:
                service.update(object())
            self.assertEqual(caught.exception.status_code, 410)
            self.assertEqual(reads[before:], [(label, "permission"), (label, "http-error")])
            invalid[label] = True
            before = len(reads)
            result = service.response({})
            self.assertEqual(result["validation_error"], label)
            expected = ("normalize", "raw", "config-error", "defaults", "audit",
                        "limit", "attempts", "address", "device", "read", "protocol",
                        "generation", "queue", "timeout")
            self.assertEqual(reads[before:], [(label, port) for port in expected])
            invalid[label] = False


if __name__ == "__main__":
    unittest.main()
