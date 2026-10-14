"""Exercise real Windows registration, safe file removal, and report locking in fixtures."""
from pathlib import Path
import os,subprocess,unittest,uuid,msvcrt
APP=Path(__file__).resolve().parents[1]
class InstallationTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.folder=APP/'tests/results'/('install-'+uuid.uuid4().hex);cls.folder.mkdir(parents=True)
  source=cls.folder/'Harness.cs'
  source.write_text(r'''using System; using System.IO; using Microsoft.Win32;
static partial class Portable {internal const string Version="1.4.14";}
class Harness {
 static int Main(string[] args){
  if(args[0]=="health")return Portable.Health(int.Parse(args[1]));
  if(args[0]=="lock"){
   try{using(var file=Installation.LockWorker(args[1])){file.Unlock(0,1);}return 0;}catch(IOException){return 17;}
  }
  if(args[0]=="paths"){
   string root=Path.Combine(args[1],"installed"),outside=Path.Combine(args[1],"reports");
   Directory.CreateDirectory(root);Directory.CreateDirectory(outside);File.WriteAllText(Path.Combine(outside,"report.xlsx"),"keep");
   Directory.CreateDirectory(Path.Combine(root,"versions","1.0"));File.WriteAllText(Path.Combine(root,"versions","1.0","app.txt"),"remove");
   try{Installation.RemoveFiles(outside,root);return 1;}catch(Exception){}
   Installation.RemoveFiles(root,root);
   return !Directory.Exists(root)&&File.ReadAllText(Path.Combine(outside,"report.xlsx"))=="keep"?0:2;
  }
  if(args[0]=="registry"){
   string key=@"Software\TitleVisionReportDeskTests\"+Guid.NewGuid().ToString("N");
   try{
    Installation.RegisterKey(key,args[1],Path.Combine(args[1],"Uninstall.exe"),Path.Combine(args[1],"app.exe"),"1.4.14");
    using(var entry=Registry.CurrentUser.OpenSubKey(key)){
     if((string)entry.GetValue("DisplayVersion")!="1.4.14")return 1;
     if((string)entry.GetValue("DisplayName")!="TitleVision Report Desk")return 2;
     if((string)entry.GetValue("UninstallString")!="\""+Path.Combine(args[1],"Uninstall.exe")+"\" --uninstall")return 3;
    }
    Installation.RegisterKey(key,args[1],Path.Combine(args[1],"Uninstall.exe"),Path.Combine(args[1],"app.exe"),"1.4.15");
    using(var entry=Registry.CurrentUser.OpenSubKey(key)){if((string)entry.GetValue("DisplayVersion")!="1.4.15")return 4;}
    return 0;
   }finally{Registry.CurrentUser.DeleteSubKeyTree(key,false);}
  }
  if(args[0]=="validate"){try{Installation.ValidateTree(args[1],args[1]);return 0;}catch{return 17;}}
  return 99;
 }
}''',encoding='utf8')
  cls.exe=cls.folder/'InstallationTests.exe'
  compiler=Path(os.environ['WINDIR'])/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
  args=[str(compiler),'/nologo','/target:exe','/platform:x64','/main:Harness','/out:'+str(cls.exe)]
  args += ['/reference:'+name+'.dll' for name in ('System.Windows.Forms','System.Drawing','System.Web.Extensions','System.IO.Compression','System.IO.Compression.FileSystem')]
  result=subprocess.run([*args,str(APP/'desktop/Portable.cs'),str(source)],capture_output=True,text=True)
  if result.returncode:raise RuntimeError(result.stdout+result.stderr)
 def test_installed_apps_registration_and_version_update(self):
  self.assertEqual(subprocess.run([str(self.exe),'registry',str(self.folder)],capture_output=True).returncode,0)
 def test_launcher_uses_health_without_waiting_for_reporting_database(self):
  from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
  import threading
  seen=[]
  class Handler(BaseHTTPRequestHandler):
   def log_message(self,*args):pass
   def do_GET(self):
    seen.append(self.path)
    self.send_response(200 if self.path=='/api/health' else 500);self.end_headers()
    self.wfile.write(b'{"edition":"portable-1","ready":true}')
  http=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
  try:self.assertEqual(subprocess.run([str(self.exe),'health',str(http.server_port)],capture_output=True).returncode,1);self.assertEqual(seen,['/api/health'])
  finally:http.shutdown();http.server_close();thread.join()
 def test_removal_is_confined_to_install_folder_and_preserves_reports(self):
  self.assertEqual(subprocess.run([str(self.exe),'paths',str(self.folder)],capture_output=True).returncode,0)
 def test_uninstall_respects_running_python_report_lock(self):
  lock=self.folder/'worker.lock'
  with lock.open('a+b') as file:
   file.seek(0);msvcrt.locking(file.fileno(),msvcrt.LK_NBLCK,1)
   self.assertEqual(subprocess.run([str(self.exe),'lock',str(lock)],capture_output=True).returncode,17)
   msvcrt.locking(file.fileno(),msvcrt.LK_UNLCK,1)
  self.assertEqual(subprocess.run([str(self.exe),'lock',str(lock)],capture_output=True).returncode,0)
 def test_linked_folder_is_rejected_before_removal(self):
  target=self.folder/'link-target';target.mkdir();linked=self.folder/'linked-root';linked.mkdir();link=linked/'junction'
  # Create a junction, then remove only that junction after verifying traversal is refused.
  env=dict(os.environ,TV_TEST_LINK=str(link),TV_TEST_TARGET=str(target))
  result=subprocess.run(['powershell','-NoProfile','-Command','New-Item -ItemType Junction -Path $env:TV_TEST_LINK -Target $env:TV_TEST_TARGET'],env=env,capture_output=True,text=True)
  if result.returncode:self.skipTest('Junction creation unavailable')
  try:self.assertEqual(subprocess.run([str(self.exe),'validate',str(linked)],capture_output=True).returncode,17)
  finally:os.rmdir(link)

if __name__=='__main__':unittest.main()
