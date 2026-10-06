"""Synthetic batch state, identity and ordered effects against the unchanged parent."""
import ast
from contextvars import ContextVar, copy_context
from dataclasses import fields
import os
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
from typing import Any
import unittest
from unittest.mock import Mock, patch
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from auto_optimization_test_ports import test_capability, assert_capability_owner
BASELINE=os.environ.get('VANTALINE_AUTO_SYNTHETIC_BATCH_BASELINE_SOURCE')
NAME='auto_optimize_generate_synthetic_batch_for_sample'

def create(bindings):
    if BASELINE:
        nodes=[n for n in ast.parse(Path(BASELINE).read_text(encoding='utf-8-sig')).body if isinstance(n,ast.FunctionDef) and n.name==NAME];assert len(nodes)==1
        ns=dict(bindings,Any=Any,time=time,np=np)
        exec(compile(ast.Module(body=nodes,type_ignores=[]),BASELINE,'exec'),ns)
        return ns[NAME],ns
    from local_inspection_service.training.auto_optimization_synthetic_batch import AutoOptimizationSyntheticBatch
    from local_inspection_service.training.auto_optimization_synthetic_batch_ports import SyntheticBatchConfiguration,SyntheticBatchSprites,SyntheticBatchPublication
    def ports(cls):return cls(**{f.name:test_capability(bindings, f.name) for f in fields(cls)})
    return getattr(AutoOptimizationSyntheticBatch(ports(SyntheticBatchConfiguration),ports(SyntheticBatchSprites),ports(SyntheticBatchPublication)),NAME),bindings

