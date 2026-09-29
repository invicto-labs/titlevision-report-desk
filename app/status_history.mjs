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
   return {status,comments:[],emptyHistory:true,vendor:vendor.selectedOptions[0]?.text.trim(),vendorUsers:[...vendor.options].filter(o=>/^u\d+$/.test(o.value)).map(o=>o.text.trim())};
  }
  if(tables.length!==1)throw Error('TitleVision comment history is missing or changed');
  const table=tables[0],headers=[...table.querySelectorAll('th')].map(e=>e.innerText.trim());
  if(JSON.stringify(headers)!==JSON.stringify(['Date/Time','User','Comment']))throw Error('TitleVision comment columns changed');
  if(table.querySelector('a[href*="Page$"]'))throw Error('Comment history pagination requires review');
  const comments=[...table.querySelectorAll('tbody tr')].map(r=>[...r.cells].map(c=>c.innerText.replace(/\u00a0/g,' ').trim()));
  if(comments.some(r=>r.length!==3))throw Error('TitleVision comment rows changed');
  return {status,comments,vendor:vendor.selectedOptions[0]?.text.trim(),vendorUsers:[...vendor.options].filter(o=>/^u\d+$/.test(o.value)).map(o=>o.text.trim())};
 });
 if(result.status!==row.values[0])throw Error('Error status changed during collection. Run these dates again.');
 if(result.vendor!==row.values[2])throw Error('Status history belongs to a different vendor');
 return {schema:1,sourceId:row.sourceId,orderId:order.searchParams.get('PublicOrderId'),url:url.href,readAt:new Date().toISOString(),...result,vendorUsers:[...new Set([...result.vendorUsers,username])]};
}
