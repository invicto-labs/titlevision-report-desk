"""October 2026 monthly lifecycle and verified status/points refresh.

All callers hold the application's worker lock. Publish immutable workbook
revisions only after source reconciliation, exact error matching and pivot checks.
"""
from datetime import date,datetime,timedelta,timezone
from pathlib import Path
from urllib.parse import urlparse,parse_qs
import calendar,hashlib,json,math,re,sys,uuid
import main_workbook as main
import manual_edits
from reconcile import canonical
from status_history import fields as status_fields

START=date(2026,10,1)
IST=timezone(timedelta(hours=5,minutes=30))
def today():return datetime.now(IST).date()
def active():return today()>=START
def eligible(month):return bool(re.fullmatch(r'\d{4}-\d{2}',month)) and month>=START.strftime('%Y-%m')
def guard(month):
 if not active():raise ValueError('Monthly status refresh and workbook management start on 1 October 2026.')
 try:first=date.fromisoformat(month+'-01')
 except (ValueError,TypeError):raise ValueError('Invalid workbook month')
 if not eligible(month) or first>today().replace(day=1):raise ValueError('Choose October 2026 or a later month that has started.')
 return first
def stamp():return datetime.now(timezone.utc).isoformat()
def state(db,month,status,message):
 with db() as c:c.execute('INSERT OR REPLACE INTO main_sync_state VALUES (?,?,?,?)',(month,status,message,stamp()))
def safe_folder(data,relative,base):
 folder=(data/relative).resolve()
 if not folder.is_relative_to((data/base).resolve()):raise ValueError('Invalid saved workbook location')
 return folder
def source_id(record):
 value=record.get('sourceId')
 if not isinstance(value,str) or not re.fullmatch(r'\d{1,64}',value):
  raise ValueError('A report has no verified TitleVision error ID. Collect its dates again with the current app before adding it.')
 return value
def order_key(record):
 url=urlparse(record['url'])
 if url.scheme!='https' or url.netloc!='tv.datatracetitle.com':raise ValueError('Invalid source order URL')
 order=parse_qs(url.query).get('PublicOrderId',[''])[0]
 if not order:raise ValueError('Source order identity is missing')
 values=canonical(record['values'])
 return order,values[1],values[12]
def read_snapshot(folder,start,end):
 source=json.loads((folder/'source.json').read_text(encoding='utf8'))
 receipt=json.loads((folder/'reconciled.json').read_text(encoding='utf8'))
 collection=json.loads((folder/'collection.json').read_text(encoding='utf8'))
 if collection['start']!=start or collection['end']!=end:raise ValueError('Month-to-date export dates do not match')
 for filename,key in [('source.json','sourceSha256'),('source.xlsx','exportSha256')]:
  if hashlib.sha256((folder/filename).read_bytes()).hexdigest()!=receipt.get(key):raise ValueError('Month-to-date source verification failed')
 if len(source)!=receipt.get('count') or len(source)!=collection['count']:raise ValueError('Month-to-date source count does not match')
 found={};points=0
 for record in source:
  if not isinstance(record.get('values'),list) or len(record['values'])!=20:raise ValueError('Unexpected month-to-date source columns')
  key=source_id(record);values=canonical(record['values']);created=values[12][:10]
  if key in found:raise ValueError('Duplicate TitleVision error ID in month-to-date export')
  if not start<=created<=end:raise ValueError('Month-to-date export includes an unexpected Created Date')
  value=float(values[15])
  if not math.isfinite(value) or value<0 or not values[0]:raise ValueError('Invalid current error status or points')
  order_key(record)
  expected=status_fields(record,required=True)
  if record.get('statusFields',expected)!=expected:raise ValueError('Status comment fields do not match their source history')
  found[key]=record;points+=value
 if points!=collection['points']:raise ValueError('Month-to-date source points do not match')
 return found
