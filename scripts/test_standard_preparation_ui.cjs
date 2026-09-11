// Real page, isolated HTTP fixture; never writes production or invokes models.
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
    let starts=0;
    const standard={id:'std',name:'标准准备测试',material_code:'TEST',version_label:'V1',standard_type:'label',status:'draft',asset_count:1,revision_number:0};
    const asset={id:'asset',standard_id:'std',asset_kind:'label_candidate',ordinal:1,status:'candidate',content_url:'/fixture/original',comparison_ready:false};
    const elements=[{id:'e1',text:'MODEL ABC',type:'text',box:[.1,.3,.5,.2],state:'keep',reason:'标签内'}];
    let progress={job:{state:'completed'},items:[]};
    await page.route('**/fixture/*', route=>route.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="600" height="500"><rect width="600" height="500" fill="white"/><rect x="70" y="120" width="420" height="300" fill="#222"/><text x="110" y="240" fill="white" font-size="30">MODEL ABC</text></svg>'}));
    await page.route('**/api/**', route=>{
      const req=route.request(), url=new URL(req.url()).pathname;
      if (!url.startsWith('/api/')) return route.continue();
      if(url.endsWith('/preparation-capabilities')) return route.fulfill({json:{enabled:true,ocr_available:true}});
      if(url.endsWith('/extraction-capabilities')) return route.fulfill({json:{enabled:false}});
      if(url==='/api/text-inspection/standards') return route.fulfill({json:{items:[standard]}});
      if(url.endsWith('/preparation/asset/confirm')) {
        const body=req.postDataJSON(); assert.equal(body.expected_draft,'p1'); assert.equal(body.elements[0].text,'MODEL XYZ');
        progress.items[0].active='p2'; return route.fulfill({json:{published:true,revision:'p2'}});
      }
      if(req.method()==='POST' && url.endsWith('/confirm')) {
        starts++; standard.status='confirmed'; standard.revision_number=1; standard.current_revision_id='r1';
        asset.content_url='/fixture/clean'; asset.comparison_ready=true; asset.active_preparation={id:'p1',sha256:'test'};
        progress={job:{state:'completed'},items:[{id:'asset',ordinal:1,source_sha256:'source',original_url:'/fixture/original',draft:'p1',active:'p1',attempt:{state:'ready',elements,diagnostics:{fake:true}},revisions:[{id:'p1',elements,clean_url:'/fixture/clean',overlay_url:'/fixture/overlay',reasons:[],human:false}]}]};
        return route.fulfill({json:standard});
      }
      if(url.endsWith('/preparation')) return route.fulfill({json:progress});
      if(url.endsWith('/std')) return route.fulfill({json:{...standard,assets:[asset]}});
      return route.fulfill({status:404,json:{detail:'fixture only'}});
    });
    await page.goto((process.env.REVIEW_UI_BASE||'http://127.0.0.1:5189')+'/tests/document-review.html');
    await page.screenshot({path:path.join(output,'initial.png'),fullPage:true});
    console.log('UI evidence',output);
    console.log('Initial page', (await page.locator('body').innerText()).slice(0,1200),errors);
    await page.getByRole('button',{name:/标准准备测试/}).click();
    await page.getByRole('button',{name:/确认保留.*并启用/}).click();
    await page.getByText(/第 1 张 · 已准备并启用/).click();
    assert.equal(starts,1);
    await page.screenshot({path:path.join(output,'desktop-ready.png'),fullPage:true});
    await page.getByRole('button',{name:'确认修改并启用新版本'}).isDisabled().then(v=>assert.equal(v,true));
    await page.getByLabel('识别内容',{exact:true}).fill('MODEL XYZ');
    await page.getByRole('checkbox').check();
    await page.getByRole('button',{name:'确认修改并启用新版本'}).click();
    await page.reload();
    await page.getByRole('button',{name:/标准准备测试/}).click();
    await page.getByText(/第 1 张 · 已准备并启用/).waitFor();
    assert.equal(starts,1,'reload does not re-submit');
    await page.setViewportSize({width:390,height:844});
    await page.getByText(/第 1 张 · 已准备并启用/).click();
    await page.screenshot({path:path.join(output,'mobile-review.png'),fullPage:true});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'no horizontal overflow');
    assert.deepEqual(errors,[]);
    fs.writeFileSync(path.join(output,'result.json'),JSON.stringify({passed:true,starts,scope:'mock HTTP; real React UI'},null,2));
    console.log(output);
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
