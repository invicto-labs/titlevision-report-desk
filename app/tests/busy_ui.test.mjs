import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';

function harness(){
 const elements=new Map(),requests=[];
 function element(id){if(!elements.has(id))elements.set(id,{value:'',hidden:false,disabled:false,textContent:'',innerHTML:'',className:'',addEventListener(name,fn){this[name]=fn;},querySelectorAll(){return [];}});return elements.get(id);}
 const context=vm.createContext({document:{getElementById:element},window:{confirm:()=>true},location:{reload(){}},AbortController,setTimeout,clearTimeout,setInterval(){},fetch:(url,options)=>{requests.push({url,options});return new Promise(()=>{});}});
 vm.runInContext(readFileSync(new URL('../public/app.js',import.meta.url),'utf8'),context);
 vm.runInContext("state={activity:{busy:false,message:''},runs:[],mainBooks:[{month:'2026-10',count:2,days:1}],sharedFolder:'test-share',phase2:{enabled:true,currentMonth:'2026-10'},update:{}};",context);
 return {context,element,requests,run:code=>vm.runInContext(code,context)};
}
test('a refresh disables conflicting actions immediately and rejects a second click',async()=>{
 const h=harness();h.run("manageMain('refresh','2026-10')");
 assert.equal(h.element('run').disabled,true);
 assert.equal(h.element('shared-sync').disabled,true);
 assert.equal(h.element('overview-refresh-status').disabled,true);
 await h.run("manageMain('refresh','2026-10')");
 await h.element('run-form').submit({preventDefault(){}});
 await h.element('shared-sync').onclick();
 assert.equal(h.requests.filter(r=>r.options?.method==='POST').length,1);
});
test('a cross-tab conflict displays current progress without a red failure',async()=>{
 const h=harness();h.run("reportError(responseError({code:'worker_busy',error:'Checking 17 of 42',activity:{busy:true,message:'Checking 17 of 42'}}));overviewControls();");
 assert.equal(h.element('notice').className,'');
 assert.match(h.element('operation-state').textContent,/17 of 42/);
 assert.equal(h.element('overview-refresh-status').disabled,true);
 h.run("state.activity={busy:false,message:''};overviewControls();");
 assert.equal(h.element('overview-refresh-status').disabled,false);
 assert.match(h.element('notice').textContent,/finished/);
});
test('old running records cannot disable an idle worker; update stays available while busy',()=>{
 const h=harness();h.run("state.runs=[{status:'running'}];mainBooksDisplay();");
 assert.equal(h.element('run').disabled,false);
 h.run("state.activity={busy:true,message:'Checking histories'};mainBooksDisplay();updateDisplay();");
 assert.equal(h.element('run').disabled,true);
 assert.equal(h.element('get-update').disabled,false);
 assert.equal(h.element('overview-reload').disabled,false);
});
test('genuine failures still show an error',()=>{
 const h=harness();h.run("reportError(responseError({error:'Source verification failed'}));");
 assert.equal(h.element('notice').className,'error');
});
test('Stop targets the visible operation and cannot be double-clicked',async()=>{
 const h=harness();h.run("state.activity={busy:true,cancellable:true,operationId:'abc',message:'Checking histories'};overviewControls();");
 assert.equal(h.element('stop-process').hidden,false);
 h.element('stop-process').onclick();
 assert.equal(h.element('stop-process').disabled,true);
 assert.equal(h.element('stop-process').textContent,'Stopping…');
 await h.element('stop-process').onclick();
 const stops=h.requests.filter(r=>r.url==='/api/operation/stop');
 assert.equal(stops.length,1);assert.equal(JSON.parse(stops[0].options.body).operationId,'abc');
 h.run("stoppingProcess=false;state.activity={busy:false};overviewControls();");
 assert.equal(h.element('stop-process').hidden,true);
});
