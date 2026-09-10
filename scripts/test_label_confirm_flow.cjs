// Real page integration with isolated HTTP fixtures; no production writes/model calls.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const { expect } = require((process.env.PLAYWRIGHT_MODULE || 'playwright') + '/test');
const output = process.env.REVIEW_UI_OUTPUT;
if (!output) throw new Error('Set REVIEW_UI_OUTPUT');
fs.mkdirSync(output, { recursive: true });
(async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const errors = []; page.on('pageerror', e => {errors.push(e.message); console.error(e.message);});
    const standard = { id:'order', name:'流程测试订单', material_code:'TEST', version_label:'V1', standard_type:'label', status:'draft', revision_number:1, asset_count:2 };
    const assets = [1,2].map(i=>({id:`asset-${i}`, ordinal:i, standard_id:'order', status:'candidate', category:'label_design', content_url:'/fixture.svg'}));
    let extraction, comparisons = 0, creates = 0;
    const revisions = [];
    await page.route('**/fixture.svg', route => route.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="600" height="400"><rect width="600" height="400" fill="#ddd"/><rect x="120" y="80" width="360" height="240" fill="#164a31"/><text x="180" y="220" fill="white" font-size="36">TEST 20V</text></svg>'}));
    await page.route('**/api/**', async route => {
      const req=route.request(), url=new URL(req.url());
      if (!url.pathname.startsWith('/api/')) return route.continue();
      const reply=json=>route.fulfill({json});
      if(url.pathname.endsWith('/extraction-capabilities')) return reply({enabled:true,ai_available:false});
      if(url.pathname==='/api/text-inspection/standards') return reply({items:[standard]});
      if(url.pathname.endsWith('/order/confirm')) {standard.status='confirmed'; return reply(standard);}
      if(url.pathname.endsWith('/standards/order')) return reply({...standard,assets});
      if(url.pathname==='/api/text-inspection/extractions') {
        creates++; extraction={id:'ext',root_id:'ext',version:0,status:'needs_adjustment',polygon:[],media:{source:'/fixture.svg'}};
        return reply(extraction);
      }
      if(url.pathname.endsWith('/revise')) {
        const body=req.postDataJSON(); assert.equal(body.version,extraction.version);
        if(body.confirm) {assert.equal(standard.status,'confirmed'); assert.ok(body.standard_asset_id);}
        revisions.push(body); extraction={...extraction,id:`ext_v${extraction.version+1}`,version:extraction.version+1,polygon:body.polygon,status:body.confirm?'confirmed':'ready',media:{source:'/fixture.svg',crop:'/fixture.svg'}};
        return reply(extraction);
      }
      if(url.pathname.endsWith('/label/compare')) {
        const body=req.postData(); assert.ok(body.includes(extraction.id)); assert.ok(!body.includes('name="captured_file"'));
        assert.equal(extraction.status,'confirmed'); comparisons++;
        return reply({comparison_id:'cmp_'+extraction.id,decision:'MATCH',message:'模拟接口：流程通过，不是模型准确性验收',differences:[]});
      }
      return route.fulfill({status:404,json:{detail:'unhandled fixture'}});
    });
    await page.goto(`${process.env.REVIEW_UI_BASE || 'http://127.0.0.1:5181'}/tests/document-review.html`);
    await page.screenshot({path:path.join(output,'flow-loading.png'),fullPage:true});
    await page.getByRole('button',{name:'图片',exact:true}).click();
    const png=await page.evaluate(()=>{const c=document.createElement('canvas');c.width=600;c.height=400;return c.toDataURL().split(',')[1];});
    await page.locator('input[type=file]').setInputFiles({name:'actual.png',mimeType:'image/png',buffer:Buffer.from(png,'base64')});
    await page.getByRole('button',{name:'手动描边',exact:true}).click();
    await page.getByRole('button',{name:'四角轮廓',exact:true}).click();
    const confirm=page.getByRole('button',{name:'确认标签并对比',exact:true});
    await expect(confirm).toBeDisabled();
    await page.getByRole('button',{name:'保存轮廓并预览',exact:true}).click();
    await expect(page.locator('#label-confirmation-help')).toContainText('展开一个标签订单');
    await page.screenshot({path:path.join(output,'crop-ready-no-standard.png'),fullPage:true});
    await page.getByRole('button',{name:/流程测试订单/}).click();
    await expect(page.locator('#label-confirmation-help')).toContainText('订单尚未启用');
    await page.getByRole('button',{name:/确认保留.*并启用/}).click();
    await expect(page.locator('#label-confirmation-help')).toContainText('用作对比标准');
    await page.getByRole('button',{name:'用作对比标准',exact:true}).first().click();
    await expect(confirm).toBeEnabled();
    await expect(page.locator('.label-crop-preview img')).toHaveCount(1);
    await confirm.click();
    await expect(page.getByText('未发现文字差异',{exact:true})).toBeVisible();
    assert.equal(comparisons,1); assert.equal(revisions.at(-1).standard_asset_id,'asset-1');
    await page.getByRole('button',{name:'用作对比标准',exact:true}).click();
    await expect(page.locator('.text-compare-result')).toHaveCount(0);
    await expect(page.locator('.label-crop-preview img')).toHaveCount(1);
    await page.getByRole('button',{name:'圆形轮廓',exact:true}).click();
    await expect(confirm).toBeDisabled();
    await expect(page.locator('#label-confirmation-help')).toContainText('轮廓已修改');
    await page.getByRole('button',{name:'保存轮廓并预览',exact:true}).click();
    await expect(confirm).toBeEnabled(); await confirm.click();
    await expect(page.getByText('未发现文字差异',{exact:true})).toBeVisible();
    assert.equal(comparisons,2); assert.equal(revisions.at(-1).standard_asset_id,'asset-2');
    assert.equal(creates,1); assert.deepEqual(errors,[]);
    await page.screenshot({path:path.join(output,'confirmed-comparison.png'),fullPage:true});
    fs.writeFileSync(path.join(output,'flow-result.json'),JSON.stringify({passed:true,fixture_api:true,real_model_calls:0,creates,comparisons,checks:['missing order','draft activation','explicit reference selection','crop preserved','saved revision confirms then compares','reference change','dirty contour gate']},null,2));
    console.log('Full label confirmation fixture: PASS',output);
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
