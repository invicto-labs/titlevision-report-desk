import test from 'node:test';import assert from 'node:assert/strict';
import {plusDays,serial,selectProduct,taskNames,teamFor,validateRows,rowId,sourceErrorId,validateErrorGrid,EXPORT_HEADERS} from '../rules.mjs';
test('TitleVision explicit empty table has no normal headers and is valid only on the first unpaged result',()=>{
 const grid={headers:[],rows:[],pages:[],empty:true};assert.doesNotThrow(()=>validateErrorGrid(grid,1));
 assert.throws(()=>validateErrorGrid(grid,2));assert.throws(()=>validateErrorGrid({...grid,pages:[{text:'2'}]},1));
 assert.throws(()=>validateErrorGrid({...grid,empty:false},1));
 assert.throws(()=>validateErrorGrid({...grid,headers:['',...EXPORT_HEADERS],empty:false},1));
});
test('normal grid schema remains enforced and cannot mix error records with an empty marker',()=>{
 const grid={headers:['',...EXPORT_HEADERS],rows:[{values:Array(20).fill('')}],pages:[],empty:false};
 assert.doesNotThrow(()=>validateErrorGrid(grid,1));assert.doesNotThrow(()=>validateErrorGrid(grid,2));
 assert.throws(()=>validateErrorGrid({...grid,headers:['',...EXPORT_HEADERS.slice(0,-1)]},1));
 assert.throws(()=>validateErrorGrid({...grid,empty:true},1));
});
test('calendar boundaries and midnight inclusion',()=>{assert.equal(plusDays('2026-01-01',-1),'2025-12-31');assert.equal(plusDays('2028-03-01',-1),'2028-02-29');assert.throws(()=>serial('2/30/2026'));const values=Array(20).fill('');Object.assign(values,{1:'Order',9:'Full Title',12:'9/16/2026 12:00:00 AM',15:'1'});assert.equal(validateRows([{values}],'2026-09-16','2026-09-16').count,1);values[12]='9/17/2026 12:00:00 AM';assert.throws(()=>validateRows([{values}],'2026-09-16','2026-09-16'));});
test('last completed human task includes blank task continuations',()=>{const r=(task,user,end)=>['',task,'9/15/2026 1:00:00 AM',user,'9/15/2026 1:00:00 AM',end];assert.deepEqual(taskNames([r('Search','First_ADSSearchType','9/15/2026 2:00:00 AM'),r('','Last_ADSSearchType','9/15/2026 3:00:00 AM'),r('','OWLServiceUser','9/15/2026 4:00:00 AM'),r('TypingModule','Typer_ADSSearchType','9/15/2026 5:00:00 AM'),r('','Unfinished_ADSSearchType','')]),['Last_ADSSearchType','Typer_ADSSearchType']);assert.deepEqual(taskNames([r('UpdateSearch','A_ADSSearchType','9/15/2026 2:00:00 AM')]),['A_ADSSearchType','']);});
test('conflicting last humans stop attribution',()=>{assert.throws(()=>taskNames([['','Search','','A','9/15/2026 1:00:00 AM','9/15/2026 2:00:00 AM'],['','','','B','9/15/2026 1:00:00 AM','9/15/2026 2:00:00 AM']]));});
test('product selection never guesses among two active products',()=>{const row=Array(20).fill('');row[9]='Full Title';row[18]='002';const products=[{name:'Full Title',external:'001',cancelled:'9/14/2026'},{name:'Full Title',external:'002',cancelled:''}];assert.equal(selectProduct(products,row).product.external,'002');row[18]='unmatched';assert.equal(selectProduct(products,row).product.external,'002');products[0].cancelled='';assert.throws(()=>selectProduct(products,row));row[9]='Two Owner';assert.throws(()=>selectProduct(products,row));});
test('team rules preserve unassigned categories and do not infer VM from notes',()=>{const r=Array(20).fill('');r[6]='Searching';assert.equal(teamFor(r),'Search');r[6]='Typing';assert.equal(teamFor(r),'Type');r[6]='Specs-Standards';assert.equal(teamFor(r),'');r[7]='15.08 - Triage Delay';assert.equal(teamFor(r),'Triage');r[7]='Other error';r[8]='sent to VM to review';assert.equal(teamFor(r),'');r[6]='VM team';assert.equal(teamFor(r),'VM team');});
test('identical source rows remain distinct occurrences',()=>{assert.notEqual(rowId(['same'],0),rowId(['same'],1));});
test('native error identity comes from the status link and must match its order',()=>{
 const order='https://tv.datatracetitle.com/OrderOverview.aspx?PublicOrderId=order-1';
 const link=id=>`showModalPopupPage('UserErrors.aspx?EditMode=Status&UserErrorId=${id}&PublicOrderId=order-1',400,930);`;
 assert.equal(sourceErrorId([link(123)],order),'123');assert.equal(sourceErrorId([],order),null);
 assert.throws(()=>sourceErrorId([link(123),link(456)],order));
 assert.throws(()=>sourceErrorId([link(123).replace('order-1','order-2')],order));
 assert.notEqual(sourceErrorId([link(123)],order),sourceErrorId([link(456)],order));
});
test('a missing product number cannot match an empty product field',()=>{const row=Array(20).fill('');row[9]='Full Title';assert.throws(()=>selectProduct([{name:'Full Title',external:'001',originator:'',cancelled:''},{name:'Full Title',external:'002',originator:'other',cancelled:''}],row));});

