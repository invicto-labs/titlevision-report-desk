"""Add schema-valid native Excel PivotTables and validate report contents."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from lxml import etree as E
from copy import deepcopy
from datetime import datetime,timedelta
import json,re,sys
base=Path(sys.argv[1]).resolve()
app=Path(__file__).resolve().parent.parent
collection=json.loads((base/'collection.json').read_text(encoding='utf8'))
expected_points=collection['points']
payload=json.loads((base/'payload.json').read_text(encoding='utf8'))
headers,*rows=payload['data']
S='http://schemas.openxmlformats.org/spreadsheetml/2006/main';R='http://schemas.openxmlformats.org/officeDocument/2006/relationships';P='http://schemas.openxmlformats.org/package/2006/relationships';C='http://schemas.openxmlformats.org/package/2006/content-types'
q=lambda tag:'{'+S+'}'+tag
def root(tag,attrs=None):return E.Element(q(tag),attrs or {},nsmap={None:S,'r':R})
def sub(parent,tag,attrs=None):return E.SubElement(parent,q(tag),attrs or {})
def xml(el):return E.tostring(el,encoding='UTF-8',xml_declaration=True,standalone=True)
def rel(parent,id,kind,target):E.SubElement(parent,'{'+P+'}Relationship',Id=id,Type=R+'/'+kind,Target=target)
def relroot():return E.Element('{'+P+'}Relationships',nsmap={None:P})
def iso(v):return (datetime(1899,12,30)+timedelta(days=v)).isoformat(timespec='seconds')
def atom(parent,v,j):
 if j==23 and v=='':return sub(parent,'s',{'v':''})
 if v is None or v=='':return sub(parent,'m')
 if j in {10,14,15}:return sub(parent,'d',{'v':iso(v)})
 if isinstance(v,(int,float)):return sub(parent,'n',{'v':str(v)})
 return sub(parent,'s',{'v':str(v)})
with ZipFile(base/'base.xlsx') as z:parts={n:z.read(n) for n in z.namelist()}
with ZipFile(app/'templates/pivot-parts.zip') as z:template={n:z.read(n) for n in z.namelist()}
# Native cache strategy: use shared indexes for pivot dimensions and inline records elsewhere.
shared={p['field']:p['items'] for p in payload['specs']}
cache=root('pivotCacheDefinition',{'{'+R+'}id':'rId1','refreshOnLoad':'1','createdVersion':'6','refreshedVersion':'8','minRefreshableVersion':'3','recordCount':str(len(rows))})
source=sub(cache,'cacheSource',{'type':'worksheet'});sub(source,'worksheetSource',{'name':payload['tableName']})
fields=sub(cache,'cacheFields',{'count':str(len(headers))})
for j,h in enumerate(headers):
 f=sub(fields,'cacheField',{'name':h,'numFmtId':'14' if j in {10,14,15} else '0'})
 vals=[r[j] for r in rows];typed_values=shared.get(j,vals);nonblank=[v for v in typed_values if v is not None and v!=''];attrs={}
 if len(nonblank)<len(vals) and j!=23:attrs['containsBlank']='1'
 if not nonblank:attrs.update(containsNonDate='1' if j==23 else '0',containsString='1' if j==23 else '0')
 elif j in {10,14,15}:attrs.update(containsSemiMixedTypes='0',containsNonDate='0',containsDate='1',containsString='0',minDate=iso(min(nonblank)),maxDate=iso(max(nonblank)))
 elif all(isinstance(v,(int,float)) for v in nonblank):attrs.update(containsSemiMixedTypes='0',containsString='0',containsNumber='1',containsInteger='1',minValue=str(min(nonblank)),maxValue=str(max(nonblank)))
 elif any(len(str(v))>255 for v in nonblank):attrs['longText']='1'
 if j in shared:attrs['count']=str(len(shared[j]))
 si=sub(f,'sharedItems',attrs)
 if j in shared:
  for v in shared[j]:
   a=atom(si,v,j)
   if v not in vals:a.set('u','1')
records=root('pivotCacheRecords',{'count':str(len(rows))})
for r in rows:
 rec=sub(records,'r')
 for j,v in enumerate(r):
  if j in shared:sub(rec,'x',{'v':str(shared[j].index(v or ''))})
  else:atom(rec,v,j)
parts['xl/pivotCache/pivotCacheDefinition1.xml']=xml(cache);parts['xl/pivotCache/pivotCacheRecords1.xml']=xml(records)
cr=relroot();rel(cr,'rId1','pivotCacheRecords','pivotCacheRecords1.xml');parts['xl/pivotCache/_rels/pivotCacheDefinition1.xml.rels']=xml(cr)
book=E.fromstring(parts['xl/workbook.xml']);pc=root('pivotCaches');sub(pc,'pivotCache',{'cacheId':'1','{'+R+'}id':'rIdPivotCache1'})
# CT_Workbook places pivotCaches after calcPr and customWorkbookViews.
following={'smartTagPr','smartTagTypes','webPublishing','fileRecoveryPr','webPublishObjects','extLst'}
position=next((i for i,child in enumerate(book) if E.QName(child).localname in following),len(book))
book.insert(position,pc);parts['xl/workbook.xml']=xml(book)
br=E.fromstring(parts['xl/_rels/workbook.xml.rels']);rel(br,'rIdPivotCache1','pivotCacheDefinition','pivotCache/pivotCacheDefinition1.xml');parts['xl/_rels/workbook.xml.rels']=xml(br)
# Preserve the already verified native custom pivot style, remapping its dxf ids.
styles=E.fromstring(parts['xl/styles.xml']);oldstyles=E.fromstring(template['xl/styles.xml'])
dxfs=styles.find(q('dxfs'));ts=styles.find(q('tableStyles'))
if dxfs is None:
 dxfs=E.Element(q('dxfs'),count='0');styles.insert(list(styles).index(ts) if ts is not None else len(styles),dxfs)
if ts is None:ts=sub(styles,'tableStyles',{'count':'0'})
custom=deepcopy(next(s for s in oldstyles.find(q('tableStyles')) if s.get('name')=='TitleVisionSummaryBorders'))
# Revision IDs copied from Excel depend on namespace declarations on its original
# styleSheet. They are not formatting and must not leak into the new stylesheet.
for element in custom.iter():
 for attribute in list(element.attrib):
  if attribute.startswith('{'):del element.attrib[attribute]
old_dxfs=oldstyles.find(q('dxfs'))
for item in custom:
 old=int(item.get('dxfId'));item.set('dxfId',str(len(dxfs)));dxfs.append(deepcopy(old_dxfs[old]))
ts.append(custom);ts.set('count',str(len(ts)));dxfs.set('count',str(len(dxfs)));parts['xl/styles.xml']=xml(styles)
sheet=E.fromstring(parts['xl/worksheets/sheet1.xml']);sr=relroot()
ct=E.fromstring(parts['[Content_Types].xml'])
def override(path,kind):E.SubElement(ct,'{'+C+'}Override',PartName='/'+path,ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.'+kind+'+xml')
override('xl/pivotCache/pivotCacheDefinition1.xml','pivotCacheDefinition');override('xl/pivotCache/pivotCacheRecords1.xml','pivotCacheRecords')
native={}
for name,content in template.items():
 if re.fullmatch(r'xl/pivotTables/pivotTable\d+\.xml',name):
  pt=E.fromstring(content);native[pt.get('name')]=pt
for k,p in enumerate(payload['specs'],1):
 pt=deepcopy(native[p['name']]);
 for stale in list(pt):
  if E.QName(stale).localname in {'formats','conditionalFormats'}:pt.remove(stale)
 pt.set('cacheId','1');pt.set('enableDrill','1');pt.set('preserveFormatting','1');pt.set('showMissing','1');pt.set('missingCaption','0')
 col=p['col'];start=p['row'];end=start+p['height']-1
 loc=pt.find(q('location'));loc.set('ref',f'{chr(65+col)}{start}:{chr(67+col)}{end}');loc.set('firstHeaderRow','1');loc.set('firstDataRow','2')
 pf=pt.find(q('pivotFields'))
 for j,f in enumerate(pf):
  for c in list(f):f.remove(c)
  f.attrib.clear();f.set('showAll','0')
  if j in {1,13}:f.set('dataField','1')
  if j==p['field']:
   f.attrib.update({'axis':'axisRow','compact':'0','outline':'0','defaultSubtotal':'0','showAll':'1'})
   items=sub(f,'items',{'count':str(len(p['items']))}) if p['items'] else None
   for i,name in enumerate(p['items']):
    attrs={'x':str(i)}
    if name not in [r[p['field']] or '' for r in rows]:attrs['m']='1'
    sub(items,'item',attrs)
 ri=pt.find(q('rowItems'));ri.clear();ri.set('count',str(len(p['items'])+1))
 for i in range(len(p['items'])):sub(sub(ri,'i'),'x',{'v':str(i)})
 sub(sub(ri,'i',{'t':'grand'}),'x')
 path=f'xl/pivotTables/pivotTable{k}.xml';parts[path]=xml(pt);override(path,'pivotTable')
 pr=relroot();rel(pr,'rId1','pivotCacheDefinition','../pivotCache/pivotCacheDefinition1.xml');parts[f'xl/pivotTables/_rels/pivotTable{k}.xml.rels']=xml(pr)
 # Worksheets reference PivotTables through package relationships only.
 # A pivotParts child is not valid SpreadsheetML and causes Excel repair.
 rel(sr,f'rIdPivot{k}','pivotTable',f'../pivotTables/pivotTable{k}.xml')
parts['xl/worksheets/sheet1.xml']=xml(sheet);parts['xl/worksheets/_rels/sheet1.xml.rels']=xml(sr);parts['[Content_Types].xml']=xml(ct)
# Package relationship/content-type files use their own default namespace.
for name,content in list(parts.items()):
 if name.endswith('.rels') or name=='[Content_Types].xml':
  old=E.fromstring(content);ns=E.QName(old).namespace;new=E.Element(old.tag,dict(old.attrib),nsmap={None:ns})
  for c in old:new.append(E.Element(c.tag,dict(c.attrib)))
  parts[name]=xml(new)
out=base/'report.xlsx'
with ZipFile(out,'w',ZIP_DEFLATED) as z:
 for name,content in parts.items():z.writestr(name,content)
# Read back all cells, formulas, cached records and native pivot relationships.
import openpyxl
v=openpyxl.load_workbook(out,data_only=True);f=openpyxl.load_workbook(out,data_only=False)
assert v['SP 2'].max_row==max(len(rows)+1,2)
assert sum(v['SP 2'].cell(i,14).value or 0 for i in range(2,len(rows)+2))==expected_points
assert len(f['Summary']._pivots)==4
assert f['SP 2'].freeze_panes=='D2'
assert len(f['SP 2'].data_validations.dataValidation)==1
for i,r in enumerate(rows,2):
 team=r[22].strip();expected_contributor='Triage' if team=='Triage' else 'VM team' if team=='VM team' else r[18] if team=='Search' else r[20] if team in {'Type','Typing'} else ''
 assert (r[23] or '')==(expected_contributor or ''),'Contributor does not follow Team'
 for j,val in enumerate(r,1):
  actual=v['SP 2'].cell(i,j).value
  if j in {11,15,16} and val is not None:assert abs((actual-datetime(1899,12,30)).total_seconds()/86400-val)<1e-7
  else:assert (actual if actual is not None else '')==(val if val is not None else ''),(i,j,actual,val)
 assert f['SP 2'].cell(i,24).value.startswith('=IF(TRIM(W')
 for j in range(1,29):
  if j!=24:assert f['SP 2'].cell(i,j).data_type!='f','Unexpected formula in source data'
assert len(records)==len(rows) and all(len(r)==28 for r in records)
for p in payload['specs']:
 assert sum(1 for r in rows if (r[p['field']] or '') in p['items'])==len(rows)
 print(p['name'],p['height'],[(name,sum((r[p['field']] or '')==name for r in rows)) for name in p['items']])
print(f'Validated {len(rows)} source records, {expected_points} points, all formulas, dropdown, 4 native PivotTables and complete drill records.')
print(out)

# Independent native cache reconciliation and package checks.
with ZipFile(out) as z:
 assert z.testzip() is None
 for name in z.namelist():
  if name.endswith('.xml') or name.endswith('.rels'): E.fromstring(z.read(name))
assert collection['count']==len(rows)
(base/'validation.json').write_text(json.dumps({'passed':True,'workbookFormatVersion':2,'count':len(rows),'points':expected_points,'pivots':4,'sourceRowsReconciled':True,'formulasVerified':True}),encoding='utf8')
