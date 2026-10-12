"""Actual authenticated config/lease/camera HTTP evidence in disposable JSON storage."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local_inspection_service.scripts import smoke_plc_web_serial_v3 as f
from local_inspection_service.plc_modbus_rtu import PROFILE, PROTOCOL, frame, write_word
from local_inspection_service.plc_fx_ascii import build_d_register_write_frame, logical_device_address
server,Client,check=f.server,f.TestClient,f.assert_status
admin=Client(server.app,base_url='https://testserver')
check(admin.post('/api/auth/bootstrap',json={'username':'admin','password':'admin-password-123'}),200,'bootstrap')
check(admin.post('/api/auth/users',json={'username':'operator','password':'operator-password-123','role':'user','permissions':['inspection'],'active':True}),200,'operator')
for protocol in ('fx','rtu'):
    c=Client(server.app,base_url='https://testserver')
    check(c.post('/api/auth/login',json={'username':'operator','password':'operator-password-123'}),200,'login')
    check(c.post('/api/plc/workstation/self-pair',json={}),200,'pair')
    config={**f.DEFAULT_WEB_SERIAL_CONFIG,'enabled':True,'result_pass_value':0,'result_fail_value':65535}
    if protocol=='rtu':config.update(profile_id=PROFILE,protocol=PROTOCOL,baudrate=19200,data_bits=8,checksum_mode='crc16')
    for key in ('result_pass_value','result_fail_value'):
        for bad in (None,'',True,0.5,-1,65536):
            check(c.post('/api/plc/workstation/self-config',json={**config,key:bad}),422,'invalid word')
    saved=c.post('/api/plc/workstation/self-config',json=config);check(saved,200,'save')
    generation=saved.json()['config_generation']
    cookie=c.cookies.get(server.PLC_WORKSTATION_COOKIE)
    check(c.post('/api/auth/logout'),200,'logout')
    assert c.cookies.get(server.PLC_WORKSTATION_COOKIE)==cookie
    check(c.post('/api/auth/login',json={'username':'operator','password':'operator-password-123'}),200,'login again')
    assert c.get('/api/plc/workstation').json()['config']==config
    claim=c.post('/api/plc/workstation/connect',json={'client_instance_id':'values-test','model_id':'','bundle_version':'plc-web-serial-v4'})
    check(claim,200,'claim');lease=claim.json();identity=dict(session_id=lease['session_id'],lease_epoch=lease['lease_epoch'])
    reads=[dict(target=x['target'],response_hex=frame(bytes.fromhex('0103020000')).hex() if protocol=='rtu' else '0230303030034333') for x in lease['connection_check']['frames']]
    check(c.post('/api/plc/workstation/connect/activate',json={**identity,'connection_check_id':lease['connection_check']['id'],'connection_reads':reads}),200,'activate')
    check(c.post('/api/plc/workstation/self-config',json={**config,'result_pass_value':42}),409,'active local config rejected')
    check(c.post('/api/plc/workstation/lease/rebind-model',json={**identity,'model_id':'model-a'}),200,'model')
    original=server._detection_analysis.analyze_bgr
    plans=[]
    try:
        for passed,value in ((True,0),(False,65535)):
            server._detection_analysis.analyze_bgr=lambda _image,request_id,_model_id=None,**kw:dict(request_id=request_id,passed=passed,rule={'passed':passed},detections=[])
            ordinary=c.post('/api/analyze/image',files={'file':('image.png',f.TINY_PNG,'image/png')})
            check(ordinary,200,'ordinary upload');assert 'plc_sync' not in ordinary.json()
            response=c.post('/api/analyze/camera',data={'model_id':'model-a','plc_session_id':identity['session_id'],'camera_request_id':f'values_{protocol}_{passed}'},files={'file':('camera.png',f.TINY_PNG,'image/png')})
            check(response,200,'camera');plan=response.json()['plc_sync'];plans.append(plan)
            expected=write_word(206,value) if protocol=='rtu' else build_d_register_write_frame(logical_device_address('D206'),value,'include_etx')
            assert plan['status']=='planned'
            record=next(x for x in server.plc_web_serial_recent_dispatches(saved.json()['station']['id']) if x['dispatch_id']==plan['dispatch_id'])
            assert record['frames'][0]['frame_hex']==expected.hex().upper()
            if passed:
                attempt=c.post(f"/api/plc/workstation/dispatches/{plan['dispatch_id']}/attempt",json={**identity,'config_generation':generation})
                check(attempt,200,'declare');a=attempt.json();op=a['frames'][0]
                check(c.post(f"/api/plc/workstation/dispatches/{plan['dispatch_id']}/receipt",json={**identity,'attempt_token':a['attempt_token'],'outcome':'acknowledged','operations':[dict(target=op['target'],frame_sha256=op['frame_sha256'],status='acknowledged',response_hex=op['expected_response_hex'],completed_at=1)]}),200,'synthetic ACK')
    finally:server._detection_analysis.analyze_bgr=original
    admin.cookies[server.PLC_WORKSTATION_COOKIE]=cookie
    changed=admin.post('/api/plc/workstation/config',json={**config,'result_pass_value':2,'result_fail_value':3})
    check(changed,200,'admin change');assert changed.json()['config_generation']==generation+1
    assert not changed.json()['effective_enabled']
    check(c.post('/api/plc/workstation/lease/heartbeat',json=identity),409,'old lease fenced')
    check(c.post(f"/api/plc/workstation/dispatches/{plans[-1]['dispatch_id']}/attempt",json={**identity,'config_generation':generation}),409,'old plan fenced')
print('PASS configurable outputs: HTTP validation, logout persistence, both protocols, camera frames, synthetic ACK and generation fencing')
