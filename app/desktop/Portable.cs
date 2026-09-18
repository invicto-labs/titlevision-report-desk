using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.IO.Compression;
using System.Net;
using System.Reflection;
using System.Security.Cryptography;
using System.Threading;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows.Forms;

static partial class Portable {
 internal const string Name="TitleVision Report Desk";
 internal static readonly string Root=AppDomain.CurrentDomain.BaseDirectory;
 internal static string Edge() {
  foreach(var root in new[]{Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86),Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles),Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData)}) {
   var p=Path.Combine(root,@"Microsoft\Edge\Application\msedge.exe"); if(File.Exists(p)) return p;
  }
  throw new Exception("Microsoft Edge is required. Install Microsoft Edge on this computer and try again.");
 }
 internal static void Prerequisites() {
  if(!Environment.Is64BitOperatingSystem) throw new Exception("This installer requires 64-bit Windows 10 or Windows 11.");
  Edge();
 }
 internal static string Hash(Stream stream) {
  using(var sha=SHA256.Create()) return BitConverter.ToString(sha.ComputeHash(stream)).Replace("-","").ToLowerInvariant();
 }
 internal static string ResourceText(string name) {
  using(var s=Assembly.GetExecutingAssembly().GetManifestResourceStream(name))
  using(var r=new StreamReader(s))return r.ReadToEnd().Trim();
 }
 internal static ProcessStartInfo Python(string root,string args) {
  var start=new ProcessStartInfo(Path.Combine(root,@"runtime\python\pythonw.exe"),args);
  start.WorkingDirectory=Path.Combine(root,"app");start.UseShellExecute=false;start.CreateNoWindow=true;
  start.EnvironmentVariables.Remove("PYTHONHOME");start.EnvironmentVariables.Remove("PYTHONPATH");
  start.EnvironmentVariables["PYTHONNOUSERSITE"]="1";
  start.EnvironmentVariables["TITLEVISION_NODE"]=Path.Combine(root,@"runtime\node\node.exe");
  return start;
 }
 internal static int Health(int port) {
  try {
   // A short HTTP connect timeout can occur even on an unused Windows port.
   // Check actual listeners before treating a failed HTTP request as a conflict.
   bool listening=false;
   foreach(var endpoint in System.Net.NetworkInformation.IPGlobalProperties.GetIPGlobalProperties().GetActiveTcpListeners())
    if(endpoint.Port==port && (IPAddress.IsLoopback(endpoint.Address) || endpoint.Address.Equals(IPAddress.Any) || endpoint.Address.Equals(IPAddress.IPv6Any))) {listening=true;break;}
   if(!listening)return 0;
   var req=(HttpWebRequest)WebRequest.Create("http://127.0.0.1:"+port+"/api/state");req.Proxy=null;req.Timeout=1200;req.ReadWriteTimeout=1200;
   using(var response=req.GetResponse())using(var reader=new StreamReader(response.GetResponseStream())) {
    var state=new JavaScriptSerializer().Deserialize<Dictionary<string,object>>(reader.ReadToEnd());
    return state.ContainsKey("edition") && Convert.ToString(state["edition"])=="portable-1" && state.ContainsKey("csrf")?1:2;
   }
  } catch(WebException e) { return e.Status==WebExceptionStatus.ConnectFailure?0:2; } catch {return 2;}
 }
 internal static void ValidateFiles(string root) {
  foreach(var file in new[]{@"app\server.py",@"app\portable.json",@"app\report\build_portable.py",@"runtime\python\pythonw.exe",@"runtime\node\node.exe",@"app\node_modules\playwright\package.json"})
   if(!File.Exists(Path.Combine(root,file)))throw new Exception("An application file is missing: "+file+". Extract the complete package or reinstall Report Desk.");
 }
 internal static void Launch(bool showWindow) {
  Prerequisites();ValidateFiles(Root);
  using(var gate=new Mutex(false,@"Local\TitleVisionReportDeskStart")) {
   bool owned=false;
   try {
    try{owned=gate.WaitOne(45000);}catch(AbandonedMutexException){owned=true;}
    if(!owned)throw new Exception("Report Desk is already starting. Try again shortly.");
    int state=Health(8765);
    if(state==2)throw new Exception("Another application or an older Report Desk service is using port 8765. Close that background service before opening this edition.");
    if(state==0) {
     var start=Python(Root,"\""+Path.Combine(Root,@"app\server.py")+"\"");
     // These defaults are also used by the scheduled process.
     start.EnvironmentVariables.Remove("TITLEVISION_DATA");start.EnvironmentVariables["TITLEVISION_PORT"]="8765";
     using(var p=Process.Start(start)) {
      bool ready=false;
      for(int i=0;i<50;i++){Thread.Sleep(500);if(Health(8765)==1){ready=true;break;}if(p.HasExited)break;}
      if(!ready)throw new Exception("The report engine could not start. Run the bundled Check Application.cmd for diagnostics.");
     }
    }
   } finally{if(owned)gate.ReleaseMutex();}
  }
  if(showWindow)Process.Start(new ProcessStartInfo(Edge(),"--app=http://127.0.0.1:8765/"){UseShellExecute=false});
 }
 internal static void Shortcut(string file,string exe) {
  var type=Type.GetTypeFromProgID("WScript.Shell");object shell=Activator.CreateInstance(type),link=null;
  try {
   link=type.InvokeMember("CreateShortcut",BindingFlags.InvokeMethod,null,shell,new object[]{file});var t=link.GetType();
   foreach(var kv in new Dictionary<string,string>{{"TargetPath",exe},{"WorkingDirectory",Path.GetDirectoryName(exe)},{"IconLocation",exe+",0"},{"Description",Name}})
    t.InvokeMember(kv.Key,BindingFlags.SetProperty,null,link,new object[]{kv.Value});
   t.InvokeMember("Save",BindingFlags.InvokeMethod,null,link,null);
  } finally {if(link!=null)System.Runtime.InteropServices.Marshal.FinalReleaseComObject(link);System.Runtime.InteropServices.Marshal.FinalReleaseComObject(shell);}
 }
}
#if SETUP
static class Program {
 [STAThread]static int Main(string[] args) {
  Application.EnableVisualStyles();
  try {
   if(args.Length==2 && args[0]=="--test-extract") {Setup.Extract(Path.GetFullPath(args[1]));return 0;}
   if(args.Length==4 && args[0]=="--apply-update") {
    if(args[3]!=Portable.Version)throw new Exception("Installer version does not match the requested release");
    Portable.Prerequisites();string target=Setup.Target();
    if(!Directory.Exists(target))Setup.Extract(target);else Setup.VerifyExisting(target);
    Setup.Activate(target,args[1],args[2]);Setup.Shortcuts(target,true);return 0;
   }
   using(var form=new Setup())Application.Run(form);return 0;
  }catch(Exception e){if(args.Length>0){
    var directory=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),@"TitleVision Report Desk\data");Directory.CreateDirectory(directory);
    var message=e.Message.StartsWith("Update did not finish:")?e.Message:"Update did not finish: "+e.Message;
    var text=new JavaScriptSerializer().Serialize(new{phase="failed",message=message,time=(DateTime.UtcNow-new DateTime(1970,1,1)).TotalSeconds,target=Portable.Version});File.WriteAllText(Path.Combine(directory,"update-status.json"),text);
   }else MessageBox.Show(e.Message,Portable.Name,MessageBoxButtons.OK,MessageBoxIcon.Error);return 1;}
 }
}
sealed class Setup:Form {
 readonly Button install=new Button();readonly Label status=new Label();readonly CheckBox desktop=new CheckBox();readonly CheckBox open=new CheckBox();
 bool busy;
 internal Setup() {
  Text=Portable.Name+" — Full Setup "+Portable.Version;ClientSize=new Size(550,355);StartPosition=FormStartPosition.CenterScreen;
  FormBorderStyle=FormBorderStyle.FixedDialog;MaximizeBox=false;Font=new Font("Segoe UI",10);BackColor=Color.White;
  Icon=Icon.ExtractAssociatedIcon(Application.ExecutablePath);
  var title=new Label{Text="Install on this Windows PC",Left=24,Top=24,Width=505,Height=38,Font=new Font("Segoe UI",18,FontStyle.Bold),ForeColor=Color.FromArgb(19,48,78)};
  var body=new Label{Text="Includes the report engine and required runtimes.\n\nAfter installation, save your TitleVision login, run one report to verify it, then enable the daily 8:45 AM schedule. Microsoft Edge must be installed.",Left=24,Top=78,Width=495,Height=110};
  desktop.SetBounds(24,200,480,25);desktop.Text="Create a desktop shortcut";desktop.Checked=true;
  open.SetBounds(24,230,480,25);open.Text="Open Report Desk after installation";open.Checked=true;
  status.SetBounds(24,282,325,55);status.Text="For 64-bit Windows 10 / 11.";
  install.SetBounds(376,283,150,42);install.Text="Install";install.BackColor=Color.FromArgb(8,127,121);install.ForeColor=Color.White;install.FlatStyle=FlatStyle.Flat;
  install.Click+=Install;Controls.AddRange(new Control[]{title,body,desktop,open,status,install});AcceptButton=install;
  FormClosing+=(s,e)=>{if(busy)e.Cancel=true;};
 }
 internal static void Extract(string target) {
  if(Directory.Exists(target))throw new Exception("This version is already installed in "+target+". Open its existing application, or choose a fresh folder for extraction.");
  // Keep the temporary name short so deeply nested dependency paths fit Windows limits.
  string staging=Path.Combine(Path.GetDirectoryName(target),".tv-"+Guid.NewGuid().ToString("N").Substring(0,12));
  using(var stream=Assembly.GetExecutingAssembly().GetManifestResourceStream("payload.zip")) {
   if(Portable.Hash(stream)!=Portable.ResourceText("payload.sha256"))throw new Exception("Installer checksum failed. Download the installer again.");
   stream.Position=0;Directory.CreateDirectory(staging);string prefix=Path.GetFullPath(staging).TrimEnd(Path.DirectorySeparatorChar)+Path.DirectorySeparatorChar;
   using(var zip=new ZipArchive(stream,ZipArchiveMode.Read))foreach(var entry in zip.Entries) {
    string file=Path.GetFullPath(Path.Combine(prefix,entry.FullName.Replace('/',Path.DirectorySeparatorChar)));
    if(!file.StartsWith(prefix,StringComparison.OrdinalIgnoreCase))throw new Exception("Invalid installer file path.");
    if(entry.FullName.EndsWith("/")){Directory.CreateDirectory(file);continue;}
    Directory.CreateDirectory(Path.GetDirectoryName(file));using(var input=entry.Open())using(var output=new FileStream(file,FileMode.CreateNew))input.CopyTo(output);
   }
  }
  Portable.ValidateFiles(staging);
  // The final version directory appears only after successful extraction.
  Directory.Move(staging,target);
 }
 internal static string Target(){return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),@"Programs\TitleVision Report Desk\versions",Portable.Version);}
 internal static void VerifyExisting(string folder){
  var manifest=new JavaScriptSerializer().Deserialize<Dictionary<string,string>>(File.ReadAllText(Path.Combine(folder,"file-manifest.json")));
  foreach(var item in manifest){var file=Path.GetFullPath(Path.Combine(folder,item.Key));if(!file.StartsWith(Path.GetFullPath(folder)+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase))throw new Exception("Invalid installed file path");using(var stream=File.OpenRead(file))if(Portable.Hash(stream)!=item.Value)throw new Exception("An installed file has changed; use a fresh release version");}
  Portable.ValidateFiles(folder);
 }
 internal static void Activate(string target,string pid,string oldRoot){
  var directory=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),@"TitleVision Report Desk\data\updates");Directory.CreateDirectory(directory);
  var result=Path.Combine(directory,"activation-"+Guid.NewGuid().ToString("N")+".json");
  var arguments="\""+Path.Combine(target,@"app\update_activate.py")+"\" "+(pid==null?"--discover":pid+" \""+oldRoot+"\"")+" --result \""+result+"\"";
  var start=Portable.Python(target,arguments);start.FileName=Path.Combine(target,@"runtime\python\python.exe");start.RedirectStandardError=true;start.RedirectStandardOutput=true;
  using(var p=Process.Start(start)){
   var stderr=p.StandardError.ReadToEndAsync();var stdout=p.StandardOutput.ReadToEndAsync();
   if(!p.WaitForExit(240000)){if(!p.HasExited)p.Kill();throw new Exception("Application activation timed out. Your report files were retained.");}
   if(p.ExitCode!=0)throw new Exception(ActivationFailure(result,stderr.Result));
  }
 }
 internal static string ActivationFailure(string file,string stderr){
  try {
   var result=new JavaScriptSerializer().Deserialize<Dictionary<string,object>>(File.ReadAllText(file));
   if(result.ContainsKey("target") && Convert.ToString(result["target"])==Portable.Version && result.ContainsKey("phase") && Convert.ToString(result["phase"])=="failed" && result.ContainsKey("message")){
    var detail=Convert.ToString(result["message"]);if(!String.IsNullOrWhiteSpace(detail))return detail;
   }
  } catch(IOException){} catch(ArgumentException){} catch(InvalidOperationException){}
  if(!String.IsNullOrWhiteSpace(stderr)){var text=stderr.Trim();return "The activation engine could not run: "+(text.Length>1800?text.Substring(text.Length-1800):text);}
  return "Activation could not finish. Run Check Application.cmd in the installed version folder. Your report files were retained.";
 }
 internal static void Shortcuts(string target,bool desktop){
  string exe=Path.Combine(target,"TitleVision Report Desk.exe");
  Portable.Shortcut(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Programs),"TitleVision Report Desk.lnk"),exe);
  if(desktop)Portable.Shortcut(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory),"TitleVision Report Desk.lnk"),exe);
 }
 async void Install(object sender,EventArgs args) {
  install.Enabled=false;busy=true;status.Text="Extracting application files…";
  try {
   Portable.Prerequisites();
   string target=Target();
   await Task.Run(()=>{if(!Directory.Exists(target))Extract(target);else VerifyExisting(target);Activate(target,null,null);});
   string exe=Path.Combine(target,"TitleVision Report Desk.exe");
   Shortcuts(target,desktop.Checked);
   status.Text="Installed. Save your login in Settings.";busy=false;
   if(open.Checked)Process.Start(new ProcessStartInfo(exe){UseShellExecute=true});
   MessageBox.Show("Installed successfully. Save your login, verify one report, then enable scheduling.",Portable.Name,MessageBoxButtons.OK,MessageBoxIcon.Information);Close();
  } catch(Exception e) {busy=false;install.Enabled=true;status.Text="Installation did not finish.";MessageBox.Show(e.Message,Portable.Name,MessageBoxButtons.OK,MessageBoxIcon.Error);}
 }
}
#else
static class Program {
 [STAThread]static int Main(string[] args) {
  Application.EnableVisualStyles();
  try {
   if(args.Length==1 && args[0]=="--check-files"){Portable.Prerequisites();Portable.ValidateFiles(Portable.Root);return 0;}
   if(args.Length==2 && args[0]=="--test-health")return Portable.Health(int.Parse(args[1]));
   Portable.Launch(args.Length!=1 || args[0]!="--start-only");return 0;
  }catch(Exception e){if(args.Length>0)File.WriteAllText(Path.Combine(Environment.CurrentDirectory,"launcher-error.txt"),e.ToString());else MessageBox.Show(e.Message,Portable.Name,MessageBoxButtons.OK,MessageBoxIcon.Error);return 1;}
 }
}
#endif
