"""Service path rebasing, public projection and scoped output behavior."""
import ast,json,os,re,sys,tempfile
from contextvars import ContextVar
from dataclasses import fields
from pathlib import Path,PurePosixPath
from types import SimpleNamespace
from typing import Any
import unittest
from unittest.mock import Mock
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from canonical_application_source_contract import read_checked_application_source
BASELINE=os.environ.get('VANTALINE_SERVICE_PATHS_BASELINE_SOURCE')
NAMES=('service_rebased_path','rebase_stale_local_path_text','rebase_stale_local_payload_text','public_path_sanitized','migrate_json_file_paths','resolve_service_path','path_is_under','public_output_url','public_output_url_for_existing','output_write_dir','output_write_dir_for_owner','output_url')
def create(b):
 if BASELINE:
  nodes=[n for n in ast.parse(Path(BASELINE).read_text(encoding='utf-8-sig')).body if isinstance(n,ast.FunctionDef) and n.name in NAMES];assert len(nodes)==12
  ns=dict(b,Any=Any,Path=Path,PurePosixPath=PurePosixPath,json=json,re=re);exec(compile(ast.Module(body=nodes,type_ignores=[]),BASELINE,'exec'),ns);return SimpleNamespace(**{n:ns[n] for n in NAMES}),ns
 from local_inspection_service.runtime.service_paths import ServicePaths
 from local_inspection_service.runtime.service_path_ports import ServicePathSettings,PathProjectionPolicy,PathCalls,PathFiles,PathIdentity
 def ports(cls):return cls(**{f.name:lambda name=f.name:b[name] for f in fields(cls)})
 service=ServicePaths(ports(ServicePathSettings),ports(PathProjectionPolicy),ports(PathCalls),ports(PathFiles),ports(PathIdentity))
 for name in NAMES:
  if name not in b:b[name]=getattr(service,name)
 return service,b
