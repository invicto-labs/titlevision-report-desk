import {chromium} from 'playwright';
import {createRequire} from 'node:module';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const require=createRequire(import.meta.url);
const root=path.dirname(fileURLToPath(import.meta.url));
if(!require.resolve('playwright').startsWith(path.join(root,'node_modules')))throw Error('Browser library is outside the application');
const browser=await chromium.launch({channel:'msedge',headless:true});
try{const page=await browser.newPage();await page.setContent('<title>Report Desk check</title>');if(await page.title()!=='Report Desk check')throw Error('Browser check failed');console.log('Included Node and headless Microsoft Edge: OK');}finally{await browser.close();}
