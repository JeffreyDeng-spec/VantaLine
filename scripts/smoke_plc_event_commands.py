"""Historical typed-event construction, using only synthetic evidence and a clock."""
import ast
import copy
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any, Callable
import types
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from smoke_plc_event_projection import record, stream, ack_items, event_stream
from local_inspection_service.plc.event_projection import project_plc_dispatch_events
from local_inspection_service.plc.errors import PlcDispatchStateConflict
from local_inspection_service.plc.transition_policy import PlcDispatchTransitionKind
from local_inspection_service.plc_fx_ascii import plc_terminal_result_is_retryable

NAMES={'append_plc_typed_event','_derive_plc_attempting','_derive_plc_start_attempt',
       '_derive_plc_advance_attempt','_derive_plc_finish_attempt','_derive_plc_deadline',
       '_derive_plc_finalize','_PLC_TYPED_EVENT_DERIVERS','_PLC_TYPED_EVENT_FIELDS'}
BASELINE=os.environ.get('VANTALINE_PLC_COMMAND_BASELINE_SOURCE')
if BASELINE:
    source=Path(BASELINE).read_text(encoding='utf-8-sig')
    nodes=[n for n in ast.parse(source).body if
        (isinstance(n,ast.FunctionDef) and n.name in NAMES) or
        (isinstance(n,ast.AnnAssign) and isinstance(n.target,ast.Name) and n.target.id in NAMES)]
    assert len(nodes)==len(NAMES)
    commands=types.ModuleType('baseline_commands')
    commands.__dict__.update(Any=Any,Callable=Callable,time=time,
        PlcDispatchStateConflict=PlcDispatchStateConflict,PlcDispatchTransitionKind=PlcDispatchTransitionKind,
        project_plc_dispatch_events=project_plc_dispatch_events,
        plc_terminal_result_is_retryable=plc_terminal_result_is_retryable)
    exec(compile(ast.Module(body=nodes,type_ignores=[]),BASELINE,'exec'),commands.__dict__)
else:
    from local_inspection_service.plc import event_commands as commands


