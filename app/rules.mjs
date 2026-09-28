import crypto from 'node:crypto';
export const EXPORT_HEADERS=['Status','Order Number','Vendor','User','Team','Task','Error Category Type','Error Category Sub Type','Notes','Product','Reported By','Created By','Created Date','Region','State','Points','Last Updated Date','Error Committed Date','EPON','PriceType'];
export function validateErrorGrid(grid,pageNo){
 // ASP.NET replaces the entire grid with one "No errors found" cell, without
 // the normal headings. Only accept that explicit first-page empty state.
 if(grid.empty&&grid.rows.length===0&&grid.pages.length===0&&pageNo===1)return;
 if(JSON.stringify(grid.headers.slice(1))!==JSON.stringify(EXPORT_HEADERS))throw Error('TitleVision error columns changed');
 if(grid.empty)throw Error('Conflicting TitleVision empty-result marker');
 if(grid.rows.length===0)throw Error('Empty error grid without a confirmed no-errors result');
}
export function isoDate(s){if(!/^\d{4}-\d{2}-\d{2}$/.test(s)||new Date(s+'T00:00:00Z').toISOString().slice(0,10)!==s)throw Error('Invalid date');return s;}
export function siteDate(s){const [y,m,d]=isoDate(s).split('-').map(Number);return `${m}/${d}/${y}`;}
export function plusDays(s,n){const d=new Date(isoDate(s)+'T00:00:00Z');d.setUTCDate(d.getUTCDate()+n);return d.toISOString().slice(0,10);}
export function serial(s){if(!s)return null;const m=String(s).trim().match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})(?: (\d{1,2}):(\d{2})(?::(\d{2}))? (AM|PM))?$/);if(!m)throw Error('Unrecognized TitleVision date: '+s);const [mo,da,y]=m.slice(1,4).map(Number);if(mo<1||mo>12||da<1||da>31|| (m[4]&&(+m[4]<1||+m[4]>12||+m[5]>59||+(m[6]||0)>59)))throw Error('Invalid TitleVision date');const t=Date.UTC(y,mo-1,da,m[4]?+m[4]%12+(m[7]==='PM'?12:0):0,+(m[5]||0),+(m[6]||0));const d=new Date(t);if(d.getUTCMonth()!==mo-1||d.getUTCDate()!==da)throw Error('Invalid calendar date');return t/86400000+25569;}
export function rowId(r,occurrence=0){return crypto.createHash('sha256').update(JSON.stringify([r,occurrence])).digest('hex').slice(0,24);}
export function sourceErrorId(links,orderUrl){
 const ids=new Set();const order=new URL(orderUrl).searchParams.get('PublicOrderId');
 for(const link of links){
  const match=String(link??'').match(/UserErrors\.aspx\?[^'"\s)]+/i);if(!match)continue;
  const url=new URL(match[0].replace(/&amp;/g,'&'),'https://tv.datatracetitle.com');
  const id=url.searchParams.get('UserErrorId');if(!id)continue;
  if(!/^\d+$/.test(id)||url.searchParams.get('PublicOrderId')!==order)throw Error('Error identity does not match its order');
  ids.add(id);
 }
 if(ids.size>1)throw Error('Conflicting source error identities');
 return [...ids][0]||null;
}
export function teamFor(r){const category=r[6].trim(),sub=r[7].trim();if(/\btriage\b/i.test(sub)||/^triage$/i.test(category))return 'Triage';if(/^VM team$/i.test(category)||/^VM team$/i.test(sub))return 'VM team';return category==='Searching'?'Search':category==='Typing'?'Type':'';}
export function selectProduct(products,row){
 const clean=s=>String(s??'').replace(/\u00a0/g,' ').trim();
 const matching=products.filter(p=>clean(p.name)===clean(row[9]));
 const number=clean(row[18]);
 const epon=number?matching.filter(p=>clean(p.external)===number||clean(p.originator)===number):[];
 if(epon.length===1)return {product:epon[0],method:'Product name and product number'};
 // When the number matches, never fall back to a different product number.
 const numbered=epon.length?epon:matching;
 const active=numbered.filter(p=>!clean(p.cancelled));
 if(active.length===1)return {product:active[0],method:'Only non-cancelled matching product'};
 // Repeated updates can have the same name and a different vendor-side EPON.
 // Use the committed date, not the reporting date or simply the newest product.
 // A date without a time represents the whole day. Incomplete/unreadable dates
 // cannot eliminate a competing candidate, so they must prevent this fallback.
 const dateRange=value=>{const s=clean(value),start=serial(s);if(start===null)throw Error('Missing date');return [start,start+(/^\d{1,2}\/\d{1,2}\/\d{4}$/.test(s)?1:0)];};
 let dated=[];
 try{
  const [errorStart,errorEnd]=dateRange(row[17]);
  // A later cancellation does not erase earlier work. When every candidate is
  // cancelled, retain historical candidates but bound their period by cancellation.
  dated=(active.length?active:numbered).filter(p=>{
   const [arrival]=dateRange(p.arrival);
   const [completed,completedEnd]=clean(p.completed)?dateRange(p.completed):[Infinity,Infinity];
   const [cancelled,cancelledEnd]=clean(p.cancelled)?dateRange(p.cancelled):[Infinity,Infinity];
   if(completed<arrival||cancelled<arrival)throw Error('Product end precedes arrival');
   return (errorEnd===errorStart?arrival<=errorStart:arrival<errorEnd)&&
    (completedEnd===completed?completed>=errorStart:completedEnd>errorStart)&&
    (cancelledEnd===cancelled?cancelled>=errorStart:cancelledEnd>errorStart);
  });
 }catch{dated=[];}
 if(dated.length===1)return {product:dated[0],method:'Only matching product whose work period overlaps Error Committed Date'};
 const error=Error(`Ambiguous product: ${matching.length} matching, ${active.length} non-cancelled. Error Committed Date did not identify one product. Review required.`);
 error.code='AMBIGUOUS_PRODUCT';throw error;
}
export function taskNames(rows){let task='';const candidates=[[],[]];
 for(const r of rows){if(r.length!==6)continue;task=r[1].trim()||task;const user=r[3].trim();const kind=['Search','AESearch','UpdateSearch'].includes(task)?0:task==='TypingModule'?1:-1;
  if(kind<0||!user||/^(OWLServiceUser|AteUser|Auto[_ ]|\(Available\))/i.test(user))continue;
  if(!r[5].trim())continue; // Only completed human work, never an unstarted assignment.
  candidates[kind].push({user,end:serial(r[5]),start:serial(r[4]),task});
 }
 return candidates.map(list=>{list.sort((a,b)=>b.end-a.end||(b.start||0)-(a.start||0));if(list.length>1&&list[0].end===list[1].end&&list[0].start===list[1].start&&list[0].user!==list[1].user)throw Error('Conflicting latest task users');return list[0]?.user||'';});
}
export function validateRows(rows,start,end){isoDate(start);isoDate(end);if(start>end)throw Error('Start date is after end date');const lo=serial(siteDate(start)),hi=serial(siteDate(plusDays(end,1)));for(const {values:r} of rows){if(r.length!==20||!r[1]||!r[9])throw Error('Unexpected export columns or missing order/product');const d=serial(r[12]);if(d===null||d<lo||d>=hi)throw Error('Source contains an error outside the requested Created Date range');if(r[15]===''||!Number.isFinite(Number(r[15]))||Number(r[15])<0)throw Error('Invalid error points');}return {count:rows.length,points:rows.reduce((s,r)=>s+Number(r.values[15]),0)};}
