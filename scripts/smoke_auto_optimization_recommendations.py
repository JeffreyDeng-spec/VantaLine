"""Synthetic rule/clamp/projection contract; never calls a model or starts training."""
import ast
import copy
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any
import types
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from local_inspection_service.training.auto_optimization_settings import AutoOptimizationSettings,normalize_expected_production_count
NAMES={'auto_optimize_complexity_rule_recommendation','clamp_auto_optimize_initialization_recommendation','public_auto_optimize_initialization_payload'}
BASELINE=os.environ.get('VANTALINE_AUTO_RECOMMENDATION_BASELINE_SOURCE')

def bounded(value,limit):return re.sub(r'\s+',' ',str(value or '')).strip()[:limit]

def create(calls):
    def lookup(config):calls.append(('lookup',config));return config
    def material(item):calls.append(('material',item));return item.get('material_type','object')
    def text(value,limit):calls.append(('text',value,limit));return bounded(value,limit)
    settings=AutoOptimizationSettings(3)
    if not BASELINE:
        from local_inspection_service.training.auto_optimization_recommendations import AutoOptimizationRecommendations
        return AutoOptimizationRecommendations(settings,lookup,material,lambda: text)
    nodes=[n for n in ast.parse(Path(BASELINE).read_text(encoding='utf-8-sig')).body if isinstance(n,ast.FunctionDef) and n.name in NAMES]
    assert len(nodes)==3
    policy=types.ModuleType('original_recommendations')
    policy.__dict__.update(Any=Any,AUTO_OPTIMIZE_NEGATIVES_PER_REAL_IMAGE=3,accessory_lookup_by_id=lookup,
        accessory_material_type=material,bounded_text=text,normalize_expected_production_count=normalize_expected_production_count,
        **{name:getattr(settings,name) for name in ('auto_optimize_training_requirements','auto_optimize_samples_per_real_image','auto_optimize_negative_samples_per_real_image','auto_optimize_positive_derivatives_per_real_image')})
    exec(compile(ast.Module(body=nodes,type_ignores=[]),BASELINE,'exec'),policy.__dict__)
    return policy