function repeatedUpdates(){
 const row=Array(20).fill('');Object.assign(row,{9:'Update Full Title',12:'9/18/2026 5:06:48 PM',17:'9/18/2026',18:'vendor-007'});
 const product=(external,arrival,completed)=>({name:row[9],external,originator:'',cancelled:'',arrival,completed});
 const products=[product('partner-002','2/1/2026 11:30:29 AM','2/2/2026 1:13:12 PM'),product('partner-003','3/18/2026 10:33:36 AM','3/19/2026 6:36:54 AM'),product('partner-004','9/17/2026 11:05:27 AM','9/18/2026 3:07:17 AM')];
 return {row,products};
}
test('repeated update regression: unique period on committed day resolves vendor EPON mismatch',()=>{
 const {row,products}=repeatedUpdates();const result=selectProduct(products,row);
 assert.equal(result.product.external,'partner-004');assert.match(result.method,/Error Committed Date/);
 assert.equal(selectProduct([...products].reverse(),row).product.external,'partner-004');
});
test('historical committed date wins over newest product and later reporting date',()=>{
 const {row,products}=repeatedUpdates();row[17]='2/2/2026';assert.equal(selectProduct(products,row).product.external,'partner-002');
 row[17]='3/19/2026';assert.equal(selectProduct(products,row).product.external,'partner-003');
});
test('exact normalized number remains authoritative even outside committed period',()=>{
 const {row,products}=repeatedUpdates();row[18]=' partner-002 ';products[0].external='\u00a0partner-002 ';assert.equal(selectProduct(products,row).product,products[0]);
 row[18]='origin-1';products[1].originator=' origin-1 ';assert.equal(selectProduct(products,row).product,products[1]);
});
test('overlapping or unreadable periods require review',()=>{
 for(const changed of [{arrival:'9/17/2026',completed:'9/19/2026'},{arrival:'',completed:'3/19/2026'},{arrival:'invalid',completed:'3/19/2026'},{arrival:'3/18/2026',completed:''},{arrival:'3/18/2026',completed:'invalid'},{arrival:'3/18/2026',completed:'3/17/2026'}]){
  const {row,products}=repeatedUpdates();Object.assign(products[1],changed);assert.throws(()=>selectProduct(products,row),{code:'AMBIGUOUS_PRODUCT'});
 }
});
test('missing, invalid or non-overlapping committed date cannot use created date',()=>{
 for(const committed of ['','9/31/2026','9/19/2026']){const {row,products}=repeatedUpdates();row[17]=committed;assert.throws(()=>selectProduct(products,row),{code:'AMBIGUOUS_PRODUCT'});}
});
test('date precision and day boundaries do not invent a timestamp',()=>{
 const {row,products}=repeatedUpdates();row[17]='9/18/2026 3:07:17 AM';assert.equal(selectProduct(products,row).product,products[2]);
 row[17]='9/18/2026 3:07:18 AM';assert.throws(()=>selectProduct(products,row));
 products[2].completed='9/18/2026';row[17]='9/18/2026 11:59:59 PM';assert.equal(selectProduct(products,row).product,products[2]);
 row[17]='9/19/2026';assert.throws(()=>selectProduct(products,row));
 products[2].arrival='9/19/2026 12:00:00 AM';products[2].completed='9/20/2026';row[17]='9/18/2026';assert.throws(()=>selectProduct(products,row));
});
test('duplicate exact EPON restricts date matching to those candidates',()=>{
 const {row,products}=repeatedUpdates();products[0].external=row[18];products[1].external=row[18];assert.throws(()=>selectProduct(products,row));
 row[17]='3/19/2026';assert.equal(selectProduct(products,row).product,products[1]);
 products[0].cancelled='2/3/2026';products[1].cancelled='3/20/2026';assert.equal(selectProduct(products,row).product,products[1]);
});

test('cancelled historical product regression retains earlier error with vendor EPON mismatch',()=>{
 const {row}=repeatedUpdates();row[9]='Full Title';row[17]='9/10/2026';row[12]='9/21/2026 11:10:27 AM';
 const product={name:'Full Title',external:'partner-001',arrival:'9/10/2026 2:58:09 PM',completed:'',cancelled:'09/21/2026 11:10 AM'};
 assert.equal(selectProduct([product],row).product,product);
 row[17]='9/21/2026 11:10:01 AM';assert.throws(()=>selectProduct([product],row),{code:'AMBIGUOUS_PRODUCT'});
 row[17]='9/9/2026';assert.throws(()=>selectProduct([product],row));
 row[17]='';assert.throws(()=>selectProduct([product],row));
});
test('cancelled periods must be valid and uniquely overlap the committed date',()=>{
 const {row,products}=repeatedUpdates();products.forEach(p=>p.cancelled='9/21/2026');
 assert.equal(selectProduct(products,row).product,products[2]);
 products[1].completed='';assert.throws(()=>selectProduct(products,row));
 products[1].completed='3/19/2026';products[1].cancelled='invalid';assert.throws(()=>selectProduct(products,row));
 products[1].cancelled='3/17/2026';assert.throws(()=>selectProduct(products,row));
});
test('cancelled product keeps completion and date-only cancellation boundaries',()=>{
 const {row,products}=repeatedUpdates();products.forEach(p=>p.cancelled='9/21/2026');
 row[17]='9/19/2026';assert.throws(()=>selectProduct(products,row));
 products[2].completed='';row[17]='9/21/2026 11:59:59 PM';assert.equal(selectProduct(products,row).product,products[2]);
 row[17]='9/22/2026';assert.throws(()=>selectProduct(products,row));
});
