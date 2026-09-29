"""Local TitleVision reporting application. No model or OpenAI API calls."""
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from pathlib import Path
from datetime import datetime,timedelta,timezone,date
import base64,ctypes,hashlib,json,os,secrets,socket,sqlite3,subprocess,sys,threading,time,uuid,webbrowser
from urllib.parse import urlparse
from contextlib import contextmanager
sys.path.insert(0,str(Path(__file__).resolve().parent))
from updater import Updates
import main_workbook,monthly_sync,manual_edits
ROOT=Path(__file__).resolve().parent
PORTABLE=(ROOT/'portable.json').exists()
DATA=Path(os.environ.get('TITLEVISION_DATA',Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'TitleVision Report Desk/data' if PORTABLE else ROOT/'data')).resolve();DATA.mkdir(parents=True,exist_ok=True)
PORT=int(os.environ.get('TITLEVISION_PORT','8765'));IST=timezone(timedelta(hours=5,minutes=30));TOKEN=secrets.token_urlsafe(32)
NODE=Path(os.environ.get('TITLEVISION_NODE',ROOT.parent/'runtime/node/node.exe' if PORTABLE else Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe'))
CREATE_NO_WINDOW=0x08000000 if os.name=='nt' else 0
class ReportHTTPServer(ThreadingHTTPServer):
 # Windows SO_REUSEADDR permits a second listener to steal the same port.
 # Exclusive ownership keeps requests routed to one verified report engine.
 allow_reuse_address=os.name!='nt'
 allow_reuse_port=False
 def server_bind(self):
  if os.name=='nt':self.socket.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
  super().server_bind()

def open_http_server():
 # Let connections from the previous engine close during an update.
 deadline=time.monotonic()+15
 while True:
  try:return ReportHTTPServer(('127.0.0.1',PORT),Handler)
  except OSError as error:
   if getattr(error,'winerror',None) not in (10013,10048) or time.monotonic()>=deadline:raise
   time.sleep(.25)
@contextmanager
def db():
 c=sqlite3.connect(DATA/'reporting.sqlite',timeout=30);c.row_factory=sqlite3.Row
 try:
  with c:yield c
 finally:c.close()
def initialize():
 with db() as c:
  c.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY,value TEXT NOT NULL)')
  c.execute('CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY,start TEXT,end TEXT,status TEXT,message TEXT,created TEXT,count INTEGER,points REAL,issues INTEGER,scheduled_day TEXT)')
  c.execute('CREATE UNIQUE INDEX IF NOT EXISTS scheduled_once ON runs(scheduled_day) WHERE scheduled_day IS NOT NULL')
  main_workbook.initialize(c)
def setting(k,default=None):
 with db() as c:r=c.execute('SELECT value FROM settings WHERE key=?',(k,)).fetchone()
 return json.loads(r[0]) if r else default
def save_setting(k,v):
 with db() as c:c.execute('INSERT OR REPLACE INTO settings VALUES (?,?)',(k,json.dumps(v)))
def dpapi(raw,decrypt=False):
 if os.name!='nt':raise ValueError('This local edition stores credentials using Windows encryption. Server deployment needs a secret store.')
 class Blob(ctypes.Structure):_fields_=[('length',ctypes.c_ulong),('data',ctypes.POINTER(ctypes.c_ubyte))]
 buf=ctypes.create_string_buffer(raw);src=Blob(len(raw),ctypes.cast(buf,ctypes.POINTER(ctypes.c_ubyte)));dst=Blob()
 fn=ctypes.windll.crypt32.CryptUnprotectData if decrypt else ctypes.windll.crypt32.CryptProtectData
 if not fn(ctypes.byref(src),None,None,None,None,1,ctypes.byref(dst)):raise ctypes.WinError()
 try:return ctypes.string_at(dst.data,dst.length)
 finally:ctypes.windll.kernel32.LocalFree(dst.data)
def credentials():
 p=DATA/'credentials.dpapi'
 if not p.exists():raise ValueError('Save your TitleVision sign-in in Settings first.')
 return json.loads(dpapi(p.read_bytes(),True))
def store_credentials(username,password):
 if not username or not password:raise ValueError('Username and password are required.')
 p=DATA/'credentials.dpapi';temp=p.with_suffix('.tmp');temp.write_bytes(dpapi(json.dumps({'username':username,'password':password}).encode()));temp.replace(p)
UPDATES=Updates(ROOT,DATA,dpapi)
def update(rid,**values):
 with db() as c:c.execute('UPDATE runs SET '+','.join(k+'=?' for k in values)+' WHERE id=?',(*values.values(),rid))
class RunLock:
 def __enter__(self):
  self.file=open(DATA/'worker.lock','a+b');self.file.seek(0);self.file.write(b'0');self.file.flush();self.file.seek(0)
  try:
   if os.name=='nt':
    import msvcrt;msvcrt.locking(self.file.fileno(),msvcrt.LK_NBLCK,1)
   else:
    import fcntl;fcntl.flock(self.file,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except OSError:self.file.close();raise ValueError('Another report is already running.')
  return self
 def __exit__(self,*args):self.file.close()
def date_range(start,end):
 a=date.fromisoformat(start);b=date.fromisoformat(end)
 if a>b or (b-a).days>30:raise ValueError('Choose a date range of 1 to 31 days.')
 if b>=datetime.now(IST).date():raise ValueError('Select a completed day, up to yesterday.')
 return a.isoformat(),b.isoformat()
def run_process(args,directory,stdin=None,progress=None,artifact_export=False):
 p=subprocess.Popen([str(x) for x in args],cwd=ROOT,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf8',errors='replace',creationflags=CREATE_NO_WINDOW)
 def stop():
  if os.name=='nt':subprocess.run(['taskkill','/PID',str(p.pid),'/T','/F'],capture_output=True,creationflags=CREATE_NO_WINDOW)
  else:p.kill()
 timer=threading.Timer(2700,stop);timer.start();lines=[]
 try:
  if stdin:p.stdin.write(json.dumps(stdin))
  p.stdin.close()
  for line in p.stdout:
   line=line.strip()
   if stdin and stdin.get('password'):line=line.replace(stdin['password'],'[redacted]')
   lines.append(line)
   if progress:
    try:progress(json.loads(line))
    except (ValueError,TypeError):pass
  code=p.wait()
  with open(directory/'execution.log','a',encoding='utf8') as f:f.write('\n'.join(lines)+'\n')
  if code and artifact_export and os.name=='nt' and code in (1,3221226505,-1073740791):
   # The bundled renderer can fail during native shutdown after successful export.
   # Accept only a completed export with its exact hash; independent XLSX validation still follows.
   marker=directory/'build-complete.json'
   if marker.exists():
    receipt=json.loads(marker.read_text(encoding='utf8'));actual=hashlib.sha256((directory/'base.xlsx').read_bytes()).hexdigest()
    if receipt['sha256']==actual:code=0
  if code:raise ValueError(next((json.loads(l).get('message') for l in reversed(lines) if l.startswith('{') and '"failed"' in l),None) or ('Report step failed. '+ '\n'.join(lines[-4:])[:600]))
 finally:timer.cancel()
def perform(rid,lock):
 directory=DATA/'runs'/rid;directory.mkdir(parents=True,exist_ok=True)
 try:
  with db() as c:run=dict(c.execute('SELECT * FROM runs WHERE id=?',(rid,)).fetchone())
  cred=credentials();update(rid,status='running',message='Signing in to TitleVision')
  def progress(event):
   if event.get('message'):update(rid,message=event['message'],**({'count':event['count'],'points':event['points']} if 'count' in event else {}))
  run_process([NODE,ROOT/'collector.mjs'],directory,dict(cred,start=run['start'],end=run['end'],directory=str(directory)),progress)
  update(rid,message='Comparing every row with the downloaded source export')
  run_process([sys.executable,ROOT/'reconcile.py',directory],directory)
  update(rid,message='Building contributor formulas and Excel summaries')
  if PORTABLE:
   run_process([NODE,ROOT/'report/prepare.mjs',directory],directory)
   run_process([sys.executable,ROOT/'report/build_portable.py',directory],directory)
  else:run_process([NODE,ROOT/'report/build.mjs',directory],directory,artifact_export=True)
  run_process([sys.executable,ROOT/'report/finish.py',directory],directory)
  checks=json.loads((directory/'validation.json').read_text(encoding='utf8'));issues=json.loads((directory/'issues.json').read_text(encoding='utf8'))
  if not checks.get('passed'):raise ValueError('Workbook validation failed; report withheld.')
  if monthly_sync.active():
   months=sorted({day[:7] for day in main_workbook.days_between(run['start'],run['end']) if monthly_sync.eligible(day[:7])})
   for month in months:
    try:
     monthly_sync.refresh(ROOT,DATA,db,run_process,lambda a,b,folder:fetch_month(a,b,folder,rid),month)
    except Exception as e:
     issues.append({'id':'month-'+month,'order':month+' main workbook','kind':'month_refresh','message':'Daily report is available. Monthly refresh failed; previous main workbook retained. '+str(e)[:500]})
   (directory/'issues.json').write_text(json.dumps(issues),encoding='utf8')
  update(rid,status='review' if issues else 'complete',message=f'{len(issues)} item(s) need review' if issues else 'All report checks passed',count=checks['count'],points=checks['points'],issues=len(issues))
 except Exception as e:
  message=str(e)[:900]
  try:message=message.replace(credentials()['password'],'[redacted]')
  except Exception:pass
  update(rid,status='failed',message=message)
 finally:lock.__exit__(None,None,None)

def fetch_month(start,end,folder,rid=None):
 def progress(event):
  if rid and event.get('message'):update(rid,message='Month-to-date refresh: '+event['message'])
 run_process([NODE,ROOT/'collector.mjs'],folder,dict(credentials(),start=start,end=end,directory=str(folder),exportOnly=True),progress)
 run_process([sys.executable,ROOT/'reconcile.py',folder],folder)
def launch_run(start,end,scheduled_day=None,background=True):
 if UPDATES.busy():raise ValueError('An application update is in progress. Run the report after it finishes.')
 start,end=date_range(start,end);credentials();lock=RunLock();lock.__enter__()
 try:
  # Any running record left while the process lock is free was interrupted.
  with db() as c:
   c.execute("UPDATE runs SET status='failed',message='Application stopped during this run. Run the date again.' WHERE status IN ('running','queued')")
   rid=uuid.uuid4().hex;c.execute('INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?,?)',(rid,start,end,'queued','Waiting to start',datetime.now(IST).isoformat(),None,None,0,scheduled_day))
 except Exception:lock.__exit__(None,None,None);raise
 if background:threading.Thread(target=perform,args=(rid,lock),daemon=True).start()
 else:perform(rid,lock)
 return rid
def scheduled(background=False):
 if not setting('schedule',False):return
 now=datetime.now(IST)
 if (now.hour,now.minute)<(8,45):return
 day=now.date().isoformat()
 yesterday=(now.date()-timedelta(days=1)).isoformat()
 with db() as c:
  if c.execute('SELECT 1 FROM runs WHERE scheduled_day=?',(day,)).fetchone():return
  done=c.execute("SELECT id FROM runs WHERE start=? AND end=? AND status IN ('complete','review') AND scheduled_day IS NULL ORDER BY created DESC LIMIT 1",(yesterday,yesterday)).fetchone()
  if done:
   c.execute('UPDATE runs SET scheduled_day=? WHERE id=?',(day,done['id']));return
 try:launch_run(yesterday,yesterday,day,background)
 except (ValueError,sqlite3.IntegrityError):return
def schedule_loop():
 while True:
  try:scheduled(True)
  except Exception:pass
  time.sleep(30)
def install_schedule(enabled):
 if os.name!='nt':raise ValueError('Windows scheduling is available in this local edition.')
 if enabled:
  with db() as c:verified=c.execute("SELECT 1 FROM runs WHERE status IN ('complete','review') LIMIT 1").fetchone()
  if not verified:raise ValueError('Complete one verified live report before enabling unattended collection. The schedule remains paused.')
 # Scope the policy to this child process and our bundled script. Do not change
 # CurrentUser/LocalMachine policy; organization Group Policy still takes priority.
 result=subprocess.run(['powershell','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(ROOT/'schedule.ps1'),'-Python',sys.executable,'-App',str(ROOT),'-Mode','Enable' if enabled else 'Disable'],capture_output=True,text=True,creationflags=CREATE_NO_WINDOW,timeout=45)
 if result.returncode:
  detail=result.stderr[-500:]
  if 'PSSecurityException' in result.stderr or 'running scripts is disabled' in result.stderr or 'not digitally signed' in result.stderr:
   detail='Windows still blocks the bundled schedule script. Ask your IT administrator to approve it under the enforced script policy. '+detail
  raise ValueError('Windows could not update the schedule: '+detail)
 save_setting('schedule',enabled)
def public_state():
 with db() as c:
  runs=[dict(r) for r in c.execute('SELECT runs.*,main_choices.choice AS mainChoice FROM runs LEFT JOIN main_choices ON main_choices.run_id=runs.id ORDER BY created DESC LIMIT 60')]
  verified=bool(c.execute("SELECT 1 FROM runs WHERE status IN ('complete','review') LIMIT 1").fetchone())
  main_books=main_workbook.books(c)
 with db() as c:syncs=[dict(r) for r in c.execute('SELECT * FROM main_sync_state ORDER BY month DESC')]
 return {'runs':runs,'mainBooks':main_books,'mainSyncs':syncs,'phase2':{'enabled':monthly_sync.active(),'starts':'2026-10-01','currentMonth':monthly_sync.today().strftime('%Y-%m')},'verifiedLive':verified,'credentialsSaved':(DATA/'credentials.dpapi').exists(),'schedule':setting('schedule',False),'time':'08:45','timezone':'Asia/Kolkata','yesterday':(datetime.now(IST).date()-timedelta(days=1)).isoformat(),'csrf':TOKEN,'edition':'portable-1' if PORTABLE else 'local','version':UPDATES.config['version'],'repository':UPDATES.config['repository'],'update':UPDATES.status(),'githubAccessSaved':(DATA/'github-update.dpapi').exists(),'processId':os.getpid()}
def downloadable_report(folder):
 def ready(directory):
  try:
   checked=json.loads((directory/'validation.json').read_text(encoding='utf8'))
   return checked.get('passed') and checked.get('workbookFormatVersion')==3 and (directory/'report.xlsx').is_file()
  except (OSError,ValueError):return False
 if ready(folder):return folder/'report.xlsx'
 corrected=folder/'workbook-v3'
 if ready(corrected):return corrected/'report.xlsx'
 with RunLock():
  if UPDATES.busy():raise ValueError('The app is updating. Download the report after it restarts.')
  if not ready(corrected):
   # Rebuild only the workbook from the already verified payload. Preserve the
   # original export, attribution decisions, report history and old workbook.
   corrected.mkdir(exist_ok=True)
   for name in ('payload.json','collection.json'):(corrected/name).write_bytes((folder/name).read_bytes())
   run_process([sys.executable,ROOT/'report/build_portable.py',corrected],corrected)
   run_process([sys.executable,ROOT/'report/finish.py',corrected],corrected)
   if not ready(corrected):raise ValueError('The corrected workbook did not pass validation.')
 return corrected/'report.xlsx'
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*a):pass
 def send(self,code,body,kind='application/json'):
  if not isinstance(body,bytes):body=json.dumps(body).encode()
  self.send_response(code);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'");self.end_headers();self.wfile.write(body)
 def guard(self,write=False):
  if self.headers.get('Host') not in {f'127.0.0.1:{PORT}',f'localhost:{PORT}'}:raise ValueError('Invalid host')
  if write and (self.headers.get('X-CSRF-Token')!=TOKEN or self.headers.get('Origin') not in {f'http://127.0.0.1:{PORT}',f'http://localhost:{PORT}'}):raise ValueError('Invalid request origin')
 def do_GET(self):
  try:
   self.guard();p=urlparse(self.path).path
   if p=='/api/health':return self.send(200,{'edition':'portable-1' if PORTABLE else 'local','version':UPDATES.config['version'],'processId':os.getpid(),'ready':True})
   if p=='/api/state':return self.send(200,public_state())
   if p.startswith('/api/main/') and p.endswith('/download'):
    chunks=p.split('/')
    if len(chunks)!=5:raise ValueError('Invalid workbook URL')
    month=chunks[3]
    with db() as c:file=main_workbook.download(DATA,c,month)
    payload=file.read_bytes();self.send_response(200);self.send_header('Content-Type','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet');self.send_header('Content-Disposition',f'attachment; filename="TitleVision Main Error Report - {month}.xlsx"');self.send_header('Content-Length',str(len(payload)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(payload);return
   if p.startswith('/api/runs/'):
    chunks=p.split('/');rid=chunks[3]
    if len(rid)!=32 or any(c not in '0123456789abcdef' for c in rid):raise ValueError('Invalid report')
    with db() as c:r=c.execute('SELECT * FROM runs WHERE id=?',(rid,)).fetchone()
    if not r:raise ValueError('Report not found')
    folder=DATA/'runs'/rid
    if len(chunks)==5 and chunks[4]=='download':
     if r['status'] not in ['complete','review']:raise ValueError('Report has not passed validation')
     payload=downloadable_report(folder).read_bytes();self.send_response(200);self.send_header('Content-Type','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet');self.send_header('Content-Disposition',f'attachment; filename="TitleVision Error Report - {r["start"]}'+(f' to {r["end"]}' if r['end']!=r['start'] else '')+'.xlsx"');self.send_header('Content-Length',str(len(payload)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(payload);return
    issues=json.loads((folder/'issues.json').read_text(encoding='utf8')) if (folder/'issues.json').exists() else []
    return self.send(200,{'run':dict(r),'issues':issues})
   files={'/':'index.html','/app.js':'app.js','/style.css':'style.css','/favicon.svg':'favicon.svg'}
   if p not in files:return self.send(404,{'error':'Not found'})
   kind={'/':'text/html; charset=utf-8','/app.js':'text/javascript; charset=utf-8','/style.css':'text/css; charset=utf-8','/favicon.svg':'image/svg+xml'}[p]
   self.send(200,(ROOT/'public'/files[p]).read_bytes(),kind)
  except (ValueError,OSError) as e:self.send(400,{'error':str(e)})
 def do_POST(self):
  try:
   self.guard(True);length=int(self.headers.get('Content-Length','0'))
   p=urlparse(self.path).path
   if p=='/api/main/edits':
    if length<=0 or length>12*1024*1024:raise ValueError('Choose an Excel workbook smaller than 12 MB.')
    month=self.headers.get('X-Workbook-Month','')
    content=self.rfile.read(length)
    with RunLock():
     if UPDATES.busy():raise ValueError('Wait for the application update to finish.')
     result=manual_edits.save(ROOT,DATA,db,run_process,month,content)
    return self.send(200,result)
   if length<=0 or length>8192:raise ValueError('Request too large')
   obj=json.loads(self.rfile.read(length))
   if p.startswith('/api/runs/') and p.endswith('/main'):
    chunks=p.split('/')
    if len(chunks)!=5:raise ValueError('Invalid report URL')
    with RunLock():
     if UPDATES.busy():raise ValueError('Wait for the application update to finish.')
     if type(obj.get('add')) is not bool:raise ValueError('Invalid main workbook choice')
     with db() as c:r=c.execute('SELECT end FROM runs WHERE id=?',(chunks[3],)).fetchone()
     if obj['add'] and monthly_sync.active() and r and r['end']>='2026-10-01':
      result=monthly_sync.add(ROOT,DATA,db,run_process,fetch_month,chunks[3])
     else:result=main_workbook.decide(ROOT,DATA,db,run_process,chunks[3],obj['add'])
    return self.send(200,result)
   if p in ('/api/main/create','/api/main/delete','/api/main/refresh'):
    month=obj.get('month')
    if not isinstance(month,str):raise ValueError('Choose a workbook month')
    with RunLock():
     if UPDATES.busy():raise ValueError('Wait for the application update to finish.')
     if p.endswith('/create'):result=monthly_sync.create(ROOT,DATA,db,run_process,month)
     elif p.endswith('/delete'):
      if obj.get('confirm') is not True:raise ValueError('Confirm removal of this monthly workbook. Daily reports will be kept.')
      result=monthly_sync.delete(DATA,db,month)
     else:
      with db() as c:exists=c.execute('SELECT 1 FROM main_books WHERE month=?',(month,)).fetchone()
      if not exists:raise ValueError('Create or add to this monthly workbook first.')
      monthly_sync.refresh(ROOT,DATA,db,run_process,fetch_month,month)
      with db() as c:result={'books':main_workbook.books(c),'message':'Month-to-date statuses and points verified; PivotTables rebuilt.'}
    return self.send(200,result)
   if p=='/api/run':return self.send(202,{'id':launch_run(obj['start'],obj['end'])})
   if p=='/api/update/check':return self.send(200,UPDATES.check())
   if p=='/api/update/install':
    with RunLock():return self.send(202,UPDATES.install())
   if p=='/api/update/token':UPDATES.save_token(obj.get('token','').strip());return self.send(200,{'saved':bool(obj.get('token'))})
   if p=='/api/credentials':store_credentials(obj['username'].strip(),obj['password']);return self.send(200,{'saved':True})
   if p=='/api/schedule':
    if type(obj.get('enabled')) is not bool:raise ValueError('Invalid schedule option')
    if obj['enabled']:credentials()
    install_schedule(obj['enabled']);return self.send(200,{'enabled':obj['enabled']})
   return self.send(404,{'error':'Not found'})
  except (ValueError,KeyError,sqlite3.Error,subprocess.SubprocessError,OSError) as e:self.send(400,{'error':str(e)})
if __name__=='__main__':
 initialize()
 if '--store-credentials' in sys.argv:
  secret=json.load(sys.stdin);store_credentials(secret['username'],secret['password']);print('Credentials encrypted for this Windows account.')
 elif '--scheduled' in sys.argv:scheduled()
 elif '--enable-schedule' in sys.argv:install_schedule(True);print('Daily schedule installed.')
 elif '--update-schedule-if-enabled' in sys.argv:
  if setting('schedule',False):install_schedule(True)
 else:
  http=open_http_server();threading.Thread(target=schedule_loop,daemon=True).start();print(f'TitleVision Report Desk: http://127.0.0.1:{PORT}',flush=True)
  if '--open' in sys.argv:webbrowser.open(f'http://127.0.0.1:{PORT}')
  http.serve_forever()