class RecommendationContract(unittest.TestCase):
    def setUp(self):
        self.env=patch.dict(os.environ,{},clear=True);self.env.start();self.addCleanup(self.env.stop)
        self.calls=[];self.policy=create(self.calls)

    def rule(self,config,ids,expected):
        before=copy.deepcopy((config,ids));result=self.policy.auto_optimize_complexity_rule_recommendation(config,ids,expected)
        self.assertEqual((config,ids),before);return result

    def test_complexity_reference_and_feasibility_boundaries(self):
        for count,kind,threshold,epochs,size in [(0,'simple',300,60,640),(2,'simple',300,60,640),(3,'medium',800,80,640),(7,'complex',1500,80,640)]:
            config={str(i):dict(source_files=['a','b','c']) for i in range(count)}
            result=self.rule(config,list(config),10000)
            self.assertEqual((result['complexity'],result['min_trainable_samples'],result['training_epochs'],result['training_image_size']),(kind,threshold,epochs,size))
            self.assertTrue(result['enabled']);self.assertTrue(result['auto_promote']);self.assertEqual(result['source'],'rules')
        config={'one':dict(material_type='text',source_files=[])}
        result=self.rule(config,['one'],2000)
        self.assertEqual(result['min_trainable_samples'],550);self.assertEqual(result['training_image_size'],768)
        self.assertFalse(self.rule(config,['one'],1833)['enabled']);self.assertTrue(self.rule(config,['one'],1834)['enabled'])

    def test_missing_and_duplicate_ids_keep_selection_semantics(self):
        config={'one':dict(source_files=['a','b','c'])}
        result=self.rule(config,['one','one','missing'],0)
        self.assertEqual(result['complexity'],'medium');self.assertEqual(result['min_trainable_samples'],800)
        self.assertFalse(result['enabled']);self.assertIn('未填写',result['reason'])
        self.assertEqual([x[0] for x in self.calls],['lookup','material','material'])
        with self.assertRaises(TypeError):self.rule({'bad':{'source_files':1}},['bad'],2000)

    def fallback(self):return self.rule({'a':{'source_files':['a','b','c']}},['a'],10000)

    def test_clamp_bounds_text_and_no_mutation(self):
        fallback=self.fallback();raw=dict(enabled=True,min_trainable_samples=1,min_positive_samples=1,min_negative_samples=-1,
            negative_samples_per_real_image=99,samples_per_real_image=99,training_epochs=999,training_image_size=9,
            max_label_jobs_per_cycle=99,shadow_min_samples=0,shadow_min_agreement=.1,complexity='  changed \n value ',reason='x'*300)
        saved=copy.deepcopy((raw,fallback))
        result=self.policy.clamp_auto_optimize_initialization_recommendation(raw,fallback,10000)
        expected=dict(min_trainable_samples=150,min_positive_samples=1,min_negative_samples=0,negative_samples_per_real_image=20,
            samples_per_real_image=50,training_epochs=500,training_image_size=320,max_label_jobs_per_cycle=20,shadow_min_samples=75,shadow_min_agreement=.8,complexity='changed value',source='gemini')
        for key,value in expected.items():self.assertEqual(result[key],value,key)
        self.assertEqual(len(result['reason']),240);self.assertEqual((raw,fallback),saved)

    def test_clamp_failure_precedence_and_infeasible_reason(self):
        fallback=self.fallback()
        result=self.policy.clamp_auto_optimize_initialization_recommendation({'enabled':True,'min_trainable_samples':'bad'},fallback,100)
        self.assertFalse(result['enabled']);self.assertIn('超过预计产量',result['reason'])
        result=self.policy.clamp_auto_optimize_initialization_recommendation({'enabled':True},fallback,500)
        self.assertIn('前 30%',result['reason'])
        with self.assertRaises(ValueError):self.policy.clamp_auto_optimize_initialization_recommendation({'samples_per_real_image':'bad'},fallback,10000)
        with self.assertRaises(KeyError):self.policy.clamp_auto_optimize_initialization_recommendation({}, {}, 10000)

    def test_public_payload_retains_unknown_fields_shallow_identity_and_reasons(self):
        for expected,enabled,fragment in [(0,False,'未填写'),(100,True,'超过预计产量'),(500,True,'超过前 30%'),(1000,True,'可开启'),(1000,False,'未由初始化')]:
            nested=['preserved'];state={'expected_production_count':expected,'auto_optimize_initialization':{'enabled':enabled,'nested':nested}}
            saved=copy.deepcopy(state)
            result=self.policy.public_auto_optimize_initialization_payload(state,{})
            self.assertEqual(result['min_trainable_samples'],200);self.assertEqual(result['samples_per_real_image'],12)
            self.assertEqual(result['positive_derivatives_per_real_image'],9);self.assertIn(fragment,result['reason'])
            self.assertEqual(state,saved);self.assertIs(result['nested'],nested)
        result=self.policy.public_auto_optimize_initialization_payload({'expected_production_count':0,'auto_optimize_initialization':{'expected_production_count':1000}}, {})
        self.assertEqual(result['expected_production_count'],1000)

    def test_public_payload_preserves_dynamic_settings_error(self):
        os.environ['VANTALINE_AUTO_OPT_EPOCHS']='bad'
        with self.assertRaises(ValueError):self.policy.public_auto_optimize_initialization_payload({}, {})

    def test_actual_root_text_callee_is_selected_before_argument_evaluation(self):
        # Execute the original definition or the actual composition plus wrapper.
        # A mutable mapping makes Python's callee-before-arguments order observable.
        source=Path(BASELINE) if BASELINE else ROOT/'local_inspection_service/server.py'
        tree=ast.parse(source.read_text(encoding='utf-8-sig'))
        name='clamp_auto_optimize_initialization_recommendation'
        nodes=[node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name==name]
        namespace=dict(Any=Any,AUTO_OPTIMIZE_NEGATIVES_PER_REAL_IMAGE=3,
            _auto_optimization_settings=AutoOptimizationSettings(3),
            accessory_lookup_by_id=lambda config:config,
            accessory_material_type=lambda item:'object')
        if not BASELINE:
            import copy
            from types import SimpleNamespace
            from local_inspection_service.training.auto_optimization_recommendations import AutoOptimizationRecommendations
            namespace['AutoOptimizationRecommendations']=AutoOptimizationRecommendations
            namespace['_auto_optimization_core']=SimpleNamespace(settings=namespace['_auto_optimization_settings'])
            core_call=next(node.value for node in tree.body if isinstance(node,ast.Assign) and any(isinstance(target,ast.Name) and target.id=='_auto_optimization_core' for target in node.targets))
            if isinstance(core_call,ast.Attribute):
                assert ast.dump(core_call,include_attributes=False)==ast.dump(ast.parse('_auto_optimization_workflows.core',mode='eval').body,include_attributes=False)
                core_call=next(node.value for node in tree.body if isinstance(node,ast.Assign) and any(isinstance(target,ast.Name) and target.id=='_auto_optimization_workflows' for target in node.targets))
            supplied={item.arg:item.value for item in core_call.keywords}
            owned_tree=ast.parse((ROOT/'local_inspection_service/training/core_composition.py').read_text(encoding='utf-8'))
            owned=next(node for node in ast.walk(owned_tree) if isinstance(node,ast.Assign) and any(isinstance(target,ast.Attribute) and target.attr=='recommendations' for target in node.targets))
            class ActualPorts(ast.NodeTransformer):
                def visit_Name(self,node):
                    if node.id=='self':return ast.copy_location(ast.Name(id='_auto_optimization_core',ctx=node.ctx),node)
                    if node.id in ('accessory_lookup','material_type','bounded_text'):
                        return copy.deepcopy(supplied[node.id])
                    return node
            construction=ast.fix_missing_locations(ActualPorts().visit(copy.deepcopy(owned)))
            aliases=[node for node in tree.body if isinstance(node,ast.Assign) and any(isinstance(target,ast.Name) and target.id=='_auto_optimization_recommendations' for target in node.targets)]
            nodes=[construction]+aliases+nodes
        for key in ('complexity','reason'):
            for fail in (False,True):
                events=[];sentinel=RuntimeError('selected text callback')
                def previous(value,limit):
                    events.append(('previous',value,limit))
                    if fail and value==('x' if key=='complexity' else 'r'):raise sentinel
                    return 'previous:'+value
                def following(value,limit):
                    events.append(('following',value,limit));return 'following:'+value
                namespace['bounded_text']=previous
                exec(compile(ast.Module(body=nodes,type_ignores=[]),str(source),'exec'),namespace)
                class RebindRaw(dict):
                    def get(self,field,default=None):
                        if field==key:
                            namespace['bounded_text']=following;events.append(('rebind',field))
                        return super().get(field,default)
                raw=RebindRaw(complexity='x',reason='r')
                if fail:
                    with self.assertRaises(RuntimeError) as raised:
                        namespace[name](raw,{'min_trainable_samples':300},10000)
                    self.assertIs(raised.exception,sentinel)
                    self.assertEqual(events,[('rebind','complexity'),('previous','x',80)] if key=='complexity' else [('previous','x',80),('rebind','reason'),('previous','r',240)])
                else:
                    result=namespace[name](raw,{'min_trainable_samples':300},10000)
                    self.assertEqual(result['complexity'],'previous:x')
                    self.assertEqual(result['reason'],'following:r' if key=='complexity' else 'previous:r')
                    self.assertEqual(events,[('rebind','complexity'),('previous','x',80),('following','r',240)] if key=='complexity' else [('previous','x',80),('rebind','reason'),('previous','r',240)])

    @unittest.skipIf(BASELINE,'candidate-only import')
    def test_lightweight_import(self):
        code="import sys; import local_inspection_service.training.auto_optimization_recommendations; assert not any(x in sys.modules for x in ('local_inspection_service.server','fastapi','psycopg'))"
        subprocess.run([sys.executable,'-c',code],cwd=ROOT,check=True)

if __name__=='__main__':unittest.main()
