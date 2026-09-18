import crypto from 'node:crypto';
export const EXPORT_HEADERS=['Status','Order Number','Vendor','User','Team','Task','Error Category Type','Error Category Sub Type','Notes','Product','Reported By','Created By','Created Date','Region','State','Points','Last Updated Date','Error Committed Date','EPON','PriceType'];
export function isoDate(s){if(!/^\d{4}-\d{2}-\d{2}$/.test(s)||new Date(s+'T00:00:00Z').toISOString().slice(0,10)!==s)throw Error('Invalid date');return s;}
export function siteDate(s){const [y,m,d]=isoDate(s).split('-').map(Number);return `${m}/${d}/${y}`;}
export function plusDays(s,n){const d=new Date(isoDate(s)+'T00:00:00Z');d.setUTCDate(d.getUTCDate()+n);return d.toISOString().slice(0,10);}
export function serial(s){if(!s)return null;const m=String(s).trim().match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})(?: (\d{1,2}):(\d{2})(?::(\d{2}))? (AM|PM))?$/);if(!m)throw Error('Unrecognized TitleVision date: '+s);const [mo,da,y]=m.slice(1,4).map(Number);if(mo<1||mo>12||da<1||da>31|| (m[4]&&(+m[4]<1||+m[4]>12||+m[5]>59||+(m[6]||0)>59)))throw Error('Invalid TitleVision date');const t=Date.UTC(y,mo-1,da,m[4]?+m[4]%12+(m[7]==='PM'?12:0):0,+(m[5]||0),+(m[6]||0));const d=new Date(t);if(d.getUTCMonth()!==mo-1||d.getUTCDate()!==da)throw Error('Invalid calendar date');return t/86400000+25569;}
export function rowId(r,occurrence=0){return crypto.createHash('sha256').update(JSON.stringify([r,occurrence])).digest('hex').slice(0,24);}
export function teamFor(r){const category=r[6].trim(),sub=r[7].trim();if(/\btriage\b/i.test(sub)||/^triage$/i.test(category))return 'Triage';if(/^VM team$/i.test(category)||/^VM team$/i.test(sub))return 'VM team';return category==='Searching'?'Search':category==='Typing'?'Type':'';}
export function selectProduct(products,row){
 const matching=products.filter(p=>p.name.trim()===row[9].trim());
 const number=String(row[18]??'').trim();
 const epon=number?matching.filter(p=>p.external===number||p.originator===number):[];
 if(epon.length===1)return {product:epon[0],method:'Product name and product number'};
 const active=matching.filter(p=>!p.cancelled);
 if(active.length===1)return {product:active[0],method:'Only non-cancelled matching product'};
 throw Error(`Ambiguous product: ${matching.length} matching, ${active.length} non-cancelled. Review required.`);
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
