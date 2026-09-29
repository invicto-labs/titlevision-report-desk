import test from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import {pathToFileURL,fileURLToPath} from 'node:url';
import {readStatusHistory} from '../status_history.mjs';
const app=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const {chromium}=await import(pathToFileURL(path.join(process.env.TITLEVISION_NODE_MODULES||path.join(app,'node_modules'),'playwright/index.mjs')).href);
const base='_uec_cEditOrderErrorControl_';
const row={sourceId:'123',url:'https://tv.datatracetitle.com/OrderOverview.aspx?PublicOrderId=order-1',values:['Non-Chargeable','','ADS SP2']};
const editor=status=>`<div id="${base}dStatus">${status}</div><select id="${base}ddUserVendor1"><option value="u1">ADSSP2_PerformanceModuleManager</option><option value="v427" selected>ADS SP2</option></select><textarea id="${base}eTbNotex"></textarea><div id="${base}lCreatedBy">Created by: brucec</div>`;
const history='<h3>Comment History</h3><table class="orderErrorCommentsHistoryTable"><thead><tr><th>Date/Time</th><th>User</th><th>Comment</th></tr></thead><tbody><tr><td>8/5/2026 5:06:50 AM</td><td>brucec</td><td>Training, reason accepted<br>Second line</td></tr></tbody></table>';
test('status popup reader handles source replies, omitted empty controls and rejects schema/status/vendor drift',async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  const context=await browser.newContext();const page=await context.newPage();let html='';
  await context.route('https://tv.datatracetitle.com/**',route=>route.fulfill({contentType:'text/html',body:'<!doctype html><html><body>'+html+'</body></html>'}));
  html=editor('Non-Chargeable')+history;
  let result=await readStatusHistory(page,row,'ADSSP2_Performance');
  assert.equal(result.sourceId,'123');assert.equal(result.orderId,'order-1');assert.equal(result.comments[0][2],'Training, reason accepted\nSecond line');assert(result.vendorUsers.includes('ADSSP2_Performance'));
  for(const status of ['Accepted','Auto-Accepted','Non-Chargeable']){
   html=editor(status);result=await readStatusHistory(page,{...row,values:[status,'','ADS SP2']},'ADSSP2_Performance');assert.deepEqual(result.comments,[]);assert.equal(result.emptyHistory,true);
  }
  for(const changed of [editor('Chargeable')+history,editor('Non-Chargeable')+history.replace('<th>Comment</th>','<th>New Comment</th>'),editor('Non-Chargeable')+history.replace('orderErrorCommentsHistoryTable','renamedTable'),editor('Non-Chargeable').replace('ADS SP2','Other Vendor')+history,editor('Non-Chargeable')+history.replace('</tbody>','<tr><td colspan="3"><a href="javascript:Page$2">2</a></td></tr></tbody>')]){
   html=changed;await assert.rejects(readStatusHistory(page,row,'ADSSP2_Performance'));
  }
 }finally{await browser.close();}
});
