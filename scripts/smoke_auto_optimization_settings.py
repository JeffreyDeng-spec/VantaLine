"""Existing auto-optimization settings defaults, coercion and exception contracts."""
import ast
import copy
import os
from pathlib import Path
import subprocess
import sys
import types
from typing import Any
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
NAMES={'default_auto_optimize_settings','auto_optimize_negative_samples_per_real_image',
       'auto_optimize_positive_derivatives_per_real_image','auto_optimize_training_requirements',
       'auto_optimize_samples_per_real_image','auto_optimize_training_parameters','normalize_expected_production_count'}
BASELINE=os.environ.get('VANTALINE_AUTO_SETTINGS_BASELINE_SOURCE')
if BASELINE:
    nodes=[n for n in ast.parse(Path(BASELINE).read_text(encoding='utf-8-sig')).body if isinstance(n,ast.FunctionDef) and n.name in NAMES]
    assert len(nodes)==7
    original=types.ModuleType('settings_original');original.__dict__.update(os=os,Any=Any,AUTO_OPTIMIZE_NEGATIVES_PER_REAL_IMAGE=3)
    exec(compile(ast.Module(body=nodes,type_ignores=[]),BASELINE,'exec'),original.__dict__)
    def create(value=3):original.AUTO_OPTIMIZE_NEGATIVES_PER_REAL_IMAGE=value;return original
else:
    from local_inspection_service.training.auto_optimization_settings import AutoOptimizationSettings,normalize_expected_production_count
    def create(value=3):return AutoOptimizationSettings(value)


