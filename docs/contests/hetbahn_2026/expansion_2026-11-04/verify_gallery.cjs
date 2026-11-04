'use strict';
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const {pathToFileURL}=require('node:url');
const {chromium}=require('C:/Users/user/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const ROOT=__dirname;
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
(async()=>{
 const gallery=path.join(ROOT,'gallery.html'),assets=JSON.parse(fs.readFileSync(path.join(ROOT,'assets.json'),'utf8'));
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 const results=[],outside=[];
 try{
  for(const width of [1200,360]){
   const page=await browser.newPage({viewport:{width,height:900},deviceScaleFactor:1});
   await page.route('**/*',route=>{const u=route.request().url();if(u.startsWith('file:')||u.startsWith('data:'))return route.continue();outside.push(u);return route.abort();});
   await page.goto(pathToFileURL(gallery).href,{waitUntil:'load'});
   await page.evaluate(async()=>{await document.fonts.ready;await Promise.all([...document.images].map(im=>im.decode()));});
   const state=await page.evaluate(()=>({viewport:innerWidth,scroll:document.documentElement.scrollWidth,title:document.title,images:[...document.images].map(im=>({alt:im.alt,width:im.naturalWidth,height:im.naturalHeight,rendered:im.getBoundingClientRect().width})),cards:document.querySelectorAll('article').length}));
   if(state.cards!==6||state.images.length!==6||state.images.some(im=>im.width!==1080||im.height!==1350)||state.scroll>state.viewport)throw Error('Gallery failed '+JSON.stringify(state));
   await page.screenshot({path:path.join(ROOT,'.private','gallery_'+width+'.png'),fullPage:true});
   results.push(state);await page.close();
  }
 }finally{await browser.close();}
 if(outside.length)throw Error('Unexpected remote request');
 const report={status:'PASS',scope:'isolated local HTML software QA, not service generation history or human response',html_sha256:sha(fs.readFileSync(gallery)),asset_hashes:Object.fromEntries(assets.entries.map(a=>[a.key,sha(fs.readFileSync(path.join(ROOT,a.stem+'.png')))])),viewports:results,external_requests:outside};
 fs.writeFileSync(path.join(ROOT,'원본과기록','갤러리_동작검사.json'),JSON.stringify(report,null,2)+'\n','utf8');
 console.log(JSON.stringify({status:report.status,viewports:results.map(s=>s.viewport),cards:6,external_requests:outside.length}));
})().catch(e=>{console.error(e.stack);process.exitCode=1;});
