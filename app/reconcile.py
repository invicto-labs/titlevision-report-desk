"""Compare downloaded export to browser grid as multisets, preserving duplicate errors."""
from collections import Counter,defaultdict,deque
from datetime import datetime,date
from pathlib import Path
import json,sys,openpyxl,re,hashlib
HEADERS=['Status','Order Number','Vendor','User','Team','Task','Error Category Type','Error Category Sub Type','Notes','Product','Reported By','Created By','Created Date','Region','State','Points','Last Updated Date','Error Committed Date','EPON','PriceType']
def norm(v):
 if v is None:return ''
 if isinstance(v,(datetime,date)):return v.strftime('%m/%d/%Y %I:%M:%S %p')
 return str(v).replace('\xa0',' ').strip()
def canonical(row):
 # Rendered HTML collapses whitespace; this is a display equivalence only.
 # Keep the original export text in the report after comparison passes.
 result=[re.sub(r'\s+',' ',norm(v)) for v in row]
 for i in [12,16,17]:
  if result[i]:
   for fmt in ['%m/%d/%Y %I:%M:%S %p','%m/%d/%Y','%Y-%m-%d %H:%M:%S']:
    try:result[i]=datetime.strptime(result[i],fmt).isoformat();break
    except ValueError:pass
   else:raise ValueError('Unrecognized export date')
 result[15]=str(float(result[15]))
 return tuple(result)
def reconcile(directory):
 root=Path(directory);source=json.loads((root/'source.json').read_text(encoding='utf8'))
 book=openpyxl.load_workbook(root/'source.xlsx',data_only=True);sheet=book.active
 allrows=list(sheet.values)
 # The on-screen heading is PriceType; the native Excel export uses Price Type.
 def headings(row):return ['PriceType' if norm(c)=='Price Type' else norm(c) for c in row][:20]
 header=next((i for i,r in enumerate(allrows) if headings(r)==HEADERS),None)
 if header is None:raise ValueError('Downloaded export headers do not match the required schema')
 exported=[r[:20] for r in allrows[header+1:] if any(v is not None for v in r)]
 if Counter(canonical(r) for r in exported)!=Counter(canonical(r['values']) for r in source):raise ValueError('The downloaded export and collected error rows differ. Report withheld.')
 pool=defaultdict(deque)
 for r in exported:pool[canonical(r)].append([norm(v) for v in r])
 original=root/'browser-source.json'
 if not original.exists():original.write_text(json.dumps(source,ensure_ascii=False,indent=2),encoding='utf8')
 for row in source:row['values']=pool[canonical(row['values'])].popleft()
 (root/'source.json').write_text(json.dumps(source,ensure_ascii=False,indent=2),encoding='utf8')
 (root/'reconciled.json').write_text(json.dumps({'count':len(source),'sourceSha256':hashlib.sha256((root/'source.json').read_bytes()).hexdigest(),'exportSha256':hashlib.sha256((root/'source.xlsx').read_bytes()).hexdigest()}),encoding='utf8')
 print(f'Reconciled all {len(exported)} exported error rows.')
if __name__=='__main__':reconcile(sys.argv[1])
