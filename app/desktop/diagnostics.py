from pathlib import Path
import os,subprocess,sys,json,tempfile
root=Path(__file__).resolve().parent
print('TitleVision Report Desk diagnostics')
import sqlite3,ssl,ctypes,openpyxl,xlsxwriter,lxml.etree
assert Path(sys.executable).is_relative_to(root/'runtime')
for module in (openpyxl,xlsxwriter,lxml.etree):assert Path(module.__file__).is_relative_to(root/'runtime')
print('Included Python and Excel libraries: OK')
command=[str(root/'runtime/node/node.exe'),str(root/'app/diagnostics.mjs')]
result=subprocess.run(command,cwd=root/'app',capture_output=True,text=True,timeout=60,creationflags=0x08000000)
if result.returncode:
 print(result.stderr[-1500:]);sys.exit(1)
print(result.stdout.strip())
with tempfile.TemporaryDirectory(prefix='titlevision-check-') as folder:
 os.environ['TITLEVISION_DATA']=folder
 sys.path.insert(0,str(root/'app'))
 import server
 server.initialize()
 assert server.PORTABLE and server.NODE==root/'runtime/node/node.exe'
 state=server.public_state()
 assert not state['credentialsSaved'] and not state['schedule']
 print('Fresh settings and portable paths: OK')
print('Application checks passed. Save your TitleVision login and verify a live report before enabling the schedule.')
