"""Owned accessory workflow boundaries, retaining original mutation/error order."""
import ast,os,sys,unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock,patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
BASELINE=os.environ.get('VANTALINE_ACCESSORY_WORKFLOW_BASELINE_SOURCE')
NAMES=('image_job_matches','ensure_object_clean_sprites_ready','update_image_worker_status','first_source_ai_reference_path')


def create(b):
    if BASELINE:
        nodes=[n for n in ast.parse(Path(BASELINE).read_text(encoding='utf-8-sig')).body if isinstance(n,ast.FunctionDef) and n.name in NAMES];assert len(nodes)==4
        ns=dict(b,Any=Any,Path=Path);exec(compile(ast.Module(body=nodes,type_ignores=[]),BASELINE,'exec'),ns)
        return SimpleNamespace(**{n:ns[n] for n in NAMES}),ns
    from local_inspection_service.accessories import image_job_metadata as metadata
    from local_inspection_service.accessories.object_preprocessing import ObjectSpritePreprocessor
    from local_inspection_service.accessories.object_preprocessing_ports import ObjectSpritePolicy
    from local_inspection_service.accessories.image_job_queue import ImageJobQueue
    from local_inspection_service.accessories.candidate_artifacts import CandidateArtifacts
    policy=ObjectSpritePolicy(material=lambda:b['accessory_material_type'],alpha=Mock(side_effect=AssertionError('unused alpha')),existing=lambda:b['clean_sprite_assets'],complete=lambda:b['clean_sprites_policy_complete'])
    sprite=ObjectSpritePreprocessor(policy,None,None,None,None,None,None)
    queue=ImageJobQueue(None,None,None);artifacts=CandidateArtifacts(None,None)
    def match(*args):
        with patch.object(metadata,'ensure_image_job_task_id',b['ensure_image_job_task_id']):return metadata.image_job_matches(*args)
    def ready(*args,**kwargs):
        with patch.object(ObjectSpritePreprocessor,'preprocess_object_clean_sprites',autospec=True,side_effect=lambda _self,*a,**k:b['preprocess_object_clean_sprites'](*a,**k)):return sprite.ensure_object_clean_sprites_ready(*args,**kwargs)
    def update(*args,**kwargs):
        with patch.object(ImageJobQueue,'mutate_candidate_image_job',autospec=True,side_effect=lambda _self,*a,**k:b['mutate_candidate_image_job'](*a,**k)):return queue.update_image_worker_status(*args,**kwargs)
    def source(*args):
        with patch.object(CandidateArtifacts,'existing_source_image_paths',autospec=True,side_effect=lambda _self,*a:b['existing_source_image_paths'](*a)):return artifacts.first_source_ai_reference_path(*args)
    return SimpleNamespace(image_job_matches=match,ensure_object_clean_sprites_ready=ready,update_image_worker_status=update,first_source_ai_reference_path=source),b


