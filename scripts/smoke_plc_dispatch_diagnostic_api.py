"""Accepted-main/candidate contract for five PLC dispatch and diagnostic HTTP flows."""
import ast
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
NAMES = (
    "declare_plc_web_serial_attempt", "create_plc_web_serial_diagnostic_plan",
    "finish_plc_web_serial_diagnostic", "confirm_plc_web_serial_diagnostic",
    "record_plc_web_serial_receipt_endpoint",
)
CALLEES = (
    "plc_web_serial_declare_attempt", "plc_web_serial_diagnostic_plan",
    "plc_web_serial_finish_diagnostic", "plc_web_serial_confirm_diagnostic",
    "plc_web_serial_record_receipt",
)
DISPATCH = (True, False, False, False, True)
ADMIN = (False, True, True, True, False)


class ConfigError(Exception):
    pass


class HttpError(Exception):
    def __init__(self, status_code, detail):
        self.status_code, self.detail = status_code, detail


class DispatchApiContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lifetime = ExitStack()
        cls.lifetime.enter_context(patch.dict(os.environ))
        root = Path(cls.lifetime.enter_context(tempfile.TemporaryDirectory(prefix="plc-dispatch-api-")))
        (root / "local_inspection_service/static").mkdir(parents=True)
        for key in ("DATABASE_URL", "VANTALINE_POSTGRES_DSN", "PGDSN"):
            os.environ.pop(key, None)
        os.environ.update(LOCAL_INSPECTION_ROOT=str(root), VANTALINE_DATA_STORE="json",
                          LOCAL_INSPECTION_AUTO_RESUME_WORKER="0", VANTALINE_LABEL_INSPECTION_ENABLED="false",
                          YOLO_AUTOINSTALL="false")
        for name in ("requests.sessions.Session.request", "urllib.request.urlopen", "subprocess.Popen", "os.kill"):
            cls.lifetime.enter_context(patch(name, side_effect=AssertionError("external operation forbidden")))
        baseline = os.environ.get("VANTALINE_PLC_DISPATCH_API_BASELINE_SOURCE")
        if baseline:
            tree = ast.parse(Path(baseline).read_text(encoding="utf-8-sig"))
            functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in NAMES]
            assert [node.name for node in functions] == list(NAMES)
            for node in functions:
                node.decorator_list = []
            cls.api = types.ModuleType("accepted_main_plc_dispatch_api")
            cls.api.__dict__.update(Any=Any, Request=object, PlcWebSerialAttemptRequest=object,
                                    PlcWebSerialDiagnosticReceiptRequest=object,
                                    PlcWebSerialDiagnosticConfirmRequest=object,
                                    PlcWebSerialReceiptRequest=object)
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
        self.request = object()
        self.payload = object()
        self.station = {"id": "station-1"}
        self.dispatch_id = "dispatch-1"
        self.results = {callee: {"operation": callee} for callee in CALLEES}
        self.replace("PlcConfigError", ConfigError)
        self.replace("HTTPException", HttpError)
        self.replace("require_permission", lambda role: self.events.append(("permission", role)))
        self.replace("require_plc_web_serial_station",
                     lambda request: self.events.append(("station", request)) or self.station)
        for callee in CALLEES:
            def make(name):
                def call(*args):
                    self.events.append((name, args))
                    return self.results[name]
                return call
            self.replace(callee, make(callee))

    def replace(self, name, value):
        self.stack.enter_context(patch.object(self.api, name, value, create=True))

    def call(self, name, dispatch):
        if dispatch:
            return getattr(self.api, name)(self.dispatch_id, self.request, self.payload)
        return getattr(self.api, name)(self.request, self.payload)

    def test_success_order_arguments_and_identity(self):
        for name, callee, dispatch, admin in zip(NAMES, CALLEES, DISPATCH, ADMIN):
            self.events.clear()
            self.assertIs(self.call(name, dispatch), self.results[callee])
            expected = [("permission", "system_settings")] if admin else []
            expected.append(("station", self.request))
            args = ("station-1", self.dispatch_id, self.payload) if dispatch else ("station-1", self.payload)
            expected.append((callee, args))
            self.assertEqual(self.events, expected)
            self.assertIs(self.events[-1][-1][-1], self.payload)

    def test_permissions_before_station_and_business(self):
        denied = ConfigError("denied")
        self.replace("require_permission", lambda role: (_ for _ in ()).throw(denied))
        for name, dispatch, admin in zip(NAMES, DISPATCH, ADMIN):
            self.events.clear()
            if admin:
                with self.assertRaises(ConfigError) as caught:
                    self.call(name, dispatch)
                self.assertIs(caught.exception, denied)
                self.assertEqual(self.events, [])
        self.replace("require_permission", lambda role: self.events.append(("permission", role)))
        self.replace("require_plc_web_serial_station",
                     lambda request: (_ for _ in ()).throw(denied))
        for name, dispatch, admin in zip(NAMES, DISPATCH, ADMIN):
            self.events.clear()
            with self.assertRaises(ConfigError) as caught:
                self.call(name, dispatch)
            self.assertIs(caught.exception, denied)
            self.assertEqual(self.events, [("permission", "system_settings")] if admin else [])

    def test_config_error_cause_and_single_partial_effect(self):
        for name, callee, dispatch in zip(NAMES, CALLEES, DISPATCH):
            effects = []
            error = ConfigError(callee)
            def mutation(*_args):
                effects.append("persisted")
                raise error
            self.replace(callee, mutation)
            with self.assertRaises(HttpError) as caught:
                self.call(name, dispatch)
            self.assertEqual((caught.exception.status_code, caught.exception.detail), (409, callee))
            self.assertIs(caught.exception.__cause__, error)
            self.assertEqual(effects, ["persisted"])

    def test_callee_binding_after_guard_before_station_string(self):
        for name, callee, dispatch in zip(NAMES, CALLEES, DISPATCH):
            self.replace(callee, lambda *_: {"selected": "early"})
            def station(request):
                setattr(self.api, callee, lambda *_: {"selected": "after-guard"})
                return self.station
            self.replace("require_plc_web_serial_station", station)
            self.assertEqual(self.call(name, dispatch), {"selected": "after-guard"})
            class StationId:
                def __str__(inner):
                    setattr(self.api, callee, lambda *_: {"selected": "too-late"})
                    return "station"
            self.station = {"id": StationId()}
            self.assertEqual(self.call(name, dispatch), {"selected": "after-guard"})

    def test_permission_selects_station_after_guard(self):
        for name, dispatch, admin in zip(NAMES, DISPATCH, ADMIN):
            if not admin:
                continue
            chosen = {"id": "from-permission"}
            self.replace("require_plc_web_serial_station", lambda request: self.station)
            self.replace("require_permission",
                         lambda role: setattr(self.api, "require_plc_web_serial_station",
                                              lambda request: chosen))
            self.assertEqual(self.call(name, dispatch)["operation"], CALLEES[NAMES.index(name)])
            self.assertEqual(self.events[-1][1][0], "from-permission")

    def test_other_business_exception_escapes_unchanged(self):
        for name, callee, dispatch in zip(NAMES, CALLEES, DISPATCH):
            error = ValueError(callee)
            self.replace(callee, lambda *_args, error=error: (_ for _ in ()).throw(error))
            with self.assertRaises(ValueError) as caught:
                self.call(name, dispatch)
            self.assertIs(caught.exception, error)

    def test_dispatch_id_passed_even_when_none(self):
        self.dispatch_id = None
        for name, callee, dispatch in zip(NAMES, CALLEES, DISPATCH):
            if not dispatch:
                continue
            self.events.clear()
            self.call(name, dispatch)
            self.assertIsNone(self.events[-1][1][1])
            self.assertIs(self.events[-1][1][2], self.payload)

    def test_dispatch_id_object_is_never_coerced_or_copied(self):
        class DispatchId:
            def __str__(inner):
                raise AssertionError("dispatch id converted")
            def __bool__(inner):
                raise AssertionError("dispatch id tested for truth")
        value = DispatchId()
        self.dispatch_id = value
        for name, dispatch in zip(NAMES, DISPATCH):
            if not dispatch:
                continue
            self.events.clear()
            self.call(name, dispatch)
            self.assertEqual(len(self.events[-1][1]), 3)
            self.assertIs(self.events[-1][1][1], value)
            self.assertIs(self.events[-1][1][2], self.payload)

    def test_station_id_config_error_is_translated(self):
        for name, callee, dispatch in zip(NAMES, CALLEES, DISPATCH):
            error = ConfigError("station id")
            called = []
            self.replace(callee, lambda *_args: called.append("business"))
            class StationId:
                def __str__(inner):
                    raise error
            self.station = {"id": StationId()}
            with self.assertRaises(HttpError) as caught:
                self.call(name, dispatch)
            self.assertEqual((caught.exception.status_code, caught.exception.detail), (409, "station id"))
            self.assertIs(caught.exception.__cause__, error)
            self.assertEqual(called, [])

    def test_station_id_value_error_escapes_without_business(self):
        for name, callee, dispatch in zip(NAMES, CALLEES, DISPATCH):
            error = ValueError("station id")
            called = []
            self.replace(callee, lambda *_args: called.append("business"))
            class StationId:
                def __str__(inner):
                    raise error
            self.station = {"id": StationId()}
            with self.assertRaises(ValueError) as caught:
                self.call(name, dispatch)
            self.assertIs(caught.exception, error)
            self.assertEqual(called, [])

    def test_error_class_and_factory_late_binding(self):
        class NewConfigError(Exception):
            def __str__(inner):
                setattr(self.api, "HTTPException", LateHttpError)
                return "late detail"
        class EarlyHttpError(HttpError):
            pass
        class LateHttpError(HttpError):
            pass
        for name, callee, dispatch in zip(NAMES, CALLEES, DISPATCH):
            error = NewConfigError()
            def mutation(*_args):
                setattr(self.api, "PlcConfigError", NewConfigError)
                raise error
            self.replace("PlcConfigError", ConfigError)
            self.replace("HTTPException", EarlyHttpError)
            self.replace(callee, mutation)
            with self.assertRaises(EarlyHttpError) as caught:
                self.call(name, dispatch)
            self.assertEqual((caught.exception.status_code, caught.exception.detail), (409, "late detail"))
            self.assertIs(caught.exception.__cause__, error)


    def test_candidate_instances_isolate_all_ports(self):
        if os.environ.get("VANTALINE_PLC_DISPATCH_API_BASELINE_SOURCE"):
            self.skipTest("candidate composition only")
        from local_inspection_service.plc.dispatch_diagnostic import DispatchDiagnostic
        from local_inspection_service.plc.dispatch_diagnostic_ports import (
            DispatchAccess, DispatchErrors, DispatchMutation)
        reads = []
        failures = {"a": False, "b": False}
        def getter(label, port, callback):
            return lambda: reads.append((label, port)) or callback
        def build(label):
            def mutation(port):
                def call(*args):
                    if failures[label]:
                        raise ConfigError(label)
                    return {"id": label, "operation": port, "args": args}
                return call
            access = DispatchAccess(
                getter(label, "permission", lambda *_: None),
                getter(label, "station", lambda *_: {"id": label}))
            mutation_ports = ("attempt", "plan", "diagnostic-receipt", "confirm", "receipt")
            mutation_set = DispatchMutation(
                *(getter(label, port, mutation(port)) for port in mutation_ports))
            errors = DispatchErrors(
                getter(label, "config-error", ConfigError),
                getter(label, "http-error", HttpError))
            return DispatchDiagnostic(access, mutation_set, errors)
        a, b = build("a"), build("b")
        self.assertEqual(reads, [])
        def forbidden(*_args, **_kwargs):
            raise AssertionError("service reached root collaborator")
        for name in ("require_permission", "require_plc_web_serial_station",
                     *CALLEES, "PlcConfigError", "HTTPException"):
            self.replace(name, forbidden)
        methods = ("declare_attempt", "diagnostic_plan", "diagnostic_receipt",
                   "diagnostic_confirm", "record_receipt")
        ports = ("attempt", "plan", "diagnostic-receipt", "confirm", "receipt")
        for service, label in ((a, "a"), (b, "b"), (a, "a")):
            for method, port, dispatch, admin in zip(methods, ports, DISPATCH, ADMIN):
                before = len(reads)
                args = (self.dispatch_id, self.request, self.payload) if dispatch else (self.request, self.payload)
                value = getattr(service, method)(*args)
                self.assertEqual(value["id"], label)
                self.assertEqual(value["operation"], port)
                self.assertIs(value["args"][-1], self.payload)
                expected = (["permission"] if admin else []) + ["station", port]
                self.assertEqual(reads[before:], [(label, item) for item in expected])
            failures[label] = True
            for method, port, dispatch, admin in zip(methods, ports, DISPATCH, ADMIN):
                before = len(reads)
                args = (self.dispatch_id, self.request, self.payload) if dispatch else (self.request, self.payload)
                with self.assertRaises(HttpError) as caught:
                    getattr(service, method)(*args)
                self.assertEqual((caught.exception.status_code, caught.exception.detail), (409, label))
                expected = (["permission"] if admin else []) + ["station", port, "config-error", "http-error"]
                self.assertEqual(reads[before:], [(label, item) for item in expected])
            failures[label] = False


if __name__ == "__main__":
    unittest.main()
