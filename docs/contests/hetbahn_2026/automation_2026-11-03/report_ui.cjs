'use strict';
const fs=require('fs'),path=require('path'),crypto=require('crypto'),assert=require('assert');
const {pathToFileURL}=require('url');
const {chromium}=require('C:/Users/user/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const root=__dirname;
const hash=p=>crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
(async()=>{
 let browser;const result={status:'FAIL',software_test_only:true,real_participants_added:0,views:[],external_requests:[],errors:[]};
 try{
  const report=JSON.parse(fs.readFileSync(path.join(root,'reports/latest.json'),'utf8'));
  const policy=JSON.parse(fs.readFileSync(path.join(root,'policy.json'),'utf8'));
  assert.equal(report.policy_sha256,hash(path.join(root,'policy.json')));
  browser=await chromium.launch({headless:true,executablePath:process.env.QA_CHROME||'C:/Program Files/Google/Chrome/Application/chrome.exe'});
  const context=await browser.newContext({viewport:{width:1200,height:1000}});
  const page=await context.newPage();
  page.on('pageerror',e=>result.errors.push(String(e)));
  await page.route('**/*',route=>{if(/^https?:/.test(route.request().url())){result.external_requests.push(route.request().url());return route.abort();}return route.continue();});
  await page.goto(pathToFileURL(path.join(root,'reports/latest.html')).href,{waitUntil:'load'});
  const expected={'FAIL':'검사 실패','SUBMISSION_READY':'제출 자료 검사 통과','EVIDENCE_PENDING':'필수 증거 대기'}[report.decision.verdict];
  assert(expected);
  const images=await page.locator('img').evaluateAll(xs=>xs.map(x=>({width:x.naturalWidth,height:x.naturalHeight,src:x.src})));
  if(report.stages.baseline.status==='PASS'&&report.stages.assets?.status==='PASS'){
   assert.equal(images.length,2);
   for(let i=0;i<2;i++){const x=images[i];assert.equal(x.width,1080);assert.equal(x.height,1350);assert(x.src.startsWith('data:image/png;base64,'));const digest=crypto.createHash('sha256').update(Buffer.from(x.src.split(',')[1],'base64')).digest('hex');assert.equal(digest,policy.assets[['A','B'][i]].sha256);}
  }
  for(const viewport of [{width:1200,height:1000},{width:360,height:780}]){
   await page.setViewportSize(viewport);
   const info=await page.evaluate(()=>({overflow:document.documentElement.scrollWidth>innerWidth+1,text:document.body.innerText}));
   assert(!info.overflow);assert(info.text.includes(expected));
   result.views.push({...viewport,horizontal_overflow:false});
   await page.screenshot({path:path.join(root,'.private','report-'+viewport.width+'.png'),fullPage:false});
  }
  assert.equal(result.errors.length,0);assert.equal(result.external_requests.length,0);
  result.status='PASS';result.html_sha256=hash(path.join(root,'reports/latest.html'));result.report_sha256=hash(path.join(root,'reports/latest.json'));
 }catch(error){result.errors.push(String(error.stack||error));process.exitCode=1;}
 finally{if(browser)await browser.close();fs.writeFileSync(path.join(root,'reports/ui_check.json'),JSON.stringify(result,null,2)+'\n');process.stdout.write(JSON.stringify(result)+'\n');}
})();
