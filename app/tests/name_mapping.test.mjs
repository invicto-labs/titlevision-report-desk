import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';

const app=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
test('private role-specific roster controls daily Searcher, Typer and contributor names',()=>{
 const folder=path.join(app,'tests','results','names-'+Date.now());fs.mkdirSync(folder,{recursive:true});
 const values=(order,category)=>{const row=Array(20).fill('');row[0]='New';row[1]=order;row[6]=category;row[9]='Full Title';row[12]='10/1/2026 12:00:00 PM';row[15]='1';return row;};
 const source=[{id:'one',values:values('Order-1','Searching')},{id:'two',values:values('Order-2','Typing')},{id:'three',values:values('Order-3','Typing')}];
 const staff={one:{tv:'TV-1',client:'Client',names:['KishoreK_ADSSearchType','DeepikaK_ADSSearchType']},two:{tv:'TV-2',client:'Client',names:['AshwinK_ADSSearchType','Sachin_ADSSearchType']},three:{tv:'TV-3',client:'Client',names:['','KishoreK_ADSSearchType']}};
 const mapping={schema:2,search:{kishorek:{id:'INV060',name:'Kishore R'},ashwink:{id:'T0315',name:'Ashwin Kumar M'}},type:{deepikak:{id:'INV160',name:'Kanna Deepika'},sachin:{id:'INV058',name:'Sachin S'}},legacy:{kishorek:'Kishore K'}};
 for(const [name,value] of Object.entries({'source.json':source,'staff.json':staff,'collection.json':{start:'2026-10-01',end:'2026-10-01',count:3,points:3},'names.json':mapping}))fs.writeFileSync(path.join(folder,name),JSON.stringify(value));
 execFileSync(process.execPath,[path.join(app,'report','prepare.mjs'),folder],{env:{...process.env,TITLEVISION_DATA:folder}});
 const rows=JSON.parse(fs.readFileSync(path.join(folder,'payload.json'),'utf8')).data.slice(1);
 assert.deepEqual([rows[0][18],rows[0][20],rows[0][23]],['Kishore R','Kanna Deepika','Kishore R']);
 assert.deepEqual([rows[1][18],rows[1][20],rows[1][23]],['Ashwin Kumar M','Sachin S','Sachin S']);
 assert.deepEqual([rows[2][18],rows[2][20],rows[2][23]],['','Kishore R','Kishore R']);
 assert.deepEqual(JSON.parse(fs.readFileSync(path.join(folder,'issues.json'),'utf8')).map(i=>i.kind),['roster_team_review']);
});
