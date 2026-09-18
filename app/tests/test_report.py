"""Regressions for native PivotTable packaging and legacy report downloads."""
import json,sys,subprocess,uuid,unittest,zipfile
from pathlib import Path
from lxml import etree as E
app=Path(__file__).resolve().parents[1]
S='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
ns={'x':S}
class ReportTests(unittest.TestCase):
 def test_report_scenarios(self):
  layout=json.loads((app/'templates/layout.json').read_text(encoding='utf8'))
  for scenario,teams in [('empty',[]),('single',['Search']),('all-teams',['Search','Type','Triage','VM team',''])]:
   with self.subTest(scenario=scenario):
    folder=app/'tests/results'/('report-'+scenario+'-'+uuid.uuid4().hex);folder.mkdir(parents=True)
    rows=[]
    for i,team in enumerate(teams):
     r=['']*28;r[0]='New';r[1]='Test-'+str(i);r[6]='Test category';r[8]='=Literal source text';r[10]=r[14]=r[15]=46282;r[13]=i+1;r[18]='Example Searcher';r[20]='Example Typer';r[22]=team;r[23]=r[18] if team=='Search' else r[20] if team=='Type' else team;rows.append(r)
    specs=[]
    for name,field,title,col,row in [('ErrorsByContributor',23,'Final Error Contributor',0,5),('ErrorsByTeam',22,'Team',4,5),('ErrorsByCategory',6,'Error Category',8,5),('ErrorsByStatus',0,'Status',4,15)]:
     items=sorted({r[field] for r in rows}|({'VM team'} if field in (22,23) else set()))
     specs.append(dict(name=name,field=field,title=title,col=col,row=row,items=items,height=len(items)+3))
    # Deliberately omit widths to exercise rebuilding older saved payloads.
    (folder/'payload.json').write_text(json.dumps({'data':[layout['headers'],*rows],'specs':specs,'tableName':'TitleVisionErrors'}),encoding='utf8')
    (folder/'collection.json').write_text(json.dumps({'start':'2026-09-17','end':'2026-09-17','count':len(rows),'points':sum(r[13] for r in rows)}),encoding='utf8')
    for script in ('build_portable.py','finish.py'):
     result=subprocess.run([sys.executable,str(app/'report'/script),str(folder)],capture_output=True,text=True)
     self.assertEqual(result.returncode,0,result.stderr)
    with zipfile.ZipFile(folder/'report.xlsx') as z:
     sheet=E.fromstring(z.read('xl/worksheets/sheet1.xml'));self.assertIsNone(sheet.find('x:pivotParts',ns))
     rels=E.fromstring(z.read('xl/worksheets/_rels/sheet1.xml.rels'));self.assertEqual(sum(r.get('Type','').endswith('/pivotTable') for r in rels),4)
     styles=E.fromstring(z.read('xl/styles.xml'))
     for style in styles.findall('x:tableStyles/x:tableStyle',ns):self.assertFalse(any(k.startswith('{') for k in style.attrib))
     order=[E.QName(c).localname for c in E.fromstring(z.read('xl/workbook.xml'))];self.assertLess(order.index('calcPr'),order.index('pivotCaches'))
     cache=E.fromstring(z.read('xl/pivotCache/pivotCacheDefinition1.xml'))
     for shared in cache.findall('x:cacheFields/x:cacheField/x:sharedItems',ns):
      if shared.get('count') is not None:self.assertEqual(shared.get('containsBlank')=='1',shared.find('x:m',ns) is not None)
    self.assertEqual(json.loads((folder/'validation.json').read_text())['workbookFormatVersion'],3)
    print('REPORT_FIXTURE='+str(folder/'report.xlsx'))
if __name__=='__main__':unittest.main()
