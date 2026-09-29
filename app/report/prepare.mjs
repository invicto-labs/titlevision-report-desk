// Portable report input: use the same collector/date/attribution rules as the local edition.
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {serial as date, teamFor} from '../rules.mjs';
const app=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const dir=path.resolve(process.argv[2]);
const read=async p=>JSON.parse(await fs.readFile(p,'utf8'));
const source=await read(path.join(dir,'source.json')),staff=await read(path.join(dir,'staff.json'));
const collection=await read(path.join(dir,'collection.json'));
const personalNames=path.join(process.env.TITLEVISION_DATA??path.join(process.env.LOCALAPPDATA??app,'TitleVision Report Desk','data'),'names.json');
const nameMap=await read(personalNames).catch(()=>read(path.join(app,'templates/names.json')));
const {headers,widths}=await read(path.join(app,'templates/layout.json'));
const issues=[];
function display(user){if(!user)return '';const n=user.replace(/_ADS.*$/i,'');return nameMap[n.toLowerCase()]??n.replace(/([a-z])([A-Z])/g,'$1 $2');}
const details=source.map(({values:r,id,statusFields,statusHistory})=>{
 const p=staff[id];if(!p)throw Error('Missing verified order '+r[1]);const team=teamFor(r);
 if((team==='Search'&&!p.names[0])||(team==='Type'&&!p.names[1]))issues.push({id,order:r[1],kind:'missing_name',message:`No completed human ${team==='Search'?'Search':'Typing'} task was recorded. Contributor left blank.`});
 if(/\b(?:VM|triage)\b/i.test(r[8])&&!['Triage','VM team'].includes(team))issues.push({id,order:r[1],kind:'cause_review',message:'Notes mention VM or triage. Review the cause before overriding Team.'});
 const searcher=display(p.names[0]),typer=display(p.names[1]);
 const contributor=team==='Search'?searcher:team==='Type'?typer:['Triage','VM team'].includes(team)?team:'';
 if(statusHistory&&(!Array.isArray(statusFields)||statusFields.length!==4))throw Error('Status comment fields were not reconciled');
 const decision=statusFields??['','','',''];
 if(['Chargeable','Non-Chargeable'].includes(r[0])&&!decision[3])issues.push({id,order:r[1],kind:'missing_client_comment',message:'TitleVision has a final status but no identifiable client reply. Final status copied; comment left blank.'});
 return [r[0],r[1],p.tv,'',p.client,r[5],r[6],r[7],r[8],r[9],date(r[12]),r[13],r[14],Number(r[15]),date(r[16]),date(r[17]),r[18],r[19],searcher,'',typer,'',team,contributor,...decision];
});
if(details.length!==collection.count||details.reduce((n,r)=>n+r[13],0)!==collection.points)throw Error('Export totals mismatch');
const specs=[{name:'ErrorsByContributor',field:23,title:'Final Error Contributor',col:0,row:5},{name:'ErrorsByTeam',field:22,title:'Team',col:4,row:5},{name:'ErrorsByCategory',field:6,title:'Error Category',col:8,row:5},{name:'ErrorsByStatus',field:0,title:'Status',col:4,row:15}];
for(const p of specs){const items=new Set(details.map(r=>r[p.field]||''));if([22,23].includes(p.field))items.add('VM team');p.items=[...items].sort((a,b)=>a===''?1:b===''?-1:a.localeCompare(b));p.height=p.items.length+3;}
await fs.writeFile(path.join(dir,'payload.json'),JSON.stringify({data:[headers,...details],specs,tableName:'TitleVisionErrors',widths}));
await fs.writeFile(path.join(dir,'issues.json'),JSON.stringify(issues));
