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
 await context.addInitScript(() => {
  const original = Element.prototype.requestFullscreen;
  window.__fullscreenRequests = 0;
  Element.prototype.requestFullscreen = function(...args) {
   window.__fullscreenRequests++;
   if(window.__denyFullscreen)return Promise.reject(new Error('fixture denied'));
   return original.apply(this,args);
  };
 });
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
  if(p.includes('/media/'))return route.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="600" height="400"><rect width="600" height="400" fill="#ddd"/><text x="40" y="100" font-size="32">MODEL: TEST</text></svg>'});
  if(p==='/api/label-inspection/tasks'){
   if(req.method()==='POST'){docs++;if(req.postData().includes('filename="标准图片.png"')){task.assets=[{id:'a1',name:'标准 1',ordinal:1,enabled:true,media}];task.runs=[];task.source={type:'image'};}if(holdImport)await new Promise(resolve=>{releaseImport=resolve;});return reply(task);}
   return reply({items:docs?[{id:task.id,name:task.name,source:task.source?.type||'word',standard_count:1,run_count:task.runs.length,updated_at:1,status:'ready',decision:'REVIEW_REQUIRED'}]:[],next_cursor:null});
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
 await page.getByRole('link',{name:'＋ 新建任务',exact:true}).click();await page.waitForFunction(()=>document.fullscreenElement?.classList.contains('label-workspace'));assert.equal(await page.evaluate(()=>window.__fullscreenRequests),1);
 // Emulate the native picker leaving fullscreen; file selection is still a user gesture.
 const pickerEvent=page.waitForEvent('filechooser');await page.getByLabel('导入 Word、PDF 或标准图片创建任务').click();await pickerEvent;
 await page.evaluate(()=>document.exitFullscreen());await page.waitForFunction(()=>!document.fullscreenElement);
 await page.locator('input[type=file]').setInputFiles({name:'test.docx',mimeType:'application/vnd.openxmlformats-officedocument.wordprocessingml.document',buffer:Buffer.from('fixture')});
 await page.getByRole('button',{name:/测试订单.*标准版本/}).waitFor();assert.ok(await page.evaluate(()=>document.fullscreenElement?.classList.contains('label-workspace')));assert.equal(await page.evaluate(()=>window.__fullscreenRequests),2);await page.getByText('图片内容无法解码',{exact:true}).waitFor();assert.ok(await page.getByRole('button',{name:'选择标准 2',exact:true}).isDisabled());
 await page.getByRole('button',{name:'选择标准 1',exact:true}).click();await page.getByRole('button',{name:'返回缩略图'}).waitFor();
 await page.getByLabel('上传实物照片').locator('input').setInputFiles({name:'actual.png',mimeType:'image/png',buffer:png});
 await page.getByRole('button',{name:'开始检测',exact:true}).dblclick();await page.getByText('识别标签布局…',{exact:false}).waitFor();assert.equal(submits,1);
 await page.reload();await page.getByText('识别标签布局…',{exact:false}).waitFor();assert.equal(submits,1);assert.equal(diagnostics,0);assert.equal(await page.evaluate(()=>window.__fullscreenRequests),0);
 task.runs[0]={...task.runs[0],status:'completed',phase:'completed',decision:'DIFFERENCES',elapsed:18,crop:[60,40,300,200],scope:'仅检测选中标签',result:{decision:'DIFFERENCES',similarity:85,issues:[{id:1,type:'missing_line',description:'缺少 MODEL 行',standardText:'MODEL: TEST',actualText:'',severity:'high',confidence:'',position_note:'无法可靠定位'}]}};
 await page.getByText('缺少 MODEL 行',{exact:true}).waitFor();assert.equal(await page.locator('.li-box-number').count(),0);await page.getByRole('button',{name:'查看异常 1 详情',exact:true}).click();await page.getByRole('dialog').getByText('模型置信度',{exact:true}).waitFor();await page.getByRole('dialog').getByText('无法可靠定位',{exact:true}).waitFor();await page.getByRole('button',{name:'关闭详情'}).click();assert.equal(await page.locator('.li-crop').count(),1);
 await page.getByText('检测编号：run-1',{exact:true}).waitFor();assert.equal(await page.getByText(/调用诊断/).count(),0);assert.equal(await page.locator('.li-results pre').count(),0);assert.equal(diagnostics,0);
 await page.screenshot({path:path.join(output,'desktop-difference.png'),fullPage:true});
 await page.getByRole('button',{name:'放大实物图',exact:true}).click();await page.getByRole('dialog').waitFor();await page.keyboard.press('Escape');assert.equal(await page.getByRole('dialog').count(),0);
 await page.getByRole('button',{name:'检测下一件',exact:true}).click();await page.getByRole('button',{name:'开始检测',exact:true}).waitFor();assert.ok(await page.getByRole('button',{name:'开始检测',exact:true}).isDisabled());
 await page.getByRole('button',{name:'开启摄像头 / 重拍',exact:true}).click();await page.getByRole('button',{name:'拍照',exact:true}).waitFor();await page.getByRole('button',{name:'拍照',exact:true}).click();await page.getByText('重新上传 · 实物拍照.jpg',{exact:true}).waitFor();assert.equal(await page.locator('video:visible').count(),0);
 await page.getByRole('button',{name:'返回缩略图'}).click();await page.getByRole('button',{name:'隐藏标准',exact:true}).click();await page.getByLabel('显示已隐藏 / 无效标准').check();await page.getByRole('button',{name:'恢复标准',exact:true}).click();assert.equal(task.revision,3);assert.equal(task.runs[0].revision,1);assert.ok(await page.locator('.li-gallery').isVisible());
 await page.setViewportSize({width:390,height:844});await page.screenshot({path:path.join(output,'mobile-workbench.png'),fullPage:true});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
 await page.getByRole('tab',{name:/历史记录/}).click();await page.getByRole('button',{name:/旧文字检验|Evolving.*版本/}).click();await page.getByText('缺少 MODEL 行',{exact:true}).waitFor();assert.equal(submits,1);
 // Compact rows: six abnormalities with trustworthy coordinates, one unlocated item.
 task.runs[0].result.issues=Array.from({length:6},(_,i)=>({...task.runs[0].result.issues[0],id:i+1,
  description:`异常 ${i+1}：型号文字与标准不一致，请核对实际印刷内容。`,
  actual_box:i===0?undefined:[.2,.1+i*.1,.25,.08]}));
 await page.reload();await page.locator('.li-issue').nth(5).waitFor();
 assert.equal(await page.locator('.li-box-number').count(),5);
 await page.locator('.li-issue-line').nth(2).click();assert.equal(await page.locator('.li-box-number.selected').textContent(),'3');
 // Fixed geometry, actual image/overlay fit and local overflow across target sizes.
 const cases=[[1920,1080],[1440,900],[1366,768],[1024,768],[390,844],[683,384]];
 for(const [width,height] of cases){
  await page.setViewportSize({width,height});
  await page.waitForFunction(()=>[...document.querySelectorAll('.li-image img')].filter(i=>i.getBoundingClientRect().width>0).every(i=>{const r=i.getBoundingClientRect();return i.naturalWidth>0&&Math.abs(r.width/r.height/(i.naturalWidth/i.naturalHeight)-1)<.01;}));
  const geometry=await page.evaluate(()=>{
   const shell=document.querySelector('.li-fixed'), button=document.querySelector('.li-result-summary button');
   const images=[...document.querySelectorAll('.li-image img')].filter(e=>e.getBoundingClientRect().width>0);
   return {height:innerHeight,scrollY,bodyHeight:document.documentElement.scrollHeight,shell:shell.getBoundingClientRect().height,
    contentHeight:document.querySelector(".li-result-content").clientHeight,buttonBottom:button.getBoundingClientRect().bottom,ratio:images.map(i=>{const r=i.getBoundingClientRect();return r.width/r.height/(i.naturalWidth/i.naturalHeight);})};
  });
  assert.ok(geometry.bodyHeight<=height+1,JSON.stringify(geometry));assert.equal(geometry.scrollY,0);assert.ok(geometry.buttonBottom<=height);assert.ok(geometry.contentHeight>=25,JSON.stringify(geometry));
  assert.ok(geometry.ratio.every(r=>Math.abs(r-1)<.01),JSON.stringify(geometry));
  if(width===1920||width===1440){
   const rows=await page.locator('.li-issue').evaluateAll(es=>{const pane=document.querySelector('.li-result-content').getBoundingClientRect();return es.map(e=>({visible:e.getBoundingClientRect().bottom<=pane.bottom,height:e.getBoundingClientRect().height,font:parseFloat(getComputedStyle(e.querySelector('.li-issue-line')).fontSize)}));});
   assert.ok(rows.every(r=>r.height===32 && r.font>=16),JSON.stringify(rows));
   assert.ok(rows.filter(r=>r.visible).length >= (width===1920?6:5),JSON.stringify(rows));
  }
  await page.screenshot({path:path.join(output,`fixed-${width}x${height}.png`),fullPage:true});
 }
 await page.setViewportSize({width:1366,height:768});
 await page.getByRole('button',{name:/测试订单.*标准版本/}).click();await page.getByRole('dialog').waitFor();
 await page.getByLabel('任务名称',{exact:true}).fill('测试订单-改名');await page.getByRole('button',{name:'保存名称',exact:true}).click();await page.getByRole('dialog').waitFor({state:'hidden'});assert.equal(task.name,'测试订单-改名');
 await page.getByRole('separator',{name:'调整结果面板高度'}).focus();await page.keyboard.press('ArrowUp');assert.equal(await page.getByRole('separator').getAttribute('aria-valuenow'),'34');
 const split=await page.getByRole('separator').boundingBox();await page.mouse.move(split.x+split.width/2,split.y+split.height/2);await page.mouse.down();await page.mouse.move(split.x+split.width/2,split.y-500);await page.mouse.up();assert.equal(await page.getByRole('separator').getAttribute('aria-valuenow'),'45');
 await page.getByRole('button',{name:'进入全屏',exact:true}).click();await page.waitForFunction(()=>!!document.fullscreenElement);
 await page.getByRole('button',{name:'退出全屏',exact:true}).click();await page.waitForFunction(()=>!document.fullscreenElement);
 // Rejection remains usable, without retrying on render.
 await page.evaluate(()=>{window.__denyFullscreen=true;});await page.getByRole('button',{name:'进入全屏',exact:true}).click();await page.getByRole('status').filter({hasText:'未能进入浏览器全屏'}).waitFor();
 const attempts=await page.evaluate(()=>window.__fullscreenRequests);await page.waitForTimeout(100);assert.equal(await page.evaluate(()=>window.__fullscreenRequests),attempts);
 await page.getByRole('button',{name:'关闭全屏提示'}).click();await page.evaluate(()=>{window.__denyFullscreen=false;});
 // Hundreds of standards/results/history must overflow only their respective panes.
 const saved=structuredClone(task.runs[0]);
 task.assets=Array.from({length:500},(_,i)=>({id:'a'+(i+1),name:'标准 '+(i+1),ordinal:i+1,enabled:true,media}));
 task.runs=Array.from({length:60},(_,i)=>({...structuredClone(saved),id:'history-'+i}));
 task.runs[0].result.issues=Array.from({length:100},(_,i)=>({...saved.result.issues[0],id:i+1,description:'长问题说明'.repeat(100)}));
 await page.goto(base+'/workspace/label-inspection?task=test-task');await page.getByRole('button',{name:'选择标准 500',exact:true}).waitFor();
 assert.ok(await page.locator('.li-gallery').evaluate(e=>e.scrollHeight>e.clientHeight));
 await page.locator('.li-gallery').hover();await page.mouse.wheel(0,30000);assert.equal(await page.evaluate(()=>scrollY),0);
 await page.getByRole('tab',{name:/历史记录/}).click();assert.ok(await page.locator('.li-history').evaluate(e=>e.scrollHeight>e.clientHeight));
 await page.locator('.li-history button').first().click();await page.getByText('长问题说明'.repeat(100),{exact:true}).first().waitFor();
 assert.ok(await page.locator('.li-result-content').evaluate(e=>e.scrollHeight>e.clientHeight));
 await page.locator('.li-result-content').hover();await page.mouse.wheel(0,30000);assert.equal(await page.evaluate(()=>scrollY),0);
 // Quality rejection is a saved non-pass, with retry retaining the selected standard.
 const qualitySaved=JSON.parse(JSON.stringify(task.runs[0]));
 task.runs[0]={...qualitySaved,status:'failed',decision:'REVIEW_REQUIRED',result:null,
  error_code:'QUALITY_BLURRED',error:'标签文字整体不够清晰，请重新对焦并保持相机稳定后拍摄',
  quality:{policy:{version:'black-label-quality-v1',config_hash:'fixture'}}};
 await page.setViewportSize({width:1440,height:900});await page.reload();
 await page.getByRole('heading',{name:'照片质量未通过',exact:true}).waitFor();
 await page.getByRole('alert').filter({hasText:'尚未完成比对'}).waitFor();
 assert.equal(await page.locator('.li-pass,.li-model-score,.li-issue').count(),0);
 await page.screenshot({path:path.join(output,'quality-rejected.png'),fullPage:true});
 await page.getByRole('button',{name:'重新拍照 / 重新上传',exact:true}).click();
 await page.getByRole('button',{name:'开启摄像头 / 重拍',exact:true}).waitFor();
 assert.ok(await page.getByRole('button',{name:'返回缩略图',exact:true}).isVisible());
 assert.equal(submits,1);
 task.runs[0]=qualitySaved;await page.goto(base+'/workspace/label-inspection?task=test-task&run='+qualitySaved.id);
 await page.getByText('当时未执行质量筛选',{exact:true}).waitFor();
 task.runs[0].error='长错误说明'.repeat(300);task.runs[0].status='failed';task.runs[0].result=null;
 await page.reload();await page.getByRole('alert').filter({hasText:'长错误说明'}).waitFor();assert.ok(await page.locator('.li-result-content').evaluate(e=>e.scrollHeight>e.clientHeight));assert.equal(await page.evaluate(()=>scrollY),0);
 await page.getByRole('button',{name:'返回任务详情',exact:true}).click();await page.getByRole('button',{name:'返回任务列表',exact:true}).click();await page.getByRole('heading',{name:'检测任务'}).waitFor();
 assert.equal(await page.evaluate(()=>!!document.fullscreenElement),false);assert.equal(await page.evaluate(()=>document.body.style.overflow),'');
 await page.getByRole('link',{name:'测试订单-改名',exact:true}).click();await page.waitForFunction(()=>!!document.fullscreenElement);
 assert.equal(submits,1);
 holdImport=true;await page.getByRole('button',{name:'更多操作',exact:true}).click();await page.getByRole('link',{name:'新建任务',exact:true}).click();
 await page.locator('input[type=file]').setInputFiles({name:'delayed.docx',mimeType:'application/vnd.openxmlformats-officedocument.wordprocessingml.document',buffer:Buffer.from('fixture')});
 await page.getByText('正在创建任务…',{exact:true}).waitFor();await page.getByRole('link',{name:'← 返回任务列表',exact:true}).click();await page.getByRole('heading',{name:'检测任务',exact:true}).waitFor();
 assert.ok(releaseImport);releaseImport();await page.waitForTimeout(600);assert.equal(new URL(page.url()).search,'');assert.equal(await page.getByRole('heading',{name:'检测任务',exact:true}).count(),1);
 // Direct image chooser/drop shares the single-file import surface and fullscreen shell.
 holdImport=false;
 await page.getByRole('link',{name:'＋ 新建任务',exact:true}).click();
 const importer=page.getByLabel('导入 Word、PDF 或标准图片创建任务');
 assert.equal(await importer.locator('input').getAttribute('accept'),'.doc,.docx,.pdf,.jpg,.jpeg,.png,.webp,.bmp');
 assert.equal(await importer.locator('input').getAttribute('multiple'),null);
 assert.equal(await importer.locator('strong').evaluate(e=>getComputedStyle(e).color),'rgb(231, 238, 249)');
 await page.screenshot({path:path.join(output,'image-import.png'),fullPage:true});
 await importer.locator('input').setInputFiles({name:'标准图片.png',mimeType:'image/png',buffer:png});
 await page.getByRole('button',{name:'选择标准 1',exact:true}).waitFor();
 await page.waitForFunction(()=>document.querySelectorAll('.li-gallery button[aria-label^="选择标准"]').length===1);
 assert.equal(await page.locator('.li-gallery button[aria-label^="选择标准"]').count(),1);
 assert.equal(submits,1);
 await page.reload();await page.getByRole('button',{name:'选择标准 1',exact:true}).click();
 await page.getByRole('button',{name:'放大标准图',exact:true}).click();await page.getByRole('dialog').waitFor();await page.keyboard.press('Escape');
 await page.getByRole('button',{name:'返回任务列表',exact:true}).click();
 await page.getByRole('combobox').first().selectOption('image');
 await page.getByText('图片上传',{exact:true}).last().waitFor();
 await page.getByRole('link',{name:'＋ 新建任务',exact:true}).click();
 await page.getByLabel('导入 Word、PDF 或标准图片创建任务').evaluate((element,bytes)=>{
  const transfer=new DataTransfer();transfer.items.add(new File([new Uint8Array(bytes)],'标准图片.png',{type:'image/png'}));
  element.dispatchEvent(new DragEvent('drop',{bubbles:true,dataTransfer:transfer}));
 },Array.from(png));
 await page.getByRole('button',{name:'选择标准 1',exact:true}).waitFor();
 await page.waitForFunction(()=>document.querySelectorAll('.li-gallery button[aria-label^="选择标准"]').length===1);
 assert.equal(await page.locator('.li-gallery button[aria-label^="选择标准"]').count(),1);
 await page.screenshot({path:path.join(output,'image-single-grid.png'),fullPage:true});
 task.source={type:'pdf'};task.status='import_running';task.revision=0;task.assets=[];task.runs=[];task.import={completed:1,total:2};
 await page.reload();await page.getByRole('heading',{name:'正在导入',exact:true}).waitFor();
 assert.equal(await page.getByRole('button',{name:'开始检测',exact:true}).count(),0);
 await page.screenshot({path:path.join(output,'pdf-import-progress.png'),fullPage:true});
 task.status='ready';task.revision=1;task.import.completed=2;task.assets=[{id:'pdf-left',name:'PDF 第 1 张 · 左',ordinal:1,enabled:true,media},{id:'pdf-right',name:'PDF 第 1 张 · 右',ordinal:2,enabled:true,media}];
 await page.getByRole('heading',{name:'标准页面',exact:true}).waitFor();
 await page.getByRole('button',{name:'选择标准 1',exact:true}).click();
 await page.getByText('每次只拍一页',{exact:false}).waitFor();
 await page.screenshot({path:path.join(output,'pdf-workspace.png'),fullPage:true});
 task.read_only=true;task.manual_history={sessions:[{id:'old-session',decision:'REVIEW_REQUIRED'}],pages:[{id:'old-page',decision:'DIFFERENCES',differences:['保留原缺字结论'],has_photo:false}],standards:[]};
 await page.reload();await page.getByRole('heading',{name:'历史记录（只读）',exact:true}).waitFor();
 await page.getByText('原记录未保留实物照片，无法回看图片。',{exact:true}).waitFor();
 assert.equal(await page.getByRole('button',{name:'开始检测',exact:true}).count(),0);
 await page.screenshot({path:path.join(output,'pdf-legacy-read-only.png'),fullPage:true});
 assert.deepEqual(errors,[]);console.log('label workspace UI PASS; screenshots: '+output);
 await require('./test_label_image_reuse.cjs')();
})().catch(async e=>{console.error(e);if(browser){const p=browser.contexts()[0]?.pages()[0];if(p){console.error(await p.locator('body').innerText());await p.screenshot({path:path.join(output,'failure.png'),fullPage:true});}}process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();vite.kill();});
