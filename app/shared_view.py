"""Read-only dashboards on teammates' PCs; never publish to the shared folder."""
import json,re,os
from pathlib import Path

def setting(db,key,default=''):
 with db() as c:row=c.execute('SELECT value FROM settings WHERE key=?',(key,)).fetchone()
 return json.loads(row[0]) if row else default

def enabled(db):return setting(db,'pc_role','collector')=='viewer'
def configured(db):return setting(db,'viewer_folder')

def location(path):
 if os.name!='nt' or not isinstance(path,str) or not path.startswith('\\\\') or len(path)>1024:
  raise ValueError('Enter the shared Windows folder path, beginning with \\\\server\\share.')
 place=Path(path.rstrip('\\/'))
 if not place.is_dir():raise ValueError('The shared folder is unavailable. Connect to the company network and check folder access.')
 return place

def books_at(place):
 result=[]
 for file in place.iterdir():
  match=re.fullmatch(r'TitleVision Main Error Report - (\d{4}-(?:0[1-9]|1[0-2]))\.xlsx',file.name)
  if match and file.is_file():result.append({'month':match[1],'sharedViewer':True})
 return sorted(result,key=lambda row:row['month'],reverse=True)

def books(db):return books_at(location(configured(db)))

def configure(db,path):
 place=location(path)
 # Listing proves read access. No write probe, import or workbook replacement.
 found=books_at(place)
 with db() as c:
  c.executemany('INSERT OR REPLACE INTO settings VALUES (?,?)',[
   ('viewer_folder',json.dumps(str(place))),('pc_role',json.dumps('viewer')),('schedule',json.dumps(False))])
 return {'message':'Viewer connected. This PC reads the shared Excel automatically; report collection is disabled.','books':found}

def collector(db):
 with db() as c:c.execute('INSERT OR REPLACE INTO settings VALUES (?,?)',('pc_role',json.dumps('collector')))
 return {'message':'Report PC mode restored. Check your report settings before enabling the daily schedule.'}

def target(db,month):return location(configured(db))/f'TitleVision Main Error Report - {month}.xlsx'