def records(root,data,db,month,selected):
 with db() as c:runs={r['id']:dict(r) for r in c.execute('SELECT * FROM runs')}
 result=[];cache={};seen=set()
 for day in sorted(d for d in selected if d.startswith(month+'-')):
  rid=selected[day]
  if rid not in cache:
   if rid not in runs:raise ValueError('An approved daily report is missing')
   main.load_report(root,data,runs[rid])
   folder=data/'runs'/rid
   source=json.loads((folder/'source.json').read_text(encoding='utf8'))
   rows=json.loads((folder/'payload.json').read_text(encoding='utf8'))['data'][1:]
   if len(source)!=len(rows):raise ValueError('Daily error identity count does not match')
   cache[rid]=list(zip(source,rows))
  for source,row in cache[rid]:
   if main.row_day(row)!=day:continue
   if source['values'][1]!=row[1]:raise ValueError('Daily error identity is attached to another order')
   if canonical(source['values'])[12][:10]!=day:raise ValueError('Daily error identity has a different Created Date')
   key=source_id(source)
   if key in seen:raise ValueError('Duplicate error ID in approved daily reports')
   seen.add(key);result.append((source,row))
 return result
def overlay(entries,current):
 rows=[];audit=[]
 for original,row in entries:
  key=source_id(original);latest=current.get(key)
  if latest is None:raise ValueError(f"{row[1]}: approved error {key} is missing from the month-to-date export. Previous workbook retained.")
  if order_key(original)!=order_key(latest):raise ValueError('A source error ID changed its order or Created Date; review required')
  values=latest['values'];updated=list(row)
  updated[0]=values[0];updated[13]=float(values[15])
  # Keep contributor choices/descriptions and refresh both source decisions/comments.
  updated[24:28]=status_fields(latest,required=True)
  modified=canonical(values)[16]
  updated[14]=(datetime.fromisoformat(modified)-datetime(1899,12,30)).total_seconds()/86400 if modified else None
  rows.append(updated);audit.append({'sourceId':key,'order':row[1],'oldStatus':row[0],'status':updated[0],'oldPoints':row[13],'points':updated[13],'oldDecisionFields':row[24:28],'decisionFields':updated[24:28],'commentHistory':latest.get('statusHistory')})
 return rows,audit
def prepare(root,data,run_process,month,days,rows,audit,through,checked,overrides=None):
 folder=data/'main'/month/uuid.uuid4().hex;folder.mkdir(parents=True)
 start,end=(days[0],days[-1]) if days else (month+'-01',month+'-01')
 points=sum(r[13] for r in rows)
 collection=dict(start=start,end=end,count=len(rows),points=points,mainMonth=month,syncThrough=through,syncedAt=checked)
 payload=main.make_payload(root,rows)
 payload.update(editIds=[a['sourceId'] for a in audit],editMonth=month,editRevision=folder.name,contributorOverrides=overrides or [None]*len(rows))
 (folder/'payload.json').write_text(json.dumps(payload),encoding='utf8')
 (folder/'collection.json').write_text(json.dumps(collection),encoding='utf8')
 (folder/'status-audit.json').write_text(json.dumps(audit),encoding='utf8')
 for script in ('build_portable.py','finish.py'):run_process([sys.executable,root/'report'/script,folder],folder)
 check=json.loads((folder/'validation.json').read_text(encoding='utf8'))
 if check.get('passed') is not True or check.get('count')!=len(rows) or check.get('points')!=points or check.get('pivots')!=4 or not (folder/'report.xlsx').is_file():
  raise ValueError('Monthly workbook validation failed. Previous workbook retained.')
 return (month,str(folder.relative_to(data)),start,end,len(rows),points,len(days),stamp())
def selected_days(db):
 with db() as c:return dict(c.execute('SELECT day,run_id FROM main_days').fetchall())
def refresh(root,data,db,run_process,fetch,month):
 first=guard(month);end=min(today()-timedelta(days=1),first.replace(day=calendar.monthrange(first.year,first.month)[1]))
 if end<first:raise ValueError('No completed day is available in this month yet.')
 state(db,month,'running','Checking month-to-date statuses and points before rebuilding PivotTables')
 folder=data/'month-snapshots'/month/uuid.uuid4().hex;folder.mkdir(parents=True)
 try:
  fetch(first.isoformat(),end.isoformat(),folder)
  current=read_snapshot(folder,first.isoformat(),end.isoformat());checked=stamp();selected=selected_days(db)
  with db() as c:exists=c.execute('SELECT 1 FROM main_books WHERE month=?',(month,)).fetchone()
  book=None
  if exists:
   days=sorted(d for d in selected if d.startswith(month+'-'))
   rows,audit=overlay(records(root,data,db,month,selected),current)
   rows,overrides=manual_edits.apply(rows,audit,manual_edits.load(db,month))
   book=prepare(root,data,run_process,month,days,rows,audit,end.isoformat(),checked,overrides)
  with db() as c:
   if book:c.execute('INSERT OR REPLACE INTO main_books VALUES (?,?,?,?,?,?,?,?)',book)
   c.execute('INSERT OR REPLACE INTO main_snapshots VALUES (?,?,?,?)',(month,str(folder.relative_to(data)),end.isoformat(),checked))
   c.execute('INSERT OR REPLACE INTO main_sync_state VALUES (?,?,?,?)',(month,'current','Latest status and points verified',checked))
  return {'month':month,'through':end.isoformat(),'checkedAt':checked,'current':current}
 except Exception as error:
  state(db,month,'failed',str(error)[:700]);raise
