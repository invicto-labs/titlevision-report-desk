import {serial} from './rules.mjs';
// Read the same page opened by an error's Status link. Never submit an edit.
export async function readStatusHistory(page,row,username){
 const order=new URL(row.url),url=new URL('/UserErrors.aspx',order.origin);
 if(order.origin!=='https://tv.datatracetitle.com'||!/^\d+$/.test(row.sourceId||''))throw Error('Status history has no verified error identity');
 url.searchParams.set('EditMode','Status');url.searchParams.set('UserErrorId',row.sourceId);url.searchParams.set('PublicOrderId',order.searchParams.get('PublicOrderId'));
 await page.goto(url.href);await page.waitForLoadState('networkidle');
 const actual=new URL(page.url());
 if(actual.origin!==url.origin||actual.pathname!==url.pathname||['EditMode','UserErrorId','PublicOrderId'].some(k=>actual.searchParams.get(k)!==url.searchParams.get(k)))throw Error('Status history opened another error or sign-in page');
 await page.locator('#_uec_cEditOrderErrorControl_ddUserVendor1').waitFor({state:'attached'});
 const result=await page.evaluate(()=>{
  const base='_uec_cEditOrderErrorControl_',vendor=document.getElementById(base+'ddUserVendor1');
  const current=document.getElementById(base+'dStatus');
  const statusSelect=document.getElementById(base+'ddStatus1');
  const status=current?.innerText.trim()||statusSelect?.selectedOptions[0]?.text.trim()||'';
  const tables=[...document.querySelectorAll('.orderErrorCommentsHistoryTable')];
  // TitleVision omits the entire comments control when its history is empty.
  // Confirm the known error editor before accepting that omission; a present
  // history heading with a missing/renamed table is a schema change, not zero rows.
  if(tables.length===0){
   if(!status||!document.getElementById(base+'eTbNotex')||!document.getElementById(base+'lCreatedBy')||/Comment History/i.test(document.body.innerText))throw Error('TitleVision comment history is missing or changed');
   return {status,comments:[],emptyHistory:true,assignedUser:vendor.selectedOptions[0]?.text.trim(),vendorUsers:[...vendor.options].filter(o=>/^u\d+$/.test(o.value)).map(o=>o.text.trim())};
  }
  if(tables.length!==1)throw Error('TitleVision comment history is missing or changed');
  const table=tables[0],headers=[...table.querySelectorAll('th')].map(e=>e.innerText.trim());
  if(JSON.stringify(headers)!==JSON.stringify(['Date/Time','User','Comment']))throw Error('TitleVision comment columns changed');
  if(table.querySelector('a[href*="Page$"]'))throw Error('Comment history pagination requires review');
  // The popup sits inside another table's tbody. Scope direct children so the
  // outer tbody cannot make this table's thead match the descendant selector.
  const comments=[...table.querySelectorAll(':scope > tbody > tr')].map(r=>[...r.cells].map(c=>c.innerText.replace(/\u00a0/g,' ').trim()));
  if(comments.some(r=>r.length!==3))throw Error('TitleVision comment rows changed');
  return {status,comments,assignedUser:vendor.selectedOptions[0]?.text.trim(),vendorUsers:[...vendor.options].filter(o=>/^u\d+$/.test(o.value)).map(o=>o.text.trim())};
 });
 if(result.status!==row.values[0])throw Error('Error status changed during collection. Run these dates again.');
 if(!result.assignedUser)throw Error('Status history has no selected User / Vendor account');
 // This selector holds an assigned user or vendor account, not the export's
 // Vendor field. Only verified ADS accounts may author our investigation reply.
 const internalUsers=[...new Set([...result.vendorUsers.filter(user=>/^ADSSP2_|_ADS(?:SearchType|SP2|P2)$/i.test(user)),username])];
 return {schema:2,sourceId:row.sourceId,orderId:order.searchParams.get('PublicOrderId'),url:url.href,readAt:new Date().toISOString(),...result,vendorUsers:[...new Set([...result.vendorUsers,username])],internalUsers};
}
// Compare native error IDs, not order numbers: one order can have several errors.
export function planStatusHistory(rows,previous={}){
 const fetch=[],counts={reused:0,skipped:0};
 for(const row of rows){
  const status=row.values[0],old=previous[row.sourceId];
  const normalized=value=>String(value??'').replace(/\s+/g,' ').trim();
  let same=false;
  try{same=old&&old.sourceId===row.sourceId&&old.url===row.url&&Array.isArray(old.values)&&[0,1,2,9].every(i=>normalized(old.values[i])===normalized(row.values[i]))&&serial(old.values[12])===serial(row.values[12]);}catch{/* Invalid cached identity must be collected again. */}
  delete row.statusHistory;delete row.statusFields;
  if(status==='New'){counts.skipped++;continue;}
  if(same&&old.statusHistory?.status===status){row.statusHistory=structuredClone(old.statusHistory);counts.reused++;continue;}
  if(['Accepted','Auto-Accepted'].includes(status)){counts.skipped++;continue;}
  if(!['Disputed','Chargeable','Non-Chargeable'].includes(status))throw Error(`Unrecognized error status: ${status}. Review required.`);
  fetch.push(row);
 }
 return {fetch,...counts};
}
