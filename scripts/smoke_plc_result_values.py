"""Configurable camera result words: synthetic protocol frames, no physical I/O."""
import hashlib
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pydantic import ValidationError
from local_inspection_service.plc_fx_ascii import PlcConfigError, build_d_register_write_frame, logical_device_address
from local_inspection_service.plc_modbus_rtu import PROFILE, PROTOCOL, write_word
from local_inspection_service.plc_web_serial import DEFAULT_WEB_SERIAL_CONFIG, normalize_web_serial_config, build_web_serial_plan, web_serial_config_fingerprint, build_connection_check
from local_inspection_service.schemas.plc import PlcWebSerialConfigRequest
from plc_result_values_source_contract import checkpoint_bytes, ROOT

class ResultValues(unittest.TestCase):
    def test_missing_defaults_and_rollback_compatibility(self):
        old = {k:v for k,v in DEFAULT_WEB_SERIAL_CONFIG.items() if k not in ('result_pass_value','result_fail_value')}
        self.assertEqual(normalize_web_serial_config(old), DEFAULT_WEB_SERIAL_CONFIG)
        self.assertEqual(PlcWebSerialConfigRequest(**old).result_pass_value, 1)
        source = checkpoint_bytes('local_inspection_service/plc_web_serial.py', (ROOT/'local_inspection_service/plc_web_serial.py').read_bytes())
        import types
        module = types.ModuleType('local_inspection_service._pre_result_values')
        module.__package__ = 'local_inspection_service'
        exec(compile(source, '<pre-feature>', 'exec'), module.__dict__)
        for protocol in ('fx', 'rtu'):
            config = dict(DEFAULT_WEB_SERIAL_CONFIG, result_pass_value=2, result_fail_value=3)
            if protocol == 'rtu': config.update(profile_id=PROFILE, protocol=PROTOCOL, baudrate=19200, data_bits=8, checksum_mode='crc16')
            with self.assertRaises(PlcConfigError): module.normalize_web_serial_config(config)
            prepared = {k:v for k,v in config.items() if k not in ('result_pass_value','result_fail_value')}
            self.assertEqual(module.normalize_web_serial_config(prepared)['result_register'], 'D206')
            # The old release resumes its documented 1/0 behavior after preparation.
            self.assertEqual(len(module.build_web_serial_plan(prepared, True)), 1)

    def test_strict_validation(self):
        for field in ('result_pass_value','result_fail_value'):
            for value in (None, '', '1', True, 1.5, -1, 65536):
                with self.subTest(field=field,value=value):
                    raw = {**DEFAULT_WEB_SERIAL_CONFIG, field:value}
                    with self.assertRaises(PlcConfigError): normalize_web_serial_config(raw)
                    with self.assertRaises(ValidationError): PlcWebSerialConfigRequest(**raw)

    def test_actual_encoded_words_and_y(self):
        for good,bad in ((1,0),(2,3),(0,1),(0,65535),(65535,0),(42,42)):
            for passed,value in ((True,good),(False,bad)):
                config = dict(DEFAULT_WEB_SERIAL_CONFIG, result_register='D207', result_pass_value=good, result_fail_value=bad)
                for y in ('','Y04'):
                    plan = build_web_serial_plan({**config,'output_control_point':y}, passed)
                    expected = build_d_register_write_frame(logical_device_address('D207'),value,'include_etx')
                    self.assertEqual(plan[0]['frame_hex'], expected.hex().upper())
                    self.assertEqual(plan[0]['expected_response_hex'], '06')
                    self.assertEqual(plan[0]['frame_sha256'], hashlib.sha256(expected).hexdigest())
                    self.assertEqual(len(plan), 2 if y else 1)
                    if y:
                        self.assertEqual(plan[1],build_web_serial_plan({**DEFAULT_WEB_SERIAL_CONFIG,'output_control_point':y},passed)[1])
                config.update(profile_id=PROFILE,protocol=PROTOCOL,baudrate=19200,data_bits=8,checksum_mode='crc16')
                plan=build_web_serial_plan(config,passed)
                self.assertEqual(len(plan),1)
                self.assertEqual(plan[0]['frame_hex'],write_word(207,value).hex().upper())
                self.assertEqual(plan[0]['expected_response_hex'],plan[0]['frame_hex'])

    def test_fingerprint_and_negotiation_preserve_values(self):
        config={**DEFAULT_WEB_SERIAL_CONFIG,'result_pass_value':0,'result_fail_value':65535}
        self.assertNotEqual(web_serial_config_fingerprint(config),web_serial_config_fingerprint(DEFAULT_WEB_SERIAL_CONFIG))
        for field in ('result_pass_value','result_fail_value'):
            self.assertNotEqual(web_serial_config_fingerprint(config),web_serial_config_fingerprint({**config,field:42}))
        lease=dict(station_id='station',session_id='session',lease_epoch=1,config_generation=2,expires_at=100)
        check=build_connection_check(lease,config,'test')
        for candidate in [check,*check['alternatives']]:
            self.assertEqual(candidate['config']['result_pass_value'],0)
            self.assertEqual(candidate['config']['result_fail_value'],65535)

    def test_exact_inverse_and_mutation_rejection(self):
        fixture=json.loads((ROOT/'tests/backend_contract/plc_result_values_delta.json').read_text())
        for path,change in fixture['files'].items():
            actual=(ROOT/path).read_bytes()
            self.assertEqual(hashlib.sha256(checkpoint_bytes(path,actual)).hexdigest(),change['parent_sha256'])
            with self.assertRaises(AssertionError):checkpoint_bytes(path,actual+b'\n# unexpected mutation\n')

if __name__=='__main__': unittest.main()
