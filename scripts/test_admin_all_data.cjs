// Real API helpers and React routes, isolated synthetic records; no production or device I/O.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const vm = require('node:vm');
const { spawn } = require('node:child_process');
const frontend = path.resolve(__dirname, '../local_inspection_service/frontend');
const ts = require(path.join(frontend, 'node_modules/typescript'));
const { chromium } = require(path.join(frontend, 'node_modules/playwright'));
const output = fs.mkdtempSync(path.join(os.tmpdir(), 'vantaline-admin-all-data-'));
const requests = [];
function loadTS(relative, imports = {}) {
  const source = fs.readFileSync(path.join(frontend, relative), 'utf8');
  const code = ts.transpileModule(source, {compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText;
  const exports = {};
  vm.runInNewContext(code, { exports, require: name => { assert.ok(imports[name], name); return imports[name]; }, Headers, FormData, URLSearchParams,
    fetch: async (url, options) => { requests.push({url, method:options.method}); return new Response('{}', {status:200}); }
  });
  return exports;
}
const client = loadTS('src/api/client.ts', {'../features/version/files':{markVersionFilesUploaded(){}},'../features/version/runtime':{versionCoordinator:{beginOperation:()=>()=>{}}},'../features/version/drafts':{savedEditorsAcknowledgement:()=>()=>{}}});
const q = loadTS('src/api/queries.ts', {'./client':client});
const identities = [{id:'admin-a',role:'admin'},{id:'admin-b',role:'admin'},{id:'alice',role:'user'}];
async function checkQueries() {
  for (const user of identities) {
    // An obsolete caller cannot reintroduce a selected-user filter.
    const auth = {user, dataUserId:'bob'};
    await q.getServiceStatus(auth); await q.getConfigSummary(auth);
    await q.getAiTasks(auth); await q.getTrainingResources(auth);
    await q.getPipeline(auth); await q.getAccessories(auth);
    await q.getLocateAccessories(auth); await q.getLabelSheetReferences(auth);
    await q.getAiTaskAutoOptimize(auth,'task / one');
    await q.getIncomingTextInspections(auth,'task / one');
    await q.getDataAnalysisRecords(auth,{taskId:'task / one',limit:24});
    const urls = requests.splice(0).map(r => new URL(r.url,'http://fixture.invalid'));
    assert.equal(urls.length,11);
    assert.ok(urls.every(u => !u.searchParams.has('user_id')));
    assert.equal(urls.find(u=>u.pathname==='/api/data-analysis/records').searchParams.get('task_id'),'task / one');
    assert.equal(urls.find(u=>u.pathname==='/api/incoming-text/inspections').searchParams.get('task_id'),'task / one');
    assert.equal(urls.find(u=>u.pathname==='/api/data-analysis/records').searchParams.get('limit'),'24');
  }
  assert.notDeepEqual(q.queryKeys.pipeline('admin-a'),q.queryKeys.pipeline('alice'));
}
const port=process.env.ADMIN_TEST_PORT || '52736';
const base='http://127.0.0.1:'+port;
let vite, browser;
(async()=>{
  await checkQueries();
  vite=spawn(process.execPath,[path.join(frontend,'node_modules/vite/bin/vite.js'),'--host','127.0.0.1','--port',port,'--strictPort','--base','/'],{cwd:frontend,env:{...process.env,VITE_ROUTER_BASENAME:'/'},stdio:'pipe'});
  let startup=''; vite.stderr.on('data',b=>startup+=b); vite.stdout.on('data',b=>startup+=b);
  for(let i=0;i<600;i++) { if(vite.exitCode!==null)throw Error(startup); try {if((await fetch(base)).ok)break;}catch{} await new Promise(r=>setTimeout(r,100)); }
  assert.ok((await fetch(base)).ok, startup);
  browser=await chromium.launch({headless:true,channel:process.env.ADMIN_TEST_BROWSER || (fs.existsSync("/Applications/Google Chrome.app")?"chrome":undefined)});
  const context=await browser.newContext({viewport:{width:1440,height:1000}});
  const page=await context.newPage(); page.setDefaultTimeout(20000);
  const errors=[], reads=[], writes=[];
  page.on('console',m=>{if(m.type()==='error')console.error(m.text());});
  page.on('requestfailed',r=>console.error('Failed request '+r.url()+': '+r.failure()?.errorText));
  page.on('pageerror',e=>{errors.push(e.message);console.error(e.message);});
  let user={...identities[0],username:'admin-a',display_name:'Admin A',permissions:[]};
  const tasks=[{id:'alice-task',name:'Alice data',owner_user_id:'alice',task_kind:'accessory_detection',stage:'library',status:'completed'},
    {id:'bob-task',name:'Bob data',owner_user_id:'bob',task_kind:'accessory_detection',stage:'library',status:'completed'},
    {id:'legacy-task',name:'Historical data',task_kind:'accessory_detection',stage:'library',status:'completed'}];
  await context.addInitScript(()=>{
    window.__deviceCalls=0;
    if(navigator.mediaDevices)navigator.mediaDevices.getUserMedia=async()=>{window.__deviceCalls++;throw Error('Synthetic camera unavailable');};
  });
  await context.route('**/api/**',async route=>{
    const req=route.request(), url=new URL(req.url());
    if(!url.pathname.startsWith('/api/'))return route.continue();
    const reply=json=>route.fulfill({json});
    if(req.method()!=='GET') {writes.push(url.pathname);if(url.pathname==='/api/auth/logout'){user=null;return reply({status:'ok'});}throw Error('Unexpected mutation '+url.pathname);}
    reads.push({account:user?.id,url:url.href});
    if(url.pathname==='/api/auth/status')return reply({authenticated:!!user,setup_required:false,user,features:{},default_user_permissions:[],legacy_owner_id:'legacy_admin'});
    if(url.pathname==='/api/version')return reply({release:'v-fixture',git_commit:'fixture-commit',consistent:true});
    const visible=user?.role==='admin'?tasks:tasks.filter(t=>t.owner_user_id===user?.id);
    if(url.pathname==='/api/pipeline/tasks')return reply({items:visible});
    if(url.pathname==='/api/training/resources')return reply({datasets:[],models:[],ai_detection_tasks:[]});
    if(url.pathname==='/api/user/preferences/tasks')return reply({exists:true,pinned_task_ids:['pipeline:alice-task','pipeline:bob-task','pipeline:legacy-task'],archived_task_ids:[]});
    if(url.pathname==='/api/auth/users-data-summary')return reply({counts:{}});
    if(url.pathname==='/api/auth/users')return reply({users:[{id:'alice',username:'alice',role:'user',active:true,permissions:[]}],features:{}});
    if(url.pathname==='/api/admin/model-profiles')return reply({revision:1,bindings:{},profiles:[],purposes:[],providers:[]});
    if(url.pathname==='/api/status')return reply({service:'running',model_exists:false,available_models:[]});
    if(url.pathname==='/api/config/summary')return reply({confidence_threshold:0.5});
    if(url.pathname==='/api/incoming-text/inspections')return reply({items:[]});
    if(url.pathname==='/api/data-analysis/records')return reply({records:[],total:0});
    return reply({items:[],tasks:[],enabled:false,configured:false});
  });
  async function checkPage(route) {
    console.log('Checking '+route);
    await page.goto(base+route);
    try {await page.locator('.app-shell').waitFor();} catch(e) {await page.screenshot({path:path.join(output,'failure.png')});console.error(await page.locator('body').innerText());console.error('Screenshot: '+output);throw e;}
    assert.equal(await page.locator('.top-scope-bar,.normal-data-scope,.normal-scope-slot,[data-admin-scope-select]').count(),0,route);
    assert.equal(await page.getByText('数据范围',{exact:true}).count(),0,route);
  }
  for(const route of ['/workspace','/workspace/pipeline','/workspace/training-library','/workspace/accessories','/workspace/data-analysis','/workspace/users','/workspace/rules','/workspace/inspect'])await checkPage(route);
  await checkPage('/workspace/pipeline');
  await page.locator('.sidebar').hover();
  await page.getByText('Alice data',{exact:true}).first().waitFor();
  await page.getByText('Bob data',{exact:true}).first().waitFor();
  await page.getByText('Historical data',{exact:true}).first().waitFor();
  await page.screenshot({path:path.join(output,'admin-all-data-desktop.png')});
  await page.setViewportSize({width:390,height:844}); await checkPage('/workspace/pipeline');
  await page.screenshot({path:path.join(output,'admin-all-data-mobile.png')});
  user={...identities[1],username:'admin-b',display_name:'Admin B',permissions:[]};
  await page.setViewportSize({width:1440,height:1000});await checkPage('/workspace/pipeline');
  await page.locator('.sidebar').hover();
  await page.getByText('Historical data',{exact:true}).first().waitFor();
  // Refocus triggers actual AuthGate identity-change invalidation without reload.
  user={...identities[2],username:'alice',display_name:'Alice',permissions:['inspection','training_pipeline']};
  await page.evaluate(()=>{
    Object.defineProperty(document,'visibilityState',{configurable:true,value:'hidden'});
    window.dispatchEvent(new Event('visibilitychange'));
    Object.defineProperty(document,'visibilityState',{configurable:true,value:'visible'});
    window.dispatchEvent(new Event('visibilitychange'));
  });
  await page.locator('.account-card').getByText('Alice',{exact:true}).waitFor({state:'attached'});
  await page.locator('.sidebar').hover();
  await page.getByText('Alice data',{exact:true}).first().waitFor();
  assert.equal(await page.getByText('Bob data',{exact:true}).count(),0);
  assert.equal(await page.getByText('Historical data',{exact:true}).count(),0);
  assert.ok(reads.every(r=>!new URL(r.url).searchParams.has('user_id')));
  assert.equal(writes.length,0);
  assert.deepEqual(errors,[]);
  await page.setContent(fs.readFileSync(path.join(frontend,'../static/index.html'),'utf8').replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi,''));
  assert.equal(await page.locator('[data-admin-scope-select],[data-admin-scope-wrap]').count(),0);
  assert.equal(await page.getByText('数据范围',{exact:true}).count(),0);
  console.log('PASS: real API queries, 8 desktop routes, mobile, two admins, live identity invalidation and user isolation.');
  console.log('Screenshots: '+output);
})().catch(e=>{console.error(e);process.exitCode=1;}).finally(async()=>{await browser?.close();vite?.kill('SIGTERM');});
