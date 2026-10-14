import io,json,hashlib,uuid,unittest,sys,os
from pathlib import Path
from unittest.mock import patch
from urllib.request import Request
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from updater import Updates,Redirects,version,INSTALLER
class UpdateTests(unittest.TestCase):
 def setUp(self):
  self.root=Path(__file__).resolve().parent/'results'/('updates-'+uuid.uuid4().hex);self.data=self.root/'data';self.data.mkdir(parents=True)
  (self.root/'version.json').write_text(json.dumps({'version':'1.2.0','repository':'invicto-labs/titlevision-report-desk'}))
  (self.root/'portable.json').write_text('{}');self.up=Updates(self.root,self.data,lambda b,*_:b)
  self.bytes=b'test-installer';self.release={'tag_name':'v1.3.0','draft':False,'prerelease':False,'assets':[{'name':INSTALLER,'state':'uploaded','id':123,'size':len(self.bytes),'digest':'sha256:'+hashlib.sha256(self.bytes).hexdigest()}]}
 def check(self):
  with patch.object(self.up,'request',return_value=io.BytesIO(json.dumps(self.release).encode())):return self.up.check()
 def test_version_order(self):self.assertGreater(version('v1.10.0'),version('1.9.9'))
 def test_bad_version(self):
  for value in ['1.2','v1.2.0-beta','../1.2.3','01.2.0']:
   with self.assertRaises(ValueError):version(value)
 def test_new_version(self):self.assertTrue(self.check()['available'])
 def test_no_downgrade(self):self.release['tag_name']='v1.1.1';self.assertFalse(self.check()['available'])
 def test_no_prerelease(self):
  self.release['prerelease']=True
  with self.assertRaises(ValueError):self.check()
 def test_checksum_required(self):
  del self.release['assets'][0]['digest']
  with self.assertRaises(ValueError):self.check()
 def test_duplicate_installer_rejected(self):
  self.release['assets']*=2
  with self.assertRaises(ValueError):self.check()
 def test_external_url_rejected(self):
  with self.assertRaises(ValueError):self.up.request('https://example.com')
 def test_redirect_strips_token(self):
  r=Request(self.up.api+'/releases/assets/1',headers={'Authorization':'Bearer test-secret'})
  new=Redirects().redirect_request(r,None,302,'',{},'https://release-assets.githubusercontent.com/file')
  self.assertFalse(new.has_header('Authorization'))
 def test_redirect_rejects_external(self):
  with self.assertRaises(ValueError):Redirects().redirect_request(Request(self.up.api),None,302,'',{},'https://example.com/file')
 def test_bad_download_not_executed(self):
  release=self.check()
  with patch.object(self.up,'request',return_value=io.BytesIO(b'wrong-content')),patch('updater.subprocess.Popen') as execute:
   self.up.download(release);execute.assert_not_called()
  self.assertEqual(self.up.status()['phase'],'failed')
 def test_verified_download_passes_version(self):
  release=self.check()
  with patch.object(self.up,'request',return_value=io.BytesIO(self.bytes)),patch('updater.subprocess.Popen') as execute:
   self.up.download(release);args=execute.call_args.args[0];self.assertEqual(args[1],'--apply-update');self.assertEqual(args[-1],'1.3.0')
  self.assertEqual(self.up.status()['phase'],'installing')
 def test_busy_flag(self):self.up.write('downloading','test');self.assertTrue(self.up.busy())
 def test_update_waits_for_refresh_then_starts_once(self):
  release=self.check()
  with patch.object(self.up,'request',return_value=io.BytesIO(self.bytes)),patch.object(self.up,'activity',side_effect=[True,True,False]),patch.object(self.up.cancelled,'wait',return_value=False) as wait,patch('updater.subprocess.Popen') as execute:
   self.up.download(release)
   self.assertEqual(wait.call_count,2);execute.assert_called_once()
  self.assertEqual(self.up.status()['phase'],'installing')
 def test_queued_update_can_be_cancelled_without_executing_installer(self):
  release=self.check()
  def cancel(*_):self.up.cancel();return True
  with patch.object(self.up,'request',return_value=io.BytesIO(self.bytes)),patch.object(self.up,'activity',return_value=True),patch.object(self.up.cancelled,'wait',side_effect=cancel),patch('updater.subprocess.Popen') as execute:
   self.up.download(release);execute.assert_not_called()
  self.assertEqual(self.up.status()['phase'],'cancelled');self.assertFalse(self.up.busy())
 def test_waiting_blocks_new_work_and_interrupted_queue_does_not_stick(self):
  self.up.write('waiting','test');self.assertTrue(self.up.busy())
  self.up.write('waiting','test',owner=-1);self.assertFalse(self.up.busy());self.assertEqual(self.up.status()['phase'],'failed')
 def test_installing_update_cannot_be_cancelled(self):
  self.up.write('installing','test')
  with self.assertRaises(ValueError):self.up.cancel()
 def test_current_version_result_stays_visible(self):
  with patch.object(self.up,'check',return_value={'available':False,'current':'1.2.0','latest':'1.2.0'}):self.up.install()
  self.assertEqual(self.up.status()['phase'],'current')
  self.assertIn('latest version',self.up.status()['message'])
 def test_saved_read_token_takes_priority(self):
  self.up.save_token('read-only-test-token')
  with patch('updater.subprocess.run') as git:
   self.assertEqual(self.up.token(),'read-only-test-token');git.assert_not_called()
 def test_existing_git_signin_stays_in_memory(self):
  from subprocess import CompletedProcess
  with patch('updater.subprocess.run',return_value=CompletedProcess([],0,'username=invicto-labs\npassword=test-token\n')) as git:
   self.assertEqual(self.up.token(),'test-token')
   self.assertEqual(git.call_args.kwargs['env']['GCM_INTERACTIVE'],'never')
   self.assertEqual(git.call_args.kwargs['env']['GIT_TERMINAL_PROMPT'],'0')
   self.assertFalse((self.data/'github-update.dpapi').exists())
 def test_wrong_git_account_ignored(self):
  from subprocess import CompletedProcess
  with patch('updater.subprocess.run',return_value=CompletedProcess([],0,'username=someone-else\npassword=test-token\n')):
   self.assertEqual(self.up.token(),'')
 def test_git_not_installed(self):
  with patch('updater.subprocess.run',side_effect=FileNotFoundError):self.assertEqual(self.up.token(),'')
 def test_interrupted_update_can_be_retried(self):
  self.up.write('installing','test')
  with patch('updater.time.time',return_value=self.up.status()['time']+1801):
   self.assertEqual(self.up.status()['phase'],'failed');self.assertFalse(self.up.busy())
if __name__=='__main__':unittest.main()
