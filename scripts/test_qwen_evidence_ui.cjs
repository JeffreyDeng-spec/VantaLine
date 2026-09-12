// Real React UI, synthetic images and fake HTTP only; no external model calls.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
(async () => {
  const output=fs.mkdtempSync(path.join(os.tmpdir(),'qwen-evidence-ui-'));
  const browser=await chromium.launch({headless:true});
  try {
    const page=await browser.newPage({viewport:{width:1360,height:900}});
    const errors=[]; page.on('pageerror',e=>errors.push(e.message));
    const svg='<svg xmlns="http://www.w3.org/2000/svg" width="400" height="200"><rect width="400" height="200" fill="white"/><text x="40" y="80">MODEL TEST</text></svg>';
    const standard={id:'std',name:'OCR evidence fixture',material_code:'TEST',version_label:'1',standard_type:'label',status:'confirmed',asset_count:1,revision_number:1};
    const asset={id:'asset',standard_id:'std',asset_kind:'label_candidate',ordinal:1,status:'candidate',content_url:'/fixture/source',comparison_ready:true,active_preparation:{id:'prep',sha256:'fixture'}};
    let submitted=0,polls=0,identity='',extractionRequests=0;
    const result=()=>({id:'record',comparison_id:identity,preparation_compare:true,status:'completed',decision:'REVIEW_REQUIRED',differences:[],message:'需要人工确认，图形未检查',reference_overlay_url:'/fixture/reference',diagnostics:{provider:'qwen_ocr',phase:'completed',normalized_response:{elements:[{element_id:'e1',type:'text',expected:'MODEL TEST',standard_box:[.1,.25,.5,.2],state:'matched',reason:'exact_characters',conflicts:[{evidence_id:'wrong',start:0,end:11}],evidence:[{evidence_id:'o1',start:0,end:10}]}],observations:[{id:'wrong',type:'text',text:'MODEL WRONG',box:[.6,.6,.9,.9]},{id:'o1',type:'text',text:'MODEL TEST',box:[.1,.25,.6,.45]}]}}});
    await page.route('**/fixture/**',r=>r.fulfill({contentType:'image/svg+xml',body:svg}));
    await page.route('**/api/**',r=>{
      const req=r.request(),url=new URL(req.url()).pathname;
      if(!url.startsWith('/api/'))return r.continue();
      if(url.endsWith('/extraction-capabilities'))return r.fulfill({json:{enabled:true,ai_available:true}});
      if(url.includes('/extractions')){extractionRequests++;return r.fulfill({status:500});}
      if(url.endsWith('/preparation-capabilities'))return r.fulfill({json:{enabled:true,ocr_available:true}});
      if(url==='/api/text-inspection/standards')return r.fulfill({json:{items:[standard]}});
      if(url==='/api/text-inspection/standards/std')return r.fulfill({json:{...standard,assets:[asset]}});
      if(url.endsWith('/preparation'))return r.fulfill({json:{job:{},items:[]}});
      if(url.endsWith('/label/compare')){
        assert.ok(req.postData().includes('name="captured_file"'));
        assert.ok(!req.postData().includes('name="extraction_id"'));
        submitted++; identity=req.postData().match(/name="comparison_id"\r\n\r\n([^\r]+)/)[1];
        return r.fulfill({json:{...result(),status:'attempting',diagnostics:{phase:'extracting_text'}}});
      }
      if(url.endsWith('/media/source'))return r.fulfill({contentType:'image/svg+xml',body:svg});
      if(url.endsWith('/prepared-comparisons/record')){polls++;return r.fulfill({json:result()});}
      return r.fulfill({status:404,json:{detail:'fixture'}});
    });
    await page.goto((process.env.REVIEW_UI_BASE||'http://127.0.0.1:5189')+'/tests/document-review.html');
    await page.getByRole('button',{name:/OCR evidence fixture/}).click().catch(async error=>{console.log(await page.locator('body').innerText(),errors);throw error;});
    await page.getByRole('button',{name:'选择第 1 张标签作为对比标准'}).click();
    await page.getByRole('group',{name:'实物图片来源'}).getByRole('button',{name:'图片',exact:true}).click();
    await page.locator('.text-compare-actual-panel input[type=file]').setInputFiles({name:'fixture.svg',mimeType:'image/svg+xml',buffer:Buffer.from(svg)});
    assert.equal(await page.getByRole('button',{name:'选择下一张',exact:true}).count(),0);
    assert.equal(await page.getByRole('button',{name:'提取框内标签',exact:true}).count(),0);
    const start=page.locator('.text-compare-actual-panel').getByRole('button',{name:'开始文字对比',exact:true});
    await start.click();
    await page.getByRole('button',{name:'提取文字…',exact:true}).waitFor();
    await page.getByRole('button',{name:'查看元素 e1: MODEL TEST',exact:true}).click();
    await page.getByText('实拍：MODEL TEST',{exact:true}).waitFor();
    await page.getByRole('button',{name:'选择下一张',exact:true}).waitFor();
    assert.equal(submitted,1);assert.equal(polls,1);assert.equal(extractionRequests,0);
    assert.equal(await page.locator('.text-compare-raw-output').getAttribute('open'),null);
    await page.screenshot({path:path.join(output,'desktop.png'),fullPage:true});
    await page.setViewportSize({width:390,height:844});
    await page.screenshot({path:path.join(output,'mobile.png'),fullPage:true});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true);
    asset.active_preparation=undefined;
    await page.reload();
    await page.getByRole('button',{name:/OCR evidence fixture/}).click();
    await page.getByRole('button',{name:'选择第 1 张标签作为对比标准'}).click();
    await page.getByText('此标准尚无元素模板，请在左侧启用标准并完成准备；不需要对实拍图抠图。',{exact:true}).waitFor();
    assert.equal(await page.getByRole('button',{name:'开始文字对比',exact:true}).isDisabled(),true);
    assert.equal(submitted,1);assert.equal(extractionRequests,0);
    assert.deepEqual(errors,[]);console.log(output);
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
