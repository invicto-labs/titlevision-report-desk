import sys,sqlite3,json,uuid,shutil,unittest,subprocess
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import state_store as module
import database_backup

class StoreTests(unittest.TestCase):
 def setUp(self):
  self.data=Path(__file__).resolve().parent/'results'/('store-'+uuid.uuid4().hex)
  self.data.mkdir(parents=True);self.store=module.Store(self.data)
  with sqlite3.connect(self.data/'reporting.sqlite') as c:
   c.execute('create table settings(key primary key,value)');c.execute("insert into settings values ('shared_folder','network-folder')")
   c.execute('create table main_edits(id primary key,value)');c.execute("insert into main_edits values (1,'private name')")
  with self.store.connect():pass
 def count(self):
  with self.store.connect() as c:return c.execute('select count(*) from main_edits').fetchone()[0]
 def test_migrate_and_ignore_legacy_writer(self):
  (self.data/'reporting.sqlite').write_bytes(b'old app damage')
  self.assertEqual(self.count(),1)
  with self.store.connect() as c:self.assertEqual(c.execute('select value from settings').fetchone()[0],'network-folder')
  self.assertNotIn('private name',(self.store.folder/'database-events.jsonl').read_text())
 def test_unverified_changes_block(self):
  with sqlite3.connect(self.store.path) as c:c.execute('delete from settings')
  with self.assertRaises(module.StateFault):self.count()
  self.assertTrue(self.store.fault.exists())
 def test_missing_database_does_not_restore_legacy(self):
  self.store.path.unlink()
  with self.assertRaises(module.StateFault):self.count()
  self.assertFalse(self.store.path.exists())
 def test_in_place_rollback_blocks_even_if_file_identity_unchanged(self):
  previous=self.store.path.read_bytes()
  with self.store.connect() as c:c.execute("insert into main_edits values (2,'new edit')")
  self.store.path.write_bytes(previous)
  with self.assertRaises(module.StateFault):self.count()
 def test_corruption_is_sticky_and_does_not_create_empty_database(self):
  self.store.path.write_bytes(b'broken sqlite')
  with self.assertRaises(module.StateFault):self.count()
  self.assertTrue(self.store.fault.exists())
 def test_lost_configuration_migration_rejected(self):
  other=self.data/'other';other.mkdir();backups=other/'database-backups';backups.mkdir()
  shutil.copy2(self.data/'reporting.sqlite',other/'reporting.sqlite')
  shutil.copy2(self.data/'reporting.sqlite',backups/'reporting-good.sqlite')
  with sqlite3.connect(other/'reporting.sqlite') as c:c.execute('delete from settings');c.execute('delete from main_edits')
  with self.assertRaises(module.StateFault):
   with module.Store(other).connect():pass
 def test_replaced_file_blocked(self):
  copy=self.store.folder/'copy.sqlite';shutil.copy2(self.store.path,copy);copy.replace(self.store.path)
  with self.assertRaises(module.StateFault):self.count()
 def test_exception_rolls_back_and_nested_savepoint(self):
  with self.assertRaises(ValueError):
   with self.store.connect() as c:c.execute('delete from main_edits');raise ValueError('abort')
  self.assertEqual(self.count(),1)
  with self.store.connect() as c:
   c.execute("insert into main_edits values (2,'saved')")
   with self.assertRaises(ValueError):
    with self.store.connect() as nested:nested.execute('delete from main_edits');raise ValueError('abort nested')
  self.assertEqual(self.count(),2)
 def test_crash_after_commit_recovers(self):
  original=module.atomic_json
  def write(path,value):
   if path==self.store.witness:raise OSError('power loss')
   return original(path,value)
  with patch.object(module,'atomic_json',side_effect=write):
   with self.assertRaises(OSError):
    with self.store.connect() as c:c.execute("insert into main_edits values (2,'saved')")
  self.assertTrue(self.store.pending.exists());self.assertEqual(self.count(),2);self.assertFalse(self.store.pending.exists())
 def test_crash_before_commit_recovers(self):
  witness=json.loads(self.store.witness.read_text());after=dict(witness,digest='uncommitted')
  module.atomic_json(self.store.pending,{'before':witness['digest'],'after':after})
  self.assertEqual(self.count(),1);self.assertFalse(self.store.pending.exists())
 def test_crash_after_witness_before_cleanup_recovers(self):
  witness=json.loads(self.store.witness.read_text())
  module.atomic_json(self.store.pending,{'before':'earlier','after':witness})
  self.assertEqual(self.count(),1)
 def test_mismatched_interrupted_commit_blocks(self):
  witness=json.loads(self.store.witness.read_text())
  module.atomic_json(self.store.pending,{'before':'wrong','after':dict(witness,digest='also wrong')})
  with self.assertRaises(module.StateFault):self.count()
 def test_backup_verifies_and_preserves_good_copy(self):
  backup=database_backup.create(self.data);before=backup.read_bytes()
  with sqlite3.connect(self.store.path) as c:c.execute('delete from main_edits')
  with self.assertRaises(module.StateFault):database_backup.create(self.data)
  self.assertEqual(backup.read_bytes(),before)
 def test_concurrent_processes_preserve_all_writes(self):
  script="import sys;sys.path.insert(0,sys.argv[1]);from state_store import Store;s=Store(sys.argv[2]);\nfor i in range(15):\n with s.connect() as c:c.execute('insert into main_edits values (?,?)',(int(sys.argv[3])+i,'saved'))"
  procs=[subprocess.Popen([sys.executable,'-c',script,str(Path(module.__file__).parent),str(self.data),str(start)],stdout=subprocess.PIPE,stderr=subprocess.PIPE) for start in (100,200)]
  for p in procs:
   out,err=p.communicate(timeout=45);self.assertEqual(p.returncode,0,err.decode())
  self.assertEqual(self.count(),31)

if __name__=='__main__':unittest.main()
