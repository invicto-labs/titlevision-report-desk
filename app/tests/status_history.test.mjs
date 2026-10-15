import test from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import {pathToFileURL,fileURLToPath} from 'node:url';
import {readStatusHistory,planStatusHistory} from '../status_history.mjs';
const app=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
test('only changed or uncached tracked statuses require popup visits',()=>{
 const record=(id,status)=>({sourceId:id,url:'https://tv.datatracetitle.com/OrderOverview.aspx?PublicOrderId=one',values:[status,'SAME-ORDER','ADS SP2','','','','','','','Full Title','','','10/1/2026']});
 const previous={};
 for(const [id,status] of [['1','Disputed'],['2','Chargeable'],['3','Non-Chargeable'],['4','Accepted'],['5','Auto-Accepted']])previous[id]={...record(id,status),statusHistory:{status,comments:[['date','author','keep exact original text']]}};
 let rows=[record('1','Disputed'),record('2','Chargeable'),record('3','Non-Chargeable'),record('4','Accepted'),record('5','Auto-Accepted'),record('6','Accepted'),record('7','New')];
 let plan=planStatusHistory(rows,previous);
 assert.equal(plan.fetch.length,0);assert.equal(plan.reused,5);assert.equal(plan.skipped,2);
 assert.deepEqual(rows[0].statusHistory,previous['1'].statusHistory);
 let exported=structuredClone(previous);exported['1'].values[12]='10/01/2026 12:00:00 AM';
 assert.equal(planStatusHistory([record('1','Disputed')],exported).fetch.length,0);
 rows=[record('1','Chargeable'),record('2','Non-Chargeable'),record('3','Disputed'),record('4','Disputed'),record('8','Non-Chargeable')];
 assert.deepEqual(planStatusHistory(rows,previous).fetch.map(r=>r.sourceId),['1','2','3','4','8']);
 // The same order number never causes a different error to inherit comments.
 assert.equal(planStatusHistory([record('9','Disputed')],previous).fetch.length,1);
 let moved=record('1','Disputed');moved.url+='-different';assert.equal(planStatusHistory([moved],previous).fetch.length,1);
 let missing=structuredClone(previous);delete missing['1'].statusHistory;assert.equal(planStatusHistory([record('1','Disputed')],missing).fetch.length,1);
 let accepted=record('1','Accepted');accepted.statusHistory=previous['1'].statusHistory;planStatusHistory([accepted],previous);assert.equal(accepted.statusHistory,undefined);
 // A -> Accepted -> A must fetch again, not reuse a historical A observation.
 assert.equal(planStatusHistory([record('1','Disputed')],{'1':record('1','Accepted')}).fetch.length,1);
});
const {chromium}=await import(pathToFileURL(path.join(process.env.TITLEVISION_NODE_MODULES||path.join(app,'node_modules'),'playwright/index.mjs')).href);
const base='_uec_cEditOrderErrorControl_';
const row={sourceId:'123',url:'https://tv.datatracetitle.com/OrderOverview.aspx?PublicOrderId=order-1',values:['Non-Chargeable','','ADS SP2']};
const editor=(status,assigned='ADS SP2')=>`<div id="${base}dStatus">${status}</div><select id="${base}ddUserVendor1"><option value="u1">ADSSP2_PerformanceModuleManager</option><option value="u2">Mekala_FAI</option><option value="v427" selected>${assigned}</option></select><textarea id="${base}eTbNotex"></textarea><div id="${base}lCreatedBy">Created by: brucec</div>`;
const history='<h3>Comment History</h3><table class="orderErrorCommentsHistoryTable"><thead><tr><th>Date/Time</th><th>User</th><th>Comment</th></tr></thead><tbody><tr><td>8/5/2026 5:06:50 AM</td><td>brucec</td><td>Training, reason accepted<br>Second line</td></tr></tbody></table>';
test('status popup reader accepts assigned accounts and rejects schema or status drift',async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  const context=await browser.newContext();const page=await context.newPage();let html='';
  // Match TitleVision's nested error-editor tables. An unscoped tbody selector
  // also matches the comment heading via the outer table's tbody.
  await context.route('https://tv.datatracetitle.com/**',route=>route.fulfill({contentType:'text/html',body:'<!doctype html><html><body><table><tbody><tr><td>'+html+'</td></tr></tbody></table></body></html>'}));
  html=editor('Non-Chargeable')+history;
  let result=await readStatusHistory(page,row,'ADSSP2_Performance');
  assert.equal(result.schema,2);assert.equal(result.sourceId,'123');assert.equal(result.orderId,'order-1');assert.equal(result.comments.length,1);assert.equal(result.comments[0][2],'Training, reason accepted\nSecond line');assert(result.vendorUsers.includes('ADSSP2_Performance'));assert(!result.internalUsers.includes('Mekala_FAI'));
  html=editor('Accepted','Mekala_FAI');result=await readStatusHistory(page,{...row,values:['Accepted','','ADS SP2']},'ADSSP2_Performance');assert.equal(result.assignedUser,'Mekala_FAI');assert(!result.internalUsers.includes('Mekala_FAI'));
  for(const status of ['Accepted','Auto-Accepted','Non-Chargeable']){
   html=editor(status);result=await readStatusHistory(page,{...row,values:[status,'','ADS SP2']},'ADSSP2_Performance');assert.deepEqual(result.comments,[]);assert.equal(result.emptyHistory,true);
  }
  for(const changed of [editor('Chargeable')+history,editor('Non-Chargeable')+history.replace('<th>Comment</th>','<th>New Comment</th>'),editor('Non-Chargeable')+history.replace('orderErrorCommentsHistoryTable','renamedTable'),editor('Non-Chargeable','')+history,editor('Non-Chargeable')+history.replace('</tbody>','<tr><td colspan="3"><a href="javascript:Page$2">2</a></td></tr></tbody>')]){
   html=changed;await assert.rejects(readStatusHistory(page,row,'ADSSP2_Performance'));
  }
 }finally{await browser.close();}
});
