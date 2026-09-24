"""Accepted-main versus candidate workstation-management HTTP behavior."""
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
NAMES = {"get_plc_web_serial_workstation", "list_plc_web_serial_workstations",
         "pair_plc_web_serial_workstation", "update_plc_web_serial_workstation_config",
         "verify_plc_web_serial_workstation_profile"}


class ConfigError(Exception):
    pass


class HttpError(Exception):
    def __init__(self, status_code, detail):
        self.status_code, self.detail = status_code, detail


class WorkstationManagementContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lifetime = ExitStack()
        cls.lifetime.enter_context(patch.dict(os.environ))
        root = Path(cls.lifetime.enter_context(tempfile.TemporaryDirectory(prefix="plc-management-")))
        (root / "local_inspection_service/static").mkdir(parents=True)
        for key in ("DATABASE_URL", "VANTALINE_POSTGRES_DSN", "PGDSN"):
            os.environ.pop(key, None)
        os.environ.update(LOCAL_INSPECTION_ROOT=str(root), VANTALINE_DATA_STORE="json",
                          LOCAL_INSPECTION_AUTO_RESUME_WORKER="0", VANTALINE_LABEL_INSPECTION_ENABLED="false",
                          YOLO_AUTOINSTALL="false")
        for name in ("requests.sessions.Session.request", "urllib.request.urlopen", "subprocess.Popen", "os.kill"):
            cls.lifetime.enter_context(patch(name, side_effect=AssertionError("external operation forbidden")))
        baseline = os.environ.get("VANTALINE_PLC_MANAGEMENT_BASELINE_SOURCE")
        if baseline:
            tree = ast.parse(Path(baseline).read_text(encoding="utf-8"))
            functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in NAMES]
            assert {node.name for node in functions} == NAMES
            for node in functions:
                node.decorator_list = []
            cls.api = types.ModuleType("accepted_main_plc_management")
            cls.api.__dict__.update(Any=Any, Request=object, Response=object,
                                    PlcWorkstationPairRequest=object,
                                    PlcWebSerialConfigRequest=object,
                                    PlcWorkstationVerifyRequest=object)
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
        self.response = types.SimpleNamespace(cookies=[])
        self.station = {"id": "station"}
        events = self.events
        self.replace("PlcConfigError", ConfigError)
        self.replace("HTTPException", HttpError)
        self.replace("require_permission", lambda name: events.append(("permission", name)))
        self.replace("plc_web_serial_station_from_request", lambda request: events.append(("station-from", request)) or self.station)
        self.replace("require_plc_web_serial_station", lambda request: events.append(("require-station", request)) or self.station)
        self.replace("plc_web_serial_station_payload", lambda station: events.append(("payload", station)) or {"paired": True})
        self.replace("plc_web_serial_unpaired_payload", lambda: events.append("unpaired") or {"paired": False})
        self.replace("plc_web_serial_list_workstations", lambda: events.append("list") or [{"id": "station"}])
        self.replace("plc_web_serial_pair", lambda *args: events.append(("pair", args)) or {"id": "station"})
        self.replace("plc_web_serial_update_config", lambda *args: events.append(("update", args)) or {"updated": True})
        self.replace("plc_web_serial_set_verified", lambda *args: events.append(("verify", args)) or {"verified": True})

    def replace(self, name, value):
        self.stack.enter_context(patch.object(self.api, name, value, create=True))

    def test_get_paired_unpaired_and_falsey_station(self):
        self.assertEqual(self.api.get_plc_web_serial_workstation(self.request), {"paired": True})
        self.assertEqual(self.events, [("station-from", self.request), ("payload", self.station)])
        self.events.clear()
        self.replace("plc_web_serial_station_from_request", lambda request: self.events.append("lookup") or {})
        self.assertEqual(self.api.get_plc_web_serial_workstation(self.request), {"paired": False})
        self.assertEqual(self.events, ["lookup", "unpaired"])

    def test_list_permission_before_state_and_failure(self):
        self.assertEqual(self.api.list_plc_web_serial_workstations(), {"items": [{"id": "station"}]})
        self.assertEqual(self.events, [("permission", "system_settings"), "list"])
        self.events.clear()
        denied = HttpError(403, "denied")
        self.replace("require_permission", lambda name: (_ for _ in ()).throw(denied))
        with self.assertRaises(HttpError) as caught:
            self.api.list_plc_web_serial_workstations()
        self.assertIs(caught.exception, denied)
        self.assertEqual(self.events, [])

    def test_pair_success_and_business_error_conversion(self):
        payload = types.SimpleNamespace(name="Station", station_id="existing")
        self.assertEqual(self.api.pair_plc_web_serial_workstation(self.request, self.response, payload), {"id": "station"})
        self.assertEqual(self.events[0], ("permission", "system_settings"))
        self.assertEqual(self.events[1], ("pair", (self.request, self.response, "Station", "existing")))
        error = ConfigError("invalid")
        self.replace("plc_web_serial_pair", lambda *args: (_ for _ in ()).throw(error))
        with self.assertRaises(HttpError) as caught:
            self.api.pair_plc_web_serial_workstation(self.request, self.response, payload)
        self.assertEqual((caught.exception.status_code, caught.exception.detail), (400, "invalid"))
        self.assertIs(caught.exception.__cause__, error)

    def test_config_callee_selected_before_model_dump(self):
        def first(station_id, data):
            self.events.append("first-update")
            return {"selected": "first"}
        def second(station_id, data):
            self.events.append("second-update")
            return {"selected": "second"}
        class Payload:
            def model_dump(inner):
                self.events.append("dump")
                setattr(self.api, "plc_web_serial_update_config", second)
                return {"enabled": False}
        self.replace("plc_web_serial_update_config", first)
        self.assertEqual(self.api.update_plc_web_serial_workstation_config(self.request, Payload()),
                         {"selected": "first"})
        self.assertNotIn("second-update", self.events)
        self.assertLess(self.events.index(("permission", "system_settings")), self.events.index("dump"))

    def test_config_error_and_station_resolution_outside_try(self):
        dumps = []
        payload = types.SimpleNamespace(model_dump=lambda: dumps.append("dump") or {"enabled": True})
        error = ConfigError("bad config")
        self.replace("plc_web_serial_update_config", lambda *args: (_ for _ in ()).throw(error))
        with self.assertRaises(HttpError) as caught:
            self.api.update_plc_web_serial_workstation_config(self.request, payload)
        self.assertEqual((caught.exception.status_code, caught.exception.detail), (400, "bad config"))
        self.assertIs(caught.exception.__cause__, error)
        dumps.clear()
        self.replace("require_plc_web_serial_station", lambda request: (_ for _ in ()).throw(error))
        with self.assertRaises(ConfigError) as caught:
            self.api.update_plc_web_serial_workstation_config(self.request, payload)
        self.assertIs(caught.exception, error)
        self.assertEqual(dumps, [])

    def test_verification_order_and_error(self):
        payload = types.SimpleNamespace(verified=False)
        self.assertEqual(self.api.verify_plc_web_serial_workstation_profile(self.request, payload),
                         {"verified": True})
        self.assertEqual(self.events[-1], ("verify", ("station", False)))
        error = ConfigError("not ready")
        self.replace("plc_web_serial_set_verified", lambda *args: (_ for _ in ()).throw(error))
        with self.assertRaises(HttpError) as caught:
            self.api.verify_plc_web_serial_workstation_profile(self.request, payload)
        self.assertEqual((caught.exception.status_code, caught.exception.detail), (400, "not ready"))
        self.assertIs(caught.exception.__cause__, error)

    def test_pair_partial_cookie_effect_is_not_retried(self):
        payload = types.SimpleNamespace(name="Station", station_id=None)
        calls = []
        error = ValueError("projection")
        def pair(request, response, name, station_id):
            calls.append("pair")
            response.cookies.append("token")
            raise error
        self.replace("plc_web_serial_pair", pair)
        with self.assertRaises(ValueError) as caught:
            self.api.pair_plc_web_serial_workstation(self.request, self.response, payload)
        self.assertIs(caught.exception, error)
        self.assertEqual((calls, self.response.cookies), (["pair"], ["token"]))


    def test_config_callee_selected_before_station_string(self):
        class StationId:
            def __str__(inner):
                self.events.append("id-str")
                setattr(self.api, "plc_web_serial_update_config", lambda *_: {"selected": "late"})
                return "station"
        self.station = {"id": StationId()}
        self.replace("plc_web_serial_update_config", lambda *_: {"selected": "early"})
        payload = types.SimpleNamespace(model_dump=lambda: {})
        self.assertEqual(self.api.update_plc_web_serial_workstation_config(self.request, payload),
                         {"selected": "early"})

    def test_exception_class_and_http_factory_late_binding(self):
        class NewConfigError(Exception):
            def __str__(inner):
                setattr(self.api, "HTTPException", LateHttpError)
                return "late detail"
        class EarlyHttpError(HttpError):
            pass
        class LateHttpError(HttpError):
            pass
        error = NewConfigError()
        def update(*args):
            setattr(self.api, "PlcConfigError", NewConfigError)
            raise error
        self.replace("plc_web_serial_update_config", update)
        self.replace("HTTPException", EarlyHttpError)
        payload = types.SimpleNamespace(model_dump=lambda: {})
        with self.assertRaises(EarlyHttpError) as caught:
            self.api.update_plc_web_serial_workstation_config(self.request, payload)
        self.assertEqual((caught.exception.status_code, caught.exception.detail), (400, "late detail"))
        self.assertIs(caught.exception.__cause__, error)

    def test_constructor_and_two_instance_isolation(self):
        if os.environ.get("VANTALINE_PLC_MANAGEMENT_BASELINE_SOURCE"):
            self.skipTest("candidate composition only")
        from local_inspection_service.plc.workstation_management import WorkstationManagement
        from local_inspection_service.plc.workstation_management_ports import (
            WorkstationAccess, WorkstationErrors, WorkstationMutation, WorkstationProjection)
        reads = []
        paired = {"a": True, "b": True}
        fail_update = {"a": False, "b": False}
        def getter(label, name, callback):
            return lambda: reads.append((label, name)) or callback
        def update_for(label):
            if fail_update[label]:
                raise ConfigError("bad")
            return {"id": label}
        def build(label):
            access = WorkstationAccess(
                getter(label, "permission", lambda *_: None),
                getter(label, "from-request", lambda *_: {"id": label} if paired[label] else {}),
                getter(label, "require", lambda *_: {"id": label}))
            projection = WorkstationProjection(
                getter(label, "payload", lambda station: {"id": station["id"]}),
                getter(label, "unpaired", lambda: {"id": None}),
                getter(label, "list", lambda: [{"id": label}]))
            mutation = WorkstationMutation(
                getter(label, "pair", lambda *_: {"id": label}),
                getter(label, "update", lambda *_: update_for(label)),
                getter(label, "verify", lambda *_: {"id": label}))
            errors = WorkstationErrors(getter(label, "config-error", ConfigError),
                                       getter(label, "http-error", HttpError))
            return WorkstationManagement(access, projection, mutation, errors)
        a, b = build("a"), build("b")
        self.assertEqual(reads, [])
        def forbidden(*_args, **_kwargs):
            raise AssertionError("business service read root collaborator")
        for name in ("require_permission", "plc_web_serial_station_from_request",
                     "require_plc_web_serial_station", "plc_web_serial_station_payload",
                     "plc_web_serial_unpaired_payload", "plc_web_serial_list_workstations",
                     "plc_web_serial_pair", "plc_web_serial_update_config",
                     "plc_web_serial_set_verified", "PlcConfigError", "HTTPException"):
            self.replace(name, forbidden)
        payload = types.SimpleNamespace(name="name", station_id=None, verified=True,
                                        model_dump=lambda: {})
        expected = ["from-request", "payload", "permission", "list",
                    "permission", "pair", "permission", "require", "update",
                    "permission", "require", "verify", "from-request", "unpaired",
                    "permission", "require", "update", "config-error", "http-error"]
        for service, label in ((a, "a"), (b, "b"), (a, "a")):
            before = len(reads)
            self.assertEqual(service.get(self.request), {"id": label})
            self.assertEqual(service.list(), {"items": [{"id": label}]})
            self.assertEqual(service.pair(self.request, self.response, payload), {"id": label})
            self.assertEqual(service.update_config(self.request, payload), {"id": label})
            self.assertEqual(service.verify_profile(self.request, payload), {"id": label})
            paired[label] = False
            self.assertEqual(service.get(self.request), {"id": None})
            paired[label] = True
            fail_update[label] = True
            with self.assertRaises(HttpError) as caught:
                service.update_config(self.request, payload)
            self.assertEqual(caught.exception.status_code, 400)
            fail_update[label] = False
            self.assertEqual(reads[before:], [(label, name) for name in expected])

if __name__ == "__main__":
    unittest.main()
