import os,sys,uuid,unittest,threading,json,urllib.request,urllib.error
from pathlib import Path
from datetime import datetime,timedelta
from unittest.mock import patch
testdata=Path(__file__).resolve().parent/'results'/uuid.uuid4().hex;testdata.mkdir(parents=True);os.environ['TITLEVISION_DATA']=str(testdata)
sys.path.insert(0,str(Path(__file__).resolve().parents[1]));import server
class ServerTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  server.initialize();cls.http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler);server.PORT=cls.http.server_port;cls.url=f'http://127.0.0.1:{server.PORT}';threading.Thread(target=cls.http.serve_forever,daemon=True).start()
 @classmethod
 def tearDownClass(cls):cls.http.shutdown();cls.http.server_close()
 def test_credential_roundtrip(self):
  server.store_credentials('test-user','test-only-password');self.assertEqual(server.credentials()['username'],'test-user');self.assertNotIn(b'test-only-password',(server.DATA/'credentials.dpapi').read_bytes());self.assertNotIn('password',json.dumps(server.public_state()))
 def test_lock_blocks_overlap(self):
  with server.RunLock():
   with self.assertRaises(ValueError):
    with server.RunLock():pass
 def test_date_validation(self):
  with self.assertRaises(ValueError):server.date_range('2026-01-02','2026-01-01')
  with self.assertRaises(ValueError):server.date_range('2026-01-01','2026-03-01')
  today=datetime.now(server.IST).date().isoformat()
  with self.assertRaises(ValueError):server.date_range(today,today)
 def test_cross_origin_mutation_is_rejected(self):
  req=urllib.request.Request(self.url+'/api/run',b'{}',headers={'Origin':'https://example.org','Content-Type':'application/json','X-CSRF-Token':server.TOKEN})
  with self.assertRaises(urllib.error.HTTPError) as e:urllib.request.urlopen(req)
  self.assertEqual(e.exception.code,400)
 def test_main_workbook_requires_same_origin_and_explicit_choice(self):
  path=self.url+'/api/runs/'+'b'*32+'/main'
  with patch.object(server.main_workbook,'decide') as decide:
   req=urllib.request.Request(path,b'{"add":true}',headers={'Origin':'https://example.org','X-CSRF-Token':server.TOKEN})
   with self.assertRaises(urllib.error.HTTPError):urllib.request.urlopen(req)
   decide.assert_not_called()
  req=urllib.request.Request(path,b'{"add":"yes"}',headers={'Origin':self.url,'X-CSRF-Token':server.TOKEN})
  with self.assertRaises(urllib.error.HTTPError):urllib.request.urlopen(req)
 def test_main_choice_is_recorded_and_main_download_has_stable_name(self):
  rid='c'*32
  with server.db() as c:c.execute('INSERT OR REPLACE INTO runs VALUES (?,?,?,?,?,?,?,?,?,?)',(rid,'2026-01-01','2026-01-01','review','test','now',2,3,1,None))
  req=urllib.request.Request(self.url+'/api/runs/'+rid+'/main',b'{"add":false}',headers={'Origin':self.url,'X-CSRF-Token':server.TOKEN})
  with urllib.request.urlopen(req) as response:self.assertEqual(json.load(response)['choice'],'no')
  state=server.public_state();self.assertEqual(next(r for r in state['runs'] if r['id']==rid)['mainChoice'],'no')
  report=testdata/'main'/'2026-01'/'test';report.mkdir(parents=True);(report/'report.xlsx').write_bytes(b'workbook')
  with server.db() as c:c.execute('INSERT INTO main_books VALUES (?,?,?,?,?,?,?,?)',('2026-01',str(report.relative_to(testdata)),'2026-01-01','2026-01-01',2,3,1,'now'))
  with urllib.request.urlopen(self.url+'/api/main/2026-01/download') as response:
   self.assertIn('TitleVision Main Error Report - 2026-01.xlsx',response.headers['Content-Disposition']);self.assertEqual(response.read(),b'workbook')
  with server.db() as c:c.execute('DELETE FROM runs WHERE id=?',(rid,))
 def test_unsafe_host_rejected(self):
  req=urllib.request.Request(self.url+'/api/state',headers={'Host':'attacker.example'})
  with self.assertRaises(urllib.error.HTTPError):urllib.request.urlopen(req)
 def test_private_files_not_served(self):
  with self.assertRaises(urllib.error.HTTPError) as e:urllib.request.urlopen(self.url+'/data/credentials.dpapi')
  self.assertEqual(e.exception.code,404)
 def test_legacy_download_is_rebuilt_without_changing_original(self):
  folder=testdata/'legacy';folder.mkdir();(folder/'report.xlsx').write_bytes(b'original')
  for name in ('payload.json','collection.json'):(folder/name).write_text('{}')
  def rebuild(args,directory,**kwargs):
   (directory/'report.xlsx').write_bytes(b'corrected')
   (directory/'validation.json').write_text(json.dumps({'passed':True,'workbookFormatVersion':3}))
  with patch.object(server,'run_process',side_effect=rebuild) as build:
   corrected=server.downloadable_report(folder)
   self.assertEqual(corrected.read_bytes(),b'corrected');self.assertEqual(build.call_count,2)
   self.assertEqual(server.downloadable_report(folder),corrected);self.assertEqual(build.call_count,2)
  self.assertEqual((folder/'report.xlsx').read_bytes(),b'original')
 def test_failed_legacy_rebuild_is_not_downloaded(self):
  folder=testdata/'invalid-legacy';folder.mkdir()
  for name in ('payload.json','collection.json'):(folder/name).write_text('{}')
  with patch.object(server,'run_process'):
   with self.assertRaisesRegex(ValueError,'did not pass'):server.downloadable_report(folder)
 def test_pending_report_download_rejected(self):
  with server.db() as c:c.execute('INSERT OR REPLACE INTO runs VALUES (?,?,?,?,?,?,?,?,?,?)',('a'*32,'2026-01-01','2026-01-01','failed','failure','now',None,None,0,None))
  with self.assertRaises(urllib.error.HTTPError):urllib.request.urlopen(self.url+'/api/runs/'+'a'*32+'/download')
 def test_schedule_is_previous_calendar_day_at_845(self):
  server.save_setting('schedule',True)
  class Clock(datetime):
   @classmethod
   def now(cls,tz=None):return cls(2026,9,21,8,45,tzinfo=server.IST)
  with patch.object(server,'datetime',Clock),patch.object(server,'launch_run') as launch:
   server.scheduled();launch.assert_called_once_with('2026-09-20','2026-09-20','2026-09-21',False)
  class Early(Clock):
   @classmethod
   def now(cls,tz=None):return cls(2026,9,21,8,44,tzinfo=server.IST)
  with patch.object(server,'datetime',Early),patch.object(server,'launch_run') as launch:
   server.scheduled();launch.assert_not_called()
  server.save_setting('schedule',False)
 def test_schedule_requires_verified_live_report(self):
  with patch.object(server.subprocess,'run') as command:
   with self.assertRaisesRegex(ValueError,'verified live report'):server.install_schedule(True)
   command.assert_not_called()
if __name__=='__main__':unittest.main()
