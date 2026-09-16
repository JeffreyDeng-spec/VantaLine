const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {spawn}=require('node:child_process');
const frontend=path.resolve(__dirname,'../local_inspection_service/frontend');
const {chromium}=require(path.join(frontend,'node_modules/playwright'));
const output=process.env.SETTINGS_UI_OUTPUT||fs.mkdtempSync(path.join(os.tmpdir(),'vantaline-settings-ui-'));
const base='http://127.0.0.1:5186';
const vite=spawn(process.execPath,[path.join(frontend,'node_modules/vite/bin/vite.js'),'--host','127.0.0.1','--port','5186','--strictPort','--base','/'],{cwd:frontend,env:{...process.env,VITE_ROUTER_BASENAME:'/'},stdio:'pipe'});
vite.stderr.on('data',b=>console.error(String(b)));
let browser,page;
(async()=>{
 for(let i=0;i<150;i++){if(vite.exitCode!==null)throw Error('Vite failed');try{if((await fetch(base)).ok)break;}catch{}await new Promise(r=>setTimeout(r,100));}
 browser=await chromium.launch({headless:true});
 const context=await browser.newContext({viewport:{width:1440,height:1000}});page=await context.newPage();
 const errors=[];page.on('pageerror',e=>{errors.push(e.message);console.error(e.message);});page.on('console',m=>{if(m.type()==='error')console.error(m.text());});page.on('requestfailed',r=>console.error('REQUEST FAILED',r.url(),r.failure()));
 let role='admin',writes=0,revision=1,bindings={label:'one',manual:'qwen',pipeline:'qwen',image:'',training_assistant:'',accessory:'',training_vision:'',document:'',ocr:''};
 const purposes=Object.keys(bindings).map(id=>({id,label:({label:'标签对比',manual:'说明书检验',pipeline:'流水线配件检测',image:'图片生成',training_assistant:'训练助手',accessory:'配件建档',training_vision:'训练视觉辅助',document:'文档准备与旧版文字检验',ocr:'专用 OCR'})[id],capability:id==='image'?'image':id==='training_assistant'?'text':id==='ocr'?'ocr':id==='document'?'qwen_vision':'vision',advanced:!['label','manual','pipeline','image'].includes(id)}));
 const providers=[{id:'doubao',model:'doubao-seed-evolving',base_url:'https://example.com/chat/completions'},{id:'qwen',model:'qwen3-vl-flash',base_url:'https://example.com/chat/completions'},{id:'qwen_image',model:'qwen-image-2.0-pro',base_url:'https://example.com/image'}];
 const make=(id,name,model,provider,key)=>({id,name,model,provider,masked_key:key,base_url:'https://example.com',timeout_seconds:30,version:1,enabled:true,pending:false,capabilities:['vision','text','qwen_vision'],used_by:[],connection_status:'not_tested'});
 const profiles=[make('one','标签主配置','doubao-seed-evolving','doubao','****A123'),make('two','标签备用','doubao-seed-evolving','doubao','****B456'),make('qwen','产线配置','qwen3-vl-flash','qwen','****C789')];
 const registry=()=>({revision,bindings,profiles,purposes,providers});
 await context.route('**/static/brand-logo.png?*',route=>route.fulfill({contentType:'image/png',path:path.join(frontend,'../static/brand-logo.png')}));
 await context.route('**/api/**',async route=>{
  const r=route.request(),p=new URL(r.url()).pathname,reply=(json,status=200)=>route.fulfill({json,status});
  if(!p.startsWith('/api/'))return route.continue();
  if(p==='/api/auth/status')return reply({authenticated:true,setup_required:false,user:{id:'fixture',username:'fixture',role,permissions:['inspection','ai_config','agent_config']}});
  if(p==='/api/training/resources')return reply({ai_detection_tasks:[],models:[],datasets:[]});
  if(p==='/api/user/preferences/tasks')return reply({exists:true,pinned_task_ids:[],archived_task_ids:[]});
  if(p==='/api/admin/api-cost-ledger')return reply({summary:{call_count:0,unpriced_call_count:0,training_sample_count:0},categories:[],daily:[],recent_calls:[]});
  if(p==='/api/version')return reply({release:'test',git_commit:'test',consistent:true});
  if(p==='/api/admin/model-profiles'){
   if(role!=='admin')throw Error('Member requested model library');
   if(r.method()==='POST'){const b=r.postDataJSON();profiles.push({...make('new',b.name,b.model,b.provider,'****N123'),base_url:b.base_url});revision++;return reply({id:'new',version:1});}
   return reply(registry());
  }
  if(p.endsWith('/model-profiles/engines'))return reply({items:[{name:'标签检查 Beta',engine:'Codex',status:'已配置',path:'/text-compare-codex'}]});
  if(p.endsWith('/model-profiles/bindings')){const b=r.postDataJSON();assert.equal(b.revision,revision);writes++;bindings=b.bindings;revision++;return reply(registry());}
  if(p.endsWith('/model-profiles/usage'))return reply({items:[{profile_id:'one',version:1,purpose:'label',model:'doubao-seed-evolving',elapsed_ms:500,ok:false,usage:{},priced:false,cost:null,at:1}]});
  return reply({items:[],enabled:false,configured:false});
 });
 await page.goto(base+'/workspace/rules');
 await page.getByLabel('标签对比',{exact:true}).waitFor();
 assert.equal(await page.locator('input[type=password]').count(),0);
 assert.equal(await page.getByRole('tab').count(),3);
 assert.equal(await page.locator('#model-label option').count(),4);
 await page.locator('#model-label').selectOption('two');assert.equal(writes,0);
 await page.getByRole('button',{name:'取消更改',exact:true}).click();assert.equal(await page.locator('#model-label').inputValue(),'one');
 await page.locator('.model-setting-row').filter({has:page.locator('#model-label')}).getByRole('button',{name:'添加 key',exact:true}).click();
 await page.getByLabel('配置名称',{exact:true}).fill('新标签配置');
 await page.getByLabel('API Key',{exact:true}).fill('test-secret-N123');
 await page.getByRole('button',{name:'保存配置',exact:true}).click();
 await page.waitForFunction(()=>document.querySelector('#model-label')?.value==='new');
 assert.equal(bindings.label,'one');assert.equal(writes,0);
 await page.getByRole('button',{name:'保存更改',exact:true}).click();
 await page.waitForFunction(()=>document.querySelector('.model-settings-footer .primary')?.disabled);
 assert.equal(bindings.label,'new');assert.equal(writes,1);
 fs.mkdirSync(output,{recursive:true});await page.screenshot({path:path.join(output,'desktop.png'),fullPage:true});
 await page.setViewportSize({width:390,height:844});await page.screenshot({path:path.join(output,'mobile.png'),fullPage:true});
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'Mobile page overflows');
 await page.getByRole('tab',{name:'用量与成本',exact:true}).click();await page.getByText('未计价',{exact:true}).first().waitFor();
 role='user';await page.reload();await page.getByRole('heading',{name:'个人与设备',exact:true}).waitFor();assert.equal(await page.getByRole('button',{name:'添加 key',exact:true}).count(),0);
 assert.deepEqual(errors,[]);console.log('PASS settings dropdown/add/save/member/mobile; artifacts '+output);
})().catch(async e=>{console.error(e);if(page)console.error(await page.locator("body").innerText());process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();vite.kill();});
