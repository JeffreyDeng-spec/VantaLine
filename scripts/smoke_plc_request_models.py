"""PLC request validation, with an optional original-source oracle for migration."""
import ast
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from pydantic import BaseModel, StrictBool, StrictFloat, StrictInt, StrictStr, ValidationError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
BASELINE = os.environ.get('VANTALINE_PLC_REQUEST_MODELS_BASELINE_SOURCE')
OPERATION = dict(target='D206', frame_sha256='digest', status='ack', response_hex='06', completed_at=100)
PAYLOADS = {
    'PlcConfigRequest': dict(enabled=False, protocol='fx', checksum_mode='include_etx', serial_port='', baudrate=9600,
        parity='E', data_bits=7, stop_bits=1, result_register='D206', output_control_point='', capture_trigger_enabled=False,
        capture_input_register='D205', capture_trigger_value=1, d206_address='', y04_address='', write_y04=False, timeout=0.5, retries=0),
    'PlcCaptureSessionRequest': dict(model_id='model', camera_ready=False),
    'PlcCaptureSessionHeartbeatRequest': dict(session_id='session'),
    'PlcWebSerialConfigRequest': dict(schema_version=5, transport_mode='web_serial', profile_id='profile', enabled=False,
        protocol='fx', checksum_mode='include_etx', baudrate=9600, parity='E', data_bits=7, stop_bits=1,
        result_register='D206', output_control_point='', capture_trigger_enabled=False, capture_input_register='D205',
        capture_trigger_value=1, capture_poll_interval_ms=200, ack_timeout_ms=500, retries=0),
    'PlcWorkstationPairRequest': dict(name='station', station_id='station'),
    'PlcWorkstationVerifyRequest': dict(verified=False),
    'PlcWorkstationLeaseRequest': dict(client_instance_id='client', model_id='model', bundle_version='bundle'),
    'PlcWorkstationLeaseActivateRequest': dict(session_id='session', lease_epoch=1, usb_vendor_id=1, usb_product_id=2),
    'PlcWorkstationLeaseHeartbeatRequest': dict(session_id='session', lease_epoch=1),
    'PlcWorkstationLeaseRebindRequest': dict(session_id='session', lease_epoch=1, model_id='model'),
    'PlcWebSerialAttemptRequest': dict(session_id='session', lease_epoch=1, config_generation=2),
    'PlcWebSerialDiagnosticReceiptRequest': dict(session_id='session', lease_epoch=1, diagnostic_id='diagnostic', attempt_token='token', outcome='ack'),
    'PlcWebSerialDiagnosticConfirmRequest': dict(session_id='session', lease_epoch=1, diagnostic_id='diagnostic', attempt_token='token'),
    'PlcWebSerialReceiptOperation': OPERATION,
    'PlcWebSerialReceiptRequest': dict(session_id='session', lease_epoch=1, attempt_token='token', outcome='ack', operations=[OPERATION]),
}


def models():
    if BASELINE:
        from local_inspection_service.plc_fx_ascii import PROTOCOL_ID
        from local_inspection_service.plc_web_serial import WEB_SERIAL_PROFILE_ID, WEB_SERIAL_SCHEMA_VERSION
        nodes = [n for n in ast.parse(Path(BASELINE).read_text(encoding='utf-8-sig')).body
                 if isinstance(n, ast.ClassDef) and n.name in PAYLOADS]
        assert len(nodes) == len(PAYLOADS)
        ns = dict(BaseModel=BaseModel, StrictBool=StrictBool, StrictFloat=StrictFloat, StrictInt=StrictInt, StrictStr=StrictStr,
                  PLC_PROTOCOL_ID=PROTOCOL_ID, WEB_SERIAL_PROFILE_ID=WEB_SERIAL_PROFILE_ID, WEB_SERIAL_SCHEMA_VERSION=WEB_SERIAL_SCHEMA_VERSION)
        exec(compile(ast.Module(body=nodes, type_ignores=[]), BASELINE, 'exec'), ns)
        return SimpleNamespace(**{name: ns[name] for name in PAYLOADS})
    from local_inspection_service.schemas import plc
    return plc


MODELS = models()


