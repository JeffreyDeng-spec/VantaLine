// Synthetic browser acceptance. Never calls a model or production API.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
(async()=>{
 const browser = await chromium.launch({headless:true,channel:process.env.QWEN_TEST_BROWSER || undefined});
 try {
  const page = await browser.newPage({viewport:{width:1360,height:900}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  const base=process.env.REVIEW_UI_BASE || 'http://127.0.0.1:5189';
  const output=process.env.CODEX_UI_OUTPUT || '/tmp/vantaline-codex-ui';fs.mkdirSync(output,{recursive:true});
  const svg='<svg xmlns="http://www.w3.org/2000/svg" width="500" height="260"><rect width="500" height="260" fill="white"/><rect x="20" y="20" width="460" height="220" rx="12" fill="none" stroke="#25483c"/><text x="45" y="85" font-family="sans-serif" font-size="30">MODEL: VL-210</text><text x="45" y="135" font-family="sans-serif" font-size="28">POWER: 220 V</text><text x="45" y="195" font-family="sans-serif" font-size="24">VantaLine Quality</text></svg>';
  let submitted=0, task=null, forbidden=false, lost=false;
  let keys=[];
  const evidence={image:'image',original:'image',preview:'preview',size:[500,260]};
  const fixture=()=>({id:'cc-fixture',status:'running',created_at:1789360000,sequence:2,finalized:false,inputs:{standard_name:'电源铭牌',standard_revision_id:'rev1',standard_revision_number:1,reference:evidence,actual:{...evidence,image:'actual',preview:'actual-preview'}},counts:{match:0,difference:0,uncertain:0},summary:null,items:[],artifacts:[],reviews:[]});
  await page.route('**/fixture/**',r=>r.fulfill({contentType:'image/svg+xml',body:svg}));
  await page.route('**/api/**',async r=>{
   const req=r.request(),url=new URL(req.url()).pathname;
   if(!url.startsWith('/api/'))return r.continue();
   if(url.includes('/media/')) return r.fulfill({contentType:'image/svg+xml',body:url.includes('actual')?svg.replace('220 V','230 V'):svg});
   if(url==='/api/text-inspection/standards')return r.fulfill({json:{items:[{id:'std',name:'电源铭牌',status:'confirmed',standard_type:'label'}]}});
   if(url==='/api/text-inspection/standards/std')return r.fulfill({json:{id:'std',name:'电源铭牌',status:'confirmed',current_revision_id:'rev1',assets:[{id:'asset',ordinal:1,status:'candidate',content_url:'/fixture/source',original_url:'/fixture/source'}]}});
   if(url.endsWith('/capabilities'))return r.fulfill({json:{enabled:!forbidden,model:'fixed-fixture'}});
   if(url==='/api/text-compare-codex/tasks'){
    if(req.method()==='POST'){
     submitted++;keys.push(req.postData().match(/name="request_id"\r\n\r\n([^\r]+)/)[1]);task ||= fixture();
     if(lost){lost=false;return r.abort('failed');}
     return r.fulfill({json:task});
    }
    return r.fulfill({json:{items:forbidden?[]:task?[task]:[],next_cursor:null}});
   }
   if(forbidden)return r.fulfill({status:404,json:{detail:'任务不存在'}});
   if(url.endsWith('/events'))return r.fulfill({json:{items:[{sequence:2,kind:'progress',created_at:1789360000,payload:{value:{message:'正在核对型号与单位'}}}]}});
   if(url.endsWith('/cancel')){task.status='cancel_requested';return r.fulfill({json:task});}
   if(url.endsWith('/review')){const b=req.postDataJSON();task.reviews.push({key:b.request_id,created_at:1789360100,value:b});return r.fulfill({json:task});}
   if(url.endsWith('/cc-fixture'))return r.fulfill({json:task});
   return r.fulfill({status:404,json:{detail:'fixture route missing'}});
  });
  const fixtureURL=base+'/tests/codex-compare.html';
  await page.goto(fixtureURL);
  await page.getByLabel('标准订单').selectOption('std');
  await page.getByRole('button',{name:'选择标准标签 1',exact:true}).click();
  await page.locator('input[type=file]').setInputFiles({name:'label.png',mimeType:'image/png',buffer:Buffer.from(svg)});
  lost=true;await page.getByRole('button',{name:'开始对比',exact:true}).click();
  await page.getByRole('alert').waitFor();
  await page.getByRole('button',{name:'开始对比',exact:true}).click();
  await page.getByText('初步结果 · 内容会随核对进展更新').waitFor();
  assert.equal(keys[0],keys[1]);assert.equal(submitted,2);
  await page.reload();await page.getByText('初步结果 · 内容会随核对进展更新').waitFor();assert.equal(submitted,2);
  task={...task,status:'completed',finalized:true,sequence:6,counts:{match:1,difference:1,uncertain:0},summary:{decision:'DIFFERENCES',message:'发现电压数值差异，建议人工复核。',checked_scope:'型号、额定电压与品牌文字',unchecked_scope:''},items:[{id:'voltage',status:'difference',reference_text:'220 V',actual_text:'230 V',explanation:'电压数字第二位不同。<script>window.evil=true</script>',reference_box:[.08,.35,.6,.2],actual_box:[.08,.35,.6,.2],artifact_ids:[]}]};
  await page.getByText('发现电压数值差异，建议人工复核。').waitFor();
  await page.getByRole('button',{name:'差异 · 220 V'}).click();assert.equal(await page.locator('.cc-box').count(),2);
  assert.equal(await page.evaluate(()=>window.evil),undefined);
  await page.getByLabel('人工结论').selectOption('DIFFERENCES');await page.getByLabel('复核备注').fill('已核对原图');await page.getByRole('button',{name:'保存人工复核'}).click();await page.getByText(/已核对原图/).first().waitFor();
  await page.screenshot({path:output+'/report-desktop.png',fullPage:true});
  await page.setViewportSize({width:390,height:844});await page.screenshot({path:output+'/report-mobile.png',fullPage:true});
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
  await page.goto(fixtureURL);await page.locator('.cc-card').waitFor();await page.screenshot({path:output+'/cards-mobile.png',fullPage:true});
  await page.locator('.cc-card').click();await page.getByText('发现电压数值差异，建议人工复核。').waitFor();
  forbidden=true;await page.evaluate(()=>sessionStorage.setItem('fixture-owner','other'));await page.reload();await page.getByText('任务不存在',{exact:false}).waitFor();
  assert.equal(await page.locator('.cc-pair').count(),0);
  assert.deepEqual(errors,[]);console.log('Codex report UI: submit identity, reload, report updates, evidence, review, account isolation, mobile: OK');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
