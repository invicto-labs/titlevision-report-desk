"""Regression checks for update diagnostics, local proxy bypass and rollback."""
from pathlib import Path
from unittest.mock import patch,Mock
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import importlib.util,json,os,subprocess,sys,threading,unittest,urllib.request,uuid
APP=Path(__file__).resolve().parents[1]
TEST=APP/'tests/results'/('activation-'+uuid.uuid4().hex);TEST.mkdir(parents=True)
spec=importlib.util.spec_from_file_location('activation_test_module',APP/'update_activate.py')
activation=importlib.util.module_from_spec(spec)
with patch.dict(os.environ,{'LOCALAPPDATA':str(TEST)}):spec.loader.exec_module(activation)

class ActivationTests(unittest.TestCase):
 def setUp(self):activation.result_file=None
 def test_attempt_result_retains_actual_error(self):
  result=TEST/('attempt-'+uuid.uuid4().hex+'.json')
  with patch.object(activation,'activate',side_effect=RuntimeError('Multiple services use port 8765 (process IDs: 40, 50)')):
   self.assertEqual(activation.main(['123',str(TEST),'--result',str(result)]),1)
  value=json.loads(result.read_text());self.assertEqual(value['phase'],'failed')
  self.assertIn('process IDs: 40, 50',value['message'])
  self.assertEqual(value['message'],json.loads((activation.data/'update-status.json').read_text())['message'])
 def test_proxy_is_not_used_for_local_health(self):
  class Handler(BaseHTTPRequestHandler):
   def log_message(self,*args):pass
   def do_GET(self):self.send_response(200);self.end_headers();self.wfile.write(b'{"local":true}')
  http=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=http.serve_forever,daemon=True).start()
  try:
   with patch('urllib.request.getproxies',return_value={'http':'http://127.0.0.1:1'}):
    with activation.local_http.open('http://127.0.0.1:'+str(http.server_port),timeout=3) as response:self.assertTrue(json.load(response)['local'])
  finally:http.shutdown();http.server_close()
 def test_schedule_error_keeps_its_details(self):
  result=subprocess.CompletedProcess([],1,b'',b'Windows denied access to the scheduled task')
  with patch.object(activation.subprocess,'run',return_value=result):
   with self.assertRaisesRegex(RuntimeError,'Windows denied access'):activation.schedule(APP.parent)
 def test_failed_new_engine_still_restarts_old_engine_if_schedule_rollback_fails(self):
  old=TEST/'old-version';old.mkdir(exist_ok=True)
  new_process=Mock();new_process.poll.return_value=1
  with patch.object(activation,'state',return_value={'processId':123,'edition':'portable-1','runs':[]}),patch.object(activation,'verify_process'),patch.object(activation,'listener_pids',return_value={123}),patch.object(activation,'schedule',side_effect=[None,RuntimeError('schedule restore denied')]),patch.object(activation.subprocess,'run'),patch.object(activation,'python_start',side_effect=[new_process,Mock()]) as start,patch.object(activation,'wait_ready',side_effect=RuntimeError('New engine startup failed')):
   with self.assertRaisesRegex(RuntimeError,'New engine startup failed.*schedule restore denied'):activation.activate(123,old)
  self.assertEqual(start.call_count,2);self.assertEqual(start.call_args.args[0],old.resolve())
 def test_startup_log_provides_the_underlying_failure(self):
  file=TEST/'startup.log';file.write_text('Traceback\nModuleNotFoundError: required component\n')
  process=Mock(reportdesk_log=file)
  self.assertIn('ModuleNotFoundError',activation.startup_failure(process))
 def test_unrelated_process_is_not_stopped(self):
  with patch.object(activation,'state',return_value={'processId':999,'edition':'portable-1','runs':[]}),patch.object(activation.subprocess,'run') as stop:
   with self.assertRaisesRegex(RuntimeError,'different application'):activation.activate(123,TEST)
   stop.assert_not_called()
 def test_duplicate_listeners_are_detected_before_stopping_the_old_engine(self):
  with patch.object(activation,'state',return_value={'processId':123,'edition':'portable-1','runs':[]}),patch.object(activation,'verify_process'),patch.object(activation,'listener_pids',return_value={123,456}),patch.object(activation.subprocess,'run') as stop:
   with self.assertRaisesRegex(RuntimeError,'process IDs: 123, 456'):activation.activate(123,TEST)
   stop.assert_not_called()
 def test_readiness_waits_for_the_exact_new_engine(self):
  process=Mock(pid=456);process.poll.return_value=None
  wrong={'ready':True,'edition':'portable-1','version':activation.version,'processId':123}
  right=dict(wrong,processId=456)
  with patch.object(activation,'health',side_effect=[OSError('starting'),wrong,right]) as health,patch.object(activation.time,'sleep'):
   activation.wait_ready(process)
  self.assertEqual(health.call_count,3)
 def test_failed_readiness_reports_the_actual_responding_process(self):
  process=Mock(pid=456);process.poll.return_value=None
  wrong={'ready':True,'edition':'portable-1','version':'old','processId':123}
  with patch.object(activation,'health',return_value=wrong),patch.object(activation.time,'monotonic',side_effect=[0,0,100]),patch.object(activation.time,'sleep'),patch.object(activation,'startup_failure',return_value='Engine not ready'):
   with self.assertRaisesRegex(RuntimeError,'returned version old / process 123'):activation.wait_ready(process)
 def test_installer_surfaces_attempt_error_and_stderr_fallback(self):
  # Compile the real installer helper; use a test entry point, without installing.
  harness=TEST/'ActivationTests.cs'
  harness.write_text('''using System; using System.IO;
static partial class Portable { internal const string Version="test-version"; }
class ActivationHarness {
 static int Main(string[] args){
  string file=Path.Combine(args[0],"failure.json");
  File.WriteAllText(file,"{\\"phase\\":\\"failed\\",\\"target\\":\\"test-version\\",\\"message\\":\\"Precise activation cause\\"}");
  if(Setup.ActivationFailure(file,"ignored")!="Precise activation cause")return 1;
  File.WriteAllText(file,"broken JSON");
  if(!Setup.ActivationFailure(file,"Python startup failed").Contains("Python startup failed"))return 2;
  File.WriteAllText(file,"{\\"phase\\":\\"failed\\",\\"target\\":\\"old-version\\",\\"message\\":\\"Stale error\\"}");
  if(Setup.ActivationFailure(file,"").Contains("Stale error"))return 3;
  return 0;
 }}''',encoding='utf8')
  compiler=Path(os.environ['WINDIR'])/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
  exe=TEST/'activation-helper.exe'
  command=[str(compiler),'/nologo','/target:exe','/platform:x64','/define:SETUP','/main:ActivationHarness','/out:'+str(exe)]
  for name in ('System.Windows.Forms','System.Drawing','System.Web.Extensions','System.IO.Compression','System.IO.Compression.FileSystem'):command.append('/reference:'+name+'.dll')
  command.extend([str(APP/'desktop/Portable.cs'),str(harness)])
  result=subprocess.run(command,capture_output=True,text=True)
  self.assertEqual(result.returncode,0,result.stdout+result.stderr)
  result=subprocess.run([str(exe),str(TEST)],capture_output=True,text=True)
  self.assertEqual(result.returncode,0,result.stdout+result.stderr)

if __name__=='__main__':unittest.main()
