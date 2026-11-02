/* DOM/브라우저 소프트웨어 QA만 수행. 실제 관객/실제 서비스/사용자 Chrome과 무관. */
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const crypto = require('node:crypto');
const vm = require('node:vm');
const {spawnSync} = require('node:child_process');
const {chromium} = require('C:/Users/user/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const chrome = process.env.QA_CHROME || 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const root = __dirname, study = path.dirname(root);
const scope = {}; vm.runInNewContext(fs.readFileSync(path.join(root,'protocol.js'),'utf8'), scope);
const P = scope.OBSERVER_PROTOCOL;
const temporary = fs.mkdtempSync(path.join(os.tmpdir(),'hetbahn-observer-qa-'));
const result = {software_test_only:true, real_participants_added:0, context:'완전히 분리한 임시 headless Chrome', offline:true, final_images_only:process.argv.includes('--final-only'), checks:{}, image_sources:{}, external_requests:[], errors:[]};
let browser;
const base = 'http://127.0.0.1:43197'; // 아래 route.fulfill로만 처리. 서버 연결/외부 네트워크를 사용하지 않는다.
const startURL = base + '/관객검증/관찰.html?qa=1';
const sha256 = b => crypto.createHash('sha256').update(b).digest('hex');
const resources = new Map();
const probeRoot = path.join(temporary,'study');
function prepareResources() {
for (const filename of ['관찰.html','protocol.js']) resources.set('/관객검증/'+filename, fs.readFileSync(path.join(root,filename)));
fs.mkdirSync(probeRoot);
fs.writeFileSync(path.join(probeRoot,'protocol.js'), fs.readFileSync(path.join(root,'protocol.js')));
for (const arm of ['A','B']) {
  const finalPath = path.resolve(root,P.images[arm].path);
  const provisionalPath = path.join(path.dirname(study),'portfolio_2026-11-02',path.basename(finalPath));
  const selected = fs.existsSync(finalPath) ? finalPath : provisionalPath;
  if (process.argv.includes('--final-only')) assert.equal(selected, finalPath, '최종 이미지가 아직 없습니다.');
  const bytes = fs.readFileSync(selected);
  assert.equal(sha256(bytes),P.images[arm].sha256,arm+' 프로토콜 해시가 현재 이미지와 다릅니다. 최종 해시를 확정한 뒤 다시 실행하세요.');
  resources.set('/'+path.basename(finalPath),bytes);
  fs.writeFileSync(path.resolve(probeRoot,P.images[arm].path),bytes);
  result.image_sources[arm] = {path:selected, final:selected===finalPath, image_sha256:sha256(bytes)};
}
}
async function isolated() {
  const context = await browser.newContext({viewport:{width:390,height:844},deviceScaleFactor:1,acceptDownloads:true,serviceWorkers:'block',offline:true});
  const requests = [];
  await context.route('**/*',async route => {
    const url = new URL(route.request().url());
    requests.push(url.href);
    if (url.origin !== base) {result.external_requests.push(url.href); await route.abort(); return;}
    const pathname = decodeURIComponent(url.pathname);
    const body = resources.get(pathname);
    if (!body) {await route.fulfill({status:404,body:'QA missing local resource'}); return;}
    await route.fulfill({status:200,contentType:pathname.endsWith('.js')?'application/javascript':pathname.endsWith('.png')?'image/png':'text/html; charset=utf-8',body});
  });
  const page = await context.newPage();
  page.on('pageerror',e => result.errors.push(String(e)));
  await page.goto(startURL);
  return {context,page,requests};
}
const key = id => `observer:${P.protocol_id}:qa:${id}`;
async function record(page,id) {return page.evaluate(k=>JSON.parse(localStorage.getItem(k)),key(id));}
async function join(page,id) {await page.locator('#participant').fill(id); await page.locator('#join button').click(); await page.locator('#entry').waitFor({state:'hidden'});}
async function begin(page,id,prior=false) {
  await join(page,id);
  const before = await page.locator('body').innerText();
  assert(!/갓지은편지|스물네장의계절|즉석밥|컬렉션/.test(before), '노출 전 제목/정답 힌트 공개');
  await page.locator('#consent').check(); await page.locator('#adult').check();
  await page.locator(`input[name=prior][value=${prior?'yes':'no'}]`).check();
  await page.locator('#begin').click(); await page.locator('#exposure').waitFor({state:'visible'});
}
async function answer(page) {
  for (const field of ['product','event','scene','share_recipient','share_sentence','share_reason']) await page.locator(`#answersForm [name=${field}]`).fill('자유 원답  '+field+'\n  표현 그대로');
  await page.locator('#answersForm button').click(); await page.locator('#waiting').waitFor({state:'visible'});
}
async function download(page,name) {
  const [file] = await Promise.all([page.waitForEvent('download'),page.locator('#download').click()]);
  assert(file.suggestedFilename().startsWith('qa_'));
  const destination = path.join(temporary,name); await file.saveAs(destination);
  const value = JSON.parse(fs.readFileSync(destination,'utf8')); assert.equal(value.record_kind,'qa'); return destination;
}
async function run() {
  prepareResources();
  browser = await chromium.launch({executablePath:chrome,headless:true,args:['--disable-background-networking','--no-first-run']});
  const initial = await isolated(); const {page,requests} = initial;
  await join(page,'P01');
  assert.equal(await page.locator('#consent').isChecked(),false);
  assert.equal(requests.filter(u=>u.endsWith('.png')).length,0);
  await page.locator('#begin').click();
  assert.equal((await record(page,'P01')).stage,'ready');
  result.checks.consent_gate_and_no_preexposure_image = true;
  await page.locator('#consent').check(); await page.locator('#adult').check(); await page.locator('input[name=prior][value=no]').check();
  await page.locator('#begin').click(); await page.locator('#exposure').waitFor({state:'visible'});
  await page.waitForTimeout(700); assert.equal(await page.locator('#exposure').isVisible(),true);
  await page.locator('#response').waitFor({state:'visible',timeout:6500});
  let saved = await record(page,'P01');
  assert(saved.exposure_ms>=2800 && saved.exposure_ms<=3800);
  assert.equal(saved.image_sha256,P.images[P.assignment.P01].sha256);
  assert.equal(await page.locator('#stimulus img').count(),0);
  result.checks.actual_3s_exposure_ms = saved.exposure_ms;
  result.checks.image_hidden_and_removed = true;
  await answer(page);
  saved = await record(page,'P01'); assert.equal(saved.raw_answers.product,'자유 원답  product\n  표현 그대로');
  assert.equal(await page.locator('#recallBegin').isDisabled(),true);
  await page.locator('#recallBegin').evaluate(el=>el.click()); assert.equal((await record(page,'P01')).stage,'waiting');
  const firstExport = await download(page,'qa_first.json');
  const pngCount = requests.filter(u=>u.endsWith('.png')).length;
  await page.reload(); await join(page,'P01');
  assert.equal((await record(page,'P01')).arm,P.assignment.P01);
  assert.equal(requests.filter(u=>u.endsWith('.png')).length,pngCount);
  assert.equal(await page.locator('#stimulus img').count(),0);
  result.checks.refresh_no_reexposure_fixed_assignment = true;
  const due = Date.parse(saved.exposure_ended_at)+24*60*60*1000;
  await page.clock.setFixedTime(new Date(due-1000)); await page.waitForTimeout(1100);
  assert.equal(await page.locator('#recallBegin').isDisabled(),true);
  await page.clock.setFixedTime(new Date(due+1000));
  await page.waitForFunction(()=>!document.getElementById('recallBegin').disabled);
  await page.locator('#recallBegin').click();
  assert.equal(requests.filter(u=>u.endsWith('.png')).length,pngCount);
  await page.locator('#recallForm [name=brand]').fill('기억 원문'); await page.locator('#recallForm [name=scene]').fill('장면 원문');
  await page.locator('#recallForm button').click();
  const finalExport = await download(page,'qa_complete.json');
  result.checks.recall_24h_lock_boundary_no_image = true;
  saved = await record(page,'P01');
  // QA/실제응답 localStorage 이름공간도 다르게 유지한다. 실제응답을 생성하지 않고 QA키 불접근만 확인.
  await page.goto(base+'/관객검증/관찰.html');
  const namespaces = await page.evaluate(()=>Object.keys(localStorage));
  assert(namespaces.every(k=>k.includes(':qa:')));
  await page.goto(startURL); await join(page,'P01'); assert.equal((await record(page,'P01')).stage,'complete');
  result.checks.qa_namespace_and_export = true;
  await initial.context.close();

  const hidden = await isolated(); await begin(hidden.page,'P02'); await hidden.page.waitForTimeout(250);
  // headless DOM 검사에서 visibilitychange를 주입한다. 실제 관객/실제 탭 조작의 증거가 아니다.
  await hidden.page.evaluate(()=>{Object.defineProperty(document,'hidden',{configurable:true,get:()=>true});document.dispatchEvent(new Event('visibilitychange'));});
  await hidden.page.locator('#response').waitFor({state:'visible'});
  const hiddenRecord = await record(hidden.page,'P02');
  assert.equal(hiddenRecord.interrupted,true); assert(hiddenRecord.events.some(e=>e.reason==='tab_hidden'));
  assert.equal(await hidden.page.locator('#stimulus img').count(),0);
  result.checks.tab_hidden_event_injected_interrupt = true;
  await hidden.context.close();

  const refresh = await isolated(); await begin(refresh.page,'P03'); await refresh.page.waitForTimeout(200);
  const originalPngs = refresh.requests.filter(u=>u.endsWith('.png')).length;
  await refresh.page.reload(); await join(refresh.page,'P03');
  const refreshRecord = await record(refresh.page,'P03');
  assert.equal(refreshRecord.interrupted,true); assert.equal(refreshRecord.stage,'response');
  await refresh.page.locator('#consentForm').evaluate(form=>form.dispatchEvent(new Event('submit',{cancelable:true})));
  await refresh.page.waitForFunction(k=>JSON.parse(localStorage.getItem(k)).events.some(e=>e.type==='restart_denied'),key('P03'),{timeout:5000});
  const afterRestart = await record(refresh.page,'P03');
  assert(afterRestart.events.some(e=>e.type==='restart_denied'));
  assert.equal(afterRestart.events.filter(e=>e.type==='exposure_start').length,1);
  assert.equal(refresh.requests.filter(u=>u.endsWith('.png')).length,originalPngs);
  result.checks.refresh_during_exposure_and_restart_denied = true;
  await refresh.context.close();

  const prior = await isolated(); await begin(prior.page,'P04',true);
  await prior.page.locator('#response').waitFor({state:'visible',timeout:6500}); await answer(prior.page);
  const priorRecord = await record(prior.page,'P04'); assert.equal(priorRecord.prior_exposure,true);
  await prior.context.close(); result.checks.prior_exposure_self_report_preserved = true;

  const stop = await isolated(); await begin(stop.page,'P05'); await stop.page.locator('#stop').click();
  const stopped = await record(stop.page,'P05'); assert.equal(stopped.interrupted,true);
  assert(stopped.events.some(e=>e.reason==='participant_stop')); assert.equal(await stop.page.locator('#stimulus img').count(),0);
  await stop.context.close(); result.checks.participant_stop = true;

  // 원답 보존/QA 제외/중복/해시/ID/프로토콜/누락/노출/24h 검사는 OS 임시 폴더의 합성 데이터만 사용.
  const inputFile = path.join(temporary,'fixtures.json');
  fs.writeFileSync(inputFile,JSON.stringify({baseline:JSON.parse(fs.readFileSync(finalExport,'utf8')),prior:priorRecord,hidden:hiddenRecord,refresh:refreshRecord}));
  const script = String.raw`
import copy, importlib.util, json, pathlib, sys
spec=importlib.util.spec_from_file_location('observer_aggregate',sys.argv[1]); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
tmp=pathlib.Path(sys.argv[2]); protocol=pathlib.Path(sys.argv[3]); data=json.loads(pathlib.Path(sys.argv[4]).read_text(encoding='utf-8'))
qa=m.aggregate([tmp/'qa_first.json',tmp/'qa_complete.json'],protocol)
assert qa['counts']['qa_excluded']==2 and qa['counts']['eligible_new_first_exposure']==0
assert not qa['duplicate_ids']
assert '0명' in qa['sample_status']
empty=m.aggregate([],protocol); assert empty['counts']['eligible_new_first_exposure']==0
assert 'results' not in empty and 'rates' not in empty
base=data['baseline']; base['record_kind']='participant'
def audit(rec,name='synthetic.json'):
 p=tmp/name; p.write_text(json.dumps(rec,ensure_ascii=False),encoding='utf-8'); return m.aggregate([p],protocol)
report=audit(base); assert report['counts']['eligible_new_first_exposure']==1, report['files'][0]['issues']
assert report['counts']['eligible_24h_recall']==1, report['files'][0]['recall_issues']
assert report['files'][0]['record']['raw_answers']==base['raw_answers']
assert report['files'][0]['human_source_verification']=='unverified'
for field,value in [('protocol_id','wrong'),('image_sha256','0'*64),('participant_id','P99'),('arm','A' if base['arm']=='B' else 'B'),('exposure_ms',100),('raw_answers',{}),('consent',None),('screen',None),('prior_exposure',True),('interrupted',True)]:
 rec=copy.deepcopy(base); rec[field]=value; assert audit(rec)['counts']['eligible_new_first_exposure']==0, field
for field in ('prior','hidden','refresh'):
 rec=data[field]; rec['record_kind']='participant'; assert audit(rec)['counts']['eligible_new_first_exposure']==0, field
rec=copy.deepcopy(base); rec['recall_submitted_at']=base['exposure_ended_at']; report=audit(rec)
assert report['counts']['eligible_24h_recall']==0
p=tmp/'duplicate1.json'; q=tmp/'duplicate2.json'; text=json.dumps(base,ensure_ascii=False); p.write_text(text,encoding='utf-8'); q.write_text(text,encoding='utf-8')
report=m.aggregate([p,q],protocol); assert report['counts']['eligible_new_first_exposure']==0 and report['duplicate_ids']==['P01']
assert report['files'][0]['raw_text']==text
bad=tmp/'invalid.json'; bad.write_text('{broken',encoding='utf-8'); assert m.aggregate([bad],protocol)['counts']['eligible_new_first_exposure']==0
print(json.dumps({'qa_excluded':True,'zero_sample_no_results_or_rates':True,'raw_preserved':True,'validation_negative_cases':True,'duplicates_excluded':True,'external_human_verification_distinct':True}))
`;
  const py = spawnSync(process.env.QA_PYTHON || 'python',['-c',script,path.join(root,'응답_집계.py'),temporary,path.join(probeRoot,'protocol.js'),inputFile],{encoding:'utf8',env:{...process.env,PYTHONDONTWRITEBYTECODE:'1',PYTHONIOENCODING:'utf-8'}});
  assert.equal(py.status,0,py.stderr || py.stdout);
  result.checks.aggregation = JSON.parse(py.stdout);
  assert.equal(result.external_requests.length,0); assert.equal(result.errors.length,0);
  result.checks.offline_route_fulfill_only_no_network = true;
  result.status = 'PASS';
}
(async()=>{
  try {await run();}
  catch(error) {result.status='FAIL'; result.failure=String(error.stack||error); process.exitCode=1;}
  finally {if(browser) await browser.close(); fs.rmSync(temporary,{recursive:true,force:true}); console.log(JSON.stringify(result,null,2));}
})();