class BatchContract(unittest.TestCase):
    def fixture(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);root=Path(tmp.name);events=[];renders=[];identity=ContextVar('synthetic-user',default=None)
        def scope(config,user):events.append(('scope',config,user));return config
        def backfill(task,state,sample):events.append(('backfill',task));sample['backfilled']=True;return 1
        def render(**kwargs):renders.append(kwargs);return {'image':str(kwargs['output_path']),'labels':str(kwargs['label_path'])}
        bindings={'safe_background_set_id':lambda x:str(x),'default_auto_optimize_settings':lambda:{'count':2},
          'auto_optimize_positive_derivatives_per_real_image':lambda s:s['count'],
          'AUTO_OPTIMIZE_SYNTHETIC_SIZE_POLICY':'fixed','_request_user':identity,'LEGACY_OWNER_ID':'legacy',
          'scope_config_for_user':scope,'load_config':lambda:{'config':'source'},'accessory_lookup_by_id':lambda c:{'a':{'name':'A'}},
          'auto_optimize_backfill_missing_sprites_for_sample':backfill,'auto_optimize_sprite_records_for_sample':lambda s:[{'accessory_id':'a'}],
          'auto_optimize_canonical_sprite_sizes':lambda state,extra_sprites=None:{'a':{'width':20,'height':30}},
          'safe_record_id':lambda x:x.replace('/','_'),'output_write_dir_for_owner':lambda category,owner:root/category/owner,
          'auto_optimize_render_synthetic_sample':render}
        call,bindings=create(bindings)
        return SimpleNamespace(root=root,events=events,renders=renders,identity=identity,call=call,bindings=bindings,
          state={'selected_accessory_ids':['a'],'owner_user_id':'owner','owner_username':'Owner'},sample={'label_status':'trainable','sample_id':'s/1','record_id':'record'})

    def test_nontrainable_no_capability_or_state_access(self):
        f=self.fixture();f.bindings['safe_background_set_id']=Mock(side_effect=AssertionError('unexpected'))
        for sample in (None,{},[],{'label_status':'review'}):self.assertEqual(f.call('t',None,sample),[])
        f.bindings['safe_background_set_id'].assert_not_called()

    def test_zero_count_completes_and_clock_failure_keeps_earlier_fields(self):
        f=self.fixture();f.state['settings']={'count':0};f.sample.update(synthetic_samples=['old'],synthetic_count=99,synthetic_error='old')
        with patch.object(time,'time',return_value=17.9):self.assertEqual(f.call('t',f.state,f.sample),[])
        self.assertEqual(f.sample['synthetic_completed_at'],17);self.assertEqual(f.sample['synthetic_status'],'completed');self.assertNotIn('synthetic_error',f.sample);self.assertEqual(f.events,[])
        f.sample['synthetic_error']='keep'
        with patch.object(time,'time',side_effect=OSError('clock')):
            with self.assertRaises(OSError):f.call('t',f.state,f.sample)
        self.assertEqual(f.sample['synthetic_samples'],[]);self.assertEqual(f.sample['synthetic_status'],'completed');self.assertEqual(f.sample['synthetic_error'],'keep')

    def test_completed_reuse_retains_record_identity_and_legacy_background(self):
        f=self.fixture();items=[{'image':'i','labels':'l','target_size_policy':'fixed','augmentation':{'background_set_id':'green_conveyor'}} for _ in range(2)]
        f.sample.update(synthetic_samples=items,synthetic_status='completed')
        result=f.call('t',f.state,f.sample);self.assertIs(result[0],items[0]);self.assertIsNot(result,items);self.assertEqual(f.events,[]);self.assertEqual(f.renders,[])
        items[0]['target_size_policy']='old';f.call('t',f.state,f.sample);self.assertEqual(len(f.renders),2)

    def test_missing_selection_and_missing_sprites_error_boundaries(self):
        f=self.fixture();f.state['selected_accessory_ids']=[]
        self.assertEqual(f.call('t',f.state,f.sample),[]);self.assertEqual(f.sample['synthetic_error'],'missing_selected_accessory_ids');self.assertEqual(f.events,[])
        f.sample['labels']=[{'accessory_id':'b'},{'accessory_id':'a'}];f.bindings['auto_optimize_sprite_records_for_sample']=lambda s:[]
        self.assertEqual(f.call('t',f.state,f.sample),[]);self.assertTrue(f.sample['backfilled']);self.assertEqual(f.sample['synthetic_error'],'no_trainable_ai_mask_sprites');self.assertNotIn('synthetic_started_at',f.sample)

    def test_success_paths_variant_index_clock_seed_and_same_rng(self):
        f=self.fixture();f.sample['synthetic_error']='old';rng=object();factory=Mock(return_value=rng)
        with patch.object(time,'time',return_value=10.5),patch.object(np.random,'default_rng',factory):result=f.call('t/x',f.state,f.sample)
        factory.assert_called_once_with(10500 ^ abs(hash('s_1')) % (2**31))
        self.assertEqual([r['variant_index'] for r in result],[0,1]);self.assertIs(result,f.sample['synthetic_samples']);self.assertEqual(f.sample['synthetic_count'],2);self.assertEqual(f.sample['synthetic_status'],'completed');self.assertNotIn('synthetic_error',f.sample)
        for idx,kwargs in enumerate(f.renders):
            self.assertIs(kwargs['rng'],rng);self.assertEqual(kwargs['class_index'],{'a':0});self.assertEqual(kwargs['split'],'train');self.assertEqual(kwargs['output_path'],f.root/'auto_optimize_synthetic/owner/t_x/s_1/images'/f'synthetic_{idx+1:04d}.png')
        self.assertEqual(result[0]['source_sample_id'],'s/1');self.assertEqual(result[0]['created_at'],10)

    def test_none_results_keep_original_variant_indices_and_all_none_failure(self):
        f=self.fixture();f.bindings['auto_optimize_render_synthetic_sample']=Mock(side_effect=[None,{'image':'second','labels':'l'}])
        result=f.call('t',f.state,f.sample);self.assertEqual(result[0]['variant_index'],1);self.assertEqual(f.sample['synthetic_count'],1)
        f.bindings['auto_optimize_render_synthetic_sample']=lambda **k:None
        self.assertEqual(f.call('t',f.state,f.sample),[]);self.assertEqual(f.sample['synthetic_status'],'failed');self.assertEqual(f.sample['synthetic_error'],'synthetic_render_failed')

    def test_second_render_failure_retains_partial_count_and_old_list(self):
        f=self.fixture();old=[{'previous':True}];first={'image':'i','labels':'l'};f.sample.update(synthetic_samples=old,synthetic_error='old')
        f.bindings['auto_optimize_render_synthetic_sample']=Mock(side_effect=[first,OSError('second')])
        with self.assertRaises(OSError):f.call('t',f.state,f.sample)
        self.assertIs(f.sample['synthetic_samples'],old);self.assertEqual(f.sample['synthetic_count'],1);self.assertEqual(f.sample['synthetic_status'],'running');self.assertEqual(f.sample['synthetic_error'],'old');self.assertEqual(first['variant_index'],0);self.assertNotIn('synthetic_completed_at',f.sample)

    def test_request_contexts_and_legacy_owner_fallback(self):
        f=self.fixture();contexts=[copy_context(),copy_context()]
        for ctx,name in zip(contexts,('alice','bob')):
            ctx.run(f.identity.set,{'id':name});ctx.run(f.call,'t',f.state,dict(f.sample))
        users=[e[2] for e in f.events if e[0]=='scope'];self.assertEqual([u['id'] for u in users],['alice','bob']);self.assertIsNone(f.identity.get())
        f.state.pop('owner_user_id');f.state.pop('owner_username');f.call('t',f.state,dict(f.sample));self.assertEqual([e[2] for e in f.events if e[0]=='scope'][-1],{'id':'legacy','username':'legacy','role':'admin'})

    def test_scope_callback_selection_precedes_load_side_effect(self):
        f=self.fixture();old=f.bindings['scope_config_for_user'];late=Mock(side_effect=AssertionError('too late'))
        def load():f.bindings['scope_config_for_user']=late;return {'loaded':True}
        f.bindings['load_config']=load;f.call('t',f.state,f.sample);late.assert_not_called();self.assertEqual(f.events[0][1],{'loaded':True})

    @unittest.skipIf(BASELINE,'candidate-only assembly')
    def test_actual_root_getters_and_forwarding(self):
        from scripts.verify_backend_contract import capture
        capture()
        from local_inspection_service import server
        service=server._auto_optimization_synthetic_batch
        for group in (service.configuration,service.sprites,service.publication):
            for f in fields(group):assert_capability_owner(self, group, f.name, server)
        mock=Mock(return_value=object());args=('task',{}, {})
        with patch.object(server,'_auto_optimization_synthetic_batch',SimpleNamespace(**{NAME:mock})):self.assertIs(getattr(server,NAME)(*args),mock.return_value)
        mock.assert_called_once_with(*args)

if __name__=='__main__':unittest.main()
