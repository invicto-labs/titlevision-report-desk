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
 def test_team_summary_endpoint_reads_workbook_without_mutation(self):
  with patch.object(server.dashboard,'summary',return_value={'available':True,'total':7,'rows':[]}) as summary:
   with urllib.request.urlopen(self.url+'/api/main/2026-10/summary') as response:self.assertEqual(json.load(response)['total'],7)
   self.assertEqual(summary.call_args.args,(server.DATA,server.db,'2026-10'))
 def test_health_is_independent_of_report_database(self):
  with patch.object(server,'db',side_effect=RuntimeError('database busy')):
   with urllib.request.urlopen(self.url+'/api/health') as response:value=json.load(response)
  self.assertTrue(value['ready']);self.assertEqual(value['processId'],os.getpid());self.assertNotIn('csrf',value)
 def post(self,path,body):
  request=urllib.request.Request(self.url+path,json.dumps(body).encode(),headers={'Origin':self.url,'X-CSRF-Token':server.TOKEN,'Content-Type':'application/json'})
  return urllib.request.urlopen(request)
 def test_every_json_mutation_rejects_wrong_body_shape_and_cross_origin(self):
  paths=['/api/run','/api/credentials','/api/schedule','/api/shared/configure','/api/shared/sync','/api/main/create','/api/main/delete','/api/main/refresh','/api/update/check','/api/update/install','/api/update/cancel','/api/update/token','/api/runs/'+'a'*32+'/main']
  for path in paths:
   with self.subTest(path=path):
    for body in (None,[],1,'text'):
     with self.assertRaises(urllib.error.HTTPError) as error:self.post(path,body)
     self.assertEqual(error.exception.code,400);self.assertIn('JSON object',json.load(error.exception)['error'])
    req=urllib.request.Request(self.url+path,b'{}',headers={'Origin':'https://example.com','X-CSRF-Token':server.TOKEN})
    with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(req)
    self.assertEqual(error.exception.code,400)
 def test_invalid_field_types_return_json_errors(self):
  for path,body in [('/api/credentials',{'username':123,'password':'x'}),('/api/credentials',{'username':'x','password':[]}),('/api/update/token',{'token':1}),('/api/run',{'start':None,'end':[]} ),('/api/schedule',{'enabled':'yes'})]:
   with self.assertRaises(urllib.error.HTTPError) as error:self.post(path,body)
   self.assertEqual(error.exception.code,400);self.assertIn('error',json.load(error.exception))
 def test_update_endpoints_work_while_monthly_refresh_holds_worker_lock(self):
  with server.RunLock(),patch.object(server.UPDATES,'install',return_value={'available':True}) as install,patch.object(server.UPDATES,'cancel',return_value={'message':'Cancelled'}) as cancel:
   with self.post('/api/update/install',{}) as response:self.assertEqual(response.status,202)
   with self.post('/api/update/cancel',{}) as response:self.assertEqual(response.status,200)
   install.assert_called_once();cancel.assert_called_once()
 def test_worker_activity_covers_refresh_without_daily_run(self):
  self.assertFalse(server.worker_busy())
  with server.RunLock():self.assertTrue(server.public_state()['activity']['busy'])
  self.assertFalse(server.public_state()['activity']['busy'])
 def test_static_health_state_and_unknown_routes(self):
  for path in ('/','/app.js','/style.css','/favicon.svg','/api/health','/api/state'):
   with urllib.request.urlopen(self.url+path) as response:self.assertEqual(response.status,200);self.assertEqual(response.headers['Cache-Control'],'no-store')
  for path in ('/unknown','/api/runs/'+'a'*32+'/unknown','/api/runs/'+'a'*32+'/download/extra'):
   with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(self.url+path)
   self.assertEqual(error.exception.code,404)
 def test_settings_and_control_routes_dispatch_in_isolated_data(self):
  with patch.object(server,'launch_run',return_value='test-id') as launch:
   with self.post('/api/run',{'start':'2026-10-01','end':'2026-10-01'}) as response:self.assertEqual(json.load(response)['id'],'test-id')
  with patch.object(server,'store_credentials') as store:
   with self.post('/api/credentials',{'username':' test ','password':'test-secret'}) as response:self.assertTrue(json.load(response)['saved'])
   store.assert_called_once_with('test','test-secret')
  with patch.object(server,'install_schedule') as schedule:
   with self.post('/api/schedule',{'enabled':False}) as response:self.assertFalse(json.load(response)['enabled'])
   schedule.assert_called_once_with(False)
  with patch.object(server.UPDATES,'check',return_value={'available':False}),patch.object(server.UPDATES,'save_token') as token:
   with self.post('/api/update/check',{}) as response:self.assertFalse(json.load(response)['available'])
   with self.post('/api/update/token',{'token':' test '}) as response:self.assertTrue(json.load(response)['saved'])
   token.assert_called_once_with('test')
 def test_monthly_routes_and_shared_sync_dispatch_without_live_collection(self):
  month='2026-08'
  with patch.object(server.monthly_sync,'create',return_value={'message':'created'}),patch.object(server.monthly_sync,'delete',return_value={'message':'deleted'}),patch.object(server.monthly_sync,'refresh') as refresh,patch.object(server,'pull_shared'),patch.object(server,'publish_shared'),patch.object(server.shared_workbook,'configured',return_value=''):
   with self.post('/api/main/create',{'month':month}) as response:self.assertEqual(json.load(response)['message'],'created')
   with self.post('/api/main/delete',{'month':month,'confirm':True}) as response:self.assertEqual(json.load(response)['message'],'deleted')
   with server.db() as c:c.execute('INSERT INTO main_books VALUES (?,?,?,?,?,?,?,?)',(month,'fixture','2026-08-01','2026-08-01',0,0,1,'now'))
   try:
    with self.post('/api/main/refresh',{'month':month}) as response:self.assertEqual(response.status,200)
    self.assertEqual(refresh.call_args.args[-1],month)
   finally:
    with server.db() as c:c.execute('DELETE FROM main_books WHERE month=?',(month,))
  with patch.object(server.shared_workbook,'configured',return_value='test-share'),patch.object(server.shared_workbook,'sync') as sync:
   with self.post('/api/shared/sync',{}) as response:self.assertIn('Synchronized',json.load(response)['message'])
   sync.assert_called_once()
 def test_completed_run_details_and_excel_download(self):
  rid=uuid.uuid4().hex;folder=server.DATA/'runs'/rid;folder.mkdir(parents=True)
  (folder/'issues.json').write_text('[]');file=folder/'report.xlsx';file.write_bytes(b'verified workbook')
  with server.db() as c:c.execute('INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?,?)',(rid,'2026-08-01','2026-08-01','complete','done','now',1,3,0,None))
  try:
   with urllib.request.urlopen(self.url+'/api/runs/'+rid) as response:self.assertEqual(json.load(response)['run']['id'],rid)
   with patch.object(server,'downloadable_report',return_value=file):
    with urllib.request.urlopen(self.url+'/api/runs/'+rid+'/download') as response:self.assertEqual(response.read(),b'verified workbook')
  finally:
   with server.db() as c:c.execute('DELETE FROM runs WHERE id=?',(rid,))
 def test_current_excel_download_returns_exact_bytes_and_rejects_corruption(self):
  with patch.object(server.dashboard,'workbook_path',return_value=(Path('shared.xlsx'),'shared')),patch.object(server.dashboard,'read_file',return_value=(b'exact workbook bytes',None)),patch.object(server.dashboard,'parse') as parse:
   with urllib.request.urlopen(self.url+'/api/main/2026-10/current') as response:
    self.assertEqual(response.read(),b'exact workbook bytes')
    self.assertIn('2026-10.xlsx',response.headers['Content-Disposition'])
   parse.assert_called_once_with(b'exact workbook bytes')
   from zipfile import BadZipFile
   parse.side_effect=BadZipFile('invalid ZIP')
   with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(self.url+'/api/main/2026-10/current')
   self.assertEqual(error.exception.code,400)
   self.assertIn('Cannot download',json.load(error.exception)['error'])
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
 def test_excel_edits_require_csrf_and_pass_raw_workbook_under_worker_lock(self):
  path=self.url+'/api/main/edits'
  with patch.object(server.manual_edits,'save',return_value={'message':'Saved'}) as save:
   req=urllib.request.Request(path,b'workbook',headers={'Origin':self.url,'X-Workbook-Month':'2026-10'})
   with self.assertRaises(urllib.error.HTTPError):urllib.request.urlopen(req)
   save.assert_not_called()
   req=urllib.request.Request(path,b'workbook',headers={'Origin':self.url,'X-CSRF-Token':server.TOKEN,'X-Workbook-Month':'2026-10'})
   with urllib.request.urlopen(req) as response:self.assertEqual(json.load(response)['message'],'Saved')
   self.assertEqual(save.call_args.args[-2:],('2026-10',b'workbook'))
   with server.RunLock():
    with self.assertRaises(urllib.error.HTTPError):urllib.request.urlopen(req)
   self.assertEqual(save.call_count,1)
 def test_shared_folder_configuration_requires_same_origin_and_worker_lock(self):
  path=self.url+'/api/shared/configure';body=json.dumps({'path':r'\\server\share\Reports'}).encode()
  with patch.object(server.shared_workbook,'configure',return_value=r'\\server\share\Reports') as configure,patch.object(server.shared_workbook,'sync') as sync:
   req=urllib.request.Request(path,body,headers={'Origin':'https://example.org','X-CSRF-Token':server.TOKEN})
   with self.assertRaises(urllib.error.HTTPError):urllib.request.urlopen(req)
   configure.assert_not_called()
   req=urllib.request.Request(path,body,headers={'Origin':self.url,'X-CSRF-Token':server.TOKEN})
   with urllib.request.urlopen(req) as response:self.assertIn('Shared folder saved',json.load(response)['message'])
   configure.assert_called_once_with(server.DATA,server.db,r'\\server\share\Reports')
   sync.assert_called_once()
   with server.RunLock():
    with self.assertRaises(urllib.error.HTTPError):urllib.request.urlopen(req)
   self.assertEqual(configure.call_count,1)
 def test_private_roster_import_requires_csrf_and_updates_state(self):
  path=self.url+'/api/names/import'
  mapping={'schema':2,'search':{'kishorek':{'id':'INV060','name':'Kishore R'}},'type':{'deepikak':{'id':'INV160','name':'Kanna Deepika'}},'legacy':{}}
  body=json.dumps(mapping).encode()
  try:
   req=urllib.request.Request(path,body,headers={'Origin':self.url})
   with self.assertRaises(urllib.error.HTTPError):urllib.request.urlopen(req)
   self.assertFalse((server.DATA/'names.json').exists())
   req=urllib.request.Request(path,body,headers={'Origin':self.url,'X-CSRF-Token':server.TOKEN})
   with urllib.request.urlopen(req) as response:self.assertEqual(json.load(response)['searchAliases'],1)
   self.assertTrue(server.public_state()['nameMapping']['loaded'])
  finally:(server.DATA/'names.json').unlink(missing_ok=True)
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
   (directory/'validation.json').write_text(json.dumps({'passed':True,'workbookFormatVersion':4}))
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
   server.scheduled();launch.assert_called_once_with('2026-09-18','2026-09-20','2026-09-21',False)
  class Early(Clock):
   @classmethod
   def now(cls,tz=None):return cls(2026,9,21,8,44,tzinfo=server.IST)
  with patch.object(server,'datetime',Early),patch.object(server,'launch_run') as launch:
   server.scheduled();launch.assert_not_called()
  class Tuesday(Clock):
   @classmethod
   def now(cls,tz=None):return cls(2026,9,22,8,45,tzinfo=server.IST)
  with patch.object(server,'datetime',Tuesday),patch.object(server,'launch_run') as launch:
   server.scheduled();launch.assert_called_once_with('2026-09-21','2026-09-21','2026-09-22',False)
  class Saturday(Clock):
   @classmethod
   def now(cls,tz=None):return cls(2026,9,19,8,45,tzinfo=server.IST)
  with patch.object(server,'datetime',Saturday),patch.object(server,'launch_run') as launch:
   server.scheduled();launch.assert_not_called()
  class MonthBoundary(Clock):
   @classmethod
   def now(cls,tz=None):return cls(2026,11,2,8,45,tzinfo=server.IST)
  with patch.object(server,'datetime',MonthBoundary),patch.object(server,'launch_run') as launch:
   server.scheduled();launch.assert_called_once_with('2026-10-30','2026-11-01','2026-11-02',False)
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
 def test_phase2_api_stays_off_before_september_and_requires_delete_confirmation(self):
  from datetime import date
  with patch.object(server.monthly_sync,'today',return_value=date(2026,8,31)):
   req=urllib.request.Request(self.url+'/api/main/create',json.dumps({'month':'2026-10'}).encode(),headers={'Origin':self.url,'X-CSRF-Token':server.TOKEN})
   with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(req)
   self.assertIn('1 September',error.exception.read().decode())
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
  def add(*args):
   self.assertTrue((folder/'validation.json').exists())
   self.assertEqual(args[-1],rid)
   raise ValueError('Simulated month export failure')
  lock=MagicMock()
  try:
   with server.db() as c:c.execute('INSERT INTO main_auto_pending VALUES (?,?)',(rid,'now'))
   with patch.object(server.monthly_sync,'today',return_value=date(2026,10,2)),patch.object(server,'credentials',return_value={'username':'test','password':'test'}),patch.object(server,'run_process',side_effect=process),patch.object(server.monthly_sync,'add',side_effect=add) as sync,patch.object(server.monthly_sync,'disputed_months',return_value=[]):
    server.perform(rid,lock);sync.assert_called_once()
   with server.db() as c:run=c.execute('SELECT * FROM runs WHERE id=?',(rid,)).fetchone()
   self.assertEqual(run['status'],'review');self.assertEqual(run['count'],1);self.assertEqual(run['points'],3)
   self.assertEqual(json.loads((folder/'issues.json').read_text())[0]['kind'],'month_refresh');lock.__exit__.assert_called_once()
   with server.db() as c:self.assertIsNotNone(c.execute('SELECT 1 FROM main_auto_pending WHERE run_id=?',(rid,)).fetchone())
  finally:
   with server.db() as c:c.execute('DELETE FROM runs WHERE id=?',(rid,));c.execute('DELETE FROM main_auto_pending WHERE run_id=?',(rid,))
 def test_verified_run_auto_adds_and_refreshes_earlier_disputes(self):
  rid=uuid.uuid4().hex;folder=server.DATA/'runs'/rid
  with server.db() as c:
   c.execute('INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?,?)',(rid,'2026-10-02','2026-10-04','queued','test','now',None,None,0,None))
   c.execute('INSERT INTO main_auto_pending VALUES (?,?)',(rid,'now'))
  def process(args,directory,*a,**kw):
   (directory/'issues.json').write_text('[]')
   (directory/'validation.json').write_text(json.dumps({'passed':True,'count':2,'points':4}))
  lock=MagicMock()
  try:
   with patch.object(server,'credentials',return_value={'username':'test','password':'test'}),patch.object(server,'run_process',side_effect=process),patch.object(server.monthly_sync,'add',return_value={'choice':'yes'}) as add,patch.object(server.monthly_sync,'disputed_months',return_value=['2026-09']),patch.object(server.monthly_sync,'refresh',return_value={}) as refresh:
    server.perform(rid,lock)
   self.assertEqual(add.call_args.args[-1],rid)
   self.assertEqual(refresh.call_args.args[-1],'2026-09')
   with server.db() as c:
    self.assertEqual(c.execute('SELECT status FROM runs WHERE id=?',(rid,)).fetchone()[0],'complete')
    self.assertIsNone(c.execute('SELECT 1 FROM main_auto_pending WHERE run_id=?',(rid,)).fetchone())
  finally:
   with server.db() as c:c.execute('DELETE FROM runs WHERE id=?',(rid,));c.execute('DELETE FROM main_auto_pending WHERE run_id=?',(rid,))
 def test_failed_month_addition_is_retried_before_next_verified_run(self):
  old=uuid.uuid4().hex;new=uuid.uuid4().hex;folder=server.DATA/'runs'/new
  with server.db() as c:
   c.execute('INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?,?)',(old,'2026-09-28','2026-09-28','review','Main update pending','earlier',1,3,1,None))
   c.execute('INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?,?)',(new,'2026-09-29','2026-09-29','queued','test','later',None,None,0,None))
   c.execute('INSERT INTO main_auto_pending VALUES (?,?)',(old,'earlier'))
   c.execute('INSERT INTO main_auto_pending VALUES (?,?)',(new,'later'))
  def process(args,directory,*a,**kw):
   (directory/'issues.json').write_text('[]')
   (directory/'validation.json').write_text(json.dumps({'passed':True,'count':1,'points':3}))
  try:
   with patch.object(server,'credentials',return_value={'username':'test','password':'test'}),patch.object(server,'run_process',side_effect=process),patch.object(server.monthly_sync,'add',return_value={'choice':'yes'}) as add,patch.object(server.monthly_sync,'disputed_months',return_value=[]):
    server.perform(new,MagicMock())
   self.assertEqual([x.args[-1] for x in add.call_args_list],[old,new])
   with server.db() as c:self.assertEqual(c.execute('SELECT count(*) FROM main_auto_pending WHERE run_id IN (?,?)',(old,new)).fetchone()[0],0)
  finally:
   with server.db() as c:
    c.execute('DELETE FROM runs WHERE id IN (?,?)',(old,new))
    c.execute('DELETE FROM main_auto_pending WHERE run_id IN (?,?)',(old,new))
if __name__=='__main__':unittest.main()
