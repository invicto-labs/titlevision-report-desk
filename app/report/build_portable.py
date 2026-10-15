"""Portable writer matching the approved SP 2 reference; finish.py adds native pivots."""
from pathlib import Path
import json, sys
import xlsxwriter
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import report_layout


def build(folder):
 folder=Path(folder)
 payload=json.loads((folder/'payload.json').read_text(encoding='utf8'))
 collection=json.loads((folder/'collection.json').read_text(encoding='utf8'))
 layout=json.loads((Path(__file__).resolve().parents[1]/'templates/layout.json').read_text(encoding='utf8'))
 rows=report_layout.current_rows(payload['data'][0],payload['data'][1:])
 for row in rows:
  if report_layout.non_chargeable(row):row[22]=report_layout.NON_CHARGEABLE
 if 'contributorOverrides' in payload:
  payload['contributorOverrides']=[report_layout.normalize_override(o) for o in payload['contributorOverrides']]
 payload.update(data=[report_layout.HEADERS,*rows],specs=report_layout.pivot_specs(rows),widths=layout['widths'])
 (folder/'payload.json').write_text(json.dumps(payload),encoding='utf8')
 headers=payload['data'][0];n=len(rows);editable='editIds' in payload
 if editable:assert len(payload['editIds'])==n and len(set(payload['editIds']))==n
 wb=xlsxwriter.Workbook(folder/'base.xlsx',{'strings_to_formulas':False,'strings_to_urls':False})
 summary=wb.add_worksheet('Sheet1');sheet=wb.add_worksheet('SP 2')
 if editable:
  meta=wb.add_worksheet('_ReportDesk');meta.write('A1','Month');meta.write('B1',payload['editMonth']);meta.write('A2','Revision');meta.write('B2',payload['editRevision']);meta.very_hidden()
 formats={}
 def fmt(**kw):
  props={'font_name':'Calibri','font_size':11,'font_color':'#000000','border':1,'border_color':'#000000',**kw}
  key=tuple(sorted(props.items()))
  if key not in formats:formats[key]=wb.add_format(props)
  return formats[key]
 header=fmt(font_size=14,bold=True,bg_color='#F4B084')
 # XlsxWriter adds 5/7 character padding; finish.py sets the precise reference widths.
 for j,width in enumerate(layout['widths']):sheet.set_column(j,j,width-5/7)
 sheet.freeze_panes(1,0);sheet.set_row(0,18.75)
 sheet.add_table(0,0,max(n,1),27 if editable else 26,{'name':payload['tableName'],'style':None,'banded_rows':False,'autofilter':False,'columns':[{'header':h,'header_format':header} for h in [*headers,*(['TitleVision Error ID'] if editable else [])]]})
 if editable:sheet.set_column(27,27,18,None,{'hidden':True})
 for i,row in enumerate(rows or [[None]*27],1):
  for j,value in enumerate(row):
   opts={}
   if j in (10,14,15):opts['num_format']='mm-dd-yy'
   if j>=24:opts.update(align='center',valign='vcenter')
   cellformat=fmt(**opts)
   if j==22:
    r=i+1
    formula=f'=IF(TRIM(D{r})="Triage","Triage",IF(TRIM(D{r})="Leadership","Leadership",IF(TRIM(D{r})="VM Team","VM Team",IF(TRIM(D{r})="Search",IF(S{r}="","",S{r}),IF(OR(TRIM(D{r})="Type",TRIM(D{r})="Typing"),IF(U{r}="","",U{r}),"")))))'
    override=(payload.get('contributorOverrides') or [None]*n)[i-1] if n else None
    if override:
     team=override['team'].replace('"','""');name=override['name'].replace('"','""')
     formula=f'=IF(TRIM(D{r})="{team}","{name}",{formula[1:]})'
    formula=f'=IF(TRIM(A{r})="Non-Chargeable","Non-Chargeable",{formula[1:]})'
    code=sheet.write_formula(i,j,formula,cellformat,value or '')
   else:code=sheet.write(i,j,value,cellformat)
   if code:raise ValueError('Excel cell write failed; report withheld')
  if editable and i<=n:sheet.write_string(i,27,payload['editIds'][i-1])
 sheet.data_validation(1,3,max(n,1),3,{'validate':'list','source':list(report_layout.TEAMS),'error_type':'stop','error_title':'Choose a team','error_message':'Select Search, Typing, Triage, VM Team or Leadership.'})
 for j,width in enumerate([19.7109375,11.85546875,13.28515625,8.43,15.5703125,11.85546875,13.28515625]):summary.set_column(j,j,width-5/7)
 for p in payload['specs']:
  matrix=[[p['title'],'Error Counts','Sum of Points']]
  for item in p['items']:
   match=[r for r in rows if (r[p['field']] if r[p['field']] is not None else '')==item]
   matrix.append([item if item!='' else '(blank)',sum(r[12] not in (None,'') for r in match),sum(r[13] for r in match)])
  matrix.append(['Grand Total',sum(r[12] not in (None,'') for r in rows),collection['points']])
  for i,row in enumerate(matrix):
   for j,value in enumerate(row):
    opts={'align':'center','valign':'vcenter'} if j else {'align':'left'}
    if i==0:opts.update(bold=True,bg_color='#D9E2F3')
    elif i==len(matrix)-1:opts['bg_color']='#D9D9D9'
    summary.write(p['row']-1+i,p['col']+j,value,fmt(**opts))
 wb.close()
 print(f'Built {n} rows using the approved reference layout.')

if __name__=='__main__':build(sys.argv[1])
