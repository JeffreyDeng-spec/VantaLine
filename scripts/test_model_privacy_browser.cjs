// Production frontend + actual Python security/presentation middleware. Synthetic
// identity and records only; no paid calls, customer media, camera or serial I/O.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {spawn} = require('node:child_process');
const root = path.resolve(__dirname,'..');
const frontend = path.join(root,'local_inspection_service/frontend');
const dist = path.join(frontend,'dist-production');
const {chromium} = require(path.join(frontend,'node_modules/playwright'));
const base='http://127.0.0.1:5196';
const python=process.env.MODEL_PRIVACY_PYTHON || 'python';
const child=spawn(python,['scripts/smoke_model_privacy.py','--serve'],{cwd:root,stdio:['ignore','pipe','pipe']});
let serverOutput='';
child.stdout.on('data',data=>serverOutput+=data);
child.stderr.on('data',data=>serverOutput+=data);
let browser, activePage, releasePending = () => {};
async function ready(){
  for(let i=0;i<80;i++){
    if(child.exitCode!==null)throw Error(serverOutput);
    try {if((await fetch(base+'/api/auth/status')).ok)return;} catch {}
    await new Promise(resolve=>setTimeout(resolve,100));
  }
  throw Error('Local privacy fixture did not start: '+serverOutput);
}
async function role(context,value){
  await context.clearCookies();
  if(value)await context.addCookies([{name:'role',value,url:base}]);
}
(async()=>{
  await ready();
  browser=await chromium.launch({headless:true,channel:process.env.MODEL_PRIVACY_BROWSER || 'chrome'});
  const context=await browser.newContext({viewport:{width:1440,height:1000}});
  const page=await context.newPage();
  activePage=page;
  page.setDefaultTimeout(10000);
  const errors=[],requests=[];
  page.on('pageerror',error=>errors.push(error.message));
  page.on('request',request=>requests.push(new URL(request.url()).pathname));
  const files=fs.readdirSync(path.join(dist,'assets'));
  const privateFile=files.find(name=>/^admin-.*\.js$/.test(name));
  assert.ok(privateFile,'Expected protected administrator module');
  const privateStyle=files.find(name=>/^admin-.*\.css$/.test(name));
  assert.ok(privateStyle,'Expected protected administrator stylesheet');
  const privateAssets=files.filter(name=>/^admin-.*\.(?:js|css)$/.test(name));
  assert.ok(privateAssets.filter(name=>name.endsWith('.js')).length>=2,'Settings and configuration tools must be protected modules');
  const identities=/yolo|gemini|doubao|豆包|qwen|千问|codex|sam[-_ ]?\d|ultralytics|paddleocr|runpod|openai|anthropic|claude|gpt[-_ ]?(?:\d|image)|seedream|seededit|seedance|dall[-_ ]?e|imagen(?:[-_ ]?\d|\b)/i;
  for(const name of files.filter(name=>/\.(?:js|css|json|map)$/.test(name)&&!name.startsWith('admin-'))){
    const response=await context.request.get(base+'/static/assets/'+name);
    assert.equal(response.status(),200,name);
    assert.equal(identities.test(await response.text()),false,name);
  }
  for(const currentRole of [undefined,'member','delegated']){
    await role(context,currentRole);
    for(const name of privateAssets)assert.equal((await context.request.get(base+'/static/assets/'+name)).status(),404,name);
    assert.equal((await context.request.get(base+'/static/assets/'+privateFile)).status(),404);
    assert.equal((await context.request.get(base+'/static/assets/'+privateStyle)).status(),404);
    assert.equal((await context.request.get(base+'/static/assets/'+privateFile+'/')).status(),404);
    assert.equal((await context.request.get(base+'/static/assets/'+privateFile+'/%2e')).status(),404);
    assert.equal((await context.request.get(base+'/static/app.js')).status(),404);
    assert.equal((await context.request.get(base+'/static/styles.css')).status(),404);
    assert.equal((await context.request.get(base+'/static/index.html')).status(),404);
    assert.equal((await context.request.get(base+'/api/admin/model-profiles')).status(),currentRole?403:401);
  }
  await role(context,undefined);
  await page.goto(base+'/');
  assert.equal(identities.test(await page.locator('body').innerText()),false);
  await role(context,'member');
  requests.length=0;
  await page.goto(base+'/workspace/rules');
  await page.getByRole('heading',{name:'个人与设备',exact:true}).waitFor();
  assert.equal(await page.getByText('模型与 API',{exact:true}).count(),0);
  assert.equal(requests.some(value=>value.startsWith('/api/admin/')),false);
  assert.equal(requests.some(value=>value.includes('/admin-')),false);
  assert.equal(await page.getByRole('heading',{name:'本机 PLC 结果同步',exact:true}).count(),0);
  // The workbench consumes opaque references and neutral mode values.
  await page.goto(base+'/workspace/tasks/pipeline%3Apipeline-one/inspect');
  await page.getByRole('heading',{name:'Privacy sample',exact:true}).waitFor();
  assert.ok((await page.locator('.task-bound-model-field select').inputValue()).startsWith('ref1_'));
  const members=await context.request.get(base+'/api/status');
  const data=await members.json();
  assert.ok(data.active_model_id.startsWith('ref1_'));
  assert.equal(data.available_models[0].variant,'vision');
  const pipeline=await (await context.request.get(base+'/api/pipeline/tasks')).json();
  assert.deepEqual(pipeline.items[0].accessory_counts,{'part-A':2});
  assert.equal(identities.test(await page.locator('body').innerText()),false);
  await role(context,'delegated');
  requests.length=0;
  await page.goto(base+'/workspace/rules');
  await page.getByRole('heading',{name:'本机 PLC 结果同步',exact:true}).waitFor();
  assert.equal(await page.getByText('模型与 API',{exact:true}).count(),0);
  assert.equal(requests.some(value=>value.startsWith('/api/admin/')),false);
  assert.equal(requests.some(value=>value.includes('/admin-')),false);
  assert.equal(identities.test(await page.locator('body').innerText()),false);
  await role(context,'admin');
  await page.goto(base+'/workspace/rules');
  await page.locator('#model-pipeline').waitFor();
  assert.match(await page.locator('#model-pipeline').textContent(), /Gemini production.*gemini-3/);
  assert.equal((await context.request.get(base+'/static/assets/'+privateFile)).status(),200);
  assert.equal((await context.request.get(base+'/static/assets/'+privateStyle)).status(),200);
  for(const name of privateAssets)assert.equal((await context.request.get(base+'/static/assets/'+name)).status(),200,name);
  let captured;
  const capturedResponse = new Promise(resolve=>captured=resolve);
  const releaseResponse = new Promise(resolve=>releasePending=resolve);
  await page.route('**/api/admin/model-profiles',async route=>{
    const response=await route.fetch();
    captured();
    await releaseResponse;
    try { await route.fulfill({response}); } catch (error) {
      if(!/cancel|closed|disposed/i.test(String(error)))throw error;
    }
  });
  await page.reload();
  await capturedResponse;
  // Same account ID, changed role, no document reload. The auth refetch fences
  // old page state and clears private query caches before mounting member UI.
  await role(context,'downgraded');
  await page.evaluate(()=>window.dispatchEvent(new Event('visibilitychange')));
  await page.getByRole('heading',{name:'个人与设备',exact:true}).waitFor();
  releasePending();
  await page.waitForTimeout(300);
  assert.equal(await page.getByText('Gemini production',{exact:true}).count(),0);
  assert.equal((await context.request.get(base+'/static/assets/'+privateFile)).status(),404);
  assert.deepEqual(errors,[]);
  console.log('Model privacy browser: public assets, four identities, member settings/workbench, admin module and same-account role downgrade passed');
})().catch(async error=>{console.error(error);if(activePage){console.error((await activePage.locator('body').innerText()).slice(0,4000));await activePage.screenshot({path:'/private/tmp/vantaline-model-privacy-failure.png',fullPage:true});}process.exitCode=1;}).finally(async()=>{releasePending();await browser?.close();child.kill('SIGTERM');});