def create(root,data,db,run_process,month):
 guard(month)
 with db() as c:
  if c.execute('SELECT 1 FROM main_books WHERE month=?',(month,)).fetchone():raise ValueError('This monthly workbook already exists')
 book=prepare(root,data,run_process,month,[],[],[],None,None)
 with db() as c:
  c.execute('INSERT INTO main_books VALUES (?,?,?,?,?,?,?,?)',book)
  c.execute('DELETE FROM main_snapshots WHERE month=?',(month,))
  c.execute('INSERT OR REPLACE INTO main_sync_state VALUES (?,?,?,?)',(month,'empty','Empty workbook. Add a verified daily report to start.',stamp()))
  return {'books':main.books(c),'message':'Monthly workbook created. Add daily reports using Yes.'}
def delete(data,db,month):
 guard(month)
 with db() as c:
  if not c.execute('SELECT 1 FROM main_books WHERE month=?',(month,)).fetchone():raise ValueError('Monthly workbook not found')
  # Remove the published workbook and approval mapping, retaining daily sources
  # and immutable revisions for recovery. No user report files are deleted.
  ids=[r[0] for r in c.execute('SELECT DISTINCT run_id FROM main_days WHERE day LIKE ?',(month+'-%',))]
  c.execute('DELETE FROM main_books WHERE month=?',(month,));c.execute('DELETE FROM main_days WHERE day LIKE ?',(month+'-%',))
  c.executemany('DELETE FROM main_choices WHERE run_id=?',[(rid,) for rid in ids])
  c.execute('DELETE FROM main_snapshots WHERE month=?',(month,));c.execute('DELETE FROM main_sync_state WHERE month=?',(month,))
  return {'books':main.books(c),'message':'Monthly workbook removed. Daily reports remain available to rebuild it.'}
def add(root,data,db,run_process,fetch,rid):
 if not re.fullmatch(r'[0-9a-f]{32}',rid):raise ValueError('Invalid report')
 with db() as c:
  found=c.execute('SELECT * FROM runs WHERE id=?',(rid,)).fetchone()
  if not found:raise ValueError('Report not found')
  run=dict(found)
 days=main.days_between(run['start'],run['end']);months=sorted({d[:7] for d in days})
 if any(not eligible(m) for m in months):raise ValueError('For Phase 2, collect October onward separately from September reports.')
 for month in months:guard(month)
 main.load_report(root,data,run)
 selected=selected_days(db);selected.update({day:rid for day in days})
 # Validate identities before requesting any live exports.
 entries={m:records(root,data,db,m,selected) for m in months}
 prepared=[]
 for month in months:
  snapshot=refresh(root,data,db,run_process,fetch,month)
  try:
   rows,audit=overlay(entries[month],snapshot['current'])
   rows,overrides=manual_edits.apply(rows,audit,manual_edits.load(db,month))
   included=sorted(d for d in selected if d.startswith(month+'-'))
   prepared.append(prepare(root,data,run_process,month,included,rows,audit,snapshot['through'],snapshot['checkedAt'],overrides))
  except Exception as error:
   state(db,month,'failed',str(error)[:700]);raise
 # Approval and all new rows publish together, after every affected month passes.
 with db() as c:
  c.executemany('INSERT OR REPLACE INTO main_books VALUES (?,?,?,?,?,?,?,?)',prepared)
  c.executemany('INSERT OR REPLACE INTO main_days VALUES (?,?)',[(day,rid) for day in days])
  c.execute('INSERT OR REPLACE INTO main_choices VALUES (?,?)',(rid,'yes'))
  return {'choice':'yes','books':main.books(c),'message':'Approved dates added. Month-to-date statuses and points verified; PivotTables rebuilt.'}
