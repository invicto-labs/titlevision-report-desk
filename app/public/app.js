const $=id=>document.getElementById(id);let state=null,selected=null,pending=false,checkingUpdate=false,updateMessage='',loadedVersion=null,mainBusy=false;
const labels={complete:'Complete',review:'Needs review',failed:'Failed',running:'Running',queued:'Queued'};
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function notice(message,error=false){$('notice').textContent=message;$('notice').className=error?'error':'';$('notice').hidden=!message;}
async function api(url,body){const r=await fetch(url,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':state.csrf},body:JSON.stringify(body)});const j=await r.json();if(!r.ok)throw Error(j.error||'Request failed');return j;}
function period(r){return r.start===r.end?r.start:`${r.start} – ${r.end}`;}
async function detail(r){mainChoiceDisplay(r);if(!r)return;selected=r.id;$('period').textContent=period(r);$('status').textContent=labels[r.status];$('status').className='badge '+r.status;$('progress').textContent=r.message;$('errors').textContent=r.count??'—';$('points').textContent=r.points??'—';$('review').textContent=r.issues??0;const ready=['complete','review'].includes(r.status);$('latest-download').hidden=!ready;$('latest-download').href=`/api/runs/${r.id}/download`;if(ready){const d=await api('/api/runs/'+r.id);$('issues-panel').hidden=!d.issues.length;$('issues').innerHTML=d.issues.map(i=>`<li><strong>${esc(i.order)}</strong> — ${esc(i.message)}</li>`).join('');}else $('issues-panel').hidden=true;}
async function refresh(){try{const initial=!state,previous=state;state=await api('/api/state');const completed=state.runs.find(r=>['complete','review'].includes(r.status)&&previous?.runs.some(old=>old.id===r.id&&['queued','running'].includes(old.status)));if(completed)selected=completed.id;mainBooksDisplay();if(loadedVersion&&loadedVersion!==state.version){location.reload();return;}loadedVersion=state.version;if(initial){$('start').value=state.yesterday;$('end').value=state.yesterday;}$('start').max=state.yesterday;$('end').max=state.yesterday;$('schedule-label').textContent=state.schedule?'Enabled · Every day at 8:45 AM India time':'Paused · Turn on automatic daily collection';$('schedule').textContent=state.schedule?'Pause schedule':'Enable schedule';$('credentials-state').textContent=state.credentialsSaved?'Sign-in saved and encrypted. Enter a password only to replace it.':'Save your sign-in before running a report.';$('run').disabled=pending||mainBusy||['downloading','installing'].includes(state.update?.phase)||state.runs.some(r=>['running','queued'].includes(r.status));$('history').innerHTML=state.runs.length?state.runs.map(r=>`<tr class="history-row" data-id="${r.id}" tabindex="0"><td><strong>${esc(period(r))}</strong></td><td>${esc(new Date(r.created).toLocaleString('en-IN',{timeZone:'Asia/Kolkata',dateStyle:'medium',timeStyle:'short'}))}</td><td><span class="badge ${r.status}">${labels[r.status]}</span></td><td>${r.count??'—'}</td><td>${r.points??'—'}</td><td>${['complete','review'].includes(r.status)?`<a href="/api/runs/${r.id}/download">Download Excel</a>`:'—'}</td></tr>`).join(''):'<tr><td colspan="6" class="empty">Your collected reports will appear here.</td></tr>';
$('schedule').disabled=!state.schedule&&!state.verifiedLive;if(!state.schedule&&!state.verifiedLive)$('schedule-label').textContent='Paused · A complete live report must pass verification first';
const r=state.runs.find(r=>r.id===selected)||state.runs[0];await detail(r);if(initial&&!state.credentialsSaved)$('settings').open=true;}catch(e){if(state?.update?.phase!=='installing')notice('Cannot connect to Report Desk. '+e.message,true);}}
$('run-form').addEventListener('submit',async e=>{e.preventDefault();if(pending)return;pending=true;$('run').disabled=true;try{const r=await api('/api/run',{start:$('start').value,end:$('end').value});selected=r.id;notice('Report started. You can leave this page open to follow its progress.');await refresh();}catch(e){notice(e.message,true);}finally{pending=false;await refresh();}});
$('yesterday').onclick=()=>{$('start').value=state.yesterday;$('end').value=state.yesterday;};
$('credentials').onsubmit=async e=>{e.preventDefault();const button=e.target.querySelector('button');button.disabled=true;try{await api('/api/credentials',{username:$('username').value,password:$('password').value});$('password').value='';notice('Sign-in saved securely for this Windows account.');await refresh();}catch(e){notice(e.message,true);}finally{button.disabled=false;}};
$('schedule').onclick=async()=>{$('schedule').disabled=true;try{await api('/api/schedule',{enabled:!state.schedule});notice('Daily schedule updated.');await refresh();}catch(e){notice(e.message,true);}finally{$('schedule').disabled=false;}};
$('history').onclick=e=>{if(e.target.closest('a'))return;const row=e.target.closest('[data-id]');if(row)detail(state.runs.find(r=>r.id===row.dataset.id)).catch(e=>notice(e.message,true));};
$('history').onkeydown=e=>{if(e.key==='Enter'){const row=e.target.closest('[data-id]');if(row)detail(state.runs.find(r=>r.id===row.dataset.id)).catch(e=>notice(e.message,true));}};
function updateDisplay(){if(!state)return;$('app-version').textContent=state.version?'Running v'+state.version:'Version unavailable';const updating=['downloading','installing'].includes(state.update?.phase);$('get-update').disabled=mainBusy||checkingUpdate||updating||state.runs.some(r=>['running','queued'].includes(r.status));$('get-update').textContent=checkingUpdate?'Checking…':updating?'Updating…':'Get update';$('update-status').textContent=checkingUpdate?'Checking the latest published release…':updateMessage||state.update?.message||'Check for a published release.';$('github-state').textContent=state.githubAccessSaved?'GitHub update access is saved and encrypted.':'No token saved. An existing Git sign-in as invicto-labs will be used if available.';}
$('get-update').onclick=async()=>{if(checkingUpdate)return;checkingUpdate=true;updateMessage='';updateDisplay();try{const result=await api('/api/update/install',{});await refresh();if(!result.available)updateMessage='You are running the latest version: v'+result.current+'.';}catch(e){updateMessage=e.message;}finally{checkingUpdate=false;updateDisplay();}};
$('github-access').onsubmit=async e=>{e.preventDefault();if(!$('github-token').value.trim())return;try{await api('/api/update/token',{token:$('github-token').value});$('github-token').value='';notice('GitHub update access saved.');updateMessage='';await refresh();}catch(e){notice(e.message,true);}updateDisplay();};
$('clear-github-access').onclick=async()=>{try{await api('/api/update/token',{token:''});await refresh();updateDisplay();notice('Saved GitHub access removed.');}catch(e){notice(e.message,true);}};

function mainBooksDisplay(){
 const books=state.mainBooks||[];
 const enabled=state.phase2?.enabled,blocked=mainBusy||state.runs.some(r=>['running','queued'].includes(r.status))||['downloading','installing'].includes(state.update?.phase);
 $('phase2-note').textContent=enabled?'October 2026 onward: after daily collection, the app checks statuses, points and dispute/client comments from the first of the month through the latest completed day. Only approved reports enter the workbook. PivotTables rebuild after all checks pass.':'Workbook creation, removal and month-to-date status refresh start on 1 October 2026. September workbooks keep their existing behavior.';
 $('create-main-form').hidden=!enabled;$('create-main').disabled=blocked;
 if(!$('main-month').value)$('main-month').value=enabled?state.phase2.currentMonth:'2026-10';
 $('main-month').max=state.phase2?.currentMonth||'';
 $('main-books').innerHTML=books.length?books.map(b=>{
  const managed=enabled&&b.month>='2026-10';
  const name=new Date(b.month+'-01T12:00:00').toLocaleDateString('en-IN',{month:'long',year:'numeric'})+' workbook';
  const refresh=b.syncStatus==='running'?'Refreshing — last verified workbook shown':b.syncStatus==='failed'?'Refresh failed — previous workbook retained':b.syncStatus==='empty'?'Empty workbook':b.syncedAt?'Verified '+new Date(b.syncedAt).toLocaleString('en-IN',{timeZone:'Asia/Kolkata'}):'Approved daily snapshots';
  return `<tr><td><strong>${esc(name)}</strong></td><td>${b.days?esc(b.start)+' – '+esc(b.end):'No approved dates'}<br><small>${b.days} approved day(s)</small></td><td class="sync-cell">${esc(refresh)}${b.syncThrough?'<br><small>Checked through '+esc(b.syncThrough)+'</small>':''}${b.syncStatus==='failed'?'<br><small>'+esc(b.syncMessage)+'</small>':''}</td><td>${b.count}</td><td>${b.points}</td><td><a href="/api/main/${encodeURIComponent(b.month)}/download">Download main Excel</a>${managed?`<div class="book-actions"><button data-month="${esc(b.month)}" data-action="refresh" ${blocked?'disabled':''}>Refresh status</button><button data-month="${esc(b.month)}" data-action="delete" ${blocked?'disabled':''}>Delete workbook</button></div>`:''}</td></tr>`;
 }).join(''):'<tr><td colspan="6" class="empty">No main workbook yet. Complete a report and choose Yes, or create an empty workbook from October onward.</td></tr>';
}
function mainChoiceDisplay(r){
 const ready=r&&['complete','review'].includes(r.status);$('main-choice').hidden=!ready;if(!ready)return;
 $('main-choice-period').textContent=`Selected report: ${period(r)} · ${r.count} errors · ${r.points} points`;
 $('main-yes').hidden=r.mainChoice==='yes';$('main-no').hidden=!!r.mainChoice;
 $('main-yes').textContent=r.mainChoice==='no'?'Add this report now':'Yes, add to main workbook';
 $('main-yes').disabled=mainBusy;$('main-no').disabled=mainBusy;
 if(!mainBusy)$('main-choice-status').textContent=r.mainChoice==='yes'?'This report was added. Download the latest monthly workbook below.':r.mainChoice==='no'?'Daily rows not added. Existing approved rows may receive status, points and comment updates.':state.phase2?.enabled&&r.end>='2026-10-01'?'Choose Yes to add these dates, verify month-to-date statuses, points and comments, then rebuild the monthly PivotTables. No keeps this daily report separate.':'Waiting for your choice. Nothing is added automatically.';
}
async function chooseMain(add){
 if(mainBusy||!selected)return;const rid=selected;mainBusy=true;mainChoiceDisplay(state.runs.find(r=>r.id===rid));updateDisplay();$('run').disabled=true;
 $('main-choice-status').textContent=add?'Updating and checking the main workbook…':'Saving your choice…';
 try{const result=await api(`/api/runs/${rid}/main`,{add});notice(result.message);}
 catch(e){notice(e.message,true);}
 finally{mainBusy=false;await refreshWithVersion();}
}
$('main-yes').onclick=()=>chooseMain(true);$('main-no').onclick=()=>chooseMain(false);
async function manageMain(action,month){
 if(mainBusy)return;
 if(action==='delete'&&!window.confirm(`Delete the ${month} main workbook and remove its approvals? Daily reports are kept so you can rebuild it.`))return;
 mainBusy=true;mainBooksDisplay();updateDisplay();notice(action==='refresh'?'Checking month-to-date data and rebuilding the workbook…':action==='create'?'Creating monthly workbook…':'Removing monthly workbook…');
 try{const result=await api('/api/main/'+action,{month,...(action==='delete'?{confirm:true}:{})});notice(result.message);}
 catch(e){notice(e.message,true);}
 finally{mainBusy=false;await refreshWithVersion();}
}
$('create-main-form').onsubmit=e=>{e.preventDefault();manageMain('create',$('main-month').value);};
$('main-books').onclick=e=>{const button=e.target.closest('button[data-action]');if(button)manageMain(button.dataset.action,button.dataset.month);};

async function refreshWithVersion(){await refresh();updateDisplay();}refreshWithVersion();setInterval(refreshWithVersion,5000);
if(document.modelContext?.registerTool){
 const life=new AbortController();window.addEventListener('pagehide',()=>life.abort(),{once:true});
 Promise.resolve(document.modelContext.registerTool({name:'get_report_runs',title:'Read report history',description:'Read the local TitleVision report runs and their completion or review status.',inputSchema:{type:'object',properties:{},additionalProperties:false},annotations:{readOnlyHint:true,untrustedContentHint:true},async execute(){await refresh();return {runs:state.runs,scheduleEnabled:state.schedule};}},{signal:life.signal})).catch(()=>{});
 Promise.resolve(document.modelContext.registerTool({name:'start_error_report',title:'Start error report',description:'Start collection of TitleVision errors for an inclusive completed date range. Creates a new report run using the locally saved sign-in.',inputSchema:{type:'object',properties:{start:{type:'string',pattern:'^\\d{4}-\\d{2}-\\d{2}$'},end:{type:'string',pattern:'^\\d{4}-\\d{2}-\\d{2}$'}},required:['start','end'],additionalProperties:false},annotations:{readOnlyHint:false,untrustedContentHint:false},async execute(input){if(!input||typeof input.start!=='string'||typeof input.end!=='string')throw Error('Both dates are required');if(!state)await refresh();const result=await api('/api/run',input);selected=result.id;await refresh();return {runId:result.id,status:'started'};}},{signal:life.signal})).catch(()=>{});
}
