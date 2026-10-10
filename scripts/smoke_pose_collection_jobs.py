"""Legacy pose job contracts with synthetic records and media adapters."""
import ast
from dataclasses import fields
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from types import SimpleNamespace
from typing import Any
import unittest
from unittest.mock import Mock, patch
import uuid

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from canonical_application_source_contract import read_checked_application_source
BASELINE=os.environ.get('VANTALINE_POSE_COLLECTION_JOBS_BASELINE_SOURCE')
NAMES=('safe_record_id','pose_collection_output_dir','pose_collection_output_name','pose_collection_job_id','source_reference_inputs_for_pose_job','make_pose_collection_job','ensure_pose_collection_image_jobs','pending_pose_collection_jobs','pose_collection_pending_detail')


def create(bindings):
    if BASELINE:
        nodes=[n for n in ast.parse(Path(BASELINE).read_text(encoding='utf-8-sig')).body if isinstance(n,ast.FunctionDef) and n.name in NAMES];assert len(nodes)==9
        bindings.update(Any=Any,Path=Path,re=re,time=time,uuid=uuid);exec(compile(ast.Module(body=nodes,type_ignores=[]),BASELINE,'exec'),bindings)
        return SimpleNamespace(**{n:bindings[n] for n in NAMES}),bindings
    from local_inspection_service.accessories.pose_collection_jobs import PoseCollectionJobs
    from local_inspection_service.accessories.pose_collection_job_ports import PoseJobIdentity,PoseJobMedia,PoseJobWorkflow
    def ports(cls):return cls(**{f.name:lambda name=f.name:bindings[name] for f in fields(cls)})
    service=PoseCollectionJobs(ports(PoseJobIdentity),ports(PoseJobMedia),ports(PoseJobWorkflow));bindings.update({n:getattr(service,n) for n in NAMES});return service,bindings


