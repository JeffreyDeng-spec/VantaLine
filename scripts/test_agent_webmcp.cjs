// Native browser WebMCP integration. All API/media traffic uses test fixtures.
// This verifies browser discovery/execution, not external LLM or physical PLC acceptance.
const assert = require('node:assert/strict');
const {waitForNativeTools} = require('./agent_browser_wait.cjs');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const base = process.env.AGENT_UI_BASE || 'http://127.0.0.1:5173';
(async()=>{
  const browser = await chromium.launch({headless:true,...(process.env.AGENT_CHROME_PATH?{executablePath:process.env.AGENT_CHROME_PATH}:{}),args:['--enable-blink-features=WebMCP,WebMCPTesting']});
  try {
    const page=await browser.newPage();const timeline=[];page.on('framenavigated',frame=>{if(frame===page.mainFrame())timeline.push({event:'navigation',url:frame.url(),time:Date.now()});});page.on('request',request=>{if(request.url().includes('/api/'))timeline.push({event:'api',url:request.url(),time:Date.now()});});const errors=[];page.on('pageerror',error=>errors.push(error.message));let authenticated=true;
    if(process.env.AGENT_TRACE_REGISTRATION) await page.addInitScript(() => {
      window.agentRegistrationTrace=[];
      const context=document.modelContext;if(!context)return;
      const original=context.registerTool.bind(context);
      context.registerTool=(tool,options)=>{window.agentRegistrationTrace.push(['register',tool.name,performance.now()]);options?.signal?.addEventListener('abort',()=>window.agentRegistrationTrace.push(['abort',tool.name,performance.now()]));return original(tool,options);};
    });
    const user={id:'agent-fixture',username:'fixture',display_name:'Fixture',role:'user',permissions:['inspection'],active:true};
    const standard={id:'standard-fixture',name:'Fixture standard',material_code:'FIXTURE',version_label:'V1',standard_type:'label',status:'confirmed',revision_number:1,asset_count:1};
    const asset={id:'asset-fixture',standard_id:standard.id,asset_kind:'label_candidate',ordinal:1,status:'candidate',category:'label_design',content_url:'/fixture-image.svg'};
    await page.route('**/*',route=>{
      const url=new URL(route.request().url());
      if(url.origin!==new URL(base).origin)return route.abort();
      if(url.pathname==='/fixture-image.svg')return route.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="400" height="200"><text y="100">Fixture</text></svg>'});
      if(!url.pathname.startsWith('/api/'))return route.continue();
      if(url.pathname==='/api/auth/logout'){authenticated=false;return route.fulfill({json:{status:'ok'}});}
      const responses={
        '/api/auth/status':{authenticated,setup_required:false,user:authenticated?user:null,features:{inspection:'Inspection'},default_user_permissions:['inspection']},
        '/api/agent/capabilities':{enabled:true},
        '/api/user/preferences/tasks':{pinned_task_ids:[],archived_task_ids:[],exists:true},
        '/api/pipeline/tasks':{items:[],accessories:[]},
        '/api/text-inspection/standards':{items:[standard]},
        '/api/text-inspection/standards/standard-fixture':{...standard,assets:[asset]},
        '/api/text-inspection/extraction-capabilities':{enabled:false,ai_available:false},
      };
      if(Object.hasOwn(responses,url.pathname))return route.fulfill({json:responses[url.pathname]});
      return route.fulfill({status:404,json:{detail:'No fixture for this endpoint'}});
    });
    await page.goto(base+'/text-compare-beta');
    await waitForNativeTools(page, {ready:true, present:['vantaline_get_context','vantaline_text_select_standard']});
    async function execute(name,input={}){
      try { return await page.evaluate(async({name,input})=>{
        const tool=(await document.modelContext.getTools()).find(item=>item.name==='vantaline_'+name);
        if(!tool){
          throw Error(JSON.stringify({missing:name,url:location.href,native:(await document.modelContext.getTools()).map(item=>item.name),trace:window.agentRegistrationTrace,registration_status:document.querySelector('[aria-label="Agent 工具状态"]')?.textContent}));
        }
        return JSON.parse(await document.modelContext.executeTool(tool,JSON.stringify(input)));
      },{name,input}); } catch(error) { console.error(JSON.stringify({timeline})); throw error; }
    }
    const context=await execute('get_context');
    assert.equal(context.data.account_id,user.id);
    const menu=await execute('list_capabilities',{limit:5});assert.equal(menu.data.actions.length,5);assert.ok(menu.data.next_offset);
    const referenceLoaded=page.waitForResponse(response=>response.url().includes('/standards/standard-fixture'));
    assert.equal((await execute('text_select_standard',{standard_id:standard.id})).status,'completed');
    await referenceLoaded;
    assert.equal((await execute('text_select_asset',{asset_id:asset.id})).status,'completed');
    assert.equal((await execute('text_get_state')).data.selectedAssetId,asset.id);
    await execute('text_prepare_import');await execute('text_import_set_fields',{name:'Agent fixture import',material_code:'AGENT',version_label:'V2'});
    assert.equal((await execute('text_import_get_state')).data.name,'Agent fixture import');
    assert.equal(await page.getByRole('dialog').count(),1);
    assert.equal((await execute('text_start_camera')).status,'requires_user_input');
    // Full route transition must unregister workspace callbacks, retaining core discovery.
    await execute('open_workspace',{workspace:'overview'});
    await waitForNativeTools(page, {present:['vantaline_get_context'], absent:['vantaline_text_get_state']});
    assert.equal((await execute('get_context')).data.route,'/');
    assert.equal((await execute('logout')).status,'completed');
    await waitForNativeTools(page, {empty:true});
    assert.equal(await page.getByRole('status').filter({hasText:'退出登录未得到确认'}).count(),0);
    assert.deepEqual(errors,[]);
    console.log(JSON.stringify({browser:await browser.version(),native_webmcp:true,result:'PASS',scope:'discovery, pagination, live React selection/form state, native permission wait, workspace cleanup'}));
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
