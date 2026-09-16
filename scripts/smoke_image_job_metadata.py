"""Actual-root metadata baselines: deterministic IDs, provenance and immutable bindings."""
import copy
from contextlib import ExitStack
import hashlib
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class MetadataContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix='image-job-metadata-')
        cls.root = Path(cls.temporary.name)
        (cls.root/'local_inspection_service/static').mkdir(parents=True)
        os.environ.update(LOCAL_INSPECTION_ROOT=str(cls.root), VANTALINE_DATA_STORE='json',
                          VANTALINE_LABEL_INSPECTION_ENABLED='false', LOCAL_INSPECTION_AUTO_RESUME_WORKER='0')
        from local_inspection_service import server
        cls.server = server

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(self.server,'POSE_TARGET_GUIDE_IMAGES',{}))
        self.stack.enter_context(patch.object(self.server,'ANCHOR_POLICY_VERSION','fixture-policy'))

    def file(self, name, content=b'synthetic bytes'):
        path = self.root/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def test_deterministic_ids_and_alias_mutations_without_changed_flag(self):
        cases = [({'id':'cand-A','created_at':123},{'pose_family':'upright','output_path':'out.png'},'imgjob_cand-A','task_a5abe677eb'),
                 ({'id':None},{},'imgjob_None','task_ea3bdb9ae7'),
                 ({},{},'imgjob_task_500fdcc049','task_df9a1f3658'),
                 ({'id':'','created_at':0},{'job_id':0,'task_id':''},'imgjob_','task_41ae43c706')]
        for candidate, job, identifier, task in cases:
            self.assertTrue(self.server.ensure_image_job_task_id(candidate,job))
            self.assertEqual((job['job_id'],job['task_id']),(identifier,task))
            self.assertFalse(self.server.ensure_image_job_task_id(candidate,job))
        job = {'job_id':'stable','task_id':'original','candidate_id':'candidate'}
        candidate = {'id':'candidate','codex_image_job':job}
        self.assertFalse(self.server.ensure_candidate_image_job_task_ids(candidate))
        self.assertIs(candidate['codex_image_jobs'][0],job)
        self.assertIs(candidate['codex_image_job'],job)
        malformed = {'codex_image_jobs':[None,'invalid'],'codex_image_job':job}
        self.assertEqual(self.server.candidate_image_jobs(malformed),[])
        self.assertFalse(self.server.ensure_candidate_image_job_task_ids(malformed))
        self.assertIs(malformed['codex_image_job'],job)

    def test_anchor_legacy_mtime_existing_hash_and_missing_file_errors(self):
        anchor = self.file('anchor-contract.png',b'new anchor')
        output = self.file('anchor-output.png',b'old output')
        os.utime(output,(100,100)); os.utime(anchor,(200,200))
        for status in ('queued','completed'):
            job = {'generation_step':'anchor_replacement','status':status,'anchor_image_path':str(anchor),'output_path':str(output)}
            with patch.object(self.server,'file_sha256',side_effect=AssertionError('must not hash legacy provenance')):
                self.assertTrue(self.server.ensure_anchor_image_provenance(job))
            self.assertIsNone(job['anchor_image_sha256'])
            self.assertEqual(job['anchor_provenance'],'legacy_path_only')
            self.assertNotIn('anchor_policy_version',job)
        current = {'generation_step':'anchor_replacement','status':'queued','anchor_image_path':str(anchor)}
        self.assertTrue(self.server.ensure_anchor_image_provenance(current))
        self.assertEqual(current['anchor_image_sha256'],hashlib.sha256(b'new anchor').hexdigest())
        self.assertEqual(current['anchor_policy_version'],'fixture-policy')
        existing = {**current,'anchor_image_sha256':'historical-digest','anchor_policy_version':'historical-policy'}
        self.assertFalse(self.server.ensure_anchor_image_provenance(existing))
        self.assertEqual(existing['anchor_image_sha256'],'historical-digest')
        null_hash = {'generation_step':'anchor_replacement','anchor_image_path':str(anchor),'anchor_image_sha256':None}
        self.assertTrue(self.server.ensure_anchor_image_provenance(null_hash))
        self.assertEqual(null_hash['anchor_provenance'],'legacy_path_only')
        self.assertIsNone(null_hash['anchor_image_sha256'])
        missing = {'generation_step':'anchor_replacement','anchor_image_path':str(self.root/'missing.png')}
        with self.assertRaises(FileNotFoundError): self.server.ensure_anchor_image_provenance(missing)
        self.assertEqual(missing['anchor_image_basename'],'missing.png')
        self.assertNotIn('anchor_image_sha256',missing)
        unreadable = {'generation_step':'anchor_replacement','anchor_image_path':str(anchor)}
        with patch.object(Path,'open',side_effect=PermissionError('synthetic read denial')):
            with self.assertRaises(PermissionError): self.server.ensure_anchor_image_provenance(unreadable)
        self.assertNotIn('anchor_image_sha256',unreadable)

    def test_guide_insertion_truncation_hash_names_and_no_change_behavior(self):
        a = self.file('guide-a/guide.png',b'guide A')
        b = self.file('guide-b/guide.png',b'guide B')
        job = {'pose_family':'fixture','anchor_image_path':'anchor','input_files':['anchor',str(a),'source']}
        with patch.object(self.server,'POSE_TARGET_GUIDE_IMAGES',{'fixture':[a,b,self.root/'missing-guide.png']}), \
             patch.object(self.server,'MAX_IMAGE_WORKER_INPUTS',3):
            self.assertTrue(self.server.ensure_image_job_target_guides(job))
            self.assertEqual(job['input_files'],['anchor',str(b),str(a)])
            self.assertEqual(job['target_guide_paths'],[str(a),str(b)])
            self.assertEqual(job['target_guide_sha256'],{'guide.png':hashlib.sha256(b'guide B').hexdigest()})
            job['input_files'].append('oversized-but-unchanged')
            self.assertFalse(self.server.ensure_image_job_target_guides(job))
            self.assertEqual(len(job['input_files']),4)
            job['target_guide_sha256'] = {'guide.png':'outdated'}
            self.assertTrue(self.server.ensure_image_job_target_guides(job))
            self.assertEqual(len(job['input_files']),3)
        untouched = {'pose_family':'missing','input_files':['keep'],'target_guide_paths':['old']}
        before = copy.deepcopy(untouched)
        self.assertFalse(self.server.ensure_image_job_target_guides(untouched))
        self.assertEqual(untouched,before)

    def test_store_freezes_before_repair_and_keeps_old_snapshot_and_duplicate_ids(self):
        fixture = self
        class Resolver:
            current = None
            snapshot = {'image':{'id':'fixture','version':7,'secret_ref':{'version':3},'prompt_version':'source-sha256:v2:historical-fixture'}}
            def current_snapshot(self): return self.current
            def snapshot_for_record(self,record):
                fixture.assertNotIn('task_id',record)
                return self.snapshot
        resolver = Resolver()
        updated = {'job_id':'replace'}
        other = {'job_id':'other','candidate_id':'candidate','task_id':'other-task'}
        candidate = {'id':'candidate','codex_image_jobs':[{'job_id':'replace'},{'job_id':'replace'},other]}
        with patch.object(self.server,'resolve_model_profiles',return_value=resolver):
            self.server.store_candidate_image_job(candidate,updated)
        self.assertEqual(len(candidate['codex_image_jobs']),3)
        self.assertIs(candidate['codex_image_jobs'][0],updated)
        self.assertIs(candidate['codex_image_jobs'][1],updated)
        self.assertIs(candidate['codex_image_jobs'][2],other)
        self.assertIs(candidate['codex_image_job'],updated)
        historical_binding = copy.deepcopy(updated['model_profiles'])
        resolver.snapshot['image']['version'] = 8
        resolver.snapshot['image']['secret_ref']['version'] = 4
        self.assertEqual(updated['model_profiles']['image']['version'],7)
        self.assertEqual(updated['model_profiles']['image']['secret_ref']['version'],3)
        with patch.object(self.server,'resolve_model_profiles',side_effect=AssertionError('bound record must retain its snapshot')):
            self.server.store_candidate_image_job(candidate,updated)
        self.assertEqual(updated['model_profiles'],historical_binding)
        self.assertEqual(updated['model_profiles']['image']['prompt_version'],'source-sha256:v2:historical-fixture')
        contextual = {'job_id':'context'}
        resolver.current = {'image':{'id':'context-snapshot','version':2}}
        with patch.object(self.server,'resolve_model_profiles',return_value=resolver):
            self.server.store_candidate_image_job(candidate,contextual)
        self.assertEqual(contextual['model_profiles'],resolver.current)
        self.assertIsNot(contextual['model_profiles'],resolver.current)
        self.assertEqual(len(candidate['codex_image_jobs']),4)

    def test_missing_resolver_fails_before_mutation_and_file_failure_keeps_binding_evidence(self):
        candidate = {'id':'candidate','codex_image_jobs':[]}
        updated = {'pose_family':'fixture'}
        with patch.object(self.server,'resolve_model_profiles',return_value=None):
            with self.assertRaisesRegex(RuntimeError,'resolver is not configured'):
                self.server.store_candidate_image_job(candidate,updated)
        self.assertEqual(updated,{'pose_family':'fixture'})
        self.assertEqual(candidate,{'id':'candidate','codex_image_jobs':[]})
        class Resolver:
            def current_snapshot(self): return {'image':{'id':'fixed-evidence','version':1}}
        updated = {'generation_step':'anchor_replacement','anchor_image_path':str(self.root/'never-existed.png')}
        with patch.object(self.server,'resolve_model_profiles',return_value=Resolver()):
            with self.assertRaises(FileNotFoundError): self.server.store_candidate_image_job(candidate,updated)
        self.assertEqual(updated['model_profiles'],{'image':{'id':'fixed-evidence','version':1}})
        self.assertTrue(updated['task_id'])
        self.assertEqual(updated['anchor_image_basename'],'never-existed.png')
        self.assertNotIn('anchor_image_sha256',updated)
        self.assertEqual(candidate,{'id':'candidate','codex_image_jobs':[]})

    def test_second_guide_hash_failure_preserves_prior_evidence_without_guide_commit(self):
        anchor = self.file('guide-failure/anchor.png',b'anchor evidence')
        a = self.file('guide-failure/a.png',b'guide A')
        b = self.file('guide-failure/b.png',b'guide B')
        candidate = {'id':'candidate','codex_image_jobs':[]}
        updated = {'pose_family':'fixture','generation_step':'anchor_replacement',
                   'output_path':str(self.root/'guide-failure/no-output.png'),
                   'anchor_image_path':str(anchor),'input_files':[str(anchor),'source'],
                   'target_guide_paths':['historical-guide'],'target_guide_sha256':{'historical-guide':'old-hash'}}
        original_hash = self.server.file_sha256
        calls = []
        def hash_file(path):
            self.assertIn('model_profiles',updated)
            calls.append(path)
            if path==b: raise PermissionError('synthetic second guide read failure')
            return original_hash(path)
        class Resolver:
            def current_snapshot(self): return {'image':{'id':'fixed-evidence','version':1}}
        with patch.object(self.server,'resolve_model_profiles',return_value=Resolver()), \
             patch.object(self.server,'POSE_TARGET_GUIDE_IMAGES',{'fixture':[a,b]}), \
             patch.object(self.server,'file_sha256',side_effect=hash_file):
            with self.assertRaises(PermissionError): self.server.store_candidate_image_job(candidate,updated)
        self.assertEqual(calls,[anchor,a,b])
        self.assertTrue(updated['task_id'])
        self.assertEqual(updated['anchor_image_sha256'],hashlib.sha256(b'anchor evidence').hexdigest())
        self.assertEqual(updated['input_files'],[str(anchor),'source'])
        self.assertEqual(updated['target_guide_paths'],['historical-guide'])
        self.assertEqual(updated['target_guide_sha256'],{'historical-guide':'old-hash'})
        self.assertEqual(candidate,{'id':'candidate','codex_image_jobs':[]})


if __name__ == '__main__':
    unittest.main()
