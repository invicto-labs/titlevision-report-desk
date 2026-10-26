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
 def test_stop_remains_available_when_database_is_blocked(self):
  with patch.object(server,'db',side_effect=server.state_store.StateFault('blocked')),patch.object(server,'worker_busy',return_value=True),patch.object(server.OPERATIONS,'request',return_value={'message':'Stopping'}) as stop:
   with self.post('/api/operation/stop',{'operationId':'current'}) as response:self.assertEqual(response.status,202)
   stop.assert_called_once_with('current')
 def test_guard_response_includes_stop_state_and_health_not_ready(self):
  with patch.object(server,'public_state',side_effect=server.state_store.StateFault('verification failed')),patch.object(server,'safe_activity',return_value={'busy':True,'cancellable':True,'operationId':'current'}):
   with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(self.url+'/api/state')
   value=json.load(error.exception);self.assertEqual(value['code'],'database_guard');self.assertEqual(value['csrf'],server.TOKEN);self.assertTrue(value['activity']['cancellable'])
  server.STORE.fault.write_text('{}')
  try:
   with urllib.request.urlopen(self.url+'/api/health') as response:self.assertFalse(json.load(response)['ready'])
  finally:server.STORE.fault.unlink()
 def test_corrupt_database_reports_repair_required_without_claiming_network_failure(self):
  with patch.object(server,'public_state',side_effect=server.sqlite3.DatabaseError('database disk image is malformed')):
   with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(self.url+'/api/state')
  self.assertEqual(error.exception.code,503)
  result=json.load(error.exception);self.assertEqual(result['code'],'database_corrupt');self.assertIn('needs repair',result['error'])
 def test_database_backup_is_readable_and_damaged_source_does_not_replace_it(self):
  import sqlite3
  data=server.DATA/'backup-fixture';data.mkdir()
  with sqlite3.connect(data/'reporting.sqlite') as c:c.execute('create table important(value)');c.execute("insert into important values ('saved edit')")
  file=server.database_backup.create(data)
  with sqlite3.connect(file) as c:self.assertEqual(c.execute('select * from important').fetchall(),[('saved edit',)])
  before=file.read_bytes();(data/'reporting.sqlite').write_bytes(b'corrupt database')
  with self.assertRaises(sqlite3.DatabaseError):server.database_backup.create(data)
  self.assertEqual(file.read_bytes(),before)
  self.assertEqual(list((data/'database-backups').glob('*.tmp')),[])
 def test_month_collection_receives_cache_and_remembers_only_after_reconciliation(self):
  import hashlib
  folder=server.DATA/'cache-integration';folder.mkdir()
  events=[]
  def process(args,directory,*positional,**kwargs):
   if str(args[1]).endswith('collector.mjs'):
    events.append('collect');job=positional[0]
    self.assertTrue(Path(job['historyCache']).is_file())
    (directory/'source.json').write_text('[]')
   else:
    events.append('reconcile')
    (directory/'reconciled.json').write_text(json.dumps({'count':0,'sourceSha256':hashlib.sha256(b'[]').hexdigest()}))
  with patch.object(server,'credentials',return_value={'username':'test','password':'test'}),patch.object(server,'run_process',side_effect=process),patch.object(server.history_cache,'remember',wraps=server.history_cache.remember) as remember:
   server.fetch_month('2026-10-01','2026-10-02',folder)
   remember.assert_called_once_with(server.DATA,folder)
  self.assertEqual(events,['collect','reconcile'])
  with patch.object(server,'credentials',return_value={'username':'test','password':'test'}),patch.object(server,'run_process',side_effect=ValueError('Export verification failed')),patch.object(server.history_cache,'remember') as remember:
   with self.assertRaises(ValueError):server.fetch_month('2026-10-01','2026-10-02',folder)
   remember.assert_not_called()
 def test_disconnected_reader_does_not_trigger_a_second_error_response(self):
  handler=object.__new__(server.Handler);handler.path='/api/health';handler.guard=MagicMock()
  for error in (BrokenPipeError,ConnectionAbortedError,ConnectionResetError):
   handler.send=MagicMock(side_effect=error('Browser stopped waiting'))
   handler.do_GET()
   self.assertEqual(handler.send.call_count,1)
 def post(self,path,body):
  request=urllib.request.Request(self.url+path,json.dumps(body).encode(),headers={'Origin':self.url,'X-CSRF-Token':server.TOKEN,'Content-Type':'application/json'})
  return urllib.request.urlopen(request)
 def test_viewer_discovers_shared_months_reads_counts_and_never_publishes(self):
  import xlsxwriter,report_layout,hashlib
  folder=server.DATA/'viewer-share';folder.mkdir(exist_ok=True)
  file=folder/'TitleVision Main Error Report - 2026-10.xlsx'
  with xlsxwriter.Workbook(file) as wb:
   ws=wb.add_worksheet('SP 2');ws.write_row(0,0,report_layout.HEADERS)
   for i,team in enumerate(['Search','Typing'],1):
    row=['']*27;row[0]='New';row[1]='same-order';row[3]=team;row[10]='2026-10-01';row[13]=i;ws.write_row(i,0,row)
  before=file.read_bytes();old_schedule=server.setting('schedule',False)
  try:
   with patch.object(server.shared_view,'location',return_value=folder),patch.object(server.shared_workbook,'sync') as sync,patch.object(server.shared_workbook,'publish') as publish:
    with self.post('/api/shared/viewer',{'path':r'\\server\reports'}) as response:self.assertIn('Viewer connected',json.load(response)['message'])
    state=server.public_state();self.assertEqual(state['pcRole'],'viewer');self.assertFalse(state['schedule']);self.assertEqual(state['runs'],[])
    self.assertEqual([b['month'] for b in state['mainBooks']],['2026-10'])
    with patch.object(server.main_workbook,'download',side_effect=AssertionError('Viewer must not read local workbooks')):
     with urllib.request.urlopen(self.url+'/api/main/2026-10/summary') as response:summary=json.load(response)
     self.assertTrue(summary['available']);self.assertEqual(summary['total'],2);self.assertEqual(summary['points'],3)
     with urllib.request.urlopen(self.url+'/api/main/2026-10/current') as response:self.assertEqual(response.read(),before)
     with urllib.request.urlopen(self.url+'/api/main/2026-10/download') as response:self.assertEqual(response.read(),before)
    with self.post('/api/shared/sync',{}) as response:self.assertIn('list refreshed',json.load(response)['message'])
    sync.assert_not_called();publish.assert_not_called();self.assertEqual(file.read_bytes(),before)
    later=folder/'TitleVision Main Error Report - 2026-11.xlsx';later.write_bytes(before)
    self.assertEqual(server.public_state()['mainBooks'][0]['month'],'2026-11');later.unlink()
    with patch.object(server.shared_view,'location',side_effect=ValueError('Share offline')):
     offline=server.public_state();self.assertEqual(offline['mainBooks'],[]);self.assertTrue(offline['sharedError'])
     with urllib.request.urlopen(self.url+'/api/main/2026-10/summary') as response:self.assertFalse(json.load(response)['available'])
  finally:server.shared_view.collector(server.db);server.save_setting('schedule',old_schedule)
 def test_viewer_blocks_report_mutations_and_schedule_but_allows_update(self):
  old_schedule=server.setting('schedule',False);server.save_setting('pc_role','viewer');server.save_setting('schedule',True)
  try:
   paths=['/api/run','/api/main/create','/api/main/delete','/api/main/refresh','/api/main/edits','/api/names/import','/api/credentials','/api/shared/configure','/api/schedule','/api/runs/'+'a'*32+'/main']
   with patch.object(server,'credentials') as credentials:
    for path in paths:
     with self.assertRaises(urllib.error.HTTPError) as error:self.post(path,{})
     self.assertIn('viewer',json.load(error.exception)['error'])
    with self.assertRaisesRegex(ValueError,'viewer'):server.launch_run('2026-01-01','2026-01-01')
    server.scheduled();credentials.assert_not_called()
   with self.assertRaisesRegex(ValueError,'viewer'):
    with server.RunLock():pass
   self.assertFalse(server.worker_busy())
   with patch.object(server.UPDATES,'install',return_value={'available':True}) as install:
    with self.post('/api/update/install',{}) as response:self.assertEqual(response.status,202)
    install.assert_called_once()
   with self.post('/api/shared/collector',{}) as response:self.assertIn('restored',json.load(response)['message'])
  finally:server.shared_view.collector(server.db);server.save_setting('schedule',old_schedule)
 def test_viewer_configuration_requires_network_path_and_cannot_race_collection(self):
  with self.assertRaises(urllib.error.HTTPError) as error:self.post('/api/shared/viewer',{'path':'C:/local'})
  self.assertIn('shared Windows folder',json.load(error.exception)['error'])
  with server.RunLock():
   with self.assertRaises(urllib.error.HTTPError) as error:self.post('/api/shared/viewer',{'path':r'\\server\reports'})
   self.assertEqual(error.exception.code,409)
  self.assertFalse(server.shared_view.enabled(server.db))
 def test_every_json_mutation_rejects_wrong_body_shape_and_cross_origin(self):
  paths=['/api/shared/viewer','/api/shared/collector','/api/run','/api/credentials','/api/schedule','/api/shared/configure','/api/shared/sync','/api/main/create','/api/main/delete','/api/main/refresh','/api/update/check','/api/update/install','/api/update/cancel','/api/update/token','/api/runs/'+'a'*32+'/main']
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
 def test_stop_token_is_specific_and_repeated_stop_is_safe(self):
  from operation_control import Controller
  with server.RunLock(cancellable=True) as lock:
   token=lock.operation
   self.assertEqual(server.activity_state()['operationId'],token)
   with self.assertRaises(urllib.error.HTTPError) as error:self.post('/api/operation/stop',{'operationId':'0'*32})
   self.assertEqual(error.exception.code,400);self.assertFalse(server.OPERATIONS.requested())
   # A different controller models the desktop talking to a scheduled process.
   Controller(server.DATA).request(token)
   self.assertTrue(server.OPERATIONS.requested())
   with self.post('/api/operation/stop',{'operationId':token}) as response:self.assertEqual(response.status,202)
   self.assertTrue(server.activity_state()['stopping'])
  with server.RunLock(cancellable=True):
   with self.assertRaises(urllib.error.HTTPError):self.post('/api/operation/stop',{'operationId':token})
   self.assertFalse(server.OPERATIONS.requested())
  with self.post('/api/operation/stop',{'operationId':token}) as response:self.assertIn('finished',json.load(response)['message'])
 def test_stop_requires_csrf(self):
  with server.RunLock(cancellable=True) as lock:
   request=urllib.request.Request(self.url+'/api/operation/stop',json.dumps({'operationId':lock.operation}).encode(),headers={'Origin':'https://example.org','X-CSRF-Token':server.TOKEN})
   with self.assertRaises(urllib.error.HTTPError):urllib.request.urlopen(request)
   self.assertFalse(server.OPERATIONS.requested())
 def test_stop_terminates_owned_child_and_preserves_workbook_and_other_process(self):
  import subprocess,time
  ready=threading.Event();errors=[];folder=server.DATA/'cancel-test';folder.mkdir(exist_ok=True)
  saved=folder/'saved.xlsx';saved.write_bytes(b'previous verified workbook')
  unrelated=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'])
  def work():
   try:
    with server.RunLock(cancellable=True):
     server.run_process([sys.executable,'-u','-c','import time;print("{\\"ready\\":true}",flush=True);time.sleep(60)'],folder,progress=lambda event:ready.set())
   except Exception as error:errors.append(error)
  worker=threading.Thread(target=work);worker.start()
  try:
   self.assertTrue(ready.wait(10))
   with self.post('/api/operation/stop',{'operationId':server.activity_state()['operationId']}) as response:self.assertEqual(response.status,202)
   worker.join(12);self.assertFalse(worker.is_alive())
   self.assertEqual(len(errors),1);self.assertIsInstance(errors[0],server.Cancelled)
   self.assertIsNone(unrelated.poll());self.assertEqual(saved.read_bytes(),b'previous verified workbook')
   self.assertFalse(server.worker_busy())
   with server.RunLock(cancellable=True):server.run_process([sys.executable,'-c','print("new run")'],folder)
  finally:
   unrelated.terminate();unrelated.wait(timeout=10);worker.join(65)
 def test_cancelled_daily_collection_keeps_schedule_marker_without_retry(self):
  with patch.object(server,'credentials',return_value={'username':'test','password':'test'}),patch.object(server,'run_process',side_effect=server.Cancelled()):
   rid=server.launch_run('2026-01-01','2026-01-01',scheduled_day='2026-01-02',background=False)
  try:
   with server.db() as c:
    run=c.execute('SELECT * FROM runs WHERE id=?',(rid,)).fetchone()
    self.assertEqual(run['status'],'cancelled');self.assertEqual(run['scheduled_day'],'2026-01-02')
    self.assertIsNone(c.execute('SELECT * FROM main_auto_pending WHERE run_id=?',(rid,)).fetchone())
   self.assertFalse(server.worker_busy())
  finally:
   with server.db() as c:c.execute('DELETE FROM runs WHERE id=?',(rid,))
 def test_overlap_returns_progress_without_starting_second_refresh(self):
  month='2026-06'
  server.monthly_sync.state(server.db,month,'running','Checking status comments 17 of 42')
  try:
   with server.RunLock(),patch.object(server.monthly_sync,'refresh') as refresh:
    with self.assertRaises(urllib.error.HTTPError) as error:self.post('/api/main/refresh',{'month':month})
    self.assertEqual(error.exception.code,409)
    result=json.load(error.exception)
    self.assertEqual(result['code'],'worker_busy');self.assertTrue(result['activity']['busy'])
    self.assertIn('17 of 42',result['error']);refresh.assert_not_called()
  finally:
   with server.db() as c:c.execute('DELETE FROM main_sync_state WHERE month=?',(month,))
  self.assertFalse(server.worker_busy())
 def test_old_running_label_does_not_keep_worker_busy(self):
  month='2026-05'
  server.monthly_sync.state(server.db,month,'running','Old interrupted progress')
  try:self.assertEqual(server.activity_state(),{'busy':False,'message':''})
  finally:
   with server.db() as c:c.execute('DELETE FROM main_sync_state WHERE month=?',(month,))
 def test_failed_operation_releases_lock_for_next_request(self):
  with patch.object(server.shared_workbook,'configured',return_value='test-share'),patch.object(server.shared_workbook,'sync',side_effect=ValueError('Source unavailable')):
   with self.assertRaises(urllib.error.HTTPError) as error:self.post('/api/shared/sync',{})
   self.assertEqual(error.exception.code,400)
  self.assertFalse(server.worker_busy())
  with patch.object(server.shared_workbook,'configured',return_value='test-share'),patch.object(server.shared_workbook,'sync') as sync:
   with self.post('/api/shared/sync',{}) as response:self.assertEqual(response.status,200)
   sync.assert_called_once()
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
   (directory/'validation.json').write_text(json.dumps({'passed':True,'workbookFormatVersion':5}))
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
  def add(*args,**kwargs):
   self.assertTrue((folder/'validation.json').exists())
   self.assertEqual(args[-1],rid)
   raise ValueError('Simulated month export failure')
  lock=MagicMock()
  try:
   with server.db() as c:c.execute('INSERT INTO main_auto_pending VALUES (?,?)',(rid,'now'))
   with patch.object(server.monthly_sync,'today',return_value=date(2026,10,2)),patch.object(server,'credentials',return_value={'username':'test','password':'test'}),patch.object(server,'run_process',side_effect=process),patch.object(server.history_cache,'remember'),patch.object(server.monthly_sync,'add',side_effect=add) as sync,patch.object(server.monthly_sync,'disputed_months',return_value=[]):
    server.perform(rid,lock);sync.assert_called_once()
   with server.db() as c:run=c.execute('SELECT * FROM runs WHERE id=?',(rid,)).fetchone()
   self.assertEqual(run['status'],'review');self.assertEqual(run['count'],1);self.assertEqual(run['points'],3)
   self.assertEqual(json.loads((folder/'issues.json').read_text())[0]['kind'],'month_refresh');lock.__exit__.assert_called_once()
   with server.db() as c:self.assertIsNotNone(c.execute('SELECT 1 FROM main_auto_pending WHERE run_id=?',(rid,)).fetchone())
  finally:
   with server.db() as c:c.execute('DELETE FROM runs WHERE id=?',(rid,));c.execute('DELETE FROM main_auto_pending WHERE run_id=?',(rid,))
 def test_verified_run_auto_adds_without_refreshing_existing_or_earlier_disputes(self):
  rid=uuid.uuid4().hex;folder=server.DATA/'runs'/rid
  with server.db() as c:
   c.execute('INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?,?)',(rid,'2026-10-02','2026-10-04','queued','test','now',None,None,0,None))
   c.execute('INSERT INTO main_auto_pending VALUES (?,?)',(rid,'now'))
  def process(args,directory,*a,**kw):
   (directory/'issues.json').write_text('[]')
   (directory/'validation.json').write_text(json.dumps({'passed':True,'count':2,'points':4}))
  lock=MagicMock()
  try:
   with patch.object(server,'credentials',return_value={'username':'test','password':'test'}),patch.object(server,'run_process',side_effect=process),patch.object(server.history_cache,'remember'),patch.object(server.monthly_sync,'add',return_value={'choice':'yes'}) as add,patch.object(server.monthly_sync,'disputed_months',return_value=['2026-09']),patch.object(server.monthly_sync,'refresh',return_value={}) as refresh:
    server.perform(rid,lock)
   self.assertEqual(add.call_args.args[-1],rid)
   self.assertEqual(add.call_args.kwargs,{'refresh_existing':False})
   refresh.assert_not_called()
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
   with patch.object(server,'credentials',return_value={'username':'test','password':'test'}),patch.object(server,'run_process',side_effect=process),patch.object(server.history_cache,'remember'),patch.object(server.monthly_sync,'add',return_value={'choice':'yes'}) as add,patch.object(server.monthly_sync,'disputed_months',return_value=[]):
    server.perform(new,MagicMock())
   self.assertEqual([x.args[-1] for x in add.call_args_list],[old,new])
   with server.db() as c:self.assertEqual(c.execute('SELECT count(*) FROM main_auto_pending WHERE run_id IN (?,?)',(old,new)).fetchone()[0],0)
  finally:
   with server.db() as c:
    c.execute('DELETE FROM runs WHERE id IN (?,?)',(old,new))
    c.execute('DELETE FROM main_auto_pending WHERE run_id IN (?,?)',(old,new))
if __name__=='__main__':unittest.main()
