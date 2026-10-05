"""Historical PLC record mutation contracts; synthetic storage, no physical I/O."""
import ast
import copy
from dataclasses import fields
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace
from typing import Any
import unittest
from unittest.mock import Mock,patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from local_inspection_service import plc_fx_ascii as fx
from local_inspection_service.plc.errors import PlcDispatchStateConflict
from local_inspection_service.plc.transition_policy import PlcDispatchTransitionKind as Kind
BASELINE=os.environ.get('VANTALINE_PLC_DISPATCH_MUTATIONS_BASELINE_SOURCE')
NAMES=('create_plc_dispatch','_apply_plc_dispatch_event','plc_transition_attempting','plc_start_attempt','plc_advance_attempt','plc_finish_attempt','plc_mark_deadline','plc_finalize_dispatch','plc_cancel_dispatch','persist_plc_dispatch_record')
ORIGINAL_DOCSTRINGS={'create_plc_dispatch':'Atomically derive a queued v1 record from the authoritative PLC namespace.','persist_plc_dispatch_record':'Retired raw compatibility shim; all creates and mutations use typed handlers.'}


def create(bindings):
    if BASELINE:
        nodes=[n for n in ast.parse(Path(BASELINE).read_text(encoding='utf-8-sig')).body if isinstance(n,ast.FunctionDef) and n.name in NAMES];assert len(nodes)==10
        bindings.update(Any=Any,hashlib=hashlib,json=json,time=time);exec(compile(ast.Module(body=nodes,type_ignores=[]),BASELINE,'exec'),bindings)
        return SimpleNamespace(**{n:bindings[n] for n in NAMES}),bindings
    from local_inspection_service.plc.dispatch_mutations import PlcDispatchMutations
    from local_inspection_service.plc.dispatch_mutation_ports import DispatchMutationStorage,DispatchMutationPolicy,DispatchMutationEvents,DispatchMutationEvidence
    def ports(cls):return cls(**{f.name:lambda name=f.name:bindings[name] for f in fields(cls)})
    service=PlcDispatchMutations(ports(DispatchMutationStorage),ports(DispatchMutationPolicy),ports(DispatchMutationEvents),ports(DispatchMutationEvidence));bindings.update({n:getattr(service,n) for n in NAMES});return service,bindings


