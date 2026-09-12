// Real React page with isolated HTTP; no production/model calls.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
(async () => {
  const output = fs.mkdtempSync(path.join(os.tmpdir(), 'standard-preparation-ui-'));
  const browser = await chromium.launch({headless:true});
  try {
    const page = await browser.newPage({viewport:{width:1440,height:1050}});
    const errors=[]; page.on('pageerror', e=>errors.push(e.message));
    let starts=0, saves=[], failSave=false;
    const standard={id:'std',name:'标准准备测试',material_code:'TEST',version_label:'V1',standard_type:'label',status:'draft',asset_count:2,revision_number:0};
    const assets=[1,2].map(n=>({id:`asset${n}`,standard_id:'std',asset_kind:'label_candidate',ordinal:n,status:'candidate',content_url:'/fixture/original',comparison_ready:false}));
    const elements=[{id:'e1',text:'MODEL ABC',type:'text',box:[.15,.4,.5,.1],state:'keep',reason:'标签内'},
      {id:'e2',text:'46.6mm',type:'text',box:[.15,.1,.3,.1],state:'uncertain',reason:'待定'}];
    let progress={job:{},items:[]};
    await page.route('**/fixture/*', route=>route.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="600" height="500"><rect width="600" height="500" fill="white"/><text x="95" y="80">46.6mm</text><rect x="70" y="120" width="420" height="300" fill="#222"/><text x="110" y="240" fill="white" font-size="30">MODEL ABC</text></svg>'}));
    await page.route('**/api/**', route=>{
      const req=route.request(), url=new URL(req.url()).pathname;
      if (!url.startsWith('/api/')) return route.continue();
      if(url.endsWith('/preparation-capabilities')) return route.fulfill({json:{enabled:true,ocr_available:true}});
      if(url.endsWith('/extraction-capabilities')) return route.fulfill({json:{enabled:false}});
      if(url==='/api/text-inspection/standards') return route.fulfill({json:{items:[standard]}});
      if(/\/preparation\/asset\d\/confirm$/.test(url)) {
        if(failSave) return route.fulfill({status:409,json:{detail:'测试保存失败'}});
        const id=url.split('/').at(-2), item=progress.items.find(i=>i.id===id), body=req.postDataJSON();
        assert.equal(body.expected_draft,item.draft); assert.equal(body.source_sha256,'source');
        assert(body.elements.every(e=>e.state!=='uncertain'));
        saves.push({id,body}); item.draft=`p${saves.length+10}`; item.active=item.draft;
        item.revisions.push({id:item.draft,elements:body.elements,clean_url:'/fixture/clean',reasons:[]});
        assets.find(a=>a.id===id).comparison_ready=true; standard.status='confirmed';
        return route.fulfill({json:{published:true,revision:item.draft}});
      }
      if(req.method()==='POST' && url.endsWith('/confirm')) {
        starts++;
        // Deliberately reverse API order: popup order must follow source ordinal.
        progress={job:{state:'completed'},items:[...assets].reverse().map(a=>({id:a.id,ordinal:a.ordinal,source_sha256:'source',original_url:'/fixture/original',draft:'p1',
          attempt:{state:'review',elements,diagnostics:{fake:true}},revisions:[{id:'p1',elements,clean_url:'/fixture/clean',reasons:['fixture-review']}]}))};
        return route.fulfill({json:standard});
      }
      if(url.endsWith('/preparation')) { assert.equal(req.method(),'GET','no separate prepare POST'); return route.fulfill({json:progress}); }
      if(url.endsWith('/std')) return route.fulfill({json:{...standard,assets}});
      return route.fulfill({status:404,json:{detail:'fixture only'}});
    });
    const dialog=n=>page.getByRole('dialog',{name:`第 ${n} 张标签元素确认`});
    const toggle=()=>page.getByRole('button',{name:/e2 46.6mm/});
    await page.goto((process.env.REVIEW_UI_BASE||'http://127.0.0.1:5189')+'/tests/document-review.html');
    await page.getByRole('button',{name:/标准准备测试/}).click().catch(async e => { console.log('Fixture failure', await page.locator('body').innerText(), errors); throw e; });
    assert.equal(await page.getByRole('button',{name:/准备并启用标准/}).count(),0);
    await page.getByRole('button',{name:/确认保留.*并启用/}).click();
    await dialog(1).waitFor();
    await page.getByRole('button',{name:'先看下一张'}).click(); await dialog(2).waitFor();
    await page.getByRole('button',{name:'先看下一张'}).click(); await dialog(1).waitFor();
    assert.equal(await page.getByRole('button',{name:'确认保存并继续'}).isDisabled(),true);
    await toggle().click(); assert.equal(await toggle().getAttribute('aria-pressed'),'true');
    await toggle().click(); assert.equal(await toggle().getAttribute('aria-pressed'),'false');
    await page.screenshot({path:path.join(output,'desktop-elements.png'),fullPage:true});
    failSave=true;
    await page.getByRole('button',{name:'确认保存并继续'}).click();
    await page.getByRole('alert').filter({hasText:'测试保存失败'}).waitFor();
    assert.equal(await toggle().getAttribute('aria-pressed'),'false','failed save keeps edit');
    failSave=false;
    await page.getByRole('button',{name:'确认保存并继续'}).click();
    await dialog(2).waitFor();
    await page.getByRole('button',{name:'稍后继续'}).click();
    await page.getByRole('button',{name:/继续确认/}).click(); await dialog(2).waitFor();
    await toggle().focus(); await page.keyboard.press('Enter'); await page.keyboard.press('Space');
    assert.equal(await toggle().getAttribute('aria-pressed'),'false','keyboard toggles');
    await page.getByRole('button',{name:'确认保存并继续'}).click();
    await page.getByRole('dialog').waitFor({state:'hidden'});
    assert.deepEqual(saves.map(s=>s.id),['asset1','asset2']); assert.equal(starts,1);
    // The gallery uses the same editor, with immutable draft checks.
    await page.getByRole('button',{name:'查看大图',exact:true}).first().click(); await dialog(1).waitFor();
    await toggle().click();
    await page.getByLabel('选中元素识别内容').fill('46.7mm');
    await page.getByRole('button',{name:'保存',exact:true}).click();
    await page.getByRole('dialog').waitFor({state:'hidden'});
    assert.equal(saves.at(-1).body.elements[1].text,'46.7mm');
    await page.reload(); await page.getByRole('button',{name:/标准准备测试/}).click();
    assert.equal(starts,1,'reload does not submit paid work');
    await page.setViewportSize({width:390,height:844});
    await page.getByRole('button',{name:'查看大图',exact:true}).first().click(); await dialog(1).waitFor();
    await page.getByRole('button',{name:'放大元素图'}).click();
    const imageBox=await page.getByAltText('标准原图与可点击元素框').boundingBox();
    const elementBox=await page.getByRole('button',{name:/e2 46.7mm/}).boundingBox();
    assert(Math.abs(elementBox.x-imageBox.x-imageBox.width*.15)<1,'overlay maps after zoom');
    await page.getByRole('button',{name:'查看已保存清理图'}).click();
    assert.equal(await page.locator('.standard-element-box').count(),0,'no source boxes on cropped preview');
    await page.getByRole('button',{name:'返回原图编辑'}).click();
    await page.getByRole('button',{name:/e2 46.7mm/}).waitFor();
    await page.screenshot({path:path.join(output,'mobile-editor.png'),fullPage:true});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
    await page.getByRole('button',{name:/e2 46.7mm/}).click();
    page.once('dialog',d=>d.dismiss()); await page.keyboard.press('Escape');
    await dialog(1).waitFor();
    page.once('dialog',d=>d.accept()); await page.keyboard.press('Escape');
    await page.getByRole('dialog').waitFor({state:'hidden'});
    // Reload while processing restores progress without resubmission; editing disabled.
    progress.job.state='processing'; progress.items[0].attempt.state='supplementing';
    await page.reload(); await page.getByRole('button',{name:/标准准备测试/}).click();
    await page.getByText(/启用中：/).waitFor();
    await page.getByRole('button',{name:'查看大图',exact:true}).nth(1).click(); await dialog(2).waitFor();
    assert.equal(await page.getByRole('button',{name:/e1 MODEL ABC/}).isDisabled(),true);
    assert.equal(await page.getByRole('button',{name:'保存',exact:true}).isDisabled(),true);
    assert.equal(starts,1); assert.deepEqual(errors,[]);
    fs.writeFileSync(path.join(output,'result.json'),JSON.stringify({passed:true,starts,saves:saves.length,scope:'mock HTTP; real React'},null,2));
    console.log(output);
  } finally { await browser.close(); }
})().catch(e=>{console.error(e);process.exit(1)});