class Contracts(unittest.TestCase):
    def setUp(self):
        b=dict(ensure_image_job_task_id=Mock(),accessory_material_type=Mock(return_value='object'),clean_sprite_assets=Mock(return_value=[]),clean_sprites_policy_complete=Mock(return_value=True),preprocess_object_clean_sprites=Mock(return_value=True),mutate_candidate_image_job=Mock(return_value={'status':'ready'}),existing_source_image_paths=Mock(return_value=[]))
        self.s,self.b=create(b)

    def test_matching_repairs_before_lookup_and_keeps_false_result_mutation(self):
        def repair(candidate,job):job.update(job_id='job',task_id='task')
        self.b['ensure_image_job_task_id'].side_effect=repair
        for lookup,expected in [('job',True),('task',True),('missing',False)]:
            job={};self.assertIs(self.s.image_job_matches({},job,lookup),expected);self.assertEqual(job,{'job_id':'job','task_id':'task'})
        self.b['ensure_image_job_task_id'].side_effect=None
        self.assertTrue(self.s.image_job_matches({}, {}, ''))

    def test_match_error_before_lookup_keeps_partial_repair(self):
        error=ValueError('repair')
        def fail(candidate,job):job['partial']=True;raise error
        self.b['ensure_image_job_task_id'].side_effect=fail;job={}
        with self.assertRaises(ValueError) as caught:self.s.image_job_matches({},job,'id')
        self.assertIs(caught.exception,error);self.assertEqual(job,{'partial':True})

    def test_text_short_circuits_even_force(self):
        self.b['accessory_material_type'].return_value='text'
        self.assertFalse(self.s.ensure_object_clean_sprites_ready({},force=True))
        self.b['clean_sprite_assets'].assert_not_called();self.b['preprocess_object_clean_sprites'].assert_not_called()

    def test_ready_short_circuit_and_empty_forces(self):
        item={'clean_sprite_status':'ready'};sprites=[{'id':'s'}];self.b['clean_sprite_assets'].return_value=sprites
        self.assertFalse(self.s.ensure_object_clean_sprites_ready(item))
        self.b['clean_sprites_policy_complete'].assert_called_once_with(item,sprites);self.b['preprocess_object_clean_sprites'].assert_not_called()
        self.s.ensure_object_clean_sprites_ready(item,force=True)
        self.b['preprocess_object_clean_sprites'].assert_called_once_with(item,allow_ai_cutout=True,force=True)
        self.assertEqual(self.b['clean_sprites_policy_complete'].call_count,1)

    def test_incomplete_missing_and_stale_sprites(self):
        for sprites,status,complete,forced in [([], 'ready', True,False),([{}],'pending',True,True),([{}],'ready',False,True)]:
            self.b['clean_sprite_assets'].return_value=sprites;self.b['clean_sprites_policy_complete'].return_value=complete;self.b['preprocess_object_clean_sprites'].reset_mock();item={'clean_sprite_status':status}
            self.assertTrue(self.s.ensure_object_clean_sprites_ready(item));self.b['preprocess_object_clean_sprites'].assert_called_once_with(item,allow_ai_cutout=True,force=forced)

    def test_preprocess_failure_preserves_its_partial_mutation(self):
        error=RuntimeError('sprite')
        def fail(item,**kwargs):item['partial']=1;raise error
        self.b['preprocess_object_clean_sprites'].side_effect=fail;item={}
        with self.assertRaises(RuntimeError) as caught:self.s.ensure_object_clean_sprites_ready(item)
        self.assertIs(caught.exception,error);self.assertEqual(item,{'partial':1})

    def test_status_merge_reference_and_return_none(self):
        path=Path('fixture.json');candidate={};job={'keep':1};self.assertIsNone(self.s.update_image_worker_status(path,candidate,job,status='ready'))
        self.b['mutate_candidate_image_job'].assert_called_once_with(path,candidate,job,{'status':'ready'})
        self.assertEqual(job,{'keep':1,'status':'ready'})

    def test_status_mutation_failure_and_invalid_result(self):
        error=OSError('save');job={'prior':1}
        def fail(path,candidate,job,updates):candidate['partial']=True;raise error
        self.b['mutate_candidate_image_job'].side_effect=fail;candidate={}
        with self.assertRaises(OSError) as caught:self.s.update_image_worker_status(Path('fixture'),candidate,job,status='ready')
        self.assertIs(caught.exception,error);self.assertEqual(candidate,{'partial':True});self.assertEqual(job,{'prior':1})
        self.b['mutate_candidate_image_job'].side_effect=None;self.b['mutate_candidate_image_job'].return_value=None
        with self.assertRaises(TypeError):self.s.update_image_worker_status(Path('fixture'),candidate,job)

    def test_first_source_identity_order_empty_and_error(self):
        item={};first=Path('first.png');self.assertIsNone(self.s.first_source_ai_reference_path(item))
        self.b['existing_source_image_paths'].return_value=[first,Path('second.png')];self.assertIs(self.s.first_source_ai_reference_path(item),first)
        error=RuntimeError('source');self.b['existing_source_image_paths'].side_effect=error
        with self.assertRaises(RuntimeError) as caught:self.s.first_source_ai_reference_path(item)
        self.assertIs(caught.exception,error)

    @unittest.skipIf(bool(BASELINE),'candidate ownership only')
    def test_actual_root_exports_and_internal_calls(self):
        from scripts.verify_backend_contract import capture
        capture()
        from local_inspection_service import server
        from local_inspection_service.accessories import image_job_metadata
        self.assertIs(server.image_job_matches,image_job_metadata.image_job_matches)
        for name,owner in [('ensure_object_clean_sprites_ready','_object_sprite_preprocessor'),('update_image_worker_status','_image_job_queue'),('first_source_ai_reference_path','_candidate_artifacts')]:
            self.assertIs(getattr(server,name).__self__,getattr(server,owner))
        job={};self.assertFalse(server.image_job_matches({'id':'fixture'},job,'absent'));self.assertTrue(job['task_id'].startswith('task_'))
        self.assertTrue(server.image_job_matches({'id':'fixture'},job,job['task_id']))


if __name__=='__main__':unittest.main()
