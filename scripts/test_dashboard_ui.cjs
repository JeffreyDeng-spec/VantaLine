// Real production bundle with isolated, in-memory API fixtures. No real API/device I/O.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const http = require('node:http');
const frontend = path.resolve(__dirname, '../local_inspection_service/frontend');
const dist = path.join(frontend, 'dist-production');
const port = Number(process.env.DASHBOARD_TEST_PORT || 5187);
const base = 'http://127.0.0.1:'+port;
const output = process.env.DASHBOARD_UI_OUTPUT || fs.mkdtempSync(path.join(os.tmpdir(), 'vantaline-dashboard-'));
fs.mkdirSync(output, { recursive: true });
let user = { id: 'overview-fixture', username: 'overview-fixture', role: 'admin', permissions: [] };
let statusFails = false, configFails = false, delay = 0, statusCalls = 0, configCalls = 0;
let status = { service: 'running', model_exists: true, active_model_id: 'yolo26_2class_ocr', available_models: Array.from({length:100},(_,i)=>({id:'fixture-'+i})), specialized_models: [{id:'fixture-special'}], rule: { confidence_threshold: 0.25 } };
let config = { confidence_threshold: 0.25 };
const writes = [], requests = [];
const json = (res, value, code=200) => { res.writeHead(code, {'Content-Type':'application/json'}); res.end(JSON.stringify(value)); };
const server = http.createServer(async (req,res) => {
  const url = new URL(req.url,base), pathname = url.pathname;
  if (pathname.startsWith('/api/')) {
    requests.push(pathname);
    if(req.method !== 'GET') { writes.push(pathname); return json(res,{detail:'Fixture rejects writes'},405); }
    if(pathname === '/api/auth/status') return json(res,{authenticated:true,setup_required:false,user});
    if(pathname === '/api/version') return json(res,{release:'development',git_commit:'unknown',consistent:true});
    if(pathname === '/api/status') { statusCalls++; if(delay) await new Promise(r=>setTimeout(r,delay)); return json(res,statusFails?{detail:'PRIVATE_SERVER_DETAIL_DO_NOT_DISPLAY'}:status,statusFails?503:200); }
    if(pathname === '/api/config/summary') { configCalls++; if(delay) await new Promise(r=>setTimeout(r,delay)); return json(res,configFails?{detail:'PRIVATE_CONFIG_DETAIL_DO_NOT_DISPLAY'}:config,configFails?503:200); }
    if(pathname === '/api/user/preferences/tasks') return json(res,{exists:true,pinned_task_ids:[],archived_task_ids:[]});
    if(pathname === '/api/training/resources') return json(res,{ai_detection_tasks:[],models:[],datasets:[],tasks:[]});
    if(pathname === '/api/auth/users') return json(res,{items:[]});
    if(pathname === '/api/label-inspection/tasks') return json(res,{items:[],next_cursor:null});
    if(pathname.endsWith('/extraction-capabilities')) return json(res,{enabled:false,ai_available:false});
    return json(res,{items:[],enabled:false,configured:false});
  }
  if(pathname === '/favicon.ico') {res.writeHead(204);return res.end();}
  let file;
  if(pathname === '/static/brand-logo.png') file=path.join(frontend,'../static/brand-logo.png');
  else if(pathname.startsWith('/static/')) file=path.resolve(dist, pathname.slice('/static/'.length));
  else file=path.join(dist,'index.html');
  if(!file.startsWith(dist+path.sep) && file!==path.join(frontend,'../static/brand-logo.png')) {res.writeHead(404);return res.end();}
  try {const ext=path.extname(file),type={'.html':'text/html','.js':'text/javascript','.css':'text/css','.webp':'image/webp','.png':'image/png','.svg':'image/svg+xml'}[ext]||'application/octet-stream';const body=fs.readFileSync(file);res.writeHead(200,{'Content-Type':type});res.end(body);} catch {res.writeHead(404);res.end();}
});
let browser;
(async()=>{
  await new Promise((resolve,reject)=>{server.once('error',reject);server.listen(port,'127.0.0.1',resolve);});
  console.log('Dashboard fixture: '+base+'/workspace');
  if(process.env.DASHBOARD_PREVIEW_ONLY==='1') return;
  const {chromium}=require(path.join(frontend,'node_modules/playwright'));
  browser=await chromium.launch({headless:true,...(process.env.DASHBOARD_TEST_BROWSER?{channel:process.env.DASHBOARD_TEST_BROWSER}:{})});
  const context=await browser.newContext({viewport:{width:1600,height:1000},reducedMotion:'reduce'});
  const page=await context.newPage();page.setDefaultTimeout(15000);
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await context.addInitScript(()=>{window.__deviceCalls=0;if(navigator.mediaDevices) navigator.mediaDevices.getUserMedia=async()=>{window.__deviceCalls++;throw Error('Unexpected camera access');};if(navigator.serial)navigator.serial.requestPort=async()=>{window.__deviceCalls++;throw Error('Unexpected serial access');};});
  const home=()=>page.goto(base+'/workspace');
  const overview=page.locator('.overview-page');
  const primary=page.locator('.overview-primary');
  const resource=page.locator('.overview-resource-links');
  const tools=page.getByRole('navigation',{name:'更多工具',exact:true});
  await home();await overview.getByText('yolo26_2class_ocr',{exact:true}).waitFor();
  assert.equal(await primary.getByRole('link').count(),2);
  assert.equal(await primary.getByRole('link',{name:'检测中心',exact:true}).getAttribute('href'),'/workspace/inspect');
  assert.equal(await primary.getByRole('link',{name:'文字检验',exact:true}).getAttribute('href'),'/workspace/label-inspection');
  const expectedResources=[['任务库','/workspace/training-library?tab=tasks'],['配件库','/workspace/accessories'],['样本与数据集','/workspace/training-library?tab=datasets'],['模型库','/workspace/training-library?tab=models']];
  for(const [name,href] of expectedResources) assert.equal(await resource.getByRole('link',{name,exact:true}).getAttribute('href'),href);
  assert.equal(await primary.locator('a a,a button,[tabindex]').count(),0);
  await page.waitForFunction(()=>[...document.querySelectorAll('.overview-launch img')].every(i=>i.complete&&i.naturalWidth>0));
  assert.ok(await primary.locator('img').evaluateAll(images=>images.every(i=>i.complete&&i.naturalWidth>0)));
  await page.screenshot({path:path.join(output,'overview-desktop.png'),fullPage:true});
  await overview.getByRole('button',{name:'更多工具',exact:true}).click();
  const expectedTools=[['标签检查 Beta','/workspace/label-check'],['AI 检测','/workspace/ai-inspect'],['数据分析','/workspace/data-analysis'],['任务流水线','/workspace/pipeline'],['设置','/workspace/rules'],['用户管理','/workspace/users'],['关于与帮助','/workspace/about']];
  assert.equal(await tools.getByRole('link').count(),7);
  for(const [name,href] of expectedTools)assert.equal(await tools.getByRole('link',{name,exact:true}).getAttribute('href'),href);
  await page.keyboard.press('End');assert.equal(await page.evaluate(()=>document.activeElement.textContent),'关于与帮助');
  await page.keyboard.press('Escape');assert.equal(await tools.count(),0);assert.equal(await overview.getByRole('button',{name:'更多工具'}).evaluate(e=>e===document.activeElement),true);
  await overview.getByRole('button',{name:'更多工具'}).click();await overview.getByRole('heading',{name:'总览',exact:true}).click();assert.equal(await tools.count(),0);
  delay=500;const before=[statusCalls,configCalls];await overview.getByRole('button',{name:'刷新',exact:true}).click();
  assert.equal(await overview.getByRole('button',{name:'刷新中',exact:true}).isDisabled(),true);
  await overview.getByRole('button',{name:'刷新',exact:true}).waitFor();
  assert.equal(statusCalls,before[0]+1);assert.equal(configCalls,before[1]+1);await page.getByText('状态已更新',{exact:true}).waitFor();delay=0;
  // Failure after a healthy response must not retain a green cached state.
  statusFails=true;await overview.getByRole('button',{name:'刷新',exact:true}).click();await overview.getByText(/检测服务状态暂不可用/).waitFor();
  assert.equal(await overview.locator('.is-running').count(),0);assert.equal(await primary.getByRole('link').count(),2);
  assert.equal(await overview.getByText('PRIVATE_SERVER_DETAIL_DO_NOT_DISPLAY').count(),0);
  assert.equal(await overview.locator('.overview-model').innerText(),'—');
  statusFails=false;configFails=true;await overview.getByRole('button',{name:'刷新',exact:true}).click();await overview.getByText(/配置摘要暂不可用/).waitFor();
  assert.equal(await overview.locator('.overview-status-item').last().locator('strong').innerText(),'0.25');
  configFails=false;status={service:'running',model_exists:false,available_models:[],specialized_models:[],rule:{confidence_threshold:0.4}};config={confidence_threshold:0};
  await overview.getByRole('button',{name:'刷新',exact:true}).click();await overview.getByText('模型缺失',{exact:true}).waitFor();
  assert.equal(await overview.locator('.overview-status-item').nth(2).locator('strong').innerText(),'0');
  assert.equal(await overview.locator('.overview-status-item').last().locator('strong').innerText(),'0');
  status={service:'unknown',model_exists:true};config={};await overview.getByRole('button',{name:'刷新',exact:true}).click();await overview.getByText('未知',{exact:true}).waitFor();
  assert.deepEqual(await overview.locator('.overview-status-item strong').allTextContents(),['未知','—','—','—']);
  // Independent queries can load/fail while the task entries stay immediately available.
  delay=800;await home();await primary.getByRole('link',{name:'文字检验',exact:true}).waitFor();assert.equal(await primary.getByRole('link').count(),2);
  await overview.getByRole('button',{name:'刷新',exact:true}).waitFor();delay=0;
  status={service:'running',model_exists:true,active_model_id:'long_model_'.repeat(45),available_models:[],specialized_models:[]};config={confidence_threshold:0.25};
  await home();await overview.getByText(status.active_model_id,{exact:true}).waitFor();
  for(const width of [1600,1440,1024,768,390]){
    await page.setViewportSize({width,height:1000});
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'overflow at '+width);
    await overview.getByRole('button',{name:'更多工具'}).click();
    await page.waitForFunction(()=>{const r=document.querySelector('.overview-tools-panel').getBoundingClientRect();return r.x>=0&&r.right<=innerWidth+1&&r.y>=0&&r.bottom<=innerHeight+1;});
    const box=await page.locator('.overview-tools-panel').boundingBox();assert.ok(box.x>=0&&box.x+box.width<=width+1&&box.y>=0&&box.y+box.height<=1001,'menu bounds at '+width+' '+JSON.stringify(box));
    await page.keyboard.press('Escape');
    await page.screenshot({path:path.join(output,'overview-'+width+'.png'),fullPage:true});
  }
  // No admin-only links leak into any placement for an ordinary text operator.
  user={...user,role:'user',permissions:['inspection']};await home();await primary.getByRole('link',{name:'文字检验',exact:true}).waitFor();
  assert.equal(await primary.getByRole('link').count(),1);assert.equal(await primary.getByRole('link',{name:'检测中心',exact:true}).count(),0);assert.equal(await resource.getByRole('link').count(),0);
  await overview.getByRole('button',{name:'更多工具'}).click();assert.equal(await tools.getByRole('link',{name:'用户管理',exact:true}).count(),0);assert.equal(await tools.getByRole('link',{name:'AI 检测',exact:true}).count(),0);await page.keyboard.press('Escape');
  await primary.getByRole('link',{name:'文字检验',exact:true}).click();await page.waitForURL(base+'/workspace/label-inspection');
  await home();user={...user,permissions:[]};await home();await overview.getByText(/当前账号暂无检测入口权限/).waitFor();assert.equal(await overview.locator('.overview-launch').count(),0);
  assert.equal(await page.evaluate(()=>window.__deviceCalls),0);assert.deepEqual(writes,[]);assert.deepEqual(errors,[]);
  assert.equal(requests.some(p=>/dispatch|attempt|warmup|\/compare$|\/extract$|\/runs$/.test(p)),false);
  fs.writeFileSync(path.join(output,'results.json'),JSON.stringify({passed:true,widths:[1600,1440,1024,768,390],permissions:['admin','text-operator','no-inspection'],writes,errors,apiRequests:requests.length},null,2));
  console.log('dashboard UI: passed; artifacts '+output);
})().catch(e=>{console.error(e);process.exitCode=1;}).finally(async()=>{if(process.env.DASHBOARD_PREVIEW_ONLY!=='1'){if(browser)await browser.close();server.close();}});
