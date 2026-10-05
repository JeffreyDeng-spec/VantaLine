"""Directory preparation and one-time local-path migration state contracts."""
import ast,os,sys,tempfile,threading,unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
BASELINE=os.environ.get('VANTALINE_DIRECTORY_LIFECYCLE_BASELINE_SOURCE')
PATH_NAMES=('UPLOAD_DIR','OUTPUT_DIR','DATA_DIR','NORMALIZED_DIR','TRAINING_JOBS_DIR','TRAINING_TASKS_DIR','ACCESSORY_CANDIDATES_DIR','AUTO_OPTIMIZE_DIR','IMAGE_WORKER_LOG_DIR','BACKGROUND_DIR','BACKGROUND_SETS_DIR')
ROOT_NAMES=('DATA_DIR','BACKGROUND_DIR','STANDARDIZED_MANUALS_DIR','PRECISE_MANUALS_DIR')
def create(b):
 if BASELINE:
  nodes=[n for n in ast.parse(Path(BASELINE).read_text(encoding='utf-8-sig')).body if isinstance(n,ast.FunctionDef) and n.name in ('ensure_dirs','migrate_persisted_local_paths_once')];assert len(nodes)==2
  ns=dict(b,Path=Path);exec(compile(ast.Module(body=nodes,type_ignores=[]),BASELINE,'exec'),ns);return SimpleNamespace(ensure_dirs=ns['ensure_dirs'],migrate_persisted_local_paths_once=ns['migrate_persisted_local_paths_once']),ns
 from local_inspection_service.runtime.directories import ServiceDirectories,LocalPathMigration
 migration=LocalPathMigration(lambda:b['CONFIG_PATH'],lambda:tuple(b[n] for n in ROOT_NAMES),lambda:b['_business_files'],lambda:b['migrate_json_file_paths'])
 b['migrate_persisted_local_paths_once']=migration.run
 dirs=ServiceDirectories(lambda:tuple(b[n] for n in PATH_NAMES),lambda:b['CONFIG_PATH'],lambda:b['DEFAULT_CONFIG'],lambda:b['_business_files'],lambda:b['save_config'],lambda:b['migrate_persisted_local_paths_once'])
 return SimpleNamespace(ensure_dirs=dirs.ensure,migrate_persisted_local_paths_once=migration.run,migration=migration),b
class Contracts(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name);self.migrated=[];self.saves=[]
  b={n:self.root/n.lower() for n in set(PATH_NAMES+ROOT_NAMES)};b.update(CONFIG_PATH=self.root/'app.json',DEFAULT_CONFIG={'default':1},_business_files=SimpleNamespace(exists=lambda p:p.exists(),glob=lambda p,pattern,recursive=False:p.rglob(pattern) if recursive else p.glob(pattern),is_file=lambda p:p.is_file()),save_config=lambda c:self.saves.append(c),migrate_json_file_paths=lambda p:self.migrated.append(p),_path_migration_done=False,_path_migration_lock=threading.RLock());self.s,self.b=create(b)
 def test_ensure_creates_all_and_preserves_default_alias(self):
  self.s.ensure_dirs();self.assertTrue(all(self.b[n].is_dir() for n in PATH_NAMES));self.assertIs(self.saves[0],self.b['DEFAULT_CONFIG']);self.assertEqual(self.migrated,[self.b['CONFIG_PATH']])
 def test_existing_config_skips_save(self):
  self.b['CONFIG_PATH'].write_text('{}');self.s.ensure_dirs();self.assertEqual(self.saves,[]);self.assertEqual(self.migrated,[self.b['CONFIG_PATH']])
 def test_directory_failure_prevents_save_and_migration(self):
  self.b['DATA_DIR'].write_text('occupied')
  with self.assertRaises(FileExistsError):self.s.ensure_dirs()
  self.assertTrue(self.b['UPLOAD_DIR'].is_dir());self.assertTrue(self.b['OUTPUT_DIR'].is_dir());self.assertFalse(self.b['NORMALIZED_DIR'].exists());self.assertEqual(self.saves,[]);self.assertEqual(self.migrated,[])
 def test_save_failure_and_retry(self):
  sentinel=RuntimeError('save');self.b['save_config']=Mock(side_effect=sentinel)
  with self.assertRaises(RuntimeError) as err:self.s.ensure_dirs()
  self.assertIs(err.exception,sentinel);self.assertEqual(self.migrated,[]);self.b['save_config']=lambda c:None;self.s.ensure_dirs();self.assertEqual(len(self.migrated),1)
 def test_migration_sorted_dedup_roots_and_json_files(self):
  data=self.b['DATA_DIR'];(data/'nested').mkdir(parents=True);(data/'z.json').write_text('{}');(data/'nested/a.json').write_text('{}');(data/'nested/b.txt').write_text('x');(data/'folder.json').mkdir();self.b['BACKGROUND_DIR']=data
  self.s.migrate_persisted_local_paths_once();self.assertEqual(self.migrated,sorted([self.b['CONFIG_PATH'],data/'z.json',data/'nested/a.json']));self.s.migrate_persisted_local_paths_once();self.assertEqual(len(self.migrated),3)
 def test_callback_false_still_marks_done(self):
  calls=[];self.b['migrate_json_file_paths']=lambda p:calls.append(p) and False;self.s.migrate_persisted_local_paths_once();self.s.migrate_persisted_local_paths_once();self.assertEqual(calls,[self.b['CONFIG_PATH']])
 def test_partial_failure_retry_restarts_sorted_candidates(self):
  data=self.b['DATA_DIR'];data.mkdir();second=data/'z.json';second.write_text('{}');calls=[]
  def migrate(p):
   calls.append(p)
   if p==second:raise RuntimeError('second')
  self.b['migrate_json_file_paths']=migrate
  with self.assertRaisesRegex(RuntimeError,'second'):self.s.migrate_persisted_local_paths_once()
  self.b['migrate_json_file_paths']=lambda p:calls.append(p);self.s.migrate_persisted_local_paths_once();self.assertEqual(calls,[self.b['CONFIG_PATH'],second,self.b['CONFIG_PATH'],second])
 def test_two_threads_perform_one_migration(self):
  entered=threading.Event();release=threading.Event();calls=[]
  def migrate(p):calls.append(p);entered.set();self.assertTrue(release.wait(5))
  self.b['migrate_json_file_paths']=migrate
  with ThreadPoolExecutor(max_workers=2) as pool:
   first=pool.submit(self.s.migrate_persisted_local_paths_once);self.assertTrue(entered.wait(5));second=pool.submit(self.s.migrate_persisted_local_paths_once);release.set();first.result(5);second.result(5)
  self.assertEqual(calls,[self.b['CONFIG_PATH']])
 def test_late_migration_callback_selected_after_save(self):
  marker=[];self.b['save_config']=lambda c:self.b.__setitem__('migrate_persisted_local_paths_once',lambda:marker.append('new'));self.s.ensure_dirs();self.assertEqual(marker,['new']);self.assertEqual(self.migrated,[])
 @unittest.skipIf(bool(BASELINE),'new lifecycle ownership only')
 def test_distinct_migration_instances(self):
  from local_inspection_service.runtime.directories import LocalPathMigration
  second=LocalPathMigration(lambda:self.b['CONFIG_PATH'],lambda:(),lambda:self.b['_business_files'],lambda:self.b['migrate_json_file_paths']);self.s.migrate_persisted_local_paths_once();self.assertFalse(second.done);second.run();self.assertEqual(len(self.migrated),2);self.assertIsNot(second.lock,self.s.migration.lock)
if __name__=='__main__':unittest.main()
