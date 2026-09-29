"""Build an allowlisted, credential-free x64 Windows distribution."""
from pathlib import Path
import shutil,subprocess,sys,os,json,hashlib,zipfile,uuid
app=Path(__file__).resolve().parents[1];desktop=app/'desktop';workspace=app.parent
runtime=Path(os.environ.get('TITLEVISION_PYTHON_HOME',Path(sys.executable).parent))
node=Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node'
node_exe=Path(os.environ.get('TITLEVISION_NODE_EXE',node/'bin/node.exe'))
modules=Path(os.environ.get('TITLEVISION_NODE_MODULES',node/'node_modules'))
config=json.loads((app/'version.json').read_text(encoding='utf8'));version=config['version']
(workspace/'work').mkdir(exist_ok=True);(workspace/'outputs').mkdir(exist_ok=True)
stage=workspace/'work'/('portable-build-'+uuid.uuid4().hex)
stage.mkdir();out=workspace/'outputs/TitleVision-Full-Windows-App';out.mkdir(exist_ok=True)
ignore=shutil.ignore_patterns('__pycache__','*.pyc')
def copy(src,dst):
 dst.parent.mkdir(parents=True,exist_ok=True)
 if src.is_dir():shutil.copytree(src,dst,ignore=ignore)
 else:shutil.copy2(src,dst)
for file in ['server.py','main_workbook.py','monthly_sync.py','manual_edits.py','status_history.py','status_history.mjs','updater.py','update_activate.py','version.json','collector.mjs','rules.mjs','reconcile.py','schedule.ps1','report/prepare.mjs','report/build_portable.py','report/finish.py']:
 copy(app/file,stage/'app'/file)
for directory in ['public','templates']:copy(app/directory,stage/'app'/directory)
(stage/'app/templates/names.json').write_text('{}',encoding='utf8')
(stage/'app/portable.json').write_text(json.dumps({'version':version}),encoding='utf8')
for name in ['playwright','playwright-core']:copy(modules/name,stage/'app/node_modules'/name)
copy(node_exe,stage/'runtime/node/node.exe')
copy(desktop/'licenses/Node-LICENSE.txt',stage/'runtime/node/LICENSE.txt')
for file in runtime.iterdir():
 if file.is_file() and (file.suffix in {'.exe','.dll','.pyd','.zip'} or file.name=='LICENSE.txt'):copy(file,stage/'runtime/python'/file.name)
if (runtime/'DLLs').exists():copy(runtime/'DLLs',stage/'runtime/python/DLLs')
for item in (runtime/'Lib').iterdir():
 if item.name not in {'site-packages','test','idlelib','tkinter','ensurepip','__pycache__'}:copy(item,stage/'runtime/python/Lib'/item.name)
packages=runtime/'Lib/site-packages'
for prefix in ['xlsxwriter','openpyxl','lxml','et_xmlfile']:
 copy(packages/prefix,stage/'runtime/python/Lib/site-packages'/prefix)
 for info in packages.glob(prefix+'-*.dist-info'):copy(info,stage/'runtime/python/Lib/site-packages'/info.name)
# Isolate Python from any Python installation, registry paths or user packages on the target PC.
(stage/'runtime/python/python312._pth').write_text('.\npython312.zip\nDLLs\nLib\nLib/site-packages\nimport site\n',encoding='ascii')
copy(desktop/'portable-readme.txt',stage/'Read me.txt')
copy(desktop/'diagnostics.py',stage/'diagnostics.py')
copy(desktop/'diagnostics.mjs',stage/'app/diagnostics.mjs')
(stage/'Check Application.cmd').write_text('@echo off\r\n"%~dp0runtime\\python\\python.exe" "%~dp0diagnostics.py"\r\npause\r\n',encoding='ascii')
compiler=Path(os.environ['WINDIR'])/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
common=[str(compiler),'/nologo','/target:winexe','/platform:x64','/optimize+',
 '/reference:System.Windows.Forms.dll','/reference:System.Drawing.dll','/reference:System.Web.Extensions.dll',
 '/reference:System.IO.Compression.dll','/reference:System.IO.Compression.FileSystem.dll',
 '/win32manifest:'+str(desktop/'app.manifest'),'/win32icon:'+str(desktop/'reportdesk.ico')]
version_source=workspace/'work'/('Version-'+uuid.uuid4().hex+'.cs')
version_source.write_text('using System.Reflection;\n[assembly: AssemblyFileVersion("'+version+'.0")]\nstatic partial class Portable { internal const string Version="'+version+'"; }',encoding='utf8')
subprocess.run(common+['/out:'+str(stage/'TitleVision Report Desk.exe'),str(desktop/'Portable.cs'),str(version_source)],check=True)
manifest={p.relative_to(stage).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in stage.rglob('*') if p.is_file()}
assert not any('/data/' in p or p.endswith('.dpapi') or '@oai' in p for p in manifest)
(stage/'file-manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf8')
payload=workspace/'work'/('portable-payload-'+uuid.uuid4().hex+'.zip')
with zipfile.ZipFile(payload,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
 for file in stage.rglob('*'):
  if file.is_file():z.write(file,file.relative_to(stage).as_posix())
checksum=payload.with_suffix('.sha256');checksum.write_text(hashlib.sha256(payload.read_bytes()).hexdigest(),encoding='ascii')
setup=out/'TitleVision Report Desk Full Setup.exe'
subprocess.run(common+['/define:SETUP','/out:'+str(setup),'/resource:'+str(payload)+',payload.zip','/resource:'+str(checksum)+',payload.sha256',str(desktop/'Portable.cs'),str(version_source)],check=True)
shutil.copy2(setup,out/'TitleVision-Report-Desk-Setup.exe')
shutil.copy2(payload,out/'TitleVision Report Desk Portable.zip')
shutil.copy2(desktop/'portable-readme.txt',out/'Read me.txt')
receipt={'stage':str(stage),'installer':str(setup),'sha256':hashlib.sha256(setup.read_bytes()).hexdigest(),'sizeMB':round(setup.stat().st_size/1048576,1),'files':len(manifest)}
(workspace/'work/full-build.json').write_text(json.dumps(receipt,indent=2),encoding='utf8')
print(json.dumps(receipt))
