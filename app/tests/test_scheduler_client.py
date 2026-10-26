import sys,json,unittest,urllib.error,subprocess,os,time,uuid,socket,urllib.request
from pathlib import Path
from unittest.mock import patch,MagicMock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import scheduler_client
APP=Path(__file__).resolve().parents[1]
class SchedulerTests(unittest.TestCase):
 def test_healthy_engine_is_woken_without_starting_another(self):
  http=MagicMock();http.open.return_value.__enter__.return_value.read.side_effect=[b'{"csrf":"token"}',b'{"ok":true}']
  with patch.object(scheduler_client.urllib.request,'build_opener',return_value=http),patch.object(scheduler_client.subprocess,'Popen') as spawn:
   self.assertEqual(scheduler_client.wake(APP,APP,8765,sys.executable),{'ok':True});spawn.assert_not_called()
   request=http.open.call_args.args[0];self.assertTrue(request.full_url.endswith('/api/scheduler/wake'));self.assertEqual(request.get_header('X-csrf-token'),'token')
 def test_unhealthy_engine_does_not_spawn_or_fall_back_to_database(self):
  for error in (urllib.error.HTTPError('url',503,'repair',None,None),urllib.error.URLError(TimeoutError('slow'))):
   http=MagicMock();http.open.side_effect=error
   with patch.object(scheduler_client.urllib.request,'build_opener',return_value=http),patch.object(scheduler_client.subprocess,'Popen') as spawn:
    with self.assertRaises(Exception):scheduler_client.wake(APP,APP,8765,sys.executable)
    spawn.assert_not_called()
 def test_no_server_starts_engine_then_forwards(self):
  data=APP/'tests/results'/('scheduler-start-'+uuid.uuid4().hex);data.mkdir(parents=True)
  http=MagicMock();response=MagicMock();response.__enter__.return_value.read.side_effect=[b'{"csrf":"token"}',b'{"ok":true}']
  http.open.side_effect=[urllib.error.URLError(ConnectionRefusedError()),response,response]
  with patch.object(scheduler_client.urllib.request,'build_opener',return_value=http),patch.object(scheduler_client.subprocess,'Popen') as spawn,patch.object(scheduler_client.time,'sleep'):
   self.assertEqual(scheduler_client.wake(APP,data,8765,sys.executable),{'ok':True})
   self.assertEqual(spawn.call_count,1);self.assertNotIn('--scheduled',spawn.call_args.args[0])
 def test_second_server_does_not_initialize_its_database(self):
  data=APP/'tests/results'/('single-engine-'+uuid.uuid4().hex);data.mkdir(parents=True)
  with socket.socket() as sock:
   sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
  env=dict(os.environ,TITLEVISION_DATA=str(data/'first'),TITLEVISION_PORT=str(port))
  first=subprocess.Popen([sys.executable,str(APP/'server.py')],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  http=urllib.request.build_opener(urllib.request.ProxyHandler({}))
  try:
   for _ in range(80):
    try:
     with http.open(f'http://127.0.0.1:{port}/api/health',timeout=1) as r:
      if json.load(r)['ready']:break
    except OSError:pass
    time.sleep(.1)
   else:self.fail('first server failed')
   other=data/'second'
   second=subprocess.run([sys.executable,str(APP/'server.py')],env=dict(env,TITLEVISION_DATA=str(other)),capture_output=True,timeout=25)
   self.assertNotEqual(second.returncode,0)
   self.assertFalse((other/'state-v2/reporting.sqlite').exists())
   self.assertFalse((other/'state-v2/committed.json').exists())
   # The scheduled invocation must forward to that existing engine, without
   # initializing a competing database even if its environment differs.
   scheduled=subprocess.run([sys.executable,str(APP/'server.py'),'--scheduled'],env=dict(env,TITLEVISION_DATA=str(other)),capture_output=True,timeout=25)
   self.assertEqual(scheduled.returncode,0,scheduled.stderr.decode())
   self.assertFalse((other/'state-v2/reporting.sqlite').exists())
  finally:first.terminate();first.wait(timeout=10)
if __name__=='__main__':unittest.main()
