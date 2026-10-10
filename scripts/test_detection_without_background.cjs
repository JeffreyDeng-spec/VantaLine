// Real workbench with isolated API/device fixtures; no inference or physical PLC I/O.
const assert = require('node:assert/strict');
const path = require('node:path');
const {spawn} = require('node:child_process');
const frontend = path.resolve(__dirname, '../local_inspection_service/frontend');
const {chromium} = require(path.join(frontend, 'node_modules/playwright'));
const base = 'http://127.0.0.1:5187';
const vite = spawn(process.execPath, [path.join(frontend, 'node_modules/vite/bin/vite.js'), '--host', '127.0.0.1', '--port', '5187', '--strictPort', '--base', '/'], {cwd: frontend, env: {...process.env, VITE_ROUTER_BASENAME: '/'}, stdio: 'pipe'});
let browser;
vite.stderr.on('data', b => {if(!String(b).includes('[console.')) process.stderr.write(b);});
(async () => {
  for(let i=0;i<150;i++) {
    if(vite.exitCode!==null) throw Error('Vite exited');
    try {if((await fetch(base)).ok) break;} catch {}
    await new Promise(r=>setTimeout(r,100));
  }
  browser = await chromium.launch({headless:true, ...(process.env.DETECTION_TEST_BROWSER ? {channel:process.env.DETECTION_TEST_BROWSER} : {}), args:['--use-fake-ui-for-media-stream','--use-fake-device-for-media-stream']});
  for(const background_set_id of ['', 'green_conveyor', 'existing-task-background']) {
    const context = await browser.newContext({viewport:{width:1440,height:1000},permissions:['camera']});
    const page = await context.newPage();
    const errors=[], forbidden=[], submissions=[];
    page.on('pageerror',e=>errors.push(e.message));
    page.on('console',m=>{if(m.type()==='error') errors.push(m.text());});
    const task={id:'fixture',name:'Background-free task',model_id:'ai_task_fixture',background_set_id,selected_accessory_ids:[],required_accessory_counts:{}};
    await context.route('**/api/**',async route=>{
      const req=route.request(),p=new URL(req.url()).pathname;
      if(!p.startsWith('/api/')) return route.continue();
      const reply=(json,status=200)=>route.fulfill({json,status});
      if(p==='/api/auth/status') return reply({authenticated:true,setup_required:false,user:{id:'operator',username:'operator',role:'user',permissions:['inspection','ai_detection']}});
      if(p==='/api/version') return reply({release:'fixture',git_commit:'fixture',consistent:true});
      if(p==='/api/status') return reply({service:'running',ai_detection_tasks:[task],available_models:[]});
      if(p==='/api/ai/tasks') return reply({tasks:[task]});
      if(p==='/api/training/resources') return reply({ai_detection_tasks:[task],models:[],datasets:[],tasks:[]});
      if(p.endsWith('/real-photo')) return reply({selected:false});
      if(p.endsWith('/environment-background') || p.endsWith('/auto-optimize')) {forbidden.push(p);return reply({detail:'Fixture background service unavailable'},404);}
      if(p==='/api/plc/workstation') return reply({paired:false,station:null,config:null});
      if(p==='/api/user/preferences/tasks') return reply({exists:true,pinned_task_ids:[],archived_task_ids:[]});
      if(p.startsWith('/api/analyze/')) {
        submissions.push({path:p,body:req.postDataBuffer().toString()});
        return reply({passed:true,counts:{},detections:[],summary:'Fixture inspection complete'});
      }
      return reply({items:[],tasks:[],models:[],ai_detection_tasks:[],enabled:false});
    });
    await page.goto(base+'/workspace/tasks/ai%3Afixture/inspect');
    try {await page.getByRole('button',{name:'开始 AI 检测',exact:true}).waitFor({timeout:10000});} catch(e) {console.error(page.url(),await page.locator('body').innerText());throw e;}
    // Allow model selection effects to settle; no missing-background check may run.
    await page.waitForFunction(()=>document.querySelector('select')?.options.length>0);
    await page.locator('input[type=file]').first().setInputFiles({name:'fixture.png',mimeType:'image/png',buffer:Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a9N8AAAAASUVORK5CYII=','base64')});
    const imageResponse=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/analyze/image');
    await page.getByRole('button',{name:'开始 AI 检测',exact:true}).click();await imageResponse;
    await page.getByRole('tab',{name:'视频',exact:true}).click();
    await page.locator('input[type=file]').first().setInputFiles({name:'fixture.mp4',mimeType:'video/mp4',buffer:Buffer.from('isolated video upload fixture')});
    const videoResponse=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/analyze/video');
    await page.getByRole('button',{name:'分析视频',exact:true}).click();await videoResponse;
    await page.getByRole('tab',{name:'摄像头',exact:true}).click();
    await page.getByRole('button',{name:'检测摄像头',exact:true}).click();
    await page.waitForFunction(()=>{const v=document.querySelector('video');return v?.videoWidth>0;});
    const cameraResponse=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/analyze/image');
    await page.getByRole('button',{name:'拍照 AI 检测',exact:true}).click();await cameraResponse;
    assert.equal(await page.getByRole('dialog',{name:'拍摄空场景背景'}).count(),0);
    assert.deepEqual(forbidden,[]);
    assert.deepEqual(submissions.map(x=>x.path),['/api/analyze/image','/api/analyze/video','/api/analyze/image']);
    for(const submission of submissions) {assert.match(submission.body,/ai_task_fixture/);assert.doesNotMatch(submission.body,/plc_session_id|camera_request_id/);}
    assert.deepEqual(errors,[]);
    await context.close();
    console.log('PASS image/video/camera without background gate:',background_set_id||'no saved background');
  }
})().catch(e=>{console.error(e);process.exitCode=1;}).finally(async()=>{await browser?.close();vite.kill('SIGTERM');});
