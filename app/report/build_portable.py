"""Redistributable workbook writer. Native pivots and independent validation follow in finish.py."""
from pathlib import Path
import json,sys,math
import xlsxwriter

def build(folder):
 folder=Path(folder)
 payload=json.loads((folder/'payload.json').read_text(encoding='utf8'))
 collection=json.loads((folder/'collection.json').read_text(encoding='utf8'))
 headers,*rows=payload['data'];widths=payload.get('widths') or json.loads((Path(__file__).resolve().parents[1]/'templates/layout.json').read_text(encoding='utf8'))['widths'];n=len(rows)
 title=collection['start'] if collection['start']==collection['end'] else collection['start']+' to '+collection['end']
 wb=xlsxwriter.Workbook(folder/'base.xlsx',{'strings_to_formulas':False,'strings_to_urls':False})
 summary=wb.add_worksheet('Summary');sheet=wb.add_worksheet('SP 2')
 navy='#17365D';formats={}
 def fmt(**kw):
  props={'font_name':'Arial','font_size':10,'font_color':'#1F2937','text_wrap':True,'valign':'vcenter',**kw}
  key=tuple(sorted(props.items()))
  if key not in formats:formats[key]=wb.add_format(props)
  return formats[key]
 border={'border':1,'border_color':'#404040'}
 header=fmt(**border,bg_color=navy,font_color='#FFFFFF',bold=True,align='center')
 for sh in (sheet,summary):sh.hide_gridlines(2);sh.set_tab_color(navy)
 for j,width in enumerate(widths):sheet.set_column(j,j,width)
 sheet.freeze_panes(1,3);sheet.set_row(0,44)
 # Add the table before writing cells so cached formula values are preserved.
 sheet.add_table(0,0,max(n,1),27,{'name':payload['tableName'],'style':None,'columns':[{'header':h,'header_format':header} for h in headers]})
 for i,row in enumerate(rows or [[None]*28],1):
  maxlines=1
  for j,value in enumerate(row):
   opts=dict(border)
   if i%2:opts['bg_color']='#EDF2F7'
   if j in (7,8,25,27):opts['valign']='top'
   if j in (10,14,15):opts['num_format']='m/d/yyyy h:mm:ss AM/PM' if j==10 else 'm/d/yyyy'
   if j==13:opts.update(num_format='0',align='right')
   if j==22:opts.update(bg_color='#FFF2CC',align='center')
   cellformat=fmt(**opts)
   if j==23:
    r=i+1
    formula=f'=IF(TRIM(W{r})="Triage","Triage",IF(TRIM(W{r})="VM team","VM team",IF(TRIM(W{r})="Search",IF(S{r}="","",S{r}),IF(OR(TRIM(W{r})="Type",TRIM(W{r})="Typing"),IF(U{r}="","",U{r}),""))))'
    code=sheet.write_formula(i,j,formula,cellformat,value or '')
   else:code=sheet.write(i,j,value,cellformat)
   if code:raise ValueError('Excel cell write failed; report withheld')
   maxlines=max(maxlines,sum(max(1,math.ceil(len(part)/max(1,widths[j]*0.85))) for part in str(value or '').split('\n')))
  sheet.set_row(i,min(409,max(52,maxlines*14+12)))
 sheet.data_validation(1,22,max(n,1),22,{'validate':'list','source':['Search','Type','Triage','VM team'],'error_type':'stop','error_title':'Choose a team','error_message':'Select Search, Type, Triage or VM team.'})
 summary.set_default_row(25)
 for j,width in enumerate([25,14,15,4,23,14,15,4,23,14,15]):summary.set_column(j,j,width)
 heading='TitleVision Error Report — '+title
 if collection.get('mainMonth'):
  from datetime import date
  heading=date.fromisoformat(collection['mainMonth']+'-01').strftime('%B %Y')+' Main Workbook'
 summary.merge_range('A2:K2',heading,fmt(bold=True,font_size=14,font_color=navy))
 summary.set_row(1,34)
 for p in payload['specs']:
  matrix=[['','Values',''],[p['title'],'Error Count','Error Points']]
  for item in p['items']:
   match=[r for r in rows if (r[p['field']] or '')==item]
   matrix.append([item or '(blank)',len(match),sum(r[13] for r in match)])
  matrix.append(['Grand Total',n,collection['points']])
  for i,row in enumerate(matrix):
   r=p['row']-1+i;summary.set_row(r,32 if i<2 else 28 if i==len(matrix)-1 else 25)
   for j,value in enumerate(row):
    props=dict(border)
    if i<2:props.update(bg_color=navy,font_color='#FFFFFF',bold=True,align='center')
    else:
     props['align']='right' if j else 'left'
     if i==len(matrix)-1:props.update(bg_color='#DCE6F1',bold=True)
    summary.write(r,p['col']+j,value,fmt(**props))
 notes=max(25,*(p['row']+p['height']+2 for p in payload['specs'] if p['col']>0))
 texts=[(0,'Double-click a PivotTable count or points total to open its full records.'),(2,'After changing Team, select Data → Refresh All to update the PivotTables.'),(4,'Team options: Search, Type, Triage, VM team.'),(6,'(blank) means no team or contributor is assigned. A blank Typer means no human typing task was recorded.'),(8,'Source: TitleVision All Errors, created '+title+'.')]
 if collection.get('mainMonth'):
  texts[-1]=(8,'Only approved daily reports are included. Status and points checked through '+collection['syncThrough']+'.' if collection.get('syncThrough') else 'Empty monthly workbook. Add a verified daily report to begin.')
 for offset,text in texts:
  r=notes+offset-1;summary.merge_range(r,4,r,10,text,fmt(**border));summary.set_row(r,42 if offset==6 else 34)
 wb.close()
 print(f'Built {n} rows using the portable workbook writer.')

if __name__=='__main__':build(sys.argv[1])