class SettingsContract(unittest.TestCase):
    def setUp(self):
        self.env=patch.dict(os.environ,{},clear=True);self.env.start();self.addCleanup(self.env.stop)
        self.policy=create()

    def test_original_complete_defaults(self):
        self.assertEqual(self.policy.default_auto_optimize_settings(),dict(enabled=False,serving_mode='api_primary',
            samples_per_real_image=12,training_epochs=60,training_image_size=640,min_trainable_samples=200,
            min_positive_samples=200,min_negative_samples=0,negative_samples_per_real_image=3,max_label_jobs_per_cycle=3,
            mask_compare_min_score=.72,shadow_min_samples=80,shadow_min_agreement=.98,auto_promote=True))

    def test_dynamic_environment_and_fixed_negative_default(self):
        os.environ.update(VANTALINE_AUTO_OPT_MIN_TRAINABLE_SAMPLES='5',VANTALINE_AUTO_OPT_SAMPLES_PER_REAL_IMAGE='100',
            VANTALINE_AUTO_OPT_EPOCHS='999',VANTALINE_AUTO_OPT_IMAGE_SIZE='10',VANTALINE_AUTO_OPT_MIN_POSITIVE_SAMPLES='0',
            VANTALINE_AUTO_OPT_MIN_NEGATIVE_SAMPLES='-3',VANTALINE_AUTO_OPT_MAX_LABEL_JOBS_PER_CYCLE='0',
            VANTALINE_AUTO_OPT_MASK_COMPARE_MIN_SCORE='2',VANTALINE_AUTO_OPT_SHADOW_MIN_SAMPLES='0',
            VANTALINE_AUTO_OPT_SHADOW_MIN_AGREEMENT='-1',VANTALINE_AUTO_OPT_NEGATIVES_PER_REAL_IMAGE='19')
        current=self.policy.default_auto_optimize_settings()
        for key,value in dict(min_trainable_samples=20,samples_per_real_image=50,training_epochs=500,training_image_size=320,
            min_positive_samples=1,min_negative_samples=0,negative_samples_per_real_image=3,max_label_jobs_per_cycle=1,
            mask_compare_min_score=1.,shadow_min_samples=10,shadow_min_agreement=0.).items():self.assertEqual(current[key],value)
        os.environ['VANTALINE_AUTO_OPT_EPOCHS']='7';self.assertEqual(self.policy.default_auto_optimize_settings()['training_epochs'],7)

    def test_override_coercion_and_no_input_mutation(self):
        rows=[None,[],{},dict(samples_per_real_image=0,negative_samples_per_real_image=0),
              dict(samples_per_real_image='5',negative_samples_per_real_image='2'),dict(samples_per_real_image='bad',negative_samples_per_real_image=None)]
        expected=[(12,3,9),(12,3,9),(12,3,9),(12,0,12),(5,2,3),(12,3,9)]
        for row,wanted in zip(rows,expected):
            before=copy.deepcopy(row)
            got=(self.policy.auto_optimize_samples_per_real_image(row),self.policy.auto_optimize_negative_samples_per_real_image(row),self.policy.auto_optimize_positive_derivatives_per_real_image(row))
            self.assertEqual(got,wanted);self.assertEqual(row,before)
        self.assertEqual(create(7).auto_optimize_negative_samples_per_real_image(None),7)

    def test_training_requirements_preserve_current_unused_source_count(self):
        row=dict(min_trainable_samples='9',min_positive_samples='bad',min_negative_samples=-5,negative_samples_per_real_image=20,samples_per_real_image=1)
        expected=dict(min_trainable_samples=9,min_positive_samples=9,min_negative_samples=0,negative_samples_per_real_image=20,positive_derivatives_per_real_image=0)
        self.assertEqual(self.policy.auto_optimize_training_requirements(row),expected)
        self.assertEqual(self.policy.auto_optimize_training_requirements(row,real_positive_source_count=10000),expected)
        self.assertEqual(self.policy.auto_optimize_training_requirements(dict(min_trainable_samples=0))['min_trainable_samples'],200)

    def test_parameters_keep_defaults_and_legacy_key_precedence(self):
        self.assertEqual(self.policy.auto_optimize_training_parameters(dict(epochs=90,image_size=1024)),dict(training_epochs=60,training_image_size=640))
        self.assertEqual(self.policy.auto_optimize_training_parameters(dict(training_epochs=0,epochs=90,training_image_size=0,image_size=1024)),dict(training_epochs=90,training_image_size=1024))
        self.assertEqual(self.policy.auto_optimize_training_parameters(dict(training_epochs='bad',training_image_size='bad')),dict(training_epochs=60,training_image_size=640))
        self.assertEqual(self.policy.auto_optimize_training_parameters(dict(training_epochs=-3,training_image_size=9999)),dict(training_epochs=1,training_image_size=2048))

    def test_environment_failures_precede_explicit_override(self):
        os.environ['VANTALINE_AUTO_OPT_EPOCHS']='not-int'
        for method,args in [('default_auto_optimize_settings',()),('auto_optimize_training_parameters',({'training_epochs':5},)),
                            ('auto_optimize_negative_samples_per_real_image',({'negative_samples_per_real_image':5},))]:
            with self.assertRaisesRegex(ValueError,'invalid literal'):getattr(self.policy,method)(*args)
        os.environ['VANTALINE_AUTO_OPT_EPOCHS']='60'
        with self.assertRaises(OverflowError):self.policy.auto_optimize_training_parameters({'training_epochs':float('inf')})

    def test_production_count_retains_numeric_edges(self):
        fn=original.normalize_expected_production_count if BASELINE else normalize_expected_production_count
        for value,wanted in [(None,0),('',0),('bad',0),(True,1),('-2.9',0),('2.9',2),(2e7,1000000),(float('nan'),0)]:self.assertEqual(fn(value),wanted)
        with self.assertRaises(OverflowError):fn(float('inf'))

    @unittest.skipIf(BASELINE,'candidate-only import')
    def test_no_application_or_runtime_import(self):
        code="import sys; from local_inspection_service.training.auto_optimization_settings import AutoOptimizationSettings; assert not any(x in sys.modules for x in ('local_inspection_service.server','fastapi','psycopg'))"
        subprocess.run([sys.executable,'-c',code],cwd=ROOT,check=True)

if __name__=='__main__':unittest.main()
