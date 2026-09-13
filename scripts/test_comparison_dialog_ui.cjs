// Synthetic HTTP only. No paid requests. The real React page exercises task lifetime.
const assert = require('node:assert/strict');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
(async () => {
  const browser = await chromium.launch({headless:true, channel:process.env.QWEN_TEST_BROWSER || undefined});
  try {
    const page = await browser.newPage({viewport:{width:1360,height:900}});
    const errors=[]; page.on('pageerror', e=>errors.push(e.message));
    const base=process.env.REVIEW_UI_BASE || 'http://127.0.0.1:5189/react-preview';
    const svg='<svg xmlns="http://www.w3.org/2000/svg" width="400" height="200"><rect width="400" height="200" fill="white"/></svg>';
    const standard={id:'std',name:'Dialog fixture',material_code:'TEST',version_label:'1',standard_type:'label',status:'confirmed',asset_count:1};
    const asset={id:'asset',standard_id:'std',asset_kind:'label_candidate',ordinal:1,status:'candidate',content_url:'/fixture/source',comparison_ready:true,active_preparation:{id:'prep',sha256:'fixture'}};
    let submitted=0, polls=0, state='attempting', failure=0, held=false, lookupMissing=false, identity='';
    let releasePost;
    const result=()=>({id:'record',comparison_id:identity,preparation_compare:true,status:state,decision:'REVIEW_REQUIRED',differences:[],message:state==='review_required'?'任务超时，请复核':'测试结果',diagnostics:{phase:state==='attempting'?'extracting_text':state}});
    await page.route('**/fixture/**', r=>r.fulfill({contentType:'image/svg+xml',body:svg}));
    await page.route('**/api/**', async r=>{
      const url=new URL(r.request().url()).pathname;
      if(!url.startsWith('/api/')) return r.continue();
      if(url.endsWith('/preparation-capabilities')) return r.fulfill({json:{enabled:true,ocr_available:true}});
      if(url==='/api/text-inspection/standards') return r.fulfill({json:{items:[standard]}});
      if(url==='/api/text-inspection/standards/std') return r.fulfill({json:{...standard,assets:[asset]}});
      if(url.endsWith('/preparation')) return r.fulfill({json:{job:{},items:[]}});
      if(url.endsWith('/label/compare')) {
        submitted++; identity=r.request().postData().match(/name="comparison_id"\r\n\r\n([^\r]+)/)[1];
        if(held) await new Promise(resolve=>releasePost=resolve);
        return r.fulfill({json:result()}).catch(()=>{});
      }
      if(url.includes('/media/')) return r.fulfill({contentType:'image/svg+xml',body:svg});
      if(url.includes('/prepared-comparisons/')) {
        polls++;
        if(failure===1) return r.abort('failed');
        if(failure) return r.fulfill({status:failure,json:{detail:'test permission'}});
        if(lookupMissing && url.includes('/by-request/')) return r.fulfill({status:404,json:{detail:'missing'}});
        return r.fulfill({json:result()});
      }
      return r.fulfill({status:404,json:{detail:'fixture'}});
    });
    const dialog=page.locator('.comparison-dialog');
    const close=()=>page.getByRole('button',{name:'关闭对比窗口'}).click();
    const main=page.locator('.text-compare-primary');
    async function fresh() {
      state='attempting'; failure=0; held=false; lookupMissing=false;
      await page.evaluate(()=>sessionStorage.clear()); await page.reload();
      await page.getByRole('button',{name:/Dialog fixture/}).click();
      await page.getByRole('button',{name:'选择第 1 张标签作为对比标准'}).click();
      await page.getByRole('group',{name:'实物图片来源'}).getByRole('button',{name:'图片',exact:true}).click();
      await page.locator('.text-compare-actual-panel input[type=file]').setInputFiles({name:'test.svg',mimeType:'image/svg+xml',buffer:Buffer.from(svg)});
    }
    await page.goto(base+'/tests/document-review.html');
    await page.waitForFunction(()=>typeof window.fixtureEstimatedProgress==='function');
    const progress=await page.evaluate(()=>[0,10,30,60,120,1000].map(window.fixtureEstimatedProgress));
    assert.deepEqual(progress,[1,35,70,90,95,95]);
    await fresh(); await main.click(); await dialog.waitFor({state:'visible'});
    await page.getByText('提取文字',{exact:true}).waitFor();
    assert.match(await dialog.innerText(),/进度为估算/);
    await page.mouse.click(2,2); assert.equal(await dialog.isVisible(),true,'backdrop does not close');
    await page.keyboard.press('Tab'); assert.equal(await page.evaluate(()=>!!document.activeElement.closest('dialog')),true);
    await close(); assert.equal(await main.evaluate(el=>el===document.activeElement),true,'focus restored');
    await main.click(); await page.keyboard.press('Escape'); assert.equal(await dialog.isVisible(),false);
    const first=submitted, before=polls;
    await page.waitForTimeout(1700); assert.ok(polls>before,'closed modal still polls');
    await page.reload(); assert.equal(await dialog.isVisible(),false,'closed survives refresh');
    await main.click(); await page.getByText('提取文字',{exact:true}).waitFor();
    await page.reload(); await dialog.waitFor({state:'visible'});
    failure=1; await page.getByText(/连接中断，正在恢复查询/).waitFor();
    failure=401; await page.getByText(/登录已过期/).waitFor();
    failure=0; await page.getByText('提取文字',{exact:true}).waitFor();
    await close(); state='completed'; await page.getByRole('button',{name:'查看结果',exact:true}).waitFor();
    assert.equal(await dialog.isVisible(),false,'completion does not reopen');
    await main.click(); await dialog.getByText('100% · 结果已保存').waitFor();
    await page.reload(); await dialog.getByText('测试结果',{exact:true}).waitFor();
    assert.equal(submitted,first,'close/reopen/reload/login/network never resubmit');
    await close(); await page.getByRole('button',{name:'选择下一张',exact:true}).click();
    assert.equal(await main.innerText(),'开始文字对比');
    // Upload accepted by server, browser has no record ID; restore through request lookup.
    await fresh(); held=true; await main.click(); await page.waitForFunction(()=>JSON.parse(sessionStorage.getItem('text-comparison:v1:fixture-owner')).requestId);
    await page.waitForTimeout(200); await page.reload(); await page.getByText('提取文字',{exact:true}).waitFor();
    assert.ok(await page.evaluate(()=>JSON.parse(sessionStorage.getItem('text-comparison:v1:fixture-owner')).recordId));
    releasePost(); const second=submitted;
    // Stored progress elapsed time is not reset to zero after refresh.
    await page.evaluate(()=>{const k='text-comparison:v1:fixture-owner',t=JSON.parse(sessionStorage.getItem(k));t.startedAt=Date.now()-180000;sessionStorage.setItem(k,JSON.stringify(t));});
    await page.reload(); await dialog.getByText('95%',{exact:true}).waitFor();
    state='review_required'; await dialog.getByText('任务超时，请复核',{exact:true}).waitFor();
    assert.equal(await dialog.getByText('100% · 结果已保存').count(),0);
    assert.equal(submitted,second);
    // No upload survived: explicit missing-file error, never auto-upload.
    await close();
    await page.evaluate(()=>{const k='text-comparison:v1:fixture-owner',t=JSON.parse(sessionStorage.getItem(k));delete t.recordId;t.open=true;sessionStorage.setItem(k,JSON.stringify(t));});
    lookupMissing=true; await page.reload(); await page.getByText(/服务器未找到本次任务/).waitFor();
    assert.equal(submitted,second);
    // Switching account cannot recover another owner's task or display its evidence.
    await page.evaluate(()=>sessionStorage.setItem('fixture-owner','other-owner')); await page.reload();
    assert.equal(await dialog.count(),0); assert.equal(await main.innerText(),'开始文字对比');
    // Explicit inaccessible record; stop polling (not a retry storm).
    await fresh(); await main.click(); await page.getByText('提取文字',{exact:true}).waitFor();
    failure=403; await page.getByText(/当前账户无法访问/).waitFor();
    const blockedPolls=polls; await page.waitForTimeout(1800); assert.equal(polls,blockedPolls);
    // Switching standard invalidates the old response. No old result may replace it.
    await fresh(); held=true; await main.click(); await dialog.waitFor({state:'visible'}); await close();
    await page.getByRole('button',{name:/Dialog fixture/}).click();
    releasePost(); await page.waitForTimeout(1700);
    assert.equal(await dialog.count(),0); assert.equal(await main.innerText(),'开始文字对比');
    assert.deepEqual(errors,[]);
    console.log('PASS: dialog lifecycle, request recovery, progress, timeout, network/auth, account and stale isolation; POSTs='+submitted);
  } finally { await browser.close(); }
})().catch(e=>{console.error(e);process.exitCode=1;});