class Contracts(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(prefix="service-path-contract-",dir=ROOT);self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name);self.identity=ContextVar('path_identity',default=None)
  files=SimpleNamespace(exists=lambda p:p.exists(),read_text=lambda p,**kw:p.read_text(**kw),write_text=lambda p,s,**kw:p.write_text(s,**kw))
  b=dict(ROOT=self.root,APP_DIR=self.root/'local_inspection_service',OUTPUT_DIR=self.root/'outputs',STALE_REPO_PATH_PREFIXES=('C:/old/assembly_line_optimize','/old/project'),REMOVED_PHASE1_PUBLIC_CONFIG_KEYS={'retired'},LEGACY_OWNER_ID='legacy',SYSTEM_OWNER_ID='system',_business_files=files,_request_user=self.identity,user_is_admin=lambda u:u.get('admin',False))
  self.s,self.b=create(b)
 def test_rebase_markers_first_position_and_nonmatches(self):
  self.assertEqual(self.s.service_rebased_path(Path('C:/old/assembly_line_optimize/local_inspection_service/file')),self.root/'local_inspection_service/file')
  self.assertEqual(self.s.service_rebased_path(Path('/old/local_inspection_service/file')),self.root/'local_inspection_service/file');self.assertIsNone(self.s.service_rebased_path(Path('/else/file')))
 def test_text_and_json_escaped_rebasing(self):
  for raw in ('C:/old/assembly_line_optimize/a','C:\\old\\assembly_line_optimize\\a','/old/project/a'):self.assertEqual(self.s.rebase_stale_local_path_text(raw),self.root.as_posix()+'/a')
  self.assertEqual(self.s.rebase_stale_local_path_text(''),'');raw=json.dumps({'p':'C:\\old\\assembly_line_optimize\\a'});out=self.s.rebase_stale_local_payload_text(raw);self.assertNotIn('assembly_line_optimize',out);self.assertEqual(json.loads(out)['p'],self.root.as_posix()+'\\a')
 def test_recursive_projection_filtering_and_nonstring_identity(self):
  atom=object();value={'model_profiles':1,'profile_snapshot':2,'secret_ref':3,'operational':4,'retired':5,'/old/project/key':[{'p':'/old/project/a'},atom],7:('unchanged',)};out=self.s.public_path_sanitized(value)
  self.assertEqual(set(out),{self.root.as_posix()+'/key',7});self.assertEqual(out[self.root.as_posix()+'/key'][0]['p'],self.root.as_posix()+'/a');self.assertIs(out[self.root.as_posix()+'/key'][1],atom);self.assertIs(out[7],value[7]);self.assertIn('secret_ref',value)
 def test_migration_missing_unchanged_invalid_and_success(self):
  p=self.root/'fixture.json';self.assertFalse(self.s.migrate_json_file_paths(p));p.write_text('{"x":1}');self.assertFalse(self.s.migrate_json_file_paths(p));self.assertEqual(p.read_text(),'{"x":1}')
  p.write_text('{"p":"/old/project/a","secret_ref":"synthetic"}');self.assertTrue(self.s.migrate_json_file_paths(p));self.assertEqual(json.loads(p.read_text()),{'p':self.root.as_posix()+'/a'})
  p.write_text('invalid /old/project/file');self.assertTrue(self.s.migrate_json_file_paths(p));self.assertEqual(p.read_text(),'invalid '+self.root.as_posix()+'/file');p.write_text('invalid unchanged');self.assertFalse(self.s.migrate_json_file_paths(p))
 def test_migration_error_boundaries(self):
  p=self.root/'p';p.write_text('{"p":"/old/project/a"}');self.b['_business_files'].write_text=Mock(side_effect=OSError('disk'));self.assertFalse(self.s.migrate_json_file_paths(p));self.b['_business_files'].read_text=Mock(side_effect=RuntimeError('not os'))
  with self.assertRaisesRegex(RuntimeError,'not os'):self.s.migrate_json_file_paths(p)
 def test_resolution_order_dedup_and_blank(self):
  observed=[];self.b['_business_files'].exists=lambda p:observed.append(p) or p==self.root/'relative';self.assertEqual(self.s.resolve_service_path('relative'),(self.root/'relative').resolve());self.assertEqual(observed,[self.root/'local_inspection_service/relative',self.root/'relative'])
  observed.clear();self.assertEqual(self.s.resolve_service_path(''),Path(''));self.assertEqual(observed,[])
  self.b['_business_files'].exists=lambda p:False;self.assertEqual(self.s.resolve_service_path('missing'),self.root/'local_inspection_service/missing')
 def test_write_rebase_skips_exists_and_read_existing_wins(self):
  self.b['_business_files'].exists=Mock(side_effect=AssertionError('write should not probe'));self.assertEqual(self.s.resolve_service_path('/old/local_inspection_service/file',for_write=True),self.root/'local_inspection_service/file');self.b['_business_files'].exists.assert_not_called()
  self.b['_business_files'].exists=lambda p:p==Path('/old/local_inspection_service/file');self.assertEqual(self.s.resolve_service_path('/old/local_inspection_service/file'),Path('/old/local_inspection_service/file').resolve())
 def test_urls_existing_containment_and_symlink(self):
  out=self.root/'outputs';out.mkdir();p=out/'file';p.write_text('fixture');self.assertEqual(self.s.public_output_url(p),'/outputs/file');self.assertEqual(self.s.output_url(p),'/outputs/file');self.assertEqual(self.s.public_output_url(self.root/'else'),'');self.assertEqual(self.s.public_output_url_for_existing(p),'/outputs/file');self.assertEqual(self.s.public_output_url_for_existing(out/'missing'),'')
  if os.name!='nt':
   (out/'escape').symlink_to(self.root,target_is_directory=True);self.assertFalse(self.s.path_is_under(out/'escape/file',out));self.assertEqual(self.s.public_output_url_for_existing(out/'escape/file'),'')
 def test_output_kind_and_owner_placement(self):
  for owner,suffix in [('',Path('')),('legacy',Path('')),('system',Path('')),('alice',Path('users/alice'))]:
   p=self.s.output_write_dir_for_owner(' ../odd kind.. ',owner);self.assertEqual(p,self.root/'outputs'/suffix/'odd_kind');self.assertTrue(p.is_dir())
  self.assertEqual(self.s.output_write_dir_for_owner('',' alice '),self.root/'outputs/users/alice')
 def test_request_identity_resolved_per_call_and_admin_shared(self):
  for user,relative in [(None,'outputs/a'),({'id':'alice'},'outputs/users/alice/a'),({'id':'bob'},'outputs/users/bob/a'),({'id':'admin','admin':True},'outputs/a')]:
   token=self.identity.set(user)
   try:self.assertEqual(self.s.output_write_dir('a'),self.root/relative)
   finally:self.identity.reset(token)
 @unittest.skipIf(bool(BASELINE),'candidate assembly only')
 def test_actual_assembly_and_light_import(self):
  import subprocess
  from application_integration_source_contract import restore_path_configuration_root
  tree=ast.parse(restore_path_configuration_root(read_checked_application_source(ROOT / 'local_inspection_service/server.py', encoding='utf-8')));binding=next(n.value for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='_service_paths' for t in n.targets));count=0
  for group in binding.keywords:
   for kw in group.value.keywords:self.assertIsInstance(kw.value,ast.Lambda);self.assertEqual(kw.arg,kw.value.body.id);count+=1
  self.assertEqual(count,18)
  subprocess.run([sys.executable,'-B','-c',"import sys; import local_inspection_service.runtime.service_paths; assert 'local_inspection_service.server' not in sys.modules; assert 'fastapi' not in sys.modules"],cwd=ROOT,check=True)
if __name__=='__main__':unittest.main()