class PoseJobsContract(unittest.TestCase):
    def fixture(self):
        events=[];files=SimpleNamespace(exists=Mock(return_value=False),stat=Mock(return_value=SimpleNamespace(st_mtime=42.9)))
        bindings={'record_owner_id':lambda i:i.get('owner_user_id','owner'),'accessory_uid':lambda i:str(i.get('id','')),'deterministic_task_id':lambda i,j:'task','record_audit_fields':lambda i:{'owner_user_id':i.get('owner_user_id','owner')},'accessory_material_type':lambda i:i.get('material_type','object'),
                  'output_write_dir_for_owner':lambda category,owner:Path('/synthetic')/owner/category,'POSE_ANCHOR_IMAGES':{'upright':Path('/anchor/up.png')},'_business_files':files,'existing_source_image_paths':lambda i:[Path(p) for p in i.get('source_files',[])],'MAX_IMAGE_WORKER_INPUTS':3,'public_output_url':lambda p:'synthetic:'+p.name,'image_job_output_path':lambda j,**kw:Path(j['output_path']),
                  'CODEX_IMAGE_WORKER_QUEUE_STATUS':'queued','LOCAL_CODEX_IMAGE_PROVIDER':'local','build_anchor_replacement_pose_prompt':lambda i,f:'prompt-'+f,'ensure_image_job_task_id':lambda i,j:events.append('id') or False,'ensure_anchor_image_provenance':lambda j:events.append('anchor') or False,'ensure_image_job_target_guides':lambda j:events.append('guides') or False,'POSE_COLLECTION_GRID_ENABLED':True,'candidate_image_jobs':lambda i:i.get('codex_image_jobs',[])}
        service,bindings=create(bindings);return SimpleNamespace(s=service,b=bindings,files=files,events=events)

    def test_identifiers_owner_paths_and_ordered_inputs(self):
        f=self.fixture();item={'id':'..x / y..','owner_user_id':'a'}
        self.assertEqual(f.s.safe_record_id(item['id']),'x_y');self.assertEqual(f.s.safe_record_id(None),'record')
        self.assertEqual(f.s.pose_collection_output_dir(item),Path('/synthetic/a/accessory_pose_collections/x_y'))
        self.assertEqual(f.s.pose_collection_job_id(item,'upright'),'imgjob_x_y_upright_anchor_replacement')
        with patch.object(uuid,'uuid4',return_value='synthetic-uuid'):
            self.assertEqual(f.s.pose_collection_output_dir({}).name,'synthetic-uuid')
        f.files.exists.return_value=True;item['source_files']=['/anchor/up.png','/one.png','/one.png','/two.png','/three.png']
        self.assertEqual(f.s.source_reference_inputs_for_pose_job(item,'upright'),[str(Path(p)) for p in ['/anchor/up.png','/one.png','/two.png']])
        f.b['MAX_IMAGE_WORKER_INPUTS']=1;self.assertEqual(len(f.s.source_reference_inputs_for_pose_job(item,'unknown')),1)

    def test_make_job_preserves_three_independent_exists_reads(self):
        f=self.fixture();item={'id':'c','name':'synthetic','owner_user_id':'a'}
        f.b['source_reference_inputs_for_pose_job']=Mock(return_value=['input']);f.files.exists.side_effect=[False,True,True]
        with patch.object(time,'time',return_value=100.9):job=f.s.make_pose_collection_job(item,'upright')
        self.assertEqual((job['status'],job['progress'],job['completed_at']),('queued',100,42))
        self.assertEqual(job['created_at'],100);self.assertEqual(job['owner_user_id'],'a');self.assertEqual(job['task_id'],'task')
        self.assertEqual(job['prompt'],'prompt-upright');self.assertEqual(f.events,['id','anchor','guides']);self.assertEqual(f.files.exists.call_count,3)
        f=self.fixture();f.b['source_reference_inputs_for_pose_job']=lambda *a:[];f.b['record_audit_fields']=lambda i:{'status':'audit-override','created_at':-1}
        job=f.s.make_pose_collection_job({'id':'c'},'lying');self.assertEqual(job['status'],'audit-override');self.assertEqual(job['created_at'],-1);self.assertEqual(job['anchor_image_path'],'')

    def test_retired_and_text_gates_do_no_job_work(self):
        for text,enabled in [(True,True),(True,False),(False,False)]:
            f=self.fixture();f.b['POSE_COLLECTION_GRID_ENABLED']=enabled;f.b['candidate_image_jobs']=Mock(side_effect=AssertionError('gate bypass'))
            item={'material_type':'text' if text else 'object'};self.assertFalse(f.s.ensure_pose_collection_image_jobs(item));self.assertEqual(f.events,[])

    def test_existing_completion_and_missing_output_requeue(self):
        f=self.fixture();jobs=[{'generation_step':'anchor_replacement','pose_family':'upright','output_path':'pose_collection_endface.png','status':'running','provider':'old'},
                              {'generation_step':'anchor_replacement','pose_family':'lying','output_path':'pose_collection_flat.png','status':'completed','completed_at':1}]
        item={'id':'c','status':'active','codex_image_jobs':jobs};f.files.exists.side_effect=lambda p:p.name=='pose_collection_endface.png'
        self.assertTrue(f.s.ensure_pose_collection_image_jobs(item));self.assertIs(item['codex_image_jobs'],jobs);self.assertIs(item['codex_image_job'],jobs[0]);self.assertEqual(len(jobs),2)
        self.assertEqual((jobs[0]['status'],jobs[0]['progress'],jobs[0]['completed_at']),('completed',100,42))
        self.assertEqual((jobs[1]['status'],jobs[1]['progress']),('queued',0));self.assertNotIn('completed_at',jobs[1]);self.assertIn('Missing target PNG',jobs[1]['error'])
        self.assertEqual(item['status'],'image_tool_plan_ready');self.assertTrue(item['ai_generation_required']);self.assertEqual(f.events,['id','anchor','guides']*2)

    def test_new_jobs_order_and_partial_error_not_replayed(self):
        f=self.fixture();calls=[];jobs=[];item={'id':'c','codex_image_jobs':jobs}
        failure=RuntimeError('second job')
        def make(i,family):
            calls.append(family)
            if family=='lying':raise failure
            return {'generation_step':'anchor_replacement','pose_family':family,'output_path':'pose_collection_endface.png'}
        f.b['make_pose_collection_job']=make
        with self.assertRaises(RuntimeError) as caught:f.s.ensure_pose_collection_image_jobs(item)
        self.assertIs(caught.exception,failure);self.assertEqual(calls,['upright','lying']);self.assertEqual(len(jobs),1);self.assertNotIn('ai_generation_required',item)
        f=self.fixture();item={'id':'c','status':'custom'}
        self.assertTrue(f.s.ensure_pose_collection_image_jobs(item));self.assertEqual([j['pose_family'] for j in item['codex_image_jobs']],['upright','lying']);self.assertEqual(item['status'],'custom')

    def test_pending_copies_and_detail_limit(self):
        f=self.fixture();nested=[];jobs=[{'generation_step':'anchor_replacement','pose_family':'lying','status':'completed','output_path':'missing.png','nested':nested},
                                      {'generation_step':'other','status':'queued','output_path':'other.png'}]
        pending=f.s.pending_pose_collection_jobs({'codex_image_jobs':jobs});self.assertEqual(len(pending),1);self.assertIsNot(pending[0],jobs[0]);self.assertIs(pending[0]['nested'],nested);self.assertNotIn('missing_output_path',jobs[0])
        item={'id':'c'};records=[dict(pending[0],error=' error ') for _ in range(5)];detail=f.s.pose_collection_pending_detail(item,records)
        self.assertEqual(detail.count('target=missing.png'),4);self.assertIn('；...。',detail);self.assertIn('配件 c',detail)
        f.files.exists.return_value=True;self.assertEqual(f.s.pending_pose_collection_jobs({'codex_image_jobs':jobs}),[])

    def test_late_publication_callbacks_and_failure_effects(self):
        f=self.fixture();events=[]
        def ensure_id(item,job):
            events.append('id');f.b['ensure_anchor_image_provenance']=lambda j:events.append('fresh-anchor') or False
            return False
        f.b['ensure_image_job_task_id']=ensure_id;f.b['ensure_anchor_image_provenance']=Mock(side_effect=AssertionError('stale callback'))
        f.s.make_pose_collection_job({'id':'c'},'lying');self.assertEqual(events,['id','fresh-anchor'])
        f=self.fixture();failure=RuntimeError('provenance');f.b['ensure_anchor_image_provenance']=Mock(side_effect=failure)
        with self.assertRaises(RuntimeError) as caught:f.s.make_pose_collection_job({'id':'c'},'lying')
        self.assertIs(caught.exception,failure);self.assertEqual(f.events,['id'])

    @unittest.skipIf(bool(BASELINE),'candidate wiring only')
    def test_wiring_and_light_import(self):
        tree=ast.parse(read_checked_application_source(ROOT / 'local_inspection_service/server.py', encoding='utf-8'));binding=next(n.value for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='_pose_collection_jobs' for t in n.targets));count=0
        for group in binding.keywords:
            for kw in group.value.keywords:self.assertIsInstance(kw.value,ast.Lambda);self.assertEqual(kw.arg,kw.value.body.id);count+=1
        self.assertEqual(count,26)
        for name in NAMES:
            node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name);self.assertEqual(len(node.body),1);self.assertIsInstance(node.body[0],ast.Return);self.assertEqual(node.body[0].value.func.attr,name)
        subprocess.run([sys.executable,'-B','-c','import sys; import local_inspection_service.accessories.pose_collection_jobs; assert "local_inspection_service.server" not in sys.modules'],cwd=ROOT,check=True)


if __name__=='__main__':unittest.main()
