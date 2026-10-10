"""Original/candidate pure PLC evidence validation; no physical or paid calls."""
import ast
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import types
import unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from canonical_application_source_contract import read_checked_application_source
from local_inspection_service import plc_fx_ascii as protocol
from local_inspection_service.plc import event_projection, transition_policy
from local_inspection_service.plc.errors import PlcDispatchStateConflict

NAMES={'PLC_LEGACY_IO_CONFIG_FIELDS','PLC_SUPPORTED_RECORD_VERSIONS','PLC_PERSISTED_DISPATCH_FIELDS',
       'normalize_plc_v1_snapshot','build_plc_v1_dispatch_plan','build_plc_dispatch_plan','verify_persisted_plc_dispatch'}
BASELINE=os.environ.get('VANTALINE_PLC_PERSISTED_BASELINE_SOURCE')
if BASELINE:
    source=Path(BASELINE).read_text(encoding='utf-8-sig');tree=ast.parse(source)
    nodes=[n for n in tree.body if (isinstance(n,ast.FunctionDef) and n.name in NAMES)
           or (isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id in NAMES for t in n.targets))]
    assert len(nodes)==7
    policy=types.ModuleType('baseline_policy')
    policy.__dict__.update(Any=object,copy=copy,hashlib=hashlib,json=json,re=re,
        DEFAULT_PLC_CONFIG=protocol.DEFAULT_PLC_CONFIG,PlcConfigError=protocol.PlcConfigError,
        normalize_plc_config=protocol.normalize_config,build_d206_frame=protocol.build_d206_frame,
        build_y04_frame=protocol.build_y04_frame,logical_device_address=protocol.logical_device_address,
        PLC_IMMUTABLE_BINDING_FIELDS=transition_policy.PLC_IMMUTABLE_BINDING_FIELDS,
        PLC_DISPATCH_KNOWN_FIELDS=transition_policy.PLC_DISPATCH_KNOWN_FIELDS,
        PLC_REDUCER_DERIVED_FIELDS=event_projection.PLC_REDUCER_DERIVED_FIELDS,
        project_plc_dispatch_events=event_projection.project_plc_dispatch_events,
        _plc_canonical=transition_policy._plc_canonical,PlcDispatchStateConflict=PlcDispatchStateConflict)
    exec(compile(ast.Module(body=nodes,type_ignores=[]),BASELINE,'exec'),policy.__dict__)
else:
    from local_inspection_service.plc import persisted_validation as policy


def record(version=2,output=False):
    if version==1:
        snapshot=policy.normalize_plc_v1_snapshot(dict(enabled=True,protocol='fx_programming_port_ascii',
            checksum_mode='exclude_etx_legacy_vb',serial_port='COM3',baudrate=9600,parity='E',data_bits=7,
            stop_bits=1,d206_address='119D',y04_address='0109',write_y04=output,timeout=1.,retries=0))
        targets,frames=policy.build_plc_v1_dispatch_plan(snapshot,True)
    else:
        snapshot=protocol.normalize_config({**protocol.DEFAULT_PLC_CONFIG,'enabled':True,'serial_port':'COM3',
            'result_register':'D206','output_control_point':'Y04' if output else '', 'retries':0})
        targets,frames=policy.build_plc_dispatch_plan(snapshot,True)
    material=dict(source='camera',request_id='fixture-request',fingerprint='fixture-fingerprint')
    identity=hashlib.sha256(json.dumps(material,sort_keys=True,ensure_ascii=True).encode()).hexdigest()[:24]
    value=dict(record_schema_version=version,protocol_contract_version=version,dispatch_id=identity,source=material['source'],
        request_id=material['request_id'],passed=True,detection_identity=material['fingerprint'],control_generation=1,
        enabled=True,config_snapshot=snapshot,protocol=snapshot['protocol'],checksum_mode=snapshot['checksum_mode'],
        planned_targets=targets,planned_frames=frames,state_version=1,created_at=100)
    return event_projection.project_plc_dispatch_events(value,[dict(seq=1,kind='create',at=100)])


