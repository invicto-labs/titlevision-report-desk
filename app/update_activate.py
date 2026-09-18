"""Activate a verified, extracted version; retain data and roll back on startup failure."""
from pathlib import Path
import ctypes,json,msvcrt,os,socket,subprocess,sys,time,urllib.request,uuid
from ctypes import wintypes
root=Path(__file__).resolve().parent.parent
data=Path(os.environ['LOCALAPPDATA'])/'TitleVision Report Desk/data';data.mkdir(parents=True,exist_ok=True)
version=json.loads((root/'app/version.json').read_text(encoding='utf8'))['version']
def status(phase,message):
 temp=data/('update-'+uuid.uuid4().hex+'.tmp');temp.write_text(json.dumps({'phase':phase,'message':message,'time':time.time(),'target':version}),encoding='utf8');temp.replace(data/'update-status.json')
def state():
 with urllib.request.urlopen('http://127.0.0.1:8765/api/state',timeout=3) as response:return json.load(response)
def python_start(folder):
 env=dict(os.environ);env.pop('PYTHONHOME',None);env.pop('PYTHONPATH',None);env.pop('TITLEVISION_DATA',None);env.pop('TITLEVISION_NODE',None);env['TITLEVISION_PORT']='8765'
 return subprocess.Popen([str(folder/'runtime/python/pythonw.exe'),str(folder/'app/server.py')],cwd=folder/'app',env=env,creationflags=0x08000000)
def schedule(folder):
 script=folder/'app/server.py'
 flag='--update-schedule-if-enabled'
 if flag not in script.read_text(encoding='utf8'):
  # Bootstrap from older editions only when the existing schedule was enabled.
  import sqlite3
  with sqlite3.connect(data/'reporting.sqlite') as db:
   row=db.execute("SELECT value FROM settings WHERE key='schedule'").fetchone()
  if not row or not json.loads(row[0]):return
  flag='--enable-schedule'
 r=subprocess.run([str(folder/'runtime/python/python.exe'),str(script),flag],cwd=folder/'app',capture_output=True,timeout=60,creationflags=0x08000000)
 if r.returncode:raise RuntimeError('The daily schedule could not be transferred to the new version')
def process_path(pid):
 kernel=ctypes.windll.kernel32;kernel.OpenProcess.restype=wintypes.HANDLE
 kernel.QueryFullProcessImageNameW.argtypes=[wintypes.HANDLE,wintypes.DWORD,wintypes.LPWSTR,ctypes.POINTER(wintypes.DWORD)]
 kernel.CloseHandle.argtypes=[wintypes.HANDLE]
 handle=kernel.OpenProcess(0x1000,False,pid)
 if not handle:raise RuntimeError('The running application changed; retry the update')
 try:
  text=ctypes.create_unicode_buffer(32768);size=ctypes.c_ulong(len(text))
  if not ctypes.windll.kernel32.QueryFullProcessImageNameW(handle,0,text,ctypes.byref(size)):raise RuntimeError('Could not verify the running application')
  return Path(text.value).resolve()
 finally:ctypes.windll.kernel32.CloseHandle(handle)
def verify_process(pid,folder):
 if process_path(pid)!=folder/'runtime/python/pythonw.exe':raise RuntimeError('The process does not belong to the previous Report Desk installation')
def discover():
 size=wintypes.ULONG(0);fn=ctypes.windll.iphlpapi.GetExtendedTcpTable
 fn(None,ctypes.byref(size),False,2,3,0);buffer=ctypes.create_string_buffer(size.value)
 if fn(buffer,ctypes.byref(size),False,2,3,0):raise RuntimeError('Could not identify the running application')
 class Row(ctypes.Structure):_fields_=[(name,wintypes.DWORD) for name in ('state','address','port','remoteAddress','remotePort','pid')]
 count=wintypes.DWORD.from_buffer(buffer).value;matches=[]
 for i in range(count):
  row=Row.from_buffer(buffer,4+i*ctypes.sizeof(Row))
  if socket.ntohs(row.port&65535)==8765 and row.address in (0,0x0100007f):matches.append(row.pid)
 matches=set(matches)
 if not matches:return None
 if len(matches)!=1:raise RuntimeError('Multiple services use the report port')
 pid=matches.pop();exe=process_path(pid);folder=exe.parents[2]
 if exe!=folder/'runtime/python/pythonw.exe' or not (folder/'app/portable.json').exists():raise RuntimeError('Another application is using port 8765')
 return pid,folder
def activate(old_pid,old_root):
 old_root=Path(old_root).resolve();stopped=False;new_process=None
 with open(data/'worker.lock','a+b') as lock:
  lock.seek(0);lock.write(b'0');lock.flush();lock.seek(0)
  try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
  except OSError:raise RuntimeError('A report is running. Finish it before updating')
  try:
   current=state()
   if current.get('processId',old_pid)!=old_pid or current.get('edition')!='portable-1':raise RuntimeError('A different application is using the report port')
   if any(r['status'] in {'running','queued'} for r in current['runs']):raise RuntimeError('A report is running. Finish it before updating')
   verify_process(old_pid,old_root)
   # Preserve the private display-name map outside versioned application files.
   old_names=old_root/'app/templates/names.json'
   if not (data/'names.json').exists() and old_names.exists():(data/'names.json').write_bytes(old_names.read_bytes())
   status('installing','Starting version '+version)
   schedule(root)
   subprocess.run(['taskkill','/PID',str(old_pid),'/F'],capture_output=True,check=True,creationflags=0x08000000);stopped=True
   new_process=python_start(root)
   for _ in range(60):
    try:
     current=state()
     if current.get('version')==version and current.get('processId')==new_process.pid:
      status('complete','Updated to version '+version+'. Your settings and reports are preserved.');return
    except OSError:pass
    if new_process.poll() is not None:break
    time.sleep(.5)
   raise RuntimeError('The new version did not start')
  except Exception:
   if stopped:
    if new_process and new_process.poll() is None:new_process.terminate();new_process.wait(timeout=10)
    schedule(old_root);python_start(old_root)
   raise
if __name__=='__main__':
 try:
  if sys.argv[1]=='--discover':
   existing=discover()
   if existing:activate(*existing)
   else:
    schedule(root);python_start(root)
  else:activate(int(sys.argv[1]),Path(sys.argv[2]))
 except Exception as error:status('failed','Update did not finish: '+str(error)+'. The previous version was retained.');sys.exit(1)
