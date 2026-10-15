const $=id=>document.getElementById(id);let state=null,selected=null,pending=false,checkingUpdate=false,updateMessage='',loadedVersion=null,mainBusy=false;
const labels={cancelled:'Stopped',complete:'Complete',review:'Needs review',failed:'Failed',running:'Running',queued:'Queued'};
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let busyNotice=false,stoppingProcess=false,roleSelectionDirty=false,connectionUnavailable=false,connectionNotice='';
const READ_TIMEOUT_MS=30000;
function isViewer(){return state?.pcRole==='viewer';}
function notice(message,error=false){busyNotice=false;connectionNotice='';$('notice').textContent=message;$('notice').className=error?'error':'';$('notice').hidden=!message;}
function connectionRestored(){connectionUnavailable=false;if(connectionNotice&&$('notice').textContent===connectionNotice)notice('');connectionNotice='';}
function connectionFailed(error){
 connectionUnavailable=true;
 const message=['request_timeout','connection_lost','database_corrupt'].includes(error.code)?error.message:'Could not refresh Report Desk. '+error.message;
 if(isViewer())overviewEmpty('Shared dashboard unavailable. Checking again automatically.');
 if(state?.update?.phase!=='installing'){notice(message,error.code!=='request_timeout');connectionNotice=message;}
 if(state)mainBooksDisplay();
}
async function api(url,body){
 const controller=body===undefined?new AbortController():null;
 const timer=controller?setTimeout(()=>controller.abort(),READ_TIMEOUT_MS):null;timer?.unref?.();
 try{const r=await fetch(url,body===undefined?{signal:controller.signal}:{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':state.csrf},body:JSON.stringify(body)});const j=await r.json();if(!r.ok)throw responseError(j);return j;}
 catch(error){
  if(controller&&(controller.signal.aborted||error.name==='AbortError'))throw Object.assign(Error('Report Desk is taking longer than usual to respond. Retrying automatically. This timeout does not stop a running report.'),{code:'request_timeout'});
  if(controller&&error.name==='TypeError')throw Object.assign(Error('Report Desk is temporarily unavailable. Checking the connection again automatically.'),{code:'connection_lost'});
  throw error;
 }
 finally{if(timer)clearTimeout(timer);}
}
function responseError(result){
 const error=Error(result.error||'Request failed');error.code=result.code;
 if(result.code==='worker_busy'&&state){state.activity=result.activity;mainBooksDisplay();}
 return error;
}
function reportError(error){notice(error.message,error.code!=='worker_busy');busyNotice=error.code==='worker_busy';}
function workBlocked(){return !state||connectionUnavailable||pending||mainBusy||state.activity?.busy||['downloading','waiting','installing'].includes(state.update?.phase);}
function preventBusyAction(){
 if(!workBlocked())return false;
 notice(state?.activity?.busy?'Work is already in progress. '+state.activity.message:mainBusy||pending?'Your request is in progress. Follow the progress above.':'Please wait for the application to be ready.');
 busyNotice=Boolean(state?.activity?.busy);return true;
}
function workControls(){
 const blocked=workBlocked();$('run').disabled=blocked||isViewer();$('shared-sync').disabled=blocked||!state?.sharedFolder;
 for(const id of ['credentials','shared-form','name-map-form'])for(const button of $(id).querySelectorAll('button'))button.disabled=blocked||(isViewer()&&id!=='shared-form');
}
function period(r){return r.start===r.end?r.start:`${r.start} – ${r.end}`;}
async function detail(r){if(!r)return;selected=r.id;$('period').textContent=period(r);$('status').textContent=labels[r.status];$('status').className='badge '+r.status;$('progress').textContent=r.message;$('errors').textContent=r.count??'—';$('points').textContent=r.points??'—';$('review').textContent=r.issues??0;const ready=['complete','review'].includes(r.status);$('latest-download').hidden=!ready;$('latest-download').href=`/api/runs/${r.id}/download`;if(ready){const d=await api('/api/runs/'+r.id);$('issues-panel').hidden=!d.issues.length;$('issues').innerHTML=d.issues.map(i=>`<li><strong>${esc(i.order)}</strong> — ${esc(i.message)}</li>`).join('');}else $('issues-panel').hidden=true;}
async function refresh(){try{const initial=!state,previous=state;state=await api('/api/state');connectionRestored();const completed=state.runs.find(r=>['complete','review'].includes(r.status)&&previous?.runs.some(old=>old.id===r.id&&['queued','running'].includes(old.status)));if(completed)selected=completed.id;mainBooksDisplay();if(loadedVersion&&loadedVersion!==state.version){location.reload();return;}loadedVersion=state.version;if(initial){$('start').value=state.yesterday;$('end').value=state.yesterday;}$('start').max=state.yesterday;$('end').max=state.yesterday;$('schedule-label').textContent=state.schedule?'Enabled · Weekdays at 8:45 AM India time · Monday covers Friday–Sunday':'Paused · Turn on automatic weekday collection';$('schedule').textContent=state.schedule?'Pause schedule':'Enable schedule';$('credentials-state').textContent=state.credentialsSaved?'Sign-in saved and encrypted. Enter a password only to replace it.':'Save your sign-in before running a report.';$('run').disabled=workBlocked()||isViewer();$('history').innerHTML=state.runs.length?state.runs.map(r=>`<tr class="history-row" data-id="${r.id}" tabindex="0"><td><strong>${esc(period(r))}</strong></td><td>${esc(new Date(r.created).toLocaleString('en-IN',{timeZone:'Asia/Kolkata',dateStyle:'medium',timeStyle:'short'}))}</td><td><span class="badge ${r.status}">${labels[r.status]}</span></td><td>${r.count??'—'}</td><td>${r.points??'—'}</td><td>${['complete','review'].includes(r.status)?`<a href="/api/runs/${r.id}/download">Download Excel</a>`:'—'}</td></tr>`).join(''):'<tr><td colspan="6" class="empty">Your collected reports will appear here.</td></tr>';
sharedControls();$('main-edit-hint').textContent=state.sharedFolder?'Open the workbook in the shared folder. Edit Team, Searcher, Typer or Final Error Contributor, then save and close Excel. The next report or Sync now imports those corrections and updates the same shared file. Keep all source rows and columns.':'Download the latest Main workbook, edit Team in column D, or edit Searcher, Typer or Final Error Contributor in Excel and save it. Then click Save Excel edits and choose that file. Saved corrections stay with each error during future monthly updates. Statuses, points and client comments continue refreshing from TitleVision. Keep all original rows and columns.';
$('schedule').disabled=!state.schedule&&!state.verifiedLive;if(!state.schedule&&!state.verifiedLive)$('schedule-label').textContent='Paused · A complete live report must pass verification first';
const r=state.runs.find(r=>r.id===selected)||state.runs[0];await detail(r);if(initial&&!state.credentialsSaved&&!isViewer()){$('all-settings').open=true;$('settings').open=true;}return true;}catch(e){connectionFailed(e);return false;}}
$('run-form').addEventListener('submit',async e=>{e.preventDefault();if(isViewer()){notice('Run reports on the designated report PC.');return;}if(preventBusyAction())return;pending=true;mainBooksDisplay();try{const r=await api('/api/run',{start:$('start').value,end:$('end').value});selected=r.id;notice('Report started. You can leave this page open to follow its progress.');await refresh();}catch(e){reportError(e);}finally{pending=false;await refresh();}});
$('yesterday').onclick=()=>{$('start').value=state.yesterday;$('end').value=state.yesterday;};
$('credentials').onsubmit=async e=>{e.preventDefault();if(preventBusyAction())return;const button=e.target.querySelector('button');button.disabled=true;try{await api('/api/credentials',{username:$('username').value,password:$('password').value});$('password').value='';notice('Sign-in saved securely for this Windows account.');await refresh();}catch(e){reportError(e);}finally{workControls();}};
$('schedule').onclick=async()=>{$('schedule').disabled=true;try{await api('/api/schedule',{enabled:!state.schedule});notice('Daily schedule updated.');await refresh();}catch(e){reportError(e);}finally{$('schedule').disabled=false;}};
function sharedControls(){
 if(!roleSelectionDirty)$('shared-role').value=state.pcRole||'collector';
 const selectedViewer=$('shared-role').value==='viewer';
 $('shared-state').textContent=isViewer()?'Viewer PC':state.sharedFolder?'Report PC · Shared':'Report PC · Local only';
 $('shared-detail').textContent=state.sharedError||(state.sharedFolder?(isViewer()?'Reading shared Excel: ':'Publishing shared Excel: ')+state.sharedFolder+(isViewer()?' · Saved changes appear automatically, usually within 15 seconds.':' · One Excel editor at a time. Save and close Excel before syncing.'):'Enter the same network folder used by the report PC.');
 if(!roleSelectionDirty&&document.activeElement!==$('shared-path'))$('shared-path').value=state.sharedFolder||'';
 $('shared-path').readOnly=!selectedViewer&&!isViewer()&&Boolean(state.sharedFolder);
 $('shared-path').required=selectedViewer||!isViewer();
 $('shared-save').hidden=!selectedViewer&&!isViewer()&&Boolean(state.sharedFolder);
 $('shared-save').textContent=selectedViewer?'Connect viewer':isViewer()?'Use report PC mode':'Use shared folder';
 $('shared-sync').textContent=isViewer()?'Refresh dashboard':'Sync now';
 $('shared-sync').disabled=!state.sharedFolder||workBlocked();
 for(const id of ['collect-section','monthly-section','history-section','employee-names','settings'])$(id).hidden=isViewer();
 $('overview-refresh-status').hidden=isViewer();
 if(isViewer())$('issues-panel').hidden=true;
}
$('shared-role').onchange=()=>{roleSelectionDirty=true;sharedControls();};
$('shared-form').onsubmit=async e=>{
 e.preventDefault();if(preventBusyAction())return;mainBusy=true;mainBooksDisplay();
 try{
  const selectedViewer=$('shared-role').value==='viewer';
  const route=selectedViewer?'/api/shared/viewer':isViewer()?'/api/shared/collector':'/api/shared/configure';
  const result=await api(route,{path:$('shared-path').value.trim()});roleSelectionDirty=false;overviewLast=0;notice(result.message);
 }catch(error){reportError(error);}
 finally{mainBusy=false;await refreshWithVersion();}
};
$('shared-sync').onclick=async()=>{if(preventBusyAction())return;mainBusy=true;mainBooksDisplay();notice(isViewer()?'Reading the shared workbook…':'Importing saved edits and updating the shared workbooks…');try{const result=await api('/api/shared/sync',{});overviewLast=0;notice(result.message);}catch(error){reportError(error);}finally{mainBusy=false;await refreshWithVersion();}};
$('history').onclick=e=>{if(e.target.closest('a'))return;const row=e.target.closest('[data-id]');if(row)detail(state.runs.find(r=>r.id===row.dataset.id)).catch(e=>notice(e.message,true));};
$('history').onkeydown=e=>{if(e.key==='Enter'){const row=e.target.closest('[data-id]');if(row)detail(state.runs.find(r=>r.id===row.dataset.id)).catch(e=>notice(e.message,true));}};
function updateDisplay(){if(!state)return;$('app-version').textContent=state.version?'Running v'+state.version:'Version unavailable';const updating=['downloading','waiting','installing'].includes(state.update?.phase);$('get-update').disabled=checkingUpdate||updating;$('cancel-update').hidden=state.update?.phase!=='waiting';$('get-update').textContent=checkingUpdate?'Checking…':state.update?.phase==='waiting'?'Update queued':updating?'Updating…':'Get update';$('update-status').textContent=checkingUpdate?'Checking the latest published release…':updateMessage||state.update?.message||'Check for a published release.';$('github-state').textContent=state.githubAccessSaved?'GitHub update access is saved and encrypted.':'No token saved. An existing Git sign-in as invicto-labs will be used if available.';}
$('name-map-form').onsubmit=async e=>{
 e.preventDefault();if(preventBusyAction())return;const file=$('name-map-file').files[0];if(!file)return;
 if(file.size>128*1024){notice('Choose an employee mapping JSON file smaller than 128 KB.',true);return;}
 const button=e.target.querySelector('button');button.disabled=true;
 try{
  const response=await fetch('/api/names/import',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':state.csrf},body:file});
  const result=await response.json();if(!response.ok)throw responseError(result);
  $('name-map-file').value='';notice(result.message);await refreshWithVersion();
 }catch(error){reportError(error);}finally{workControls();}
};
$('get-update').onclick=async()=>{if(checkingUpdate)return;checkingUpdate=true;updateMessage='';updateDisplay();try{const result=await api('/api/update/install',{});await refresh();if(!result.available)updateMessage='You are running the latest version: v'+result.current+'.';}catch(e){updateMessage=e.message;}finally{checkingUpdate=false;updateDisplay();}};
$('github-access').onsubmit=async e=>{e.preventDefault();if(!$('github-token').value.trim())return;try{await api('/api/update/token',{token:$('github-token').value});$('github-token').value='';notice('GitHub update access saved.');updateMessage='';await refresh();}catch(e){reportError(e);}updateDisplay();};
$('clear-github-access').onclick=async()=>{try{await api('/api/update/token',{token:''});await refresh();updateDisplay();notice('Saved GitHub access removed.');}catch(e){reportError(e);}};

function mainBooksDisplay(){
 overviewControls();
 const books=state.mainBooks||[];
 const enabled=state.phase2?.enabled&&!isViewer(),blocked=workBlocked();
 $('phase2-note').textContent=enabled?'Verified runs add their dates to the Main workbook automatically. Existing statuses and comments are rechecked only when you click Check latest error status for that month. Download the latest workbook after each refresh.':'Monthly refresh begins with September 2026.';
 $('create-main-form').hidden=!enabled;$('create-main').disabled=blocked;
 if(!$('main-month').value)$('main-month').value=enabled?state.phase2.currentMonth:'2026-09';
 $('main-month').max=state.phase2?.currentMonth||'';
 $('main-books').innerHTML=books.length?books.map(b=>{
  const managed=enabled&&b.month>='2026-09';
  const name=new Date(b.month+'-01T12:00:00').toLocaleDateString('en-IN',{month:'long',year:'numeric'})+' workbook';
  const refresh=b.syncStatus==='cancelled'?'Stopped — last saved workbook retained':b.syncStatus==='running'?(state.activity?.busy?'Refreshing — last verified workbook shown':'Previous refresh interrupted — you can retry'):b.syncStatus==='failed'?'Refresh failed — previous workbook retained':b.syncStatus==='empty'?'Empty workbook':b.syncedAt?'Verified '+new Date(b.syncedAt).toLocaleString('en-IN',{timeZone:'Asia/Kolkata'}):'Verified daily snapshots';
  return `<tr><td><strong>${esc(name)}</strong></td><td>${b.days?esc(b.start)+' – '+esc(b.end):'No collected dates'}<br><small>${b.days} collected day(s)</small></td><td class="sync-cell">${esc(refresh)}${b.syncThrough?'<br><small>Checked through '+esc(b.syncThrough)+'</small>':''}${b.syncStatus==='failed'?'<br><small>'+esc(b.syncMessage)+'</small>':''}</td><td>${b.count}</td><td>${b.points}</td><td><a href="/api/main/${encodeURIComponent(b.month)}/download">Download main Excel</a>${managed?`<div class="book-actions"><button data-month="${esc(b.month)}" data-action="edits" ${blocked||!b.count?'disabled':''}>Save Excel edits</button><button data-month="${esc(b.month)}" data-action="refresh" ${blocked?'disabled':''}>Check latest error status</button>${state.sharedFolder?'':`<button data-month="${esc(b.month)}" data-action="delete" ${blocked?'disabled':''}>Delete workbook</button>`}</div>`:''}</td></tr>`;
 }).join(''):'<tr><td colspan="6" class="empty">No main workbook yet. Complete a verified report to create one automatically.</td></tr>';
}
async function manageMain(action,month){
 if(isViewer()){notice('Use the designated report PC to change reports.');return;}
 if(preventBusyAction())return;
 if(action==='edits'){chooseEditedWorkbook(month);return;}
 if(action==='delete'&&!window.confirm(`Delete the ${month} main workbook and remove its included dates? Daily reports are kept so you can rebuild it.`))return;
 mainBusy=true;mainBooksDisplay();updateDisplay();notice(action==='refresh'?'Checking month-to-date data and rebuilding the workbook…':action==='create'?'Creating monthly workbook…':'Removing monthly workbook…');
 try{const result=await api('/api/main/'+action,{month,...(action==='delete'?{confirm:true}:{})});notice(result.message);}
 catch(e){reportError(e);}
 finally{mainBusy=false;overviewLast=0;await refreshWithVersion();}
}
function chooseEditedWorkbook(month){
 const input=document.createElement('input');input.type='file';input.accept='.xlsx';
 input.onchange=async()=>{
  const file=input.files[0];if(!file||preventBusyAction())return;
  if(file.size>12*1024*1024){notice('Choose an Excel workbook smaller than 12 MB.',true);return;}
  mainBusy=true;mainBooksDisplay();updateDisplay();notice('Checking and saving your contributor edits…');
  try{
   const response=await fetch('/api/main/edits',{method:'POST',headers:{'Content-Type':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','X-CSRF-Token':state.csrf,'X-Workbook-Month':month},body:file});
   const result=await response.json();if(!response.ok)throw responseError(result);notice(result.message);
  }catch(e){reportError(e);}
  finally{mainBusy=false;overviewLast=0;await refreshWithVersion();}
 };
 input.click();
}
$('create-main-form').onsubmit=e=>{e.preventDefault();manageMain('create',$('main-month').value);};
$('main-books').onclick=e=>{const button=e.target.closest('button[data-action]');if(button)manageMain(button.dataset.action,button.dataset.month);};

const overviewTeams=['Search','Typing','VM Team','Leadership','Triage'];
let overviewLoading=false,overviewLast=0,overviewLoadedMonth='',overviewOptionKey='';
function displaySummary(prefix,result){
 $(prefix+'counts').innerHTML=result.rows.map(r=>`<tr><td>${esc(r.team)}</td><td>${r.count.toLocaleString('en-IN')}</td><td>${r.points.toLocaleString('en-IN',{maximumFractionDigits:10})}</td></tr>`).join('');
 $(prefix+'total').textContent=result.total.toLocaleString('en-IN');
 $(prefix+'points').textContent=result.points.toLocaleString('en-IN',{maximumFractionDigits:10});
}
function overviewEmpty(message){
 for(const prefix of ['team-','latest-team-']){ $(prefix+'counts').innerHTML=overviewTeams.map(team=>`<tr><td>${team}</td><td>—</td><td>—</td></tr>`).join('');$(prefix+'total').textContent='—';$(prefix+'points').textContent='—'; }
 $('latest-summary-date').textContent=message;
 $('team-total').textContent='—';$('overview-status').textContent=message;$('overview-status').className='muted unavailable';
 $('overview-download').hidden=true;$('overview-warning').hidden=true;
}
function overviewControls(){
 const books=state?.mainBooks||[],key=books.map(b=>b.month).join(',');
 if(key!==overviewOptionKey||!$('overview-month').value){
  const previous=$('overview-month').value;overviewOptionKey=key;
  $('overview-month').innerHTML=books.length?books.map(b=>`<option value="${esc(b.month)}">${esc(new Date(b.month+'-01T12:00:00').toLocaleDateString('en-IN',{month:'long',year:'numeric'}))}</option>`).join(''):'<option value="">No workbook yet</option>';
  $('overview-month').value=books.some(b=>b.month===previous)?previous:books.some(b=>b.month===state.phase2?.currentMonth)?state.phase2.currentMonth:books[0]?.month||'';
 }
 $('header-schedule').textContent=isViewer()?'Viewer PC · Shared Excel':state.schedule?'Scheduled · 8:45 AM weekdays':'Automatic collection paused';
 $('operation-state').hidden=!(state.activity?.busy||mainBusy||pending);$('operation-state').textContent=state.activity?.busy?'Working · '+state.activity.message+' — Your last saved workbook remains available while this finishes.':mainBusy||pending?'Starting your request…':'';
 if(busyNotice){notice(state.activity?.busy?'Work is in progress. '+state.activity.message:'The previous operation has finished. You can start your next action.');busyNotice=Boolean(state.activity?.busy);}
 $('stop-process').hidden=!state.activity?.busy||!state.activity?.cancellable;$('stop-process').disabled=stoppingProcess||Boolean(state.activity?.stopping);$('stop-process').textContent=stoppingProcess||state.activity?.stopping?'Stopping…':'Stop process';
 $('overview-refresh-status').disabled=!$('overview-month').value||workBlocked();
 workControls();
 $('overview-reload').disabled=overviewLoading||!$('overview-month').value;
 if(!books.length)overviewEmpty(state.sharedError||(isViewer()?'No monthly workbooks in the shared folder yet.':'Collect a report to create a workbook'));
}
async function fetchOverview(force=false){
 if(!state||overviewLoading)return;
 const month=$('overview-month').value;
 if(!month)return;
 if(!force&&overviewLoadedMonth===month&&Date.now()-overviewLast<15000)return;
 overviewLoading=true;overviewLast=Date.now();$('overview-reload').disabled=true;
 const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),15000);
 try{
  const response=await fetch('/api/main/'+encodeURIComponent(month)+'/summary',{signal:controller.signal});
  const result=await response.json();
  if($('overview-month').value!==month)return;
  overviewLoadedMonth=month;
  if(!response.ok||!result.available)throw Error(result.message||result.error||'Workbook unavailable');
  if(result.rows.reduce((n,r)=>n+r.count,0)!==result.total)throw Error('Team counts do not match the workbook total.');
  for(const section of [result,result.latest]){
   if(section.rows.reduce((n,r)=>n+r.count,0)!==section.total||Math.abs(section.rows.reduce((n,r)=>n+r.points,0)-section.points)>1e-8)throw Error('Team totals do not match the workbook.');
  }
  displaySummary('team-',result);displaySummary('latest-team-',result.latest);
  $('latest-summary-date').textContent=result.latest.date?new Date(result.latest.date+'T12:00:00').toLocaleDateString('en-IN',{day:'numeric',month:'long',year:'numeric'}):'No error dates in this workbook';
  $('overview-status').className='muted';$('overview-status').textContent='Saved '+new Date(result.savedAt*1000).toLocaleString('en-IN',{timeZone:'Asia/Kolkata',dateStyle:'medium',timeStyle:'short'});
  $('overview-download').href='/api/main/'+encodeURIComponent(month)+'/current';$('overview-download').hidden=false;
  $('overview-source').textContent=(result.source==='shared'?'Shared Excel':'Main Excel')+' · Counts check for saved changes every 15 seconds. Unsaved Excel edits appear after saving.';
  const extra=result.rows.filter(r=>['Unassigned','Other'].includes(r.team));
  $('overview-warning').hidden=!extra.length;$('overview-warning').textContent=extra.length?'Unassigned or other team values are included so the total matches every error row in SP 2.':'';
 }catch(error){
  if($('overview-month').value===month)overviewEmpty(error.name==='AbortError'?'Workbook is taking too long to respond. Retrying automatically.':error.message);
 }finally{
  clearTimeout(timer);overviewLoading=false;overviewControls();
  if($('overview-month').value!==month)fetchOverview(true);
 }
}
$('overview-month').onchange=()=>{overviewEmpty('Reading workbook…');overviewLoadedMonth='';fetchOverview(true);};
$('overview-reload').onclick=()=>fetchOverview(true);
$('overview-refresh-status').onclick=()=>manageMain('refresh',$('overview-month').value);

let refreshPoll=null;
function refreshWithVersion(){if(refreshPoll)return refreshPoll;refreshPoll=(async()=>{try{const connected=await refresh();updateDisplay();if(connected)fetchOverview();if(state)$('name-map-status').textContent=state.nameMapping?.loaded?`Loaded · ${state.nameMapping.searchAliases} Search / ${state.nameMapping.typingAliases} Typing aliases`:'No roster loaded';}finally{refreshPoll=null;}})();return refreshPoll;}refreshWithVersion();setInterval(refreshWithVersion,5000);
if(document.modelContext?.registerTool){
 const life=new AbortController();window.addEventListener('pagehide',()=>life.abort(),{once:true});
 Promise.resolve(document.modelContext.registerTool({name:'get_report_runs',title:'Read report history',description:'Read the local TitleVision report runs and their completion or review status.',inputSchema:{type:'object',properties:{},additionalProperties:false},annotations:{readOnlyHint:true,untrustedContentHint:true},async execute(){await refresh();return {runs:state.runs,scheduleEnabled:state.schedule};}},{signal:life.signal})).catch(()=>{});
 Promise.resolve(document.modelContext.registerTool({name:'start_error_report',title:'Start error report',description:'Start collection of TitleVision errors for an inclusive completed date range. Creates a new report run using the locally saved sign-in.',inputSchema:{type:'object',properties:{start:{type:'string',pattern:'^\\d{4}-\\d{2}-\\d{2}$'},end:{type:'string',pattern:'^\\d{4}-\\d{2}-\\d{2}$'}},required:['start','end'],additionalProperties:false},annotations:{readOnlyHint:false,untrustedContentHint:false},async execute(input){if(!input||typeof input.start!=='string'||typeof input.end!=='string')throw Error('Both dates are required');if(!state)await refresh();const result=await api('/api/run',input);selected=result.id;await refresh();return {runId:result.id,status:'started'};}},{signal:life.signal})).catch(()=>{});
}

$('cancel-update').onclick=async()=>{try{const result=await api('/api/update/cancel',{});notice(result.message);await refreshWithVersion();}catch(error){reportError(error);}};

$('stop-process').onclick=async()=>{
 if(stoppingProcess||!state?.activity?.cancellable||state.activity.stopping)return;
 const operationId=state.activity.operationId;stoppingProcess=true;overviewControls();
 try{const result=await api('/api/operation/stop',{operationId});notice(result.message);busyNotice=true;}
 catch(error){reportError(error);}
 finally{stoppingProcess=false;await refreshWithVersion();overviewControls();}
};