class DispatchMutationContract(unittest.TestCase):
    def fixture(self):
        config={'generation':3,'plc':{'enabled':True,'protocol':'synthetic','checksum_mode':'synthetic'},'plc_dispatches':[]};events=[]
        def mutate(fn):
            events.append('begin');candidate=copy.deepcopy(config);fn(candidate);config.clear();config.update(candidate);events.append('commit')
        bindings={'runtime_postgres_repository_or_none':lambda:None,'mutate_app_config_atomically':mutate,'plc_dispatch_audit_records':lambda c:c.get('plc_dispatches',[]),'verify_persisted_plc_dispatch':lambda r:r,'raw_plc_namespace':lambda c:c.get('plc',fx.PLC_CONFIG_ABSENT),'plc_pg_coordination_available':Mock(return_value=True),'public_path_sanitized':lambda v:v,'plc_dispatch_existing':lambda i:next((r for r in config['plc_dispatches'] if r['dispatch_id']==i),None),
                  'PlcDispatchStateConflict':PlcDispatchStateConflict,'PLC_CONFIG_ABSENT':fx.PLC_CONFIG_ABSENT,'normalize_plc_config':lambda v:v,'PlcConfigError':fx.PlcConfigError,'PLC_CONTROL_GENERATION_KEY':'generation','build_plc_dispatch_plan':lambda c,p:(['D'],[{'target':'D'}]),'PLC_RECORD_SCHEMA_VERSION':1,'PLC_PROTOCOL_CONTRACT_VERSION':2,'PLC_QUEUE_WAIT_SECONDS':10.0,'PLC_FINALIZE_REASONS':{'','cancelled_after_disable','cancelled_after_config_change','audit_persist_failed_after_ack'},
                  'project_plc_dispatch_events':lambda r,e:{**r,'events':e,'status':'queued'},'PlcDispatchTransitionKind':Kind,'_PLC_TYPED_EVENT_DERIVERS':{Kind.DISPATCH_TRANSITION:lambda r,p:{**r,'status':'attempting'}},'_PLC_TYPED_EVENT_FIELDS':{Kind.DISPATCH_TRANSITION:frozenset()},'validate_plc_dispatch_transition':Mock(),
                  'PlcAttemptTerminalResult':fx.PlcAttemptTerminalResult,'PlcTerminalResultCode':fx.PlcTerminalResultCode,'PLC_TERMINAL_RESULT_CODES':fx.PLC_TERMINAL_RESULT_CODES,'PlcTransportPhase':fx.PlcTransportPhase,'PLC_TERMINAL_ALLOWED_PHASES':fx.PLC_TERMINAL_ALLOWED_PHASES,'PLC_TERMINAL_DIAGNOSTIC_SOURCES':fx.PLC_TERMINAL_DIAGNOSTIC_SOURCES}
        service,bindings=create(bindings);return SimpleNamespace(s=service,b=bindings,config=config,events=events)

    def create_record(self,f,**overrides):
        args={'source':' camera ','request_id':'request','passed':True,'fingerprint':'digest','expected_generation':3};args.update(overrides)
        with patch.object(time,'time',side_effect=[100.9,101.1]):return f.s.create_plc_dispatch(**args)

    def test_create_metadata_identity_duplicate_and_collision(self):
        f=self.fixture();row=self.create_record(f);material=json.dumps({'source':'camera','request_id':'request','fingerprint':'digest'},sort_keys=True,ensure_ascii=True)
        self.assertEqual(row['dispatch_id'],hashlib.sha256(material.encode()).hexdigest()[:24]);self.assertEqual(row['created_at'],100);self.assertEqual(row['dispatch_deadline_at_ms'],111100);self.assertEqual(row['state_version'],1);self.assertEqual(row['events'],[{'seq':1,'kind':'create','at':100}]);self.assertEqual(f.events,['begin','commit'])
        f.config['generation']=4;f.config['plc']['enabled']=False
        duplicate=self.create_record(f);self.assertEqual(duplicate,row);self.assertEqual(len(f.config['plc_dispatches']),1)
        with self.assertRaises(PlcDispatchStateConflict) as caught:self.create_record(f,passed=False)
        self.assertEqual(caught.exception.reason,'create_dispatch_identity_conflict');self.assertEqual(caught.exception.authoritative,row)

    def test_create_input_failures_before_transaction(self):
        cases=[({'source':' '},'create_source_required'),({'request_id':1},'create_request_id_must_be_string'),({'passed':1},'create_passed_must_be_boolean'),({'fingerprint':''},'create_fingerprint_required'),({'expected_generation':True},'create_expected_generation_invalid'),({'expected_generation':-1},'create_expected_generation_invalid')]
        for change,reason in cases:
            f=self.fixture()
            with self.assertRaises(PlcDispatchStateConflict) as caught:self.create_record(f,**change)
            self.assertEqual(caught.exception.reason,reason);self.assertEqual(f.events,[])

    def test_authoritative_generation_namespace_and_falsey_repository(self):
        for change,reason in [('missing','create_plc_namespace_absent'),('disabled','create_plc_disabled'),('generation','create_generation_mismatch'),('repository','plc_pg_coordination_unavailable')]:
            f=self.fixture()
            if change=='missing':f.config.pop('plc')
            elif change=='disabled':f.config['plc']['enabled']=False
            elif change=='generation':f.config['generation']=4
            else:f.b['runtime_postgres_repository_or_none']=lambda:False;f.b['plc_pg_coordination_available'].return_value=False
            with self.assertRaises(PlcDispatchStateConflict) as caught:self.create_record(f)
            self.assertEqual(caught.exception.reason,reason);self.assertEqual(f.config['plc_dispatches'],[]);self.assertEqual(f.events,['begin'])
        f=self.fixture();error=fx.PlcConfigError('invalid');f.b['normalize_plc_config']=Mock(side_effect=error)
        with self.assertRaises(PlcDispatchStateConflict) as caught:self.create_record(f)
        self.assertIs(caught.exception.__cause__,error)

    def test_cas_transition_copy_validation_and_deduplication(self):
        f=self.fixture();row=self.create_record(f);identifier=row['dispatch_id'];other={'dispatch_id':'other','state_version':1};f.config['plc_dispatches']=[dict(row,state_version=0),other,row]
        result=f.s._apply_plc_dispatch_event(identifier,expected_version=1,transition_kind=Kind.DISPATCH_TRANSITION,event_payload={})
        self.assertEqual(result['state_version'],2);self.assertEqual(result['status'],'attempting');self.assertEqual([r['dispatch_id'] for r in f.config['plc_dispatches']],['other',identifier]);self.assertEqual(row['state_version'],1)
        validator=f.b['validate_plc_dispatch_transition'];validator.assert_called_once();self.assertEqual(validator.call_args.kwargs,{'transition_kind':Kind.DISPATCH_TRANSITION})
        with self.assertRaises(PlcDispatchStateConflict) as caught:f.s._apply_plc_dispatch_event(identifier,expected_version=1,transition_kind=Kind.DISPATCH_TRANSITION,event_payload={})
        self.assertTrue(caught.exception.reason.startswith('state_version_mismatch:'));self.assertEqual(caught.exception.authoritative,result)

    def test_payload_priority_missing_rows_and_atomic_failure(self):
        f=self.fixture()
        with self.assertRaises(PlcDispatchStateConflict) as caught:f.s._apply_plc_dispatch_event('x',expected_version=0,transition_kind='invalid',event_payload={})
        self.assertEqual(caught.exception.reason,'unknown_transition_kind');self.assertEqual(f.events,[])
        f.b['_PLC_TYPED_EVENT_FIELDS'][Kind.DISPATCH_TRANSITION]=frozenset({'required'})
        for payload,reason in [({'extra':1},'transition_payload_extra_field:extra'),({},'transition_payload_missing_field:required')]:
            with self.assertRaises(PlcDispatchStateConflict) as caught:f.s._apply_plc_dispatch_event('x',expected_version=0,transition_kind=Kind.DISPATCH_TRANSITION,event_payload=payload)
            self.assertEqual(caught.exception.reason,reason)
        f.b['_PLC_TYPED_EVENT_FIELDS'][Kind.DISPATCH_TRANSITION]=frozenset()
        with self.assertRaises(PlcDispatchStateConflict) as caught:f.s._apply_plc_dispatch_event('missing',expected_version=0,transition_kind=Kind.DISPATCH_TRANSITION,event_payload={})
        self.assertEqual(caught.exception.reason,'transition_requires_existing_dispatch')
        row=self.create_record(f);before=copy.deepcopy(f.config);failure=RuntimeError('validation');f.b['validate_plc_dispatch_transition']=Mock(side_effect=failure)
        with self.assertRaises(RuntimeError) as caught:f.s._apply_plc_dispatch_event(row['dispatch_id'],expected_version=1,transition_kind=Kind.DISPATCH_TRANSITION,event_payload={})
        self.assertIs(caught.exception,failure);self.assertEqual(f.config,before)

    def test_public_typed_payload_and_retired_raw_boundary(self):
        f=self.fixture();apply=Mock(return_value={'synthetic':True});f.b['_apply_plc_dispatch_event']=apply
        f.s.plc_transition_attempting('x',expected_version=2);self.assertEqual(apply.call_args.kwargs['event_payload'],{})
        f.s.plc_start_attempt('x',expected_version=2,target='D');self.assertEqual(apply.call_args.kwargs['event_payload'],{'target':'D'})
        f.s.plc_advance_attempt('x',expected_version=2,attempt_id='attempt',bytes_written=1,physical_status='partial_write',outcome='outcome_uncertain');self.assertEqual(apply.call_args.kwargs['event_payload']['bytes_written'],1)
        f.s.plc_mark_deadline('x',expected_version=2);self.assertEqual(apply.call_args.kwargs['transition_kind'],Kind.DEADLINE)
        f.s.plc_finalize_dispatch('x',expected_version=2,reason='audit_persist_failed_after_ack');self.assertEqual(apply.call_args.kwargs['transition_kind'],Kind.AUDIT_FAILURE_FINALIZE)
        f.s.plc_cancel_dispatch('x',expected_version=2,reason='cancelled_after_disable');self.assertEqual(apply.call_args.kwargs['event_payload'],{'reason':'cancelled_after_disable'})
        with self.assertRaises(PlcDispatchStateConflict):f.s.plc_finish_attempt('x',expected_version=2,attempt_id='attempt',terminal_result=object())
        with self.assertRaises(PlcDispatchStateConflict) as caught:f.s.persist_plc_dispatch_record({'dispatch_id':'x'},transition_kind='unknown')
        self.assertEqual(caught.exception.reason,'public_raw_transition_kind_not_allowed')

    def test_late_transaction_callbacks_and_deriver_capture(self):
        f=self.fixture();original=f.b['mutate_app_config_atomically'];events=[]
        def mutate(callback):
            f.b['plc_dispatch_audit_records']=lambda config:events.append('new-reader') or config['plc_dispatches'];return original(callback)
        f.b['mutate_app_config_atomically']=mutate;row=self.create_record(f);self.assertEqual(events,['new-reader'])
        deriver=Mock(side_effect=lambda r,p:{**r,'status':'captured'});f.b['_PLC_TYPED_EVENT_DERIVERS'][Kind.DISPATCH_TRANSITION]=deriver
        def mutate_again(callback):f.b['_PLC_TYPED_EVENT_DERIVERS'][Kind.DISPATCH_TRANSITION]=Mock(side_effect=AssertionError('late deriver'));return original(callback)
        f.b['mutate_app_config_atomically']=mutate_again
        result=f.s._apply_plc_dispatch_event(row['dispatch_id'],expected_version=1,transition_kind=Kind.DISPATCH_TRANSITION,event_payload={})
        self.assertEqual(result['status'],'captured');deriver.assert_called_once()

    @unittest.skipIf(bool(BASELINE), 'candidate actual-root compatibility')
    def test_actual_root_existing_typed_storage_contracts(self):
        code = """from pathlib import Path
import os, shutil, tempfile
os.environ['VANTALINE_DATA_STORE'] = 'json'
from local_inspection_service.scripts import smoke_plc_phase1_hardening as existing
try:
    existing.server.plc_pg_coordination_available = lambda: True
    existing.test_strict_create_boundary_json()
    existing.test_actual_typed_handler_boundary_json_and_pg()
    print('PASS actual root strict-create and typed JSON/PG-substitute contracts')
finally:
    owned = existing.ROOT.resolve()
    assert owned.parent == Path(tempfile.gettempdir()).resolve()
    assert owned.name.startswith('vantaline_plc_hardening_')
    shutil.rmtree(owned)
"""
        subprocess.run([sys.executable, '-X', 'utf8', '-B', '-c', code], cwd=ROOT, check=True)

    @unittest.skipIf(bool(BASELINE),'candidate wiring only')
    def test_wiring_docs_and_light_import(self):
        tree=ast.parse((ROOT/'local_inspection_service/server.py').read_text(encoding='utf-8'));binding=next(n.value for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='_plc_dispatch_mutations' for t in n.targets));count=0
        for group in binding.keywords:
            for kw in group.value.keywords:self.assertIsInstance(kw.value,ast.Lambda);self.assertEqual(kw.arg,kw.value.body.id);count+=1
        self.assertEqual(count,31)
        for name in NAMES:
            node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name);doc=ast.get_docstring(node,clean=False);self.assertEqual(doc,ORIGINAL_DOCSTRINGS.get(name));body=node.body[1:] if doc is not None else node.body;self.assertEqual(len(body),1);self.assertIsInstance(body[0],ast.Return);self.assertEqual(body[0].value.func.attr,name)
        subprocess.run([sys.executable,'-B','-c','import sys; import local_inspection_service.plc.dispatch_mutations; assert "local_inspection_service.server" not in sys.modules'],cwd=ROOT,check=True)


if __name__=='__main__':unittest.main()
