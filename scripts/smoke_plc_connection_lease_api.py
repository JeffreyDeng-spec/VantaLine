"""Accepted-main/candidate contract for the five PLC lease HTTP entry points."""
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
    "claim_plc_web_serial_connection", "activate_plc_web_serial_connection",
    "heartbeat_plc_web_serial_connection", "rebind_plc_web_serial_connection_model",
    "disconnect_plc_web_serial_connection",
)
CALLEES = (
    "plc_web_serial_claim_connecting_lease", "plc_web_serial_activate_lease",
    "plc_web_serial_heartbeat", "plc_web_serial_rebind_model",
    "plc_web_serial_release_lease",
)


class ConfigError(Exception):
    pass


class HttpError(Exception):
    def __init__(self, status_code, detail):
        self.status_code, self.detail = status_code, detail


class LeaseApiContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lifetime = ExitStack()
        cls.lifetime.enter_context(patch.dict(os.environ))
        root = Path(cls.lifetime.enter_context(tempfile.TemporaryDirectory(prefix="plc-lease-api-")))
        (root / "local_inspection_service/static").mkdir(parents=True)
        for key in ("DATABASE_URL", "VANTALINE_POSTGRES_DSN", "PGDSN"):
            os.environ.pop(key, None)
        os.environ.update(LOCAL_INSPECTION_ROOT=str(root), VANTALINE_DATA_STORE="json",
                          LOCAL_INSPECTION_AUTO_RESUME_WORKER="0", VANTALINE_LABEL_INSPECTION_ENABLED="false",
                          YOLO_AUTOINSTALL="false")
        for name in ("requests.sessions.Session.request", "urllib.request.urlopen", "subprocess.Popen", "os.kill"):
            cls.lifetime.enter_context(patch(name, side_effect=AssertionError("external operation forbidden")))
        baseline = os.environ.get("VANTALINE_PLC_LEASE_API_BASELINE_SOURCE")
        if baseline:
            tree = ast.parse(Path(baseline).read_text(encoding="utf-8-sig"))
            functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in NAMES]
            assert {node.name for node in functions} == set(NAMES)
            for node in functions:
                node.decorator_list = []
            cls.api = types.ModuleType("accepted_main_plc_lease_api")
            cls.api.__dict__.update(Any=Any, Request=object, PlcWorkstationLeaseRequest=object,
                                    PlcWorkstationLeaseActivateRequest=object,
                                    PlcWorkstationLeaseHeartbeatRequest=object,
                                    PlcWorkstationLeaseRebindRequest=object)
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
        self.payload = types.SimpleNamespace(model_id="model-1")
        self.station = {"id": "station-1"}
        self.replace("PlcConfigError", ConfigError)
        self.replace("HTTPException", HttpError)
        self.replace("require_plc_web_serial_station", lambda request: self.events.append(("station", request)) or self.station)
        self.replace("require_analyze_model_permission", lambda model: self.events.append(("model", model)))
        for callee in CALLEES:
            self.replace(callee, lambda station_id, payload, callee=callee:
                         self.events.append((callee, station_id, payload)) or {"operation": callee})

    def replace(self, name, value):
        self.stack.enter_context(patch.object(self.api, name, value, create=True))

    def test_success_order_payload_identity_and_rebind_permission(self):
        for name, callee in zip(NAMES, CALLEES):
            self.events.clear()
            self.assertEqual(getattr(self.api, name)(self.request, self.payload), {"operation": callee})
            expected = [("station", self.request)]
            if name == NAMES[3]:
                expected.append(("model", "model-1"))
            expected.append((callee, "station-1", self.payload))
            self.assertEqual(self.events, expected)
            self.assertIs(self.events[-1][2], self.payload)

    def test_station_and_model_denial_escape_unchanged(self):
        denial = HttpError(403, "denied")
        self.replace("require_plc_web_serial_station", lambda request: (_ for _ in ()).throw(denial))
        for name in NAMES:
            with self.assertRaises(HttpError) as caught:
                getattr(self.api, name)(self.request, self.payload)
            self.assertIs(caught.exception, denial)
        self.replace("require_plc_web_serial_station", lambda request: self.station)
        self.replace("require_analyze_model_permission", lambda model: (_ for _ in ()).throw(denial))
        with self.assertRaises(HttpError) as caught:
            self.api.rebind_plc_web_serial_connection_model(self.request, self.payload)
        self.assertIs(caught.exception, denial)

    def test_config_error_in_authorization_escapes_before_business(self):
        guard_error = ConfigError("guard")
        calls = []
        for callee in CALLEES:
            self.replace(callee, lambda *_args, callee=callee: calls.append(callee))
        self.replace("require_plc_web_serial_station",
                     lambda request: (_ for _ in ()).throw(guard_error))
        for name in NAMES:
            with self.assertRaises(ConfigError) as caught:
                getattr(self.api, name)(self.request, self.payload)
            self.assertIs(caught.exception, guard_error)
        self.assertEqual(calls, [])
        self.replace("require_plc_web_serial_station", lambda request: self.station)
        self.replace("require_analyze_model_permission",
                     lambda model: (_ for _ in ()).throw(guard_error))
        with self.assertRaises(ConfigError) as caught:
            self.api.rebind_plc_web_serial_connection_model(self.request, self.payload)
        self.assertIs(caught.exception, guard_error)
        self.assertEqual(calls, [])

    def test_permission_evaluation_and_business_late_binding(self):
        for name, callee in zip(NAMES, CALLEES):
            self.replace(callee, lambda *_: {"selected": "early"})
            self.replace("require_plc_web_serial_station",
                         lambda request, callee=callee: setattr(
                             self.api, callee, lambda *_: {"selected": "after-station"}) or self.station)
            self.assertEqual(getattr(self.api, name)(self.request, self.payload),
                             {"selected": "after-station"})
        self.replace("require_plc_web_serial_station", lambda request: self.station)
        self.replace("plc_web_serial_rebind_model", lambda *_: {"selected": "early"})
        self.replace("require_analyze_model_permission",
                     lambda model: setattr(self.api, "plc_web_serial_rebind_model",
                                           lambda *_: {"selected": "after-model"}) or None)
        self.assertEqual(self.api.rebind_plc_web_serial_connection_model(self.request, self.payload),
                         {"selected": "after-model"})
        self.replace("require_analyze_model_permission",
                     lambda model: self.events.append(("early-model", model)))
        class Payload:
            @property
            def model_id(inner):
                setattr(self.api, "require_analyze_model_permission",
                        lambda model: self.events.append(("late-model", model)))
                return "model-2"
        self.events.clear()
        self.api.rebind_plc_web_serial_connection_model(self.request, Payload())
        self.assertIn(("early-model", "model-2"), self.events)
        self.assertNotIn(("late-model", "model-2"), self.events)

    def test_partial_business_effect_not_retried(self):
        for name, callee in zip(NAMES, CALLEES):
            evidence = []
            error = ConfigError("after write")
            def mutate(*_args):
                evidence.append("persisted")
                raise error
            self.replace(callee, mutate)
            with self.assertRaises(HttpError) as caught:
                getattr(self.api, name)(self.request, self.payload)
            self.assertEqual(evidence, ["persisted"])
            self.assertIs(caught.exception.__cause__, error)

    def test_config_error_converts_once_with_cause(self):
        for name, callee in zip(NAMES, CALLEES):
            error = ConfigError(callee)
            self.replace(callee, lambda *_args, error=error: (_ for _ in ()).throw(error))
            with self.assertRaises(HttpError) as caught:
                getattr(self.api, name)(self.request, self.payload)
            self.assertEqual((caught.exception.status_code, caught.exception.detail), (409, callee))
            self.assertIs(caught.exception.__cause__, error)

    def test_callee_selected_before_station_string(self):
        for name, callee in zip(NAMES, CALLEES):
            early = lambda *_: {"selected": "early"}
            late = lambda *_: {"selected": "late"}
            self.replace(callee, early)
            class StationId:
                def __str__(inner):
                    setattr(self.api, callee, late)
                    return "station"
            self.station = {"id": StationId()}
            self.assertEqual(getattr(self.api, name)(self.request, self.payload), {"selected": "early"})

    def test_late_config_error_and_http_factory_binding(self):
        class NewConfigError(Exception):
            def __str__(inner):
                setattr(self.api, "HTTPException", LateHttpError)
                return "late detail"
        class EarlyHttpError(HttpError):
            pass
        class LateHttpError(HttpError):
            pass
        for name, callee in zip(NAMES, CALLEES):
            error = NewConfigError()
            def call(*_args):
                setattr(self.api, "PlcConfigError", NewConfigError)
                raise error
            self.replace("PlcConfigError", ConfigError)
            self.replace("HTTPException", EarlyHttpError)
            self.replace(callee, call)
            with self.assertRaises(EarlyHttpError) as caught:
                getattr(self.api, name)(self.request, self.payload)
            self.assertEqual((caught.exception.status_code, caught.exception.detail), (409, "late detail"))
            self.assertIs(caught.exception.__cause__, error)


    def test_constructor_two_instance_isolation(self):
        if os.environ.get("VANTALINE_PLC_LEASE_API_BASELINE_SOURCE"):
            self.skipTest("candidate composition only")
        from local_inspection_service.plc.connection_lease import ConnectionLease
        from local_inspection_service.plc.connection_lease_ports import LeaseAccess, LeaseErrors, LeaseMutation
        reads = []
        def getter(label, name, callback):
            return lambda: reads.append((label, name)) or callback
        def build(label):
            access = LeaseAccess(getter(label, "station", lambda *_: {"id": label}),
                                 getter(label, "model", lambda *_: None))
            mutation = LeaseMutation(*(getter(label, name, lambda sid, payload, name=name: {"id": sid, "op": name})
                                       for name in ("claim", "activate", "heartbeat", "rebind", "disconnect")))
            errors = LeaseErrors(getter(label, "config", ConfigError), getter(label, "http", HttpError))
            return ConnectionLease(access, mutation, errors)
        a, b = build("a"), build("b")
        self.assertEqual(reads, [])
        def forbidden(*_args, **_kwargs):
            raise AssertionError("business service reached root collaborator")
        for name in ("require_plc_web_serial_station", "require_analyze_model_permission",
                     *CALLEES, "PlcConfigError", "HTTPException"):
            self.replace(name, forbidden)
        for service, label in ((a, "a"), (b, "b"), (a, "a")):
            before = len(reads)
            for method in ("claim", "activate", "heartbeat", "rebind_model", "disconnect"):
                result = getattr(service, method)(self.request, self.payload)
                self.assertEqual(result["id"], label)
            self.assertEqual(reads[before:], [(label, "station"), (label, "claim"),
                                              (label, "station"), (label, "activate"),
                                              (label, "station"), (label, "heartbeat"),
                                              (label, "station"), (label, "model"), (label, "rebind"),
                                              (label, "station"), (label, "disconnect")])


    def test_two_instance_error_ports_are_isolated(self):
        if os.environ.get("VANTALINE_PLC_LEASE_API_BASELINE_SOURCE"):
            self.skipTest("candidate composition only")
        from local_inspection_service.plc.connection_lease import ConnectionLease
        from local_inspection_service.plc.connection_lease_ports import LeaseAccess, LeaseErrors, LeaseMutation
        reads = []
        def build(label):
            error = ConfigError(label)
            def fail(*_):
                raise error
            access = LeaseAccess(lambda: lambda *_: {"id": label}, lambda: lambda *_: None)
            mutation = LeaseMutation(*(lambda fail=fail: fail for _ in CALLEES))
            errors = LeaseErrors(lambda: reads.append((label, "config")) or ConfigError,
                                 lambda: reads.append((label, "http")) or HttpError)
            return ConnectionLease(access, mutation, errors), error
        a, ae = build("a")
        b, be = build("b")
        def forbidden(*_args, **_kwargs):
            raise AssertionError("error path reached root collaborator")
        for name in ("require_plc_web_serial_station", "require_analyze_model_permission",
                     *CALLEES, "PlcConfigError", "HTTPException"):
            self.replace(name, forbidden)
        for service, error, label in ((a, ae, "a"), (b, be, "b"), (a, ae, "a")):
            for method in ("claim", "activate", "heartbeat", "rebind_model", "disconnect"):
                with self.assertRaises(HttpError) as caught:
                    getattr(service, method)(self.request, self.payload)
                self.assertIs(caught.exception.__cause__, error)
                self.assertEqual(caught.exception.detail, label)
        self.assertEqual(reads, [(label, port) for label in ("a", "b", "a")
                                 for _ in range(5) for port in ("config", "http")])


if __name__ == "__main__":
    unittest.main()
