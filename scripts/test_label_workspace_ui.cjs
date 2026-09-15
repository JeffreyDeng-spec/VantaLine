// Actual app/router, isolated API fixtures and synthetic camera only. No paid calls.
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {spawn}=require('node:child_process');
const frontend=path.resolve(__dirname,'../local_inspection_service/frontend');
const {chromium}=require(path.join(frontend,'node_modules/playwright'));
const output=fs.mkdtempSync(path.join(os.tmpdir(),'vantaline-label-ui-'));
const base='http://127.0.0.1:5186';
const vite=spawn(process.execPath,[path.join(frontend,'node_modules/vite/bin/vite.js'),'--host','127.0.0.1','--port','5186','--strictPort','--base','/'],{cwd:frontend,env:{...process.env,VITE_ROUTER_BASENAME:'/'},stdio:'ignore'});
let browser;
(async()=>{
 for(let i=0;i<100;i++){try{if((await fetch(base)).ok)break;}catch{}await new Promise(r=>setTimeout(r,100));}
 browser=await chromium.launch({headless:true,args:['--use-fake-device-for-media-stream','--use-fake-ui-for-media-stream']});
 const context=await browser.newContext({viewport:{width:1440,height:1000},permissions:['camera']});const page=await context.newPage();page.setDefaultTimeout(15000);
 const errors=[];page.on('pageerror',e=>{errors.push(e.message);console.error('PAGE ERROR',e.message);});
 page.on('console',m=>{if(m.type()==='error')console.error(m.text());});
 const media={original:'o',image:'i',preview:'p',size:[600,400]};
 const task={id:'test-task',name:'测试订单',revision:1,assets:[{id:'a1',name:'标准 1',ordinal:1,enabled:true,media},{id:'invalid',name:'无法解码图片',ordinal:2,enabled:false,error:'图片内容无法解码'}],runs:[]};
 let submits=0,docs=0,diagnostics=0,holdImport=false,releaseImport;
 const png=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aD1sAAAAASUVORK5CYII=','base64');
 await context.route('**/api/**',async route=>{
  const req=route.request(),u=new URL(req.url()),p=u.pathname;if(!p.startsWith('/api/'))return route.continue();const reply=(v,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(v)});
  if(p==='/api/auth/status')return reply({authenticated:true,setup_required:false,user:{id:'fixture',username:'fixture',role:'user',permissions:['inspection']},features:{},default_user_permissions:[]});
  if(p==='/api/label-inspection/capabilities')return reply({enabled:true});
  if(p.includes('/media/'))return route.fulfill({contentType:'image/png',body:png});
  if(p==='/api/label-inspection/tasks'){
   if(req.method()==='POST'){docs++;if(holdImport)await new Promise(resolve=>{releaseImport=resolve;});return reply(task);}
   return reply({items:docs?[{id:task.id,name:task.name,source:'word',standard_count:1,run_count:task.runs.length,updated_at:1,status:'ready',decision:'REVIEW_REQUIRED'}]:[],next_cursor:null});
  }
  if(p==='/api/label-inspection/tasks/test-task'){
   if(req.method()==='PATCH'){const b=req.postDataJSON();if(b.operation==='name')task.name=b.value;else{task.revision++;task.assets[0].enabled=b.operation==='restore';}}
   return reply(task);
  }
  if(p==='/api/label-inspection/tasks/test-task/runs'){
   submits++;task.runs=[{id:'run-1',task_id:task.id,revision:task.revision,status:'running',phase:'layout',decision:'REVIEW_REQUIRED',created_at:1,reference:structuredClone(task.assets[0]),actual:media}];return reply(task.runs[0]);
  }
  if(p.startsWith('/api/label-inspection/requests/'))return reply({run:task.runs[0]||null});
  if(p.endsWith('/diagnostics')){diagnostics++;return reply({calls:[]});}
  return reply({items:[],enabled:false});
 });
 await page.goto(base+'/workspace/label-inspection');await page.getByRole('heading',{name:'检测任务',exact:true}).waitFor();assert.equal(await page.locator('.sidebar').count(),0);
 await page.getByRole('link',{name:'＋ 新建任务',exact:true}).click();
 await page.locator('input[type=file]').setInputFiles({name:'test.docx',mimeType:'application/vnd.openxmlformats-officedocument.wordprocessingml.document',buffer:Buffer.from('fixture')});
 await page.getByRole('heading',{name:'测试订单',exact:true}).waitFor();await page.getByText('图片内容无法解码',{exact:true}).waitFor();assert.ok(await page.getByRole('button',{name:'选择标准 2',exact:true}).isDisabled());
 await page.getByRole('button',{name:'选择标准 1',exact:true}).click();await page.getByRole('button',{name:'返回缩略图'}).waitFor();
 await page.getByLabel('上传实物照片').locator('input').setInputFiles({name:'actual.png',mimeType:'image/png',buffer:png});
 await page.getByRole('button',{name:'开始检测',exact:true}).dblclick();await page.getByText('识别标签布局…',{exact:false}).waitFor();assert.equal(submits,1);
 await page.reload();await page.getByText('识别标签布局…',{exact:false}).waitFor();assert.equal(submits,1);assert.equal(diagnostics,0);
 task.runs[0]={...task.runs[0],status:'completed',phase:'completed',decision:'DIFFERENCES',elapsed:18,crop:[60,40,300,200],scope:'仅检测选中标签',result:{decision:'DIFFERENCES',similarity:85,issues:[{id:1,type:'missing_line',description:'缺少 MODEL 行',standardText:'MODEL: TEST',actualText:'',severity:'high',confidence:'',position_note:'无法可靠定位'}]}};
 await page.getByText('缺少 MODEL 行',{exact:true}).waitFor();await page.getByText('模型置信度：未提供',{exact:false}).waitFor();assert.equal(await page.locator('.li-crop').count(),1);
 await page.getByText('调用诊断（默认折叠）',{exact:true}).click();await page.waitForFunction(()=>document.querySelector('.li-results pre')?.textContent.includes('calls'));assert.equal(diagnostics,1);
 await page.screenshot({path:path.join(output,'desktop-difference.png'),fullPage:true});
 await page.getByRole('button',{name:'放大实物图',exact:true}).click();await page.getByRole('dialog').waitFor();await page.keyboard.press('Escape');assert.equal(await page.getByRole('dialog').count(),0);
 await page.getByRole('button',{name:'检测下一件',exact:true}).click();await page.getByRole('button',{name:'开始检测',exact:true}).waitFor();assert.ok(await page.getByRole('button',{name:'开始检测',exact:true}).isDisabled());
 await page.getByRole('button',{name:'开启摄像头 / 重拍',exact:true}).click();await page.getByRole('button',{name:'拍照',exact:true}).waitFor();await page.getByRole('button',{name:'拍照',exact:true}).click();await page.getByText('重新上传 · 实物拍照.jpg',{exact:true}).waitFor();assert.equal(await page.locator('video:visible').count(),0);
 await page.getByRole('button',{name:'返回缩略图'}).click();await page.getByRole('button',{name:'隐藏标准',exact:true}).click();await page.getByLabel('显示已隐藏 / 无效标准').check();await page.getByRole('button',{name:'恢复标准',exact:true}).click();assert.equal(task.revision,3);assert.equal(task.runs[0].revision,1);
 await page.setViewportSize({width:390,height:844});await page.screenshot({path:path.join(output,'mobile-workbench.png'),fullPage:true});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
 await page.getByRole('button',{name:/旧文字检验|Evolving.*版本/}).click();await page.getByText('缺少 MODEL 行',{exact:true}).waitFor();assert.equal(submits,1);
 holdImport=true;await page.getByRole('link',{name:'新建任务',exact:true}).click();
 await page.locator('input[type=file]').setInputFiles({name:'delayed.docx',mimeType:'application/vnd.openxmlformats-officedocument.wordprocessingml.document',buffer:Buffer.from('fixture')});
 await page.getByText('正在提取图片…',{exact:true}).waitFor();await page.getByRole('link',{name:'← 返回任务列表',exact:true}).click();await page.getByRole('heading',{name:'检测任务',exact:true}).waitFor();
 assert.ok(releaseImport);releaseImport();await page.waitForTimeout(600);assert.equal(new URL(page.url()).search,'');assert.equal(await page.getByRole('heading',{name:'检测任务',exact:true}).count(),1);
 assert.deepEqual(errors,[]);console.log('label workspace UI PASS; screenshots: '+output);
})().catch(async e=>{console.error(e);if(browser){const p=browser.contexts()[0]?.pages()[0];if(p){console.error(await p.locator('body').innerText());await p.screenshot({path:path.join(output,'failure.png'),fullPage:true});}}process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();vite.kill();});