class PersistedContract(unittest.TestCase):
    def verify(self,value):
        before=copy.deepcopy(value)
        try:return policy.verify_persisted_plc_dispatch(value)
        finally:self.assertEqual(value,before,'validator changed evidence')

    def reject(self,value,reason):
        with self.assertRaises(PlcDispatchStateConflict) as caught:self.verify(value)
        self.assertEqual(caught.exception.reason,reason)
        self.assertEqual(caught.exception.authoritative,value)
        self.assertIsNot(caught.exception.authoritative,value)

    def corrupt(self,changes,reason):
        value=record();value.update(changes);self.reject(value,'corrupt_persisted_dispatch:'+reason)

    def test_canonical_versions_and_original_nested_identity(self):
        for version in (1,2):
            for output in (False,True):
                value=record(version,output);result=self.verify(value)
                self.assertEqual(result,value);self.assertIsNot(result,value)
                self.assertIs(result['config_snapshot'],value['config_snapshot'])
                self.assertEqual(len(result['planned_targets']),2 if output else 1)
        historical=record(1,True)
        self.assertEqual(historical['config_snapshot']['d206_address'],'119D')
        self.assertEqual(historical['config_snapshot']['y04_address'],'0109')

    def test_legacy_shape_and_address_errors(self):
        snapshot=record(1)['config_snapshot']
        for value in (None,[],{**snapshot,'extra':1},{k:v for k,v in snapshot.items() if k!='retries'}):
            with self.assertRaises(protocol.PlcConfigError):policy.normalize_plc_v1_snapshot(value)
        for field,value,message in [('d206_address','xyz','legacy D address must contain four hexadecimal characters'),
            ('y04_address','12345','legacy Y address must contain four hexadecimal characters'),
            ('write_y04',1,'legacy write_y04 must be a boolean')]:
            with self.assertRaisesRegex(protocol.PlcConfigError,message):policy.normalize_plc_v1_snapshot({**snapshot,field:value})
        self.assertEqual(policy.normalize_plc_v1_snapshot({**snapshot,'d206_address':' 119d '})['d206_address'],'119D')

    def test_frame_bytes_and_blank_output(self):
        for version in (1,2):
            for passed in (False,True):
                snapshot=record(version,True)['config_snapshot'];before=copy.deepcopy(snapshot)
                method=policy.build_plc_v1_dispatch_plan if version==1 else policy.build_plc_dispatch_plan
                targets,frames=method(snapshot,passed)
                address=snapshot['d206_address'] if version==1 else protocol.logical_device_address(snapshot['result_register'])
                self.assertEqual(frames[0]['frame_hex'],protocol.build_d206_frame(address,passed,snapshot['checksum_mode']).hex().upper())
                self.assertEqual(snapshot,before);self.assertEqual(targets,['D206','Y04'])
                no_y={**snapshot,('write_y04' if version==1 else 'output_control_point'):(False if version==1 else '')}
                targets,frames=method(no_y,passed);self.assertEqual(targets,['D206']);self.assertEqual(len(frames),1)

    def test_version_and_field_error_precedence(self):
        for changes in ({'record_schema_version':True},{'record_schema_version':3},{'protocol_contract_version':1},
                        {'record_schema_version':None,'unexpected':1}):
            value=record();value.update(changes);self.reject(value,'dispatch_migration_required')
        self.corrupt({'z_unknown':1,'a_unknown':2},'unknown_field:a_unknown')
        self.corrupt({'effective_enabled':True},'response_only_field:effective_enabled')
        value=record();del value['passed'];self.reject(value,'corrupt_persisted_dispatch:required_field_missing')

    def test_strict_types_and_id_binding(self):
        for changes,reason in [({'passed':1},'passed_invalid'),({'source':' camera'},'identity_type_invalid'),
             ({'enabled':1},'enabled_binding_invalid'),({'control_generation':True},'generation_invalid'),
             ({'state_version':True},'state_version_invalid'),({'dispatch_deadline_at_ms':99999},'dispatch_deadline_invalid'),
             ({'dispatch_id':'changed'},'identity_binding_invalid')]:self.corrupt(changes,reason)

    def test_snapshot_and_plan_binding(self):
        self.corrupt({'config_snapshot':None},'snapshot_invalid')
        value=record();value['config_snapshot']['serial_port']=' COM3 '
        self.reject(value,'corrupt_persisted_dispatch:snapshot_not_canonical')
        self.corrupt({'protocol':'changed'},'plan_binding_invalid')
        value=record();value['planned_frames'][0]['frame_hex']='0203'
        self.reject(value,'corrupt_persisted_dispatch:plan_binding_invalid')

    def test_event_and_projection_error_precedence(self):
        value=record();value['events']=None;self.reject(value,'dispatch_migration_required')
        value=record();value['events'][0]['seq']=True;self.reject(value,'corrupt_persisted_dispatch:create_event_invalid')
        self.corrupt({'state_version':2},'state_version_event_count_mismatch')
        self.corrupt({'duplicate':True},'persisted_duplicate_flag_invalid')
        self.corrupt({'created_at':101},'created_at_event_mismatch')
        self.corrupt({'status':'acknowledged'},'projection_mismatch:status')

    def test_actual_ack_and_uncertain_terminal_evidence(self):
        for result_code,phase,source in [('acknowledged','response','ack_byte'),('write_result_unknown','write','write_returned_none')]:
            value=record();target=value['planned_targets'][0];attempt=value['dispatch_id']+':'+target+':1'
            length=len(bytes.fromhex(value['planned_frames'][0]['frame_hex']))
            events=[dict(kind='create'),dict(kind='attempting'),dict(kind='start_attempt',target=target,attempt_id=attempt),
                dict(kind='advance_attempt',attempt_id=attempt,bytes_written=0,physical_status='write_call_started',outcome='write_outcome_uncertain')]
            if result_code=='acknowledged':events.append(dict(kind='advance_attempt',attempt_id=attempt,bytes_written=length,physical_status='full_frame_written',outcome='awaiting_acknowledgement'))
            events.extend([dict(kind='finish_attempt',attempt_id=attempt,bytes_written=length if result_code=='acknowledged' else 0,
                               result_code=result_code,result_phase=phase,diagnostic_source=source),dict(kind='finalize',reason='')])
            events=[dict(seq=i+1,at=100+i,**row) for i,row in enumerate(events)]
            projected=event_projection.project_plc_dispatch_events(value,events);projected['state_version']=len(events)
            self.verify(projected)
            self.assertEqual(projected['status'],'acknowledged' if result_code=='acknowledged' else 'failed')
            if result_code!='acknowledged':self.assertEqual(projected['outcome'],'write_outcome_uncertain')

    @unittest.skipIf(BASELINE,'candidate direct import boundary')
    def test_lightweight_and_root_direct_aliases(self):
        code="import sys; from local_inspection_service.plc import persisted_validation; assert not any(n in sys.modules for n in ('local_inspection_service.server','fastapi','psycopg','serial'))"
        subprocess.run([sys.executable,'-c',code],cwd=ROOT,check=True,timeout=10)
        tree=ast.parse(read_checked_application_source(ROOT / 'local_inspection_service/server.py', encoding='utf8'))
        imports=[n for n in tree.body if isinstance(n,ast.ImportFrom) and n.level==1 and n.module=='plc.persisted_validation']
        self.assertEqual(len(imports),1);self.assertEqual({a.name for a in imports[0].names if a.asname is None},NAMES)
        self.assertFalse(any(isinstance(n,ast.FunctionDef) and n.name in NAMES for n in tree.body))


if __name__=='__main__':unittest.main()
