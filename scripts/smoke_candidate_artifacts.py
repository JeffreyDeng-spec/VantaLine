"""Candidate ownership, shared-reference protection and cleanup failure contracts."""
import ast
from dataclasses import fields
import os
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace
from typing import Any
import unittest
from unittest.mock import Mock

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
BASELINE=os.environ.get('VANTALINE_CANDIDATE_ARTIFACT_BASELINE_SOURCE')
NAMES=('cleanup_accessory_candidate_artifacts','existing_source_image_paths')


def create(b):
    if BASELINE:
        nodes=[n for n in ast.parse(Path(BASELINE).read_text(encoding='utf-8-sig')).body if isinstance(n,ast.FunctionDef) and n.name in NAMES]
        assert len(nodes)==2
        b.update(Path=Path,Any=Any)
        exec(compile(ast.Module(body=nodes,type_ignores=[]),BASELINE,'exec'),b)
        return SimpleNamespace(**{n:b[n] for n in NAMES})
    from local_inspection_service.accessories.candidate_artifacts import CandidateArtifacts
    from local_inspection_service.accessories.candidate_artifact_ports import CandidateArtifactFiles,CandidateArtifactRecords
    def ports(cls):return cls(**{f.name:lambda name=f.name:b[name] for f in fields(cls)})
    return CandidateArtifacts(ports(CandidateArtifactFiles),ports(CandidateArtifactRecords))


