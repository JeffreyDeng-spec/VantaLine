"""Authenticated actual ASGI RTU negotiation; isolated JSON fixtures, no serial I/O."""
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local_inspection_service.scripts import smoke_plc_web_serial_v3 as fixture
from local_inspection_service.plc_modbus_rtu import frame
server, Client, check = fixture.server, fixture.TestClient, fixture.assert_status
admin = Client(server.app, base_url="https://testserver")
check(admin.post('/api/auth/bootstrap', json={'username':'admin','password':'admin-password-123'}),200,'bootstrap')
check(admin.post('/api/auth/users',json={'username':'operator','password':'operator-password-123','role':'user','permissions':['inspection'],'active':True}),200,'operator')
operator=Client(server.app,base_url='https://testserver')
check(operator.post('/api/auth/login',json={'username':'operator','password':'operator-password-123'}),200,'login')
check(operator.post('/api/plc/workstation/self-pair',json={}),200,'pair')
check(operator.post('/api/plc/workstation/self-config',json={**fixture.DEFAULT_WEB_SERIAL_CONFIG,'enabled':True,'capture_trigger_enabled':True}),200,'FX config')
claimed=operator.post('/api/plc/workstation/connect',json={'client_instance_id':'modbus-browser','model_id':'','bundle_version':'plc-web-serial-v4'})
check(claimed,200,'claim')
lease=claimed.json();alt=lease['connection_check']['alternatives'][0]
assert alt['config']['protocol']=='modbus_rtu' and len(alt['frames'])==2
response=frame(bytes.fromhex('0103020000')).hex().upper()
activation=dict(session_id=lease['session_id'],lease_epoch=lease['lease_epoch'],connection_check_id=alt['id'],connection_reads=[dict(target=f['target'],response_hex=response) for f in alt['frames']])
bad={**activation,'connection_reads':[dict(target=f['target'],response_hex='01030200000000') for f in alt['frames']]}
check(operator.post('/api/plc/workstation/connect/activate',json=bad),409,'CRC rejects')
assert operator.get('/api/plc/workstation').json()['config']['protocol']=='fx_programming_port_ascii'
activated=operator.post('/api/plc/workstation/connect/activate',json=activation)
check(activated,200,'RTU activates')
current=operator.get('/api/plc/workstation').json()
assert current['config']['protocol']=='modbus_rtu'
assert current['config']['baudrate']==19200 and current['config']['data_bits']==8
assert current['config_generation']==lease['config_generation']+1
assert activated.json()['config_generation']==current['config_generation']
assert current['lease']['communication_verified'] and current['production_ready']
assert not current['config']['capture_trigger_enabled'] and not current['station']['profile_verified']
assert current['capture_read_plan']['expected_response_bytes']==7
check(operator.post('/api/plc/workstation/connect/activate',json=activation),409,'no repeated activation')
identity=dict(session_id=lease['session_id'],lease_epoch=lease['lease_epoch'])
check(operator.post('/api/plc/workstation/lease/heartbeat',json=identity),200,'generation persists')
check(operator.post('/api/plc/workstation/diagnostic-plan',json={**identity,'config_generation':current['config_generation']}),403,'operator cannot use admin write diagnostic')
# Admin uses the same workstation capability for the unsupported-diagnostic gate.
admin.cookies[server.PLC_WORKSTATION_COOKIE] = operator.cookies.get(server.PLC_WORKSTATION_COOKIE)
check(admin.post('/api/plc/workstation/lease/heartbeat',json=identity),409,'different owner cannot heartbeat')
check(operator.post('/api/plc/workstation/lease/disconnect',json=identity),200,'disconnect')
again=operator.post('/api/plc/workstation/connect',json={'client_instance_id':'modbus-browser','model_id':'','bundle_version':'plc-web-serial-v4'})
check(again,200,'saved RTU claim')
assert again.json()['connection_check']['config']['protocol']=='modbus_rtu'
assert not again.json()['connection_check'].get('alternatives')
print('smoke_plc_modbus_http: PASS (actual auth, CRC fencing, atomic profile/generation persistence, saved RTU and connection-based readiness)')
