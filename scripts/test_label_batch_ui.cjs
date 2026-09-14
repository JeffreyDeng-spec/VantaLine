// Synthetic input only; no production/model calls.
const assert=require('node:assert/strict');const fs=require('node:fs');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
(async()=>{
 const browser=await chromium.launch({headless:true,channel:process.env.QWEN_TEST_BROWSER||undefined});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
  const base=process.env.REVIEW_UI_BASE||'http://127.0.0.1:5194/react-preview';const out=process.env.CODEX_UI_OUTPUT||'/tmp/vantaline-batch-ui';fs.mkdirSync(out,{recursive:true});
  const svg='<svg xmlns="http://www.w3.org/2000/svg" width="500" height="260"><rect width="500" height="260" fill="white"/><rect x="20" y="20" width="460" height="220" rx="12" fill="none" stroke="#25483c"/><text x="45" y="85" font-size="30">MODEL: VL-210</text><text x="45" y="135" font-size="28">POWER: 220 V</text><text x="45" y="195" font-size="24">VantaLine Quality</text></svg>';
  const evidence={image:'image',original:'image',preview:'preview',size:[500,260]};
  let task=null,uploads=0,submitted=0,forbidden=false;
  function makeLabel(i){return {id:'L'+i,name:'实拍标签 '+i,actual:evidence,outcome:'pending',finalized:false,match:{status:'pending',reason:'',reference_id:null,candidate_ids:[]},summary:null,progress:{total:0,settled:0,elements:0},inputs:{reference:null,actual:evidence,standard_name:'电源标签订单',standard_revision_number:1,standard_revision_id:'v1'},elements:[],checks:[],issues:[],artifacts:[],reviews:[]};}
  await page.route('**/api/**',async r=>{
   const url=new URL(r.request().url()).pathname,method=r.request().method();const root='/api/text-compare-codex/batches';
   if(!url.startsWith('/api/'))return r.continue();
   if(url.endsWith('/capabilities'))return r.fulfill({json:{enabled:!forbidden,model:'fixture'}});
   if(forbidden)return r.fulfill({status:404,json:{detail:'批次不存在'}});
   if(url.includes('/media/'))return r.fulfill({contentType:'image/svg+xml',body:svg});
   if(url==='/api/text-inspection/standards')return r.fulfill({json:{items:[{id:'std',name:'电源标签订单',standard_type:'label',status:'draft'}]}});
   if(url===root){if(method==='POST'){task={id:'batch-1',status:'draft',created_at:1789360000,sequence:1,summary:null,inputs:{references:{}},references:[],labels:[],counts:{pending:0,difference:0,uncertain:0,match:0}};return r.fulfill({json:task});}return r.fulfill({json:{items:task?[task]:[],next_cursor:null}});}
   if(url.endsWith('/document')){task.inputs={standard_id:'std',standard_name:'电源标签订单',references:{R:{id:'R',name:'标准图 1',media:evidence,sources:[{id:'R'}]}}};task.import_state='ready';return r.fulfill({json:task});}
   if(url.endsWith('/photos')){uploads++;task.labels.push(makeLabel(uploads));task.counts.pending=uploads;return r.fulfill({json:task});}
   if(url.endsWith('/submit')){submitted++;task.status='running';return r.fulfill({json:task});}
   if(url.match(/\/labels\/L\d+$/)){return r.fulfill({json:task.labels.find(e=>url.endsWith('/'+e.id))});}
   if(url.endsWith('/review')){const id=url.split('/').at(-2);task.labels.find(e=>e.id===id).reviews.push({key:'rev',created_at:1789360300,value:r.request().postDataJSON()});return r.fulfill({json:task.labels.find(e=>e.id===id)});}
   if(url.endsWith('/batch-1'))return r.fulfill({json:task});
   return r.fulfill({json:{items:[]}});
  });
  const url=base+'/tests/label-batch.html';await page.goto(url);
  assert.equal(await page.locator('.sidebar').count(),0);
  await page.locator('input[accept=".doc,.docx"]').setInputFiles({name:'订单.docx',mimeType:'application/octet-stream',buffer:Buffer.from('fixture')});
  await page.getByText('文档及提取图片已保存',{exact:true}).waitFor();
  await page.locator('input[accept="image/*"]').setInputFiles([1,2,3].map(i=>({name:'label'+i+'.png',mimeType:'image/png',buffer:Buffer.from(svg)})));
  await page.locator('.bw-actual-gallery figure').nth(2).waitFor();assert.equal(uploads,3);
  await page.reload();await page.locator('.bw-actual-gallery figure').nth(2).waitFor();assert.equal(uploads,3);
  await page.getByRole('button',{name:'开始检查整批'}).click();await page.getByRole('button',{name:'取消整批',exact:true}).waitFor();assert.equal(submitted,1);
  // Incremental outcomes: problems must sort before pass even when the upload order differs.
  task.labels[0].outcome='match';task.labels[0].inputs.reference=evidence;task.labels[0].match.status='matched';task.labels[0].summary={decision:'MATCH',message:'全部一致',checked_scope:'全部',unchecked_scope:''};
  const e=task.labels[1];e.outcome='difference';e.inputs.reference=evidence;e.match={status:'matched',reference_id:'R',reason:'型号对应',candidate_ids:['R']};e.summary={decision:'DIFFERENCES',message:'额定电压存在差异',checked_scope:'电压',unchecked_scope:''};
  e.elements=[{id:'E1',name:'电压',category:'text',description:'额定电压',reference:{box:[.1,.3,.6,.3]},actual:{box:[.1,.3,.6,.3]}}];
  e.checks=[{id:'C1',element_ids:['E1'],dimension:'text',expected:'220 V',observed:'230 V',status:'difference',explanation:'数值不同',artifact_ids:[],decode_ids:[]}];
  e.issues=[{id:'I1',check_id:'C1',title:'电压不同',explanation:'<script>window.evil=true</script>',reference:{box:[.1,.3,.6,.3]},actual:{box:[.1,.3,.6,.3]},artifact_ids:[],resolved:false}];e.progress={total:1,settled:1,elements:1};
  task.labels[2].outcome='uncertain';task.labels[2].match.status='needs_confirmation';task.labels[2].match.reason='两个相似标准，需要人工确认';task.counts={difference:1,uncertain:1,match:1,pending:0};task.sequence++;
  await page.locator('.bw-card.difference').waitFor();assert.match(await page.locator('.bw-card').first().innerText(),/实拍标签 2/);
  assert.equal(await page.locator('.cc-items').count(),0);await page.screenshot({path:out+'/batch-desktop.png',fullPage:true});
  await page.locator('.bw-card.difference').click();await page.getByText('元素与检查清单',{exact:true}).waitFor();
  await page.getByRole('button',{name:'I1 · 电压不同',exact:true}).click();assert.equal(await page.locator('.cc-issue-mark .selected').count(),2);assert.equal(await page.evaluate(()=>window.evil),undefined);
  await page.screenshot({path:out+'/batch-label-detail.png',fullPage:true});
  await page.getByRole('button',{name:'返回批次',exact:true}).click();await page.locator('.bw-card.difference').waitFor();
  await page.setViewportSize({width:390,height:844});await page.screenshot({path:out+'/batch-mobile.png',fullPage:true});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
  await page.reload();await page.locator('.bw-card.difference').waitFor();assert.equal(submitted,1);
  forbidden=true;await page.evaluate(()=>sessionStorage.setItem('fixture-owner','other'));await page.reload();await page.getByRole('alert').first().waitFor();assert.equal(await page.locator('.bw-card').count(),0);
  assert.deepEqual(errors,[]);console.log('Batch UI: upload, durable draft, single submit, problems-first, detail, markers, reload, mobile, owner isolation OK');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