class CandidateContract(unittest.TestCase):
    def fixture(self):
        tmp=tempfile.TemporaryDirectory(prefix='vantaline-candidate-contract-');self.addCleanup(tmp.cleanup)
        root=Path(tmp.name).resolve();events=[]
        def remove(p):
            # Every destructive test action must stay strictly below this test's owned directory.
            p=p.resolve();self.assertTrue(p.is_relative_to(root));self.assertNotEqual(p,root)
            events.append(('delete',p));shutil.rmtree(p)
        files=SimpleNamespace(exists=lambda p:p.exists(),is_file=lambda p:p.is_file(),glob=lambda p,pattern,recursive=False:p.rglob(pattern) if recursive else p.glob(pattern),rmtree=remove)
        b=dict(_business_files=files,UPLOAD_DIR=root/'uploads',output_write_dir=lambda kind:root/'outputs'/kind,
            IMAGE_REFERENCE_SUFFIXES={'.png','.jpg'},safe_record_id=lambda v:v.replace('/','_'),
            load_config=lambda:{'accessories':[]},list_accessory_candidate_records=lambda **kw:[])
        return create(b),b,root,events

    def write(self,p):
        p.parent.mkdir(parents=True,exist_ok=True);p.write_text('synthetic');return p

    def test_empty_and_confirmed_records_have_no_effect(self):
        s,b,r,e=self.fixture();b['safe_record_id']=Mock(side_effect=AssertionError('not reached'))
        for c in ({},{'id':' '},{'id':'a','status':'CONFIRMED'},{'candidate_id':'a','confirmed_accessory_id':'saved'}):
            self.assertEqual(s.cleanup_accessory_candidate_artifacts(c),[])
        self.assertEqual(e,[])

    def test_owned_upload_and_output_deleted_sorted_and_input_preserved(self):
        s,b,r,e=self.fixture();u=self.write(r/'uploads/accessory_candidates/a/x');o=self.write(r/'outputs/accessory_candidates/a/y')
        c={'candidate_id':'a','source_files':[str(u)]};before=dict(c)
        self.assertEqual(s.cleanup_accessory_candidate_artifacts(c),sorted([str(u.parent),str(o.parent)]));self.assertEqual(c,before)
        self.assertFalse(u.parent.exists());self.assertFalse(o.parent.exists())

    def test_only_explicit_source_buckets_collect_paths(self):
        s,b,r,e=self.fixture();u=self.write(r/'uploads/accessory_candidates/src_1/nested/x.png');outside=self.write(r/'elsewhere/z')
        c={'id':'a','source_files':[{},None,42,' ',{'path':str(u)}], 'original_source_files':'bad', 'video_reference_frames':[str(outside)]}
        self.assertEqual(s.cleanup_accessory_candidate_artifacts(c),[str(u.parents[1])]);self.assertTrue(outside.exists())

    def test_all_source_buckets_support_source_directory_ownership(self):
        for key in ('source_files','original_source_files','video_reference_frames'):
            with self.subTest(key=key):
                s,b,r,e=self.fixture();u=self.write(r/'uploads/accessory_candidates/src_x/a')
                self.assertEqual(s.cleanup_accessory_candidate_artifacts({'id':'a',key:[str(u)]}),[str(u.parent)])

    def test_unreferenced_source_file_refuses_entire_directory(self):
        s,b,r,e=self.fixture();u=self.write(r/'uploads/accessory_candidates/src_x/a');v=self.write(u.parent/'unlisted')
        with self.assertRaisesRegex(OSError,'unreferenced files'):s.cleanup_accessory_candidate_artifacts({'id':'a','source_files':[str(u)]})
        self.assertEqual(e,[]);self.assertTrue(v.exists())

    def test_protected_nested_reference_preflight_blocks_all_deletes(self):
        for key in ('source_files','original_source_files','video_reference_frames','thumbnails','normalized_assets','ai_profile_reference_files','codex_image_jobs','codex_image_job'):
            with self.subTest(key=key):
                s,b,r,e=self.fixture();u=self.write(r/'uploads/accessory_candidates/a/x');self.write(r/'outputs/accessory_candidates/a/y')
                b['load_config']=lambda:{'accessories':[None,{key:{'nested':[{'path':str(u)}]}}]}
                with self.assertRaisesRegex(OSError,'still referenced'):s.cleanup_accessory_candidate_artifacts({'id':'a'})
                self.assertEqual(e,[]);self.assertTrue(u.exists())

    def test_other_candidate_protects_but_same_raw_id_does_not(self):
        s,b,r,e=self.fixture();u=self.write(r/'uploads/accessory_candidates/a/x')
        def listing(**kw):
            self.assertEqual(kw,{'reverse':False});return [(r/'record',{'id':'other','source_files':[str(u)]})]
        b['list_accessory_candidate_records']=listing
        with self.assertRaisesRegex(OSError,'still referenced'):s.cleanup_accessory_candidate_artifacts({'id':'a'})
        b['list_accessory_candidate_records']=lambda **kw:[(r/'record',{'id':'a','source_files':[str(u)]})]
        self.assertEqual(s.cleanup_accessory_candidate_artifacts({'id':'a'}),[str(u.parent)])

    def test_unknown_owner_and_relative_protected_paths_do_not_expand_authority(self):
        s,b,r,e=self.fixture();u=self.write(r/'uploads/accessory_candidates/other/x');v=self.write(r/'uploads/accessory_candidates/a/y')
        b['load_config']=lambda:{'accessories':[{'source_files':['relative/y']}]}
        self.assertEqual(s.cleanup_accessory_candidate_artifacts({'id':'a','source_files':[str(u)]}),[str(v.parent)]);self.assertTrue(u.exists())

    def test_read_failure_propagates_before_delete(self):
        s,b,r,e=self.fixture();u=self.write(r/'uploads/accessory_candidates/a/x');error=RuntimeError('read failure')
        b['load_config']=Mock(side_effect=error)
        with self.assertRaises(RuntimeError) as caught:s.cleanup_accessory_candidate_artifacts({'id':'a'})
        self.assertIs(caught.exception,error);self.assertEqual(e,[]);self.assertTrue(u.exists())

    def test_second_delete_failure_preserves_original_partial_effect(self):
        s,b,r,e=self.fixture();u=self.write(r/'uploads/accessory_candidates/a/x');o=self.write(r/'outputs/accessory_candidates/a/y')
        original=b['_business_files'].rmtree;error=OSError('second failed');calls=[]
        def remove(p):
            calls.append(p)
            if len(calls)==2:raise error
            original(p)
        b['_business_files'].rmtree=remove
        with self.assertRaises(OSError) as caught:s.cleanup_accessory_candidate_artifacts({'id':'a'})
        self.assertIs(caught.exception,error);self.assertEqual(calls,sorted([u.parent,o.parent],key=str));self.assertFalse(calls[0].exists());self.assertTrue(calls[1].exists())

    @unittest.skipIf(os.name=='nt','symlink containment exercised in Linux')
    def test_owned_symlink_outside_roots_is_rejected(self):
        s,b,r,e=self.fixture();outside=self.write(r/'unowned/x');link=r/'uploads/accessory_candidates/a';link.parent.mkdir(parents=True);link.symlink_to(outside.parent,target_is_directory=True)
        with self.assertRaisesRegex(OSError,'non-candidate'):s.cleanup_accessory_candidate_artifacts({'id':'a'})
        self.assertEqual(e,[]);self.assertTrue(outside.exists())

    def test_existing_images_preserve_order_exact_path_dedup_and_suffix_filter(self):
        s,b,r,e=self.fixture();a=self.write(r/'a.PNG');z=self.write(r/'z.txt');m=r/'missing.jpg'
        self.assertEqual(s.existing_source_image_paths({'source_files':[str(a),str(a),str(z),str(m)]}),[a])
        b['IMAGE_REFERENCE_SUFFIXES']={'.txt'};self.assertEqual(s.existing_source_image_paths({'source_files':[str(a),str(z)]}),[z])
        self.assertEqual(s.existing_source_image_paths({'source_files':None}),[])

    @unittest.skipIf(bool(BASELINE),'new assembly only')
    def test_actual_root_composition_and_independent_instances(self):
        s,a,ra,ea=self.fixture();t,b,rb,eb=self.fixture()
        source=(ROOT/'local_inspection_service/server.py').read_text(encoding='utf-8');tree=ast.parse(source)
        nodes=[n for n in tree.body if (isinstance(n,ast.ImportFrom) and n.module in ('accessories.candidate_artifacts','accessories.candidate_artifact_ports')) or (isinstance(n,ast.Assign) and any(isinstance(x,ast.Name) and x.id=='_candidate_artifacts' for x in n.targets)) or (isinstance(n,ast.FunctionDef) and n.name in NAMES)]
        self.assertEqual(len(nodes),5);ns=dict(a,Any=Any,Path=Path,__package__='local_inspection_service');exec(compile(ast.Module(body=nodes,type_ignores=[]),'<assembly>','exec'),ns)
        pa=self.write(ra/'uploads/accessory_candidates/a/x');pb=self.write(rb/'uploads/accessory_candidates/b/x')
        self.assertEqual(ns[NAMES[0]]({'id':'a'}),[str(pa.parent)]);self.assertTrue(pb.exists())
        self.assertEqual(t.cleanup_accessory_candidate_artifacts({'id':'b'}),[str(pb.parent)])
        a['safe_record_id']=lambda value:'renamed';p=self.write(ra/'uploads/accessory_candidates/renamed/x');self.assertEqual(s.cleanup_accessory_candidate_artifacts({'id':'a'}),[str(p.parent)])


if __name__=='__main__':unittest.main()