class CommandContract(unittest.TestCase):
    def queued(self,targets=('D206',),retries=0):
        return project_plc_dispatch_events(record(targets,retries),event_stream([{'kind':'create'}]))

    def derive(self,name,before,payload):
        saved=copy.deepcopy((before,payload))
        try:
            with patch.object(commands.time,'time',return_value=9999.75):
                return getattr(commands,name)(before,payload)
        finally:self.assertEqual((before,payload),saved)

    def reject(self,name,before,payload,reason):
        with self.assertRaises(PlcDispatchStateConflict) as caught:self.derive(name,before,payload)
        self.assertEqual(caught.exception.reason,reason)
        self.assertEqual(caught.exception.authoritative,before)

    def test_append_preserves_original_shallow_copy_and_payload_override(self):
        nested=['saved'];before={'events':[{'seq':9,'nested':nested},'ignored']}
        with patch.object(commands.time,'time',return_value=10.75):
            rows=commands.append_plc_typed_event(before,'deadline',at=20,seq=30)
        self.assertEqual(rows[-1],{'seq':30,'kind':'deadline','at':20})
        self.assertIsNot(rows[0],before['events'][0]);self.assertIs(rows[0]['nested'],nested)
        self.assertEqual(before['events'][0]['seq'],9)

    def test_actual_ack_chain_and_input_immutability(self):
        value=self.derive('_derive_plc_attempting',self.queued(),{})
        for payload in ack_items():
            item=dict(payload);kind=item.pop('kind')
            if kind!='start_attempt':item.pop('target',None)
            if kind=='start_attempt':item.pop('attempt_id')
            value=self.derive('_derive_plc_'+kind,value,item)
        value=self.derive('_derive_plc_finalize',value,{'reason':''})
        self.assertEqual(value['status'],'acknowledged');self.assertEqual(value['targets'],['D206'])
        self.assertEqual(value['events'][-1]['at'],9999);self.assertTrue(value['worker_done'])

    def test_attempting_requires_queue_and_start_requires_plan_order(self):
        self.reject('_derive_plc_attempting',{'status':'failed'},{},'attempting_requires_queued')
        before=self.derive('_derive_plc_attempting',self.queued(('D206','Y04')), {})
        self.reject('_derive_plc_start_attempt',before,{'target':'Y04'},'attempt_target_out_of_plan_or_order')
        bad={**before,'planned_frames':[]}
        self.reject('_derive_plc_start_attempt',bad,{'target':'D206'},'attempt_frame_does_not_match_plan')

    def test_start_attempt_rejects_budget_unfinished_ack_and_uncertain_retry(self):
        before=self.derive('_derive_plc_attempting',self.queued(retries=1),{})
        operation={'target':'D206','finished_at':10,'outcome':'not_written','result_code':'write_result_unknown','result_phase':'write'}
        self.reject('_derive_plc_start_attempt',{**before,'operations':[operation]*2},{'target':'D206'},'attempt_retry_budget_exceeded')
        self.reject('_derive_plc_start_attempt',{**before,'operations':[{**operation,'finished_at':None}]},{'target':'D206'},'previous_attempt_not_finished')
        self.reject('_derive_plc_start_attempt',{**before,'operations':[{**operation,'outcome':'acknowledged'}]},{'target':'D206'},'acknowledged_target_cannot_retry')
        self.reject('_derive_plc_start_attempt',{**before,'operations':[operation]},{'target':'D206'},'previous_attempt_result_is_not_retryable')

    def test_advance_rejects_wrong_identity_bytes_and_combinations(self):
        started=project_plc_dispatch_events(record(),stream(ack_items()[0]))
        payload=dict(attempt_id='dispatch:D206:1',bytes_written=0,physical_status='write_call_started',outcome='write_outcome_uncertain')
        self.reject('_derive_plc_advance_attempt',started,{**payload,'attempt_id':'other'},'advance_attempt_requires_started_operation')
        for value in (-1,3,True,'1'):
            self.reject('_derive_plc_advance_attempt',started,{**payload,'bytes_written':value},'advance_attempt_bytes_written_invalid')
        self.reject('_derive_plc_advance_attempt',started,{**payload,'outcome':'acknowledged'},'advance_attempt_evidence_combination_invalid')
        result=self.derive('_derive_plc_advance_attempt',started,payload)
        self.assertEqual(result['operations'][0]['outcome'],'write_outcome_uncertain')

    def test_finish_requires_matching_persisted_bytes(self):
        started=project_plc_dispatch_events(record(),stream(ack_items()[0]))
        payload=dict(attempt_id='dispatch:D206:1',bytes_written=2,result_code='acknowledged',result_phase='response',diagnostic_source='ack_byte')
        self.reject('_derive_plc_finish_attempt',started,payload,'finish_attempt_bytes_do_not_match_authoritative_operation')
        self.reject('_derive_plc_finish_attempt',started,{**payload,'attempt_id':'other'},'finish_attempt_requires_started_operation')

    def test_deadline_and_finalize_do_not_invent_acknowledgement(self):
        started=project_plc_dispatch_events(record(),stream(*ack_items()[:2]))
        deadline=self.derive('_derive_plc_deadline',started,{})
        self.assertTrue(deadline['deadline_exceeded']);self.assertNotEqual(deadline['status'],'acknowledged')
        self.reject('_derive_plc_finalize',deadline,{'reason':''},'corrupt_persisted_dispatch:finalize_event_invalid')
        self.assertEqual(deadline['operations'][0]['outcome'],'write_outcome_uncertain')

    def test_missing_payload_keeps_original_key_error(self):
        for name in ('_derive_plc_start_attempt','_derive_plc_advance_attempt','_derive_plc_finish_attempt','_derive_plc_finalize'):
            with self.assertRaises(KeyError):self.derive(name,self.queued(),{})

    def test_handler_tables_retain_actual_callable_identity(self):
        mapping={'DISPATCH_TRANSITION':'attempting','START_ATTEMPT':'start_attempt',
                 'ADVANCE_ATTEMPT':'advance_attempt','FINISH_ATTEMPT':'finish_attempt',
                 'DEADLINE':'deadline','FINALIZE':'finalize','AUDIT_FAILURE_FINALIZE':'finalize'}
        self.assertEqual(len(commands._PLC_TYPED_EVENT_DERIVERS),len(mapping))
        for kind,name in mapping.items():
            key=getattr(PlcDispatchTransitionKind,kind)
            self.assertIs(commands._PLC_TYPED_EVENT_DERIVERS[key],getattr(commands,'_derive_plc_'+name))
            self.assertIsInstance(commands._PLC_TYPED_EVENT_FIELDS[key],frozenset)

    @unittest.skipIf(BASELINE,'module import is candidate-only')
    def test_lightweight_import(self):
        code="import sys; import local_inspection_service.plc.event_commands; assert not any(n in sys.modules for n in ('local_inspection_service.server','fastapi','psycopg','serial'))"
        subprocess.run([sys.executable,'-c',code],cwd=ROOT,check=True)

if __name__=='__main__':unittest.main()
