// Actual React task page, isolated HTTP fixtures, no paid work or customer images.
const assert = require('node:assert/strict');
const path = require('node:path');
const {spawn} = require('node:child_process');
const frontend=path.resolve(__dirname,'../local_inspection_service/frontend');
const {chromium}=require(path.join(frontend,'node_modules/playwright'));
const base='http://127.0.0.1:5188';
const vite=spawn(process.execPath,[path.join(frontend,'node_modules/vite/bin/vite.js'),'--host','127.0.0.1','--port','5188','--strictPort','--base','/'],{cwd:frontend,env:{...process.env,VITE_ROUTER_BASENAME:'/'},stdio:'pipe'});
let browser;
vite.stderr.on("data",b=>{if(!String(b).includes("[console."))process.stderr.write(b);});
(async()=>{
  for(let i=0;i<150;i++){try{if((await fetch(base)).ok)break;}catch{} await new Promise(r=>setTimeout(r,100));}
  browser=await chromium.launch({headless:true,...(process.env.PHOTO_TEST_BROWSER ? {channel:process.env.PHOTO_TEST_BROWSER}:{})});
  for(const mode of ['running','paused','blocked','completed','unselected','legacy','loading','error']){
    const context=await browser.newContext({viewport:{width:1366,height:900}}), page=await context.newPage();
    const writes=[],errors=[],queries=[];
    page.on('pageerror',e=>errors.push(e.message));
    page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
    page.on('requestfailed',r=>console.error('request failed',r.url(),r.failure()));
    let enabled=!['paused','unselected','legacy'].includes(mode);
    let selected=!['unselected','legacy'].includes(mode);
    const state=()=>({available:mode!=='legacy',selected,enabled,candidate_count:105,approved_count:35,positive_count:34,negative_count:1,agent_filtered_count:70,excluded_count:70,pending_annotation_count:0,pending_review_count:0,failed_annotation_count:0,
      ...(mode==='blocked'?{pause_reason:'fixture blocked'}:{}),jobs:[],samples:[],datasets:[{id:'frozen-set',real_source_count:20,snapshot_fingerprint:'frozen'}],
      candidate_models:mode==='completed'?[{model_id:'candidate-model',status:'completed',real_source_count:20,positive_image_count:19,negative_image_count:1,split_image_counts:{train:16,val:2,test:2},unsupported_by_real_data:[]}]:[]});
    await context.route('**/api/**',async route=>{
      const req=route.request(),url=new URL(req.url()),p=url.pathname;
      if(!p.startsWith('/api/'))return route.continue();
      const reply=(json,status=200)=>route.fulfill({json,status});
      if(req.method()!=='GET')writes.push({p,body:req.postData()});
      if(p==='/api/auth/status')return reply({authenticated:true,setup_required:false,user:{id:'operator',username:'operator',role:'admin',permissions:['inspection','ai_detection','training']}});
      if(p==='/api/user/preferences/tasks')return reply({exists:true,pinned_task_ids:[],archived_task_ids:[]});
      if(p==='/api/version')return reply({consistent:true});
      const task={id:'fixture',name:'Isolated task',selected_accessory_ids:[],created_at:1};
      if(p==='/api/training/resources')return reply({ai_detection_tasks:[task],models:[],datasets:[],tasks:[]});
      if(p.endsWith('/real-photo')){
        if(mode==='loading'){await new Promise(r=>setTimeout(r,1500));}
        if(mode==='error')return reply({detail:'isolated failure'},503);
        if(req.method()==='PATCH'){enabled=JSON.parse(req.postData()).enabled;if(enabled)selected=true;}
        return reply(state());
      }
      if(p.endsWith('/real-photo/samples')){
        queries.push(url.search);
        const second=url.searchParams.has('cursor'), filtered=url.searchParams.get('category')==='agent_filtered', detail=url.searchParams.get('sample_id');
        const sample={sample_id:detail|| (second?'old-0':filtered?'excluded-104':'sample-104'),current_status:filtered?'exclude':'pending_review',geometry:{width:80,height:60},annotation:{status:'completed',version:1,objects:[]},review:filtered?{decision:'exclude',reason:'Agent fixture exclusion'}:null};
        return reply({samples:[sample],total:filtered?70:105,next_cursor:second||detail?null:'second-page'});
      }
      if(p.endsWith('/versions'))return reply({annotations:[],reviews:[],source_groups:[],masks:[]});
      if(p.endsWith('/image'))return route.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="80" height="60"/>'});
      return reply({items:[],tasks:[],models:[],records:[],enabled:false,samples:[]});
    });
    await page.goto(base+'/workspace/tasks/ai%3Afixture');
    try {await page.getByRole('heading',{name:'任务过程数据'}).waitFor({timeout:10000});} catch(e) {console.error(mode,page.url(),await page.locator("body").innerText(),errors);throw e;}
    if(mode==='loading'||mode==='error'){
      assert.equal(await page.getByRole('button',{name:/需要人工处理|合成训练图|正式训练集/}).count(),0);
      if(mode==='error'){await page.getByText('回流状态加载失败').waitFor({timeout:20000});await context.close();console.log('PASS',mode);continue;}
    }
    if(mode==='legacy'||mode==='unselected'){
      await page.getByRole('button',{name:/需要人工处理/}).waitFor();
      assert.equal(await page.locator('.task-drawer-entry').count(),4);
      for(const title of ['采集样本与自动标注','需要人工处理','合成训练图','正式训练集']){
        await page.getByRole('button',{name:new RegExp(title)}).click();
        await page.getByRole('dialog',{name:title}).waitFor();await page.keyboard.press('Escape');
        assert.equal(await page.getByRole('dialog').count(),0);
      }
      if(mode==='unselected'){
        await page.getByRole('button',{name:'启用实拍回流',exact:true}).click();
        await page.getByRole('button',{name:/Agent 筛选结果/}).waitFor();
        assert.equal(await page.locator('.task-drawer-entry').count(),3);
      }
    }else{
      await page.getByRole('button',{name:/Agent 筛选结果.*70/}).waitFor();
      assert.equal(await page.locator('.task-drawer-entry').count(),3);
      assert.equal(await page.locator('svg[aria-label="实拍原图与当前 bbox"]').count(),0);
      await page.getByRole('button',{name:/采集样本与自动标注/}).click();
      await page.getByRole('button',{name:'下一页'}).waitFor();
      await page.getByRole('button',{name:'下一页'}).click();await page.getByText('old-0',{exact:true}).waitFor();
      await page.getByRole('button',{name:'查看样本详情'}).click();
      await page.getByRole('heading',{name:/old-0/}).waitFor();
      assert.equal(await page.getByText('高级操作',{exact:true}).evaluate(e=>e.parentElement.open),false);
      await page.getByRole('button',{name:'关闭',exact:true}).click();
      await page.getByRole('button',{name:/Agent 筛选结果.*70/}).click();await page.getByText('Agent fixture exclusion',{exact:true}).waitFor();
      await Promise.all([page.waitForResponse(r=>r.url().includes('decision=uncertain')),page.getByLabel('筛选结论').selectOption('uncertain')]);
      await page.getByRole('button',{name:'关闭',exact:true}).click();
      await page.getByRole('button',{name:/实拍训练集.*35/}).click();await page.getByText('frozen-set',{exact:false}).waitFor();
      if(mode==='completed')await page.getByText('candidate-model',{exact:false}).first().waitFor();
      await page.getByRole('button',{name:'关闭',exact:true}).click();
      if(mode==='running'){
        await page.getByRole('button',{name:'暂停实拍回流',exact:true}).click();await page.getByRole('button',{name:'启用实拍回流',exact:true}).waitFor();
        assert.equal(await page.locator('.task-drawer-entry').count(),3);
      }
      assert.ok(queries.some(q=>q.includes('cursor=second-page')));
    }
    assert.equal(writes.length,['running','unselected'].includes(mode)?1:0);assert.deepEqual(errors,[]);
    await page.screenshot({path:`/private/tmp/real-photo-process-${mode}.png`,fullPage:true});
    await page.setViewportSize({width:390,height:844});
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1));
    await context.close();console.log('PASS',mode);
  }
})().catch(e=>{console.error(e);process.exitCode=1;}).finally(async()=>{await browser?.close();vite.kill('SIGTERM');});
