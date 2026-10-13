"""Configured read-only output plans preserve the original input contract."""
import hashlib
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local_inspection_service.plc_web_serial import build_web_serial_capture_read_plan
from local_inspection_service.plc_fx_ascii import build_d_register_read_frame, logical_device_address
from local_inspection_service.plc_modbus_rtu import read_word
for protocol, size in [('fx_programming_port_ascii', 8), ('modbus_rtu', 7)]:
    for address in ['D1', 'D42', 'D206']:
        config = {'protocol': protocol, 'capture_input_register': 'D0', 'result_register': address, 'capture_trigger_enabled': False}
        if size == 7:
            config.update(profile_id='xinje_xd5_modbus_rtu', checksum_mode='crc16', baudrate=19200, data_bits=8)
        plan = build_web_serial_capture_read_plan(config, 7)
        output = plan['result_read_plan']
        assert plan['target'] == 'D0' and plan['operation'] == 'read_capture_input'
        assert plan['poll_interval_ms'] == 200 and plan['trigger_value'] == 1
        assert output['target'] == address and output['operation'] == 'read_result_register'
        assert output['poll_interval_ms'] == 1000 and output['expected_response_bytes'] == size
        assert output['config_generation'] == 7 and output['protocol_version'] == 'plc-web-serial-v4'
        frame = read_word(int(address[1:])) if size == 7 else build_d_register_read_frame(logical_device_address(address), 'include_etx')
        assert output['frame_hex'] == frame.hex().upper()
        assert output['frame_sha256'] == hashlib.sha256(frame).hexdigest()
print('PASS FX/RTU configured output plans and preserved input fields; no serial I/O')
