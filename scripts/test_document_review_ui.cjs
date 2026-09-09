// Real React page with an in-memory API fixture, never a production write.
// Start frontend Vite with --host 127.0.0.1 --base /, then run this script.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const output = process.env.REVIEW_UI_OUTPUT;
if (!output) throw new Error('Set REVIEW_UI_OUTPUT to a test-artifact directory');
fs.mkdirSync(output, { recursive: true });
(async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
    const errors = [];
    page.on('pageerror', e => { errors.push(e.message); console.error('Browser error:', e.message); });
    const standard = { id: 'test-standard', name: '测试订单（模拟数据）', material_code: 'REVIEW-TEST', version_label: 'V1', standard_type: 'label', status: 'draft', asset_count: 3, revision_number: 0 };
    const assets = ['candidate', 'needs_confirmation', 'excluded'].map((status, i) => ({ id: `asset-${i}`, standard_id: standard.id, asset_kind: 'label_candidate', ordinal: i+1, status, category: i === 2 ? 'physical_photo' : 'label_design', classification_source: 'vlm', classification_reason: '这是测试分类依据，不是本次模型识别结果。', content_url: `/review-media/${i}` }));
    let rejectNext = false;
    const mutations = [];
    await page.route('**/review-media/*', route => {
      const i = Number(route.request().url().split('/').pop());
      const fixtureDir = process.env.REVIEW_IMAGE_FIXTURES;
      if (fixtureDir) return route.fulfill({ contentType: 'image/jpeg', path: path.join(fixtureDir, ['doc1-image003', 'doc1-image001', 'doc2-image023'][i], 'input.jpg') });
      return route.fulfill({ contentType: 'image/svg+xml', body: `<svg xmlns="http://www.w3.org/2000/svg" width="400" height="240"><rect width="400" height="240" fill="white"/><rect x="50" y="40" width="300" height="160" fill="#21382c"/><text x="90" y="125" fill="white" font-size="28">TEST LABEL ${i+1}</text></svg>` });
    });
    await page.route('**/api/**', async route => {
      const req = route.request(); const url = new URL(req.url());
      if (!url.pathname.startsWith('/api/')) return route.continue();
      if (url.pathname.endsWith('/extraction-capabilities')) return route.fulfill({ json: { enabled: false, ai_available: false } });
      if (url.pathname === '/api/text-inspection/standards') return route.fulfill({ json: { items: [standard] } });
      if (req.method() === 'PATCH') {
        if (rejectNext) { rejectNext = false; return route.fulfill({ status: 409, json: { detail: '模拟保存冲突，请刷新后重试' } }); }
        const { action } = req.postDataJSON();
        const asset = assets.find(x => url.pathname.endsWith('/'+x.id)); assert.ok(asset);
        asset.status = { confirm: 'candidate', remove: 'excluded', review: 'needs_confirmation' }[action];
        asset.classification_source = 'human'; mutations.push(action);
        return route.fulfill({ json: { ...asset, standard } });
      }
      if (url.pathname.endsWith('/confirm')) { assert.ok(!assets.some(x => x.status === 'needs_confirmation')); standard.status = 'confirmed'; return route.fulfill({ json: standard }); }
      if (url.pathname.endsWith('/test-standard')) return route.fulfill({ json: { ...standard, assets } });
      return route.fulfill({ status: 404, json: { detail: 'No test fixture for this request' } });
    });
    await page.goto(`${process.env.REVIEW_UI_BASE || 'http://127.0.0.1:5173'}/tests/document-review.html`);
    await page.screenshot({ path: path.join(output, 'loading-debug.png'), fullPage: true });
    await page.getByRole('button', { name: /测试订单/ }).click();
    const picker = i => page.getByRole('combobox', { name: `第 ${i} 张图片分类` });
    await picker(1).waitFor();
    assert.equal(await page.locator('.text-standard-asset-card').count(), 3);
    assert.equal(await page.getByRole('button', { name: /确认保留.*并启用/ }).isDisabled(), true);
    await page.screenshot({ path: path.join(output, 'desktop-three-states.png'), fullPage: true });
    await page.getByRole('button', { name: '待定 1', exact: true }).click();
    assert.equal(await page.locator('.text-standard-asset-card').count(), 1);
    await picker(2).selectOption('candidate');
    await page.getByText('这个分类下暂无图片').waitFor();
    await page.getByRole('button', { name: '查看全部图片', exact: true }).click();
    await picker(3).selectOption('candidate');
    await page.getByRole('button', { name: '标签 3', exact: true }).waitFor();
    rejectNext = true;
    await picker(1).selectOption('excluded');
    await page.getByText('模拟保存冲突，请刷新后重试').first().waitFor();
    assert.equal(await picker(1).inputValue(), 'candidate');
    await picker(1).selectOption('needs_confirmation');
    await page.getByRole('button', { name: '待定 1', exact: true }).waitFor();
    await picker(1).selectOption('excluded');
    await page.getByRole('button', { name: '非标签 1', exact: true }).waitFor();
    assert.equal(await page.getByRole('button', { name: /确认保留.*并启用/ }).isEnabled(), true);
    await page.reload();
    await page.getByRole('button', { name: /测试订单/ }).click();
    assert.equal(await picker(1).inputValue(), 'excluded');
    assert.equal(await picker(3).inputValue(), 'candidate');
    await page.getByRole('button', { name: '查看大图', exact: true }).first().click();
    await page.getByRole('dialog').waitFor();
    assert.equal(await page.locator('.text-compare-lightbox img').evaluate(img => getComputedStyle(img).filter), 'none');
    await page.getByRole('button', { name: '关闭放大预览' }).click();
    await page.setViewportSize({ width: 390, height: 844 });
    await page.screenshot({ path: path.join(output, 'mobile-reviewed.png'), fullPage: true });
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth);
    assert.equal(overflow, false, 'no page-wide horizontal overflow');
    await page.getByRole('button', { name: /确认保留.*并启用/ }).click();
    await page.getByText('已启用', { exact: true }).waitFor();
    assert.equal(standard.status, 'confirmed');
    assert.deepEqual(mutations, ['confirm', 'confirm', 'review', 'remove']);
    assert.deepEqual(errors, []);
    fs.writeFileSync(path.join(output, 'result.json'), JSON.stringify({ passed: true, fixture_api: true, real_model_calls: 0, checks: ['three states', 'pending blocks confirmation', 'filter empty state', 'manual restore', 'failure preserves state', 'mark pending', 'exclude', 'reload', 'undimmed zoom', 'mobile overflow', 'explicit activation'], mutations }, null, 2));
    console.log('Document review UI checks passed; screenshots:', output);
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exitCode = 1; });
