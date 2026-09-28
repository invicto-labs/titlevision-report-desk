import {chromium} from 'playwright';
import fs from 'node:fs/promises';
import path from 'node:path';
import {siteDate,plusDays,rowId,selectProduct,taskNames,validateRows,sourceErrorId,validateErrorGrid} from './rules.mjs';
let input='';for await(const c of process.stdin)input+=c;const job=JSON.parse(input);input='';
const dir=path.resolve(job.directory);const emit=(phase,message,extra={})=>console.log(JSON.stringify({phase,message,...extra}));
const BASE='https://tv.datatracetitle.com';let browser,activePage;const network=[];
const normalize=s=>String(s??'').replace(/\u00a0/g,' ').trim();
async function postback(page,locator){const response=page.waitForResponse(r=>r.request().method()==='POST'&&r.url().includes('UserErrors.aspx'),{timeout:60000});await locator.click();await(await response).finished();await page.waitForLoadState('networkidle');}
async function grid(page){const result=await page.locator('#_uec__gvUserErrors').evaluate(t=>({headers:[...t.querySelectorAll('th')].map(e=>e.innerText.trim()),empty:[...t.querySelectorAll('tr')].some(r=>r.cells.length===1&&/^No errors found[.!]?$/i.test(r.innerText.trim())),rows:[...t.querySelectorAll('tr')].filter(r=>r.querySelector('a[href*="OrderOverview.aspx"]')).map(r=>({values:[...r.cells].slice(1).map(c=>(c.innerText||'').replace(/\u00a0/g,' ').trim()),url:new URL(r.querySelector('a[href*="OrderOverview.aspx"]').getAttribute('href'),location.href).href,errorLinks:[...r.querySelectorAll('a')].map(a=>a.getAttribute('onclick')||a.getAttribute('href'))})),pages:[...t.querySelectorAll('a[href*="Page$"]')].map(a=>({text:a.innerText,href:a.getAttribute('href')}))}));for(const row of result.rows){row.sourceId=sourceErrorId(row.errorLinks,row.url);delete row.errorLinks;}return result;}
try{
 emit('login','Signing in to TitleVision');
 browser=await chromium.launch({channel:'msedge',headless:!job.headed,...(job.headed?{args:['--start-minimized']}:{})});const context=await browser.newContext({acceptDownloads:true});const page=await context.newPage();activePage=page;page.setDefaultTimeout(30000);page.setDefaultNavigationTimeout(60000);
 context.on('response',r=>{const u=new URL(r.url());if(u.hostname==='tv.datatracetitle.com')network.push({path:u.pathname,status:r.status(),type:r.headers()['content-type'],disposition:r.headers()['content-disposition']});});
 await page.goto(BASE+'/UserErrors.aspx?ViewMode=full');
 if(new URL(page.url()).hostname==='login.datatracetitle.com'){
  await page.getByRole('textbox',{name:'Username',exact:true}).fill(job.username);
  await page.getByRole('textbox',{name:'Password',exact:true}).fill(job.password);
  await page.getByRole('button',{name:'Sign in',exact:true}).click();
  await page.waitForURL(u=>u.hostname==='tv.datatracetitle.com',{timeout:60000});
 }
 job.password='';emit('filters','Setting Created Date filters');await page.goto(BASE+'/UserErrors.aspx?ViewMode=full');
 await page.locator('#_uec__btnResetFilters').waitFor({state:'visible'});
 await page.locator('#_uec__btnResetFilters').click();await page.waitForLoadState('networkidle');
 await page.locator('#_uec__txtFilterErrorStartDate').fill(siteDate(job.start));
 await page.locator('#_uec__txtFilterErrorEndDate').fill(siteDate(plusDays(job.end,1)));
 // Read every status from the live site, including Accepted/Auto-Accepted and future additions.
 const allStatuses=await page.locator('#_uec_lstStatuses option').evaluateAll(es=>es.map(e=>({value:e.value,label:e.text})));
 if(!allStatuses.length)throw Error('Status options are missing');
 await page.locator('#_uec_lstStatuses').selectOption(allStatuses.map(s=>s.value));
 await postback(page,page.locator('#_uec__btnSearch'));
 const filters=await page.locator('input[type=text],select').evaluateAll(es=>es.map(e=>({id:e.id,value:e.tagName==='SELECT'?[...e.selectedOptions].map(o=>o.text):e.value})));
 await fs.writeFile(path.join(dir,'filters.json'),JSON.stringify(filters,null,2));
 const filterMap=Object.fromEntries(filters.map(f=>[f.id,f.value]));
 for(const suffix of ['Originators','Users','Teams','Tasks','Codes'])if(JSON.stringify(filterMap['_uec__ddlFilter'+suffix])!==JSON.stringify(['<Select>']))throw Error('An unexpected '+suffix+' filter is active');
 for(const suffix of ['MinPoints','MaxPoints','ErrorCommittedDateStart','ErrorCommittedDateEnd'])if(filterMap['_uec__txtFilter'+suffix]!=='')throw Error('An unexpected '+suffix+' filter is active');
 const statuses=filterMap['_uec_lstStatuses'];
 if(JSON.stringify(statuses)!==JSON.stringify(allStatuses.map(s=>s.label))||JSON.stringify(filterMap['_uec__ddlFilterDeleted'])!==JSON.stringify(['<Any>']))throw Error('An unexpected Status or Deleted filter is active');
 if(filterMap['_uec__txtFilterErrorStartDate']!==siteDate(job.start)||filterMap['_uec__txtFilterErrorEndDate']!==siteDate(plusDays(job.end,1)))throw Error('Created Date filters were not applied');
 await fs.writeFile(path.join(dir,'filters.json'),JSON.stringify(filters,null,2));
 const rows=[];const seenPages=new Set();let pageNo=1;
 for(;;){
  if(await page.locator('#_uec__gvUserErrors').count()===0){const text=await page.locator('body').innerText();if(/no (records|errors|results|data).*found/i.test(text)){break;}throw Error('Error grid missing; cannot confirm an empty report');}
  const g=await grid(page);
  try{validateErrorGrid(g,pageNo);}catch(e){await fs.writeFile(path.join(dir,'error-grid-review.json'),JSON.stringify({pageNo,headers:g.headers,rowCount:g.rows.length,empty:g.empty,pages:g.pages},null,2));throw e;}
  const signature=JSON.stringify(g.rows);if(seenPages.has(signature))throw Error('Repeated result page');seenPages.add(signature);rows.push(...g.rows);
  const next=g.pages.find(p=>p.text.trim()===String(pageNo+1))||g.pages.find(p=>/Page\$Next/.test(p.href));if(!next){if(g.pages.some(p=>/Page\$(Last|\d+)/.test(p.href)&&Number(p.text)>pageNo))throw Error('Cannot verify all result pages');break;}
  if(++pageNo>1000)throw Error('Too many result pages');await postback(page,page.locator('#_uec__gvUserErrors a').filter({hasText:new RegExp('^'+next.text.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')+'$')}).first());
 }
 const totals=validateRows(rows,job.start,job.end);const counts=new Map();for(const r of rows){const s=JSON.stringify(r.values),n=counts.get(s)||0;counts.set(s,n+1);r.id=rowId(r.values,n);}
 await fs.writeFile(path.join(dir,'source.json'),JSON.stringify(rows,null,2));
 emit('export',`Exporting ${totals.count} errors`,totals);
 let exportFailure;
 try{
 let resolveDownload;const downloadReady=new Promise(resolve=>{resolveDownload=resolve});
 const onDownload=d=>resolveDownload(d);let exportPage;
 const onPage=p=>{exportPage=p;activePage=p;p.on('download',onDownload)};
 let exportRequested=false;const onRequest=r=>{const u=new URL(r.url());if(u.origin===BASE&&u.pathname.toLowerCase()==='/export.aspx')exportRequested=true;};
 context.on('page',onPage);page.on('download',onDownload);context.on('request',onRequest);
 let timer;
 try{
  const exportResponse=page.waitForResponse(r=>r.request().method()==='POST'&&r.url().includes('UserErrors.aspx'));
  await page.locator('#_uec_btnExport').click();const response=await exportResponse;const exportText=await response.text();
  const exportMatch=exportText.match(/doExport\('([^']+)'\)/);if(!exportMatch)throw Error('TitleVision did not return its export link');
  const exportUrl=new URL(exportMatch[1].replace(/&amp;/g,'&'),BASE);if(exportUrl.origin!==BASE||exportUrl.pathname.toLowerCase()!=='/export.aspx')throw Error('Unexpected export destination');
  await page.waitForLoadState('networkidle');
  if(!exportRequested)await page.evaluate(url=>window.open(url),exportUrl.href);
  const downloaded=await Promise.race([downloadReady,new Promise(resolve=>{timer=setTimeout(()=>resolve(null),45000)})]);
  if(!downloaded){const body=await exportPage?.locator('body').innerText().catch(()=>'');if(/Application Error/.test(body||''))throw Error('TitleVision export returned an Application Error. '+(body.match(/Error Id:\s*([a-f0-9-]+)/i)?.[0]||''));throw Error('TitleVision export download did not finish');}
  await downloaded.saveAs(path.join(dir,'source.xlsx'));
  emit('exported','Native Excel export downloaded');
 }finally{clearTimeout(timer);context.off('page',onPage);context.off('request',onRequest);page.off('download',onDownload);activePage=page;}
 }catch(e){
  exportFailure=String(e.message).split('\n')[0];
  await fs.writeFile(path.join(dir,'export-failure.json'),JSON.stringify({message:exportFailure,text:await activePage.locator('body').innerText().catch(()=>'' )},null,2));
  emit('history','Export unavailable; checking histories for diagnostics. Report will be withheld.');
 }
 if(!job.exportOnly){
 const detail=await context.newPage();detail.setDefaultTimeout(30000);detail.setDefaultNavigationTimeout(60000);const staff={};const cache=new Map();
 await fs.writeFile(path.join(dir,'staff.json'),JSON.stringify(staff,null,2));
 for(let i=0;i<rows.length;i++){
  const row=rows[i],v=row.values;emit('history',`Checking ${i+1} of ${rows.length}: ${v[1]}`,{done:i,total:rows.length});
  if(new URL(row.url).origin!==BASE)throw Error('Unexpected order destination');
  let verified;let lastError;
  for(let attempt=0;attempt<2;attempt++)try{
   activePage=detail;await detail.goto(row.url);await detail.locator('#ctl00_ContentPlaceHolder1_grdWorkflowInstances_ctl00').waitFor();
   const productHeaders=await detail.locator('#ctl00_ContentPlaceHolder1_grdWorkflowInstances_ctl00 th').allTextContents();
   const expectedProductHeaders=['Product','External Product Number','Originator Product Number','Arrival Time','Completed Time','Cancelled Time'];
   const normalizedHeaders=productHeaders.map(normalize);
   if(expectedProductHeaders.some(label=>normalizedHeaders.filter(h=>h===label).length!==1)){
    await fs.writeFile(path.join(dir,'product-headers.json'),JSON.stringify(productHeaders,null,2));throw Error('TitleVision product columns changed');
   }
   const tv=normalize(await detail.locator('#ctl00_ContentPlaceHolder1_OrderWorkflowDetails1_lblServiceProviderOrderNumber').innerText());const client=normalize(await detail.locator('#ctl00_ContentPlaceHolder1_OrderWorkflowDetails1_lblOriginatorClient').innerText());
   const indexes=Object.fromEntries(expectedProductHeaders.map(label=>[label,normalizedHeaders.indexOf(label)]));
   const products=await detail.locator('#ctl00_ContentPlaceHolder1_grdWorkflowInstances_ctl00').evaluate((t,ix)=>[...t.querySelectorAll('tr')].filter(r=>r.querySelector('a[href*="showUtilityControlsWFI"]')).map(r=>{const c=[...r.cells].map(c=>c.innerText.trim());const a=r.querySelector('a[href*="showUtilityControlsWFI"]');return {name:a.innerText.trim(),href:a.getAttribute('href'),external:c[ix['External Product Number']],originator:c[ix['Originator Product Number']],arrival:c[ix['Arrival Time']],completed:c[ix['Completed Time']],cancelled:c[ix['Cancelled Time']]};}),indexes);
   let selected;
   try{selected=selectProduct(products,v);}catch(e){
    if(e.code==='AMBIGUOUS_PRODUCT')await fs.writeFile(path.join(dir,'product-review.json'),JSON.stringify({rowId:row.id,order:v[1],orderUrl:row.url,product:v[9],epon:v[18],errorCommittedDate:v[17],products,message:e.message},null,2));
    throw e;
   }
   const key=row.url+'|'+selected.product.href;
   if(cache.has(key))verified={...cache.get(key),selection:selected.method};else{
    const match=selected.product.href.match(/^javascript:showUtilityControlsWFI\('([a-f0-9-]{36})'\);\s*$/i);if(!match)throw Error('Unrecognized product task link');
    const tasks=new URL('/Tasks.aspx',BASE);tasks.searchParams.set('PublicOrderId',new URL(row.url).searchParams.get('PublicOrderId'));tasks.searchParams.set('wfiid',match[1]);await detail.goto(tasks.href,{referer:row.url});
    await detail.locator('#OrderWorkflowTasks1_RadGrid1_ctl00').waitFor();
    const history=await detail.locator('#OrderWorkflowTasks1_RadGrid1_ctl00').evaluate(t=>{
     const headers=[...t.querySelectorAll('th')].map(c=>c.innerText.trim());const labels=['Task','Avail','User','Start','End'];
     if(labels.some(label=>headers.filter(h=>h===label).length!==1))return {headers,rows:[]};
     const ix=labels.map(label=>headers.indexOf(label));
     const rows=[...t.querySelectorAll('tr')].filter(r=>!r.querySelector('th')&&r.cells.length>Math.max(...ix)).map(r=>['',...ix.map(i=>r.cells[i].innerText.replace(/\u00a0/g,' ').trim())]);
     return {headers,rows};
    });
    if(!history.rows.length)throw Error('Task history missing or changed');
    verified={tv,client,names:taskNames(history.rows),history:history.rows,product:selected.product,selection:selected.method,orderUrl:row.url};cache.set(key,verified);
   }
   break;
  }catch(e){lastError=e;if(/Ambiguous product|Conflicting latest/.test(e.message))break;}
  if(!verified)throw Error(`${v[1]}: ${lastError?.message||'History unavailable'}`);staff[row.id]=verified;
  await fs.writeFile(path.join(dir,'staff.json'),JSON.stringify(staff,null,2));
 }
 }
 if(exportFailure)throw Error(exportFailure+' Report withheld until the source export can be verified.');
 await fs.writeFile(path.join(dir,'collection.json'),JSON.stringify({start:job.start,end:job.end,...totals,collectedAt:new Date().toISOString(),pages:pageNo},null,2));emit('collected','Collection complete',totals);
}catch(e){try{await fs.writeFile(path.join(dir,'diagnostic.json'),JSON.stringify({network,text:await activePage?.locator('body').innerText()},null,2));await activePage?.screenshot({path:path.join(dir,'failure.png'),fullPage:true});}catch{}emit('failed',String(e.message).split('\n')[0].replace(/https:\/\/login\.[^\s]+/g,'[login page]'));process.exitCode=1;}finally{await browser?.close();}
