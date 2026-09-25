import os,sys,uuid,unittest,threading,json,urllib.request,urllib.error
from pathlib import Path
from datetime import datetime,timedelta
from unittest.mock import patch,MagicMock
testdata=Path(__file__).resolve().parent/'results'/uuid.uuid4().hex;testdata.mkdir(parents=True);os.environ['TITLEVISION_DATA']=str(testdata)
sys.path.insert(0,str(Path(__file__).resolve().parents[1]));import server
class ServerTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  server.initialize();cls.http=server.ReportHTTPServer(('127.0.0.1',0),server.Handler);server.PORT=cls.http.server_port;cls.url=f'http://127.0.0.1:{server.PORT}';threading.Thread(target=cls.http.serve_forever,daemon=True).start()
 @classmethod
 def tearDownClass(cls):cls.http.shutdown();cls.http.server_close()
 def test_credential_roundtrip(self):
  server.store_credentials('test-user','test-only-password');self.assertEqual(server.credentials()['username'],'test-user');self.assertNotIn(b'test-only-password',(server.DATA/'credentials.dpapi').read_bytes());self.assertNotIn('password',json.dumps(server.public_state()))
 def test_health_is_independent_of_report_database(self):
  with patch.object(server,'db',side_effect=RuntimeError('database busy')):
   with urllib.request.urlopen(self.url+'/api/health') as response:value=json.load(response)
  self.assertTrue(value['ready']);self.assertEqual(value['processId'],os.getpid());self.assertNotIn('csrf',value)
 def test_windows_exclusive_listener_prevents_duplicate_engine(self):
  if os.name!='nt':self.skipTest('Windows socket ownership')
  with self.assertRaises(OSError):server.ThreadingHTTPServer(('127.0.0.1',server.PORT),server.Handler)
 def test_exclusive_port_can_restart_after_completed_request(self):
  from http.server import BaseHTTPRequestHandler
  class Handler(BaseHTTPRequestHandler):
   def log_message(self,*args):pass
   def do_GET(self):self.send_response(200);self.end_headers();self.wfile.write(b'ok')
  first=server.ReportHTTPServer(('127.0.0.1',0),Handler);port=first.server_port
  thread=threading.Thread(target=first.serve_forever,daemon=True);thread.start()
  try:
   with urllib.request.urlopen('http://127.0.0.1:'+str(port),timeout=3) as response:self.assertEqual(response.read(),b'ok')
  finally:first.shutdown();first.server_close();thread.join(timeout=3)
  second=server.ReportHTTPServer(('127.0.0.1',port),Handler);second.server_close()
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
 def test_schedule_policy_is_scoped_to_bundled_script_process(self):
  from types import SimpleNamespace
  with patch.object(server.subprocess,'run',return_value=SimpleNamespace(returncode=0,stderr='')) as command:
   server.install_schedule(False)
  args=command.call_args.args[0]
  self.assertEqual(args[:7],['powershell','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(server.ROOT/'schedule.ps1')])
  self.assertNotIn('Set-ExecutionPolicy',' '.join(args))
  self.assertEqual(args[-2:],['-Mode','Disable']);self.assertFalse(server.setting('schedule'))
 def test_schedule_policy_failure_does_not_change_saved_enabled_state(self):
  from types import SimpleNamespace
  server.save_setting('schedule',True)
  try:
   with patch.object(server.subprocess,'run',return_value=SimpleNamespace(returncode=1,stderr='PSSecurityException: running scripts is disabled')):
    with self.assertRaisesRegex(ValueError,'IT administrator'):server.install_schedule(False)
   self.assertTrue(server.setting('schedule'))
  finally:server.save_setting('schedule',False)
 def test_schedule_script_starts_under_inherited_restricted_policy(self):
  if os.name!='nt':self.skipTest('Windows PowerShell policy regression')
  # Exercise a harmless replacement script; never register or alter real tasks.
  folder=testdata/'schedule policy probe';folder.mkdir()
  (folder/'schedule.ps1').write_text("param([string]$Python,[string]$App,[string]$Mode)\n$ErrorActionPreference='Stop'\n[IO.File]::WriteAllText([IO.Path]::Combine($App,'script-ran.txt'),'ran')\n",encoding='utf8')
  with patch.dict(os.environ,{'PSExecutionPolicyPreference':'Restricted'}),patch.object(server,'ROOT',folder):
   baseline=server.subprocess.run(['powershell','-NoProfile','-NonInteractive','-File',str(folder/'schedule.ps1'),'-App',str(folder),'-Mode','Disable'],capture_output=True,text=True,creationflags=server.CREATE_NO_WINDOW,timeout=30)
   self.assertNotEqual(baseline.returncode,0,'The baseline must reproduce the script-policy failure')
   server.install_schedule(False)
   self.assertEqual((folder/'script-ran.txt').read_text(),'ran')
   self.assertEqual(os.environ['PSExecutionPolicyPreference'],'Restricted')
 def test_phase2_api_stays_off_before_october_and_requires_delete_confirmation(self):
  from datetime import date
  with patch.object(server.monthly_sync,'today',return_value=date(2026,9,30)):
   req=urllib.request.Request(self.url+'/api/main/create',json.dumps({'month':'2026-10'}).encode(),headers={'Origin':self.url,'X-CSRF-Token':server.TOKEN})
   with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(req)
   self.assertIn('1 October',error.exception.read().decode())
  with patch.object(server.monthly_sync,'delete') as delete:
   req=urllib.request.Request(self.url+'/api/main/delete',json.dumps({'month':'2026-10'}).encode(),headers={'Origin':self.url,'X-CSRF-Token':server.TOKEN})
   with self.assertRaises(urllib.error.HTTPError):urllib.request.urlopen(req)
   delete.assert_not_called()
 def test_daily_phase2_refresh_runs_after_validation_and_failure_keeps_daily_downloadable(self):
  from datetime import date
  rid=uuid.uuid4().hex;folder=server.DATA/'runs'/rid
  with server.db() as c:c.execute('INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?,?)',(rid,'2026-10-01','2026-10-01','queued','test','now',None,None,0,None))
  def process(args,directory,*a,**kw):
   (directory/'issues.json').write_text('[]')
   (directory/'validation.json').write_text(json.dumps({'passed':True,'count':1,'points':3}))
  def refresh(*args):
   self.assertTrue((folder/'validation.json').exists())
   self.assertEqual(args[-1],'2026-10')
   raise ValueError('Simulated month export failure')
  lock=MagicMock()
  try:
   with patch.object(server.monthly_sync,'today',return_value=date(2026,10,2)),patch.object(server,'credentials',return_value={'username':'test','password':'test'}),patch.object(server,'run_process',side_effect=process),patch.object(server.monthly_sync,'refresh',side_effect=refresh) as sync:
    server.perform(rid,lock);sync.assert_called_once()
   with server.db() as c:run=c.execute('SELECT * FROM runs WHERE id=?',(rid,)).fetchone()
   self.assertEqual(run['status'],'review');self.assertEqual(run['count'],1);self.assertEqual(run['points'],3)
   self.assertEqual(json.loads((folder/'issues.json').read_text())[0]['kind'],'month_refresh');lock.__exit__.assert_called_once()
  finally:
   with server.db() as c:c.execute('DELETE FROM runs WHERE id=?',(rid,))
if __name__=='__main__':unittest.main()