class PlcRequestContracts(unittest.TestCase):
    def test_complete_fields_and_roundtrip(self):
        for name, payload in PAYLOADS.items():
            with self.subTest(name=name):
                cls = getattr(MODELS, name)
                self.assertEqual(set(payload), set(cls.model_fields))
                self.assertEqual(cls.model_validate(payload).model_dump(), payload)
                self.assertEqual(cls.model_validate_json(cls(**payload).model_dump_json()).model_dump(), payload)

    def test_strict_scalars_and_error_location(self):
        for name, payload in PAYLOADS.items():
            for field, value in payload.items():
                bad = {str: 7, int: True, bool: 'false', float: '0.5'}.get(type(value), None)
                if bad is None:
                    continue
                with self.subTest(name=name, field=field):
                    with self.assertRaises(ValidationError) as raised:
                        getattr(MODELS, name)(**dict(payload, **{field: bad}))
                    self.assertTrue(all(error['loc'][0] == field for error in raised.exception.errors()))

    def test_extra_fields_and_missing_required(self):
        for name, payload in PAYLOADS.items():
            cls = getattr(MODELS, name)
            with self.subTest(name=name):
                with self.assertRaises(ValidationError) as raised:
                    cls(**dict(payload, unrecognized='no'))
                self.assertEqual([(e['loc'], e['type']) for e in raised.exception.errors()], [(('unrecognized',), 'extra_forbidden')])
                for field, spec in cls.model_fields.items():
                    if spec.is_required():
                        with self.assertRaises(ValidationError) as raised:
                            cls(**{k: v for k, v in payload.items() if k != field})
                        self.assertEqual([(e['loc'], e['type']) for e in raised.exception.errors()], [((field,), 'missing')])

    def test_defaults_and_optional_values(self):
        from local_inspection_service.plc_fx_ascii import PROTOCOL_ID
        from local_inspection_service.plc_web_serial import WEB_SERIAL_PROFILE_ID, WEB_SERIAL_SCHEMA_VERSION
        self.assertEqual(MODELS.PlcConfigRequest().model_dump(), dict.fromkeys(PAYLOADS['PlcConfigRequest']))
        self.assertEqual(MODELS.PlcWebSerialConfigRequest().model_dump(), dict(PAYLOADS['PlcWebSerialConfigRequest'],
            protocol=PROTOCOL_ID, profile_id=WEB_SERIAL_PROFILE_ID, schema_version=WEB_SERIAL_SCHEMA_VERSION))
        self.assertIsNone(MODELS.PlcCaptureSessionRequest(camera_ready=False).model_id)
        self.assertIsNone(MODELS.PlcWorkstationPairRequest(name='station').station_id)
        self.assertEqual(MODELS.PlcWorkstationLeaseActivateRequest(session_id='s', lease_epoch=1).model_dump(),
            dict(session_id='s', lease_epoch=1, usb_vendor_id=None, usb_product_id=None))
        self.assertEqual(MODELS.PlcConfigRequest(timeout=1).timeout, 1)

    def test_nested_receipt_validation(self):
        payload = PAYLOADS['PlcWebSerialReceiptRequest']
        receipt = MODELS.PlcWebSerialReceiptRequest(**payload)
        self.assertIsInstance(receipt.operations[0], MODELS.PlcWebSerialReceiptOperation)
        for operation, location, kind in [(dict(OPERATION, completed_at=True), ('operations', 0, 'completed_at'), 'int_type'),
                                         (dict(OPERATION, unexpected=1), ('operations', 0, 'unexpected'), 'extra_forbidden')]:
            with self.assertRaises(ValidationError) as raised:
                MODELS.PlcWebSerialReceiptRequest(**dict(payload, operations=[operation]))
            self.assertEqual([(e['loc'], e['type']) for e in raised.exception.errors()], [(location, kind)])
        self.assertEqual(MODELS.PlcWebSerialReceiptRequest(**dict(payload, operations=[])).operations, [])

    @unittest.skipIf(BASELINE, 'Original models reside in the application entry')
    def test_no_reverse_import_and_application_class_identity(self):
        self.assertNotIn('local_inspection_service.server', sys.modules)
        with tempfile.TemporaryDirectory(prefix='vantaline-plc-schemas-') as temporary:
            (Path(temporary) / 'local_inspection_service/static').mkdir(parents=True)
            with patch.dict(os.environ, {'LOCAL_INSPECTION_ROOT': temporary, 'VANTALINE_DATA_STORE': 'json',
                    'VANTALINE_LABEL_INSPECTION_ENABLED': 'false', 'LOCAL_INSPECTION_AUTO_RESUME_WORKER': '0',
                    'INSPECTION_WORKER_WATCHER': '0', 'VANTALINE_YOLO_PREWARM': '0'}):
                from local_inspection_service import server
                for name in PAYLOADS:
                    self.assertIs(getattr(server, name), getattr(MODELS, name))


if __name__ == '__main__':
    unittest.main()
