// Synthetic API, real React. History never writes or starts paid work.
const assert = require('node:assert/strict');
const fs = require('node:fs'); const os = require('node:os'); const path = require('node:path');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
(async()=>{
  const output=fs.mkdtempSync(path.join(os.tmpdir(),'comparison-history-ui-'));
  const browser=await chromium.launch({headless:true,channel:process.env.QWEN_TEST_BROWSER || undefined});
  try {
    const page=await browser.newPage({viewport:{width:1360,height:900}});
    const errors=[]; page.on('pageerror',e=>{errors.push(e.message);console.error(e.message);});
    const svg='<svg xmlns="http://www.w3.org/2000/svg" width="400" height="240"><rect width="400" height="240" fill="white"/><text x="40" y="90">MODEL TEST</text></svg>';
    let writes=0,logs=0,originals=0,activePolls=0,listQueries=0,otherAccount=false;
    const summaries=Array.from({length:25},(_,i)=>({id:`ins_${i}`,standard_id:'std',created_at:1700000000-i,status:'completed',decision:'REVIEW_REQUIRED',standard_revision_number:1,display:{name:`测试订单 ${i}`,material_code:'TEST',version_label:'V1',ordinal:1},metadata_source:'snapshot',execution_state:i===2?'failed':'completed',preview_url:`/api/text-inspection/history/ins_${i}/media/preview`}));
    const result=id=>({id,comparison_id:'current-request',status:'completed',decision:'REVIEW_REQUIRED',differences:[],message:'需要人工复核',reference_overlay_url:`/api/text-inspection/history/${id}/media/reference`,source_url:`/api/text-inspection/history/${id}/media/source`,source_preview_url:`/api/text-inspection/history/${id}/media/preview`,diagnostics_url:`/api/text-inspection/history/${id}/diagnostics`,history:summaries.find(r=>r.id===id),diagnostics:{provider:'qwen_ocr',normalized_response:{elements:[{element_id:'e1',expected:'MODEL TEST',standard_box:[.1,.2,.6,.3],state:'matched',reason:'exact_characters',evidence:[{evidence_id:'o1',start:0,end:10}]}],observations:[{id:'o1',type:'text',text:'MODEL TEST',box:[.1,.2,.7,.5]}]}}});
    await page.addInitScript(()=>{if(!sessionStorage.getItem('initialized')){sessionStorage.setItem('initialized','1');sessionStorage.setItem('text-comparison:v1:fixture-owner',JSON.stringify({owner:'fixture-owner',requestId:'current-request',recordId:'current',standardId:'std',assetId:'asset',photoId:'hash',startedAt:Date.now(),open:false}));}});
    await page.route('**/api/**',r=>{
      const req=r.request(), u=new URL(req.url()), p=u.pathname;
      if(!p.startsWith('/api/'))return r.continue();
      if(req.method()!=='GET'){writes++;return r.fulfill({status:500});}
      if(p==='/api/text-inspection/standards')return r.fulfill({json:{items:[]}});
      if(p.endsWith('/prepared-comparisons/current')){activePolls++;return r.fulfill({json:{...result('current'),status:'attempting',diagnostics:{phase:'extracting_text'}}});}
      if(p==='/api/text-inspection/history'){
        listQueries++; let items=otherAccount?[]:summaries;
        if(u.searchParams.get('q'))items=items.filter(x=>x.display.name.includes(u.searchParams.get('q')));
        if(u.searchParams.get('result')==='MATCH')items=[];
        const offset=u.searchParams.get('cursor')?20:0;
        return r.fulfill({json:{items:items.slice(offset,offset+20),next_cursor:items.length>offset+20?'next':null}});
      }
      if(p.endsWith('/diagnostics')){logs++;return r.fulfill({json:{...result('ins_0').diagnostics,provider_result:{parsed_response:{audit:'saved-only'}}}});}
      if(p.includes('/media/')){if(p.endsWith('/source')) originals++;return r.fulfill({contentType:'image/svg+xml',body:svg});}
      if(p.match(/\/history\/ins_\d+$/)){
        const id=p.split('/').pop();const value=result(id);
        if(id==='ins_1'){value.diagnostics={};value.history_warning='旧记录仅展示当时保存的证据';}
        return r.fulfill({json:value});
      }
      return r.fulfill({status:404,json:{detail:'fixture unavailable'}});
    });
    await page.goto((process.env.REVIEW_UI_BASE||'http://127.0.0.1:5189/react-preview')+'/tests/document-review.html');
    await page.getByRole('button',{name:'历史记录',exact:true}).click();
    await page.waitForTimeout(1700); // Current task polling must continue behind history.
    const dialog=page.getByRole('dialog',{name:'文字检验历史记录',exact:true});
    await dialog.locator('.text-history-row').last().waitFor();assert.equal(await dialog.locator('.text-history-row').count(),20);
    await dialog.getByRole('button',{name:'加载更多'}).click();await page.waitForFunction(()=>document.querySelectorAll('.text-history-row').length===25);
    await dialog.locator('.text-history-list').evaluate(el=>el.scrollTop=200);
    await dialog.locator('.text-history-row').nth(4).click();
    await page.getByRole('button',{name:'查看元素 e1: MODEL TEST'}).click();
    assert.equal(logs,0);assert.equal(originals,0);
    await page.getByRole('button',{name:'查看标准元素核对图'}).click();await page.getByRole('region',{name:'历史图片放大'}).waitFor();
    await page.keyboard.press('Escape');assert.equal(await page.getByRole('region',{name:'历史图片放大'}).count(),0);
    assert.equal(await page.getByRole('button',{name:'查看元素 e1: MODEL TEST'}).getAttribute('aria-pressed'),'true');
    await page.getByText('Raw Output（调试信息）',{exact:true}).click();await page.getByText('saved-only',{exact:false}).first().waitFor();assert.equal(logs,1);
    await page.getByRole('button',{name:'返回历史',exact:true}).click();assert.equal(await dialog.locator('.text-history-row').count(),25);
    assert.ok(await dialog.locator('.text-history-list').evaluate(el=>el.scrollTop>0));
    await dialog.getByRole('textbox',{name:'搜索订单或标准'}).fill('测试订单 1');await dialog.getByRole('button',{name:'搜索',exact:true}).click();
    await page.waitForFunction(()=>document.querySelectorAll('.text-history-row').length===11);
    await dialog.getByRole('combobox',{name:'按结果筛选'}).selectOption('MATCH');await dialog.getByText('暂无符合条件的对比记录').waitFor();
    await dialog.getByRole('combobox',{name:'按结果筛选'}).selectOption('all');await page.waitForFunction(()=>document.querySelectorAll('.text-history-row').length===11);
    await dialog.locator('.text-history-row').first().click();await page.getByText('旧记录仅展示当时保存的证据').waitFor();
    await page.screenshot({path:path.join(output,'desktop.png'),fullPage:true});
    await page.setViewportSize({width:390,height:844});await page.screenshot({path:path.join(output,'mobile.png'),fullPage:true});
    assert.ok(await page.getByRole('dialog',{name:'历史对比结果'}).evaluate(el=>el.scrollWidth<=el.clientWidth+1));
    await page.getByRole('button',{name:'返回历史',exact:true}).click();await page.screenshot({path:path.join(output,'mobile-list.png'),fullPage:true});
    await page.getByRole('button',{name:'关闭对比窗口',exact:true}).click();
    assert.equal(await page.getByRole('button',{name:'历史记录',exact:true}).evaluate(el=>el===document.activeElement),true);
    const active=await page.evaluate(()=>JSON.parse(sessionStorage.getItem('text-comparison:v1:fixture-owner')));
    assert.equal(active.recordId,'current');assert.equal(active.open,false);assert.ok(activePolls>0);assert.equal(writes,0);
    otherAccount=true;
    await page.evaluate(()=>sessionStorage.setItem('fixture-owner','other-owner'));
    await page.reload();await page.getByRole('button',{name:'历史记录',exact:true}).click();
    await page.getByText('暂无符合条件的对比记录').waitFor();
    assert.equal(await page.locator('.text-history-row').count(),0);
    assert.deepEqual(errors,[]);
    console.log(JSON.stringify({output,writes,logs,originals,activePolls,listQueries}));
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
