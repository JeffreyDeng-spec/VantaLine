// Real app/router with isolated API fixtures. No production, model or device I/O.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawn } = require('node:child_process');
const frontend = path.resolve(__dirname, '../local_inspection_service/frontend');
const { chromium } = require(path.join(frontend, 'node_modules/playwright'));
const output = process.env.NAVIGATION_UI_OUTPUT || fs.mkdtempSync(path.join(os.tmpdir(), 'vantaline-navigation-ui-'));
fs.mkdirSync(output, { recursive: true });
console.log('Navigation test artifacts: '+output);
const base = 'http://127.0.0.1:5184';
const vite = spawn(process.execPath, [path.join(frontend, 'node_modules/vite/bin/vite.js'), '--host', '127.0.0.1', '--port', '5184', '--strictPort', '--base', '/'], { cwd: frontend, env: { ...process.env, VITE_ROUTER_BASENAME: '/' }, stdio: 'pipe' });
let startupError = '';
vite.stderr.on('data', b => { startupError += b; });
let browser;
(async () => {
  for (let i = 0; i < 150; i++) {
    if (vite.exitCode !== null) throw new Error(startupError || 'Vite exited');
    try { if ((await fetch(base)).ok) break; } catch {}
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce' });
  const page = await context.newPage();
  page.setDefaultTimeout(15000);
  const errors = [], writes = [], requests = [];
  context.on('page', p => p.on('pageerror', e => errors.push(e.message)));
  page.on('pageerror', e => { errors.push(e.message); console.error(e.message); });
  let user = null, authUnavailable = true, logoutFails = false, expireStatus = false;
  await context.route('**/static/brand-logo.png?*', route => route.fulfill({ contentType: 'image/png', path: path.join(frontend, '../static/brand-logo.png') }));
  const makeUser = (username, permissions = ['inspection']) => ({ id: username, username, display_name: username, role: 'user', permissions });
  await context.addInitScript(() => {
    window.__deviceCalls = 0;
    if (navigator.mediaDevices) navigator.mediaDevices.getUserMedia = async () => { window.__deviceCalls++; throw new Error('Unexpected camera access'); };
  });
  await context.route('**/api/**', async route => {
    const req = route.request(), url = new URL(req.url());
    if (!url.pathname.startsWith('/api/')) return route.continue();
    requests.push(url.pathname);
    const reply = (json, status = 200) => route.fulfill({ status, json });
    if (req.method() !== 'GET') writes.push(url.pathname);
    if (url.pathname === '/api/auth/status') return authUnavailable ? reply({ detail: 'Test auth unavailable' }, 503) : reply({ authenticated: !!user, setup_required: false, user });
    if (url.pathname === '/api/auth/login') { user = makeUser(req.postDataJSON().username); return reply({ user }); }
    if (url.pathname === '/api/auth/logout') { if (logoutFails) return reply({ detail: 'Test logout failed' }, 503); user = null; return reply({ status: 'ok' }); }
    if (url.pathname === '/api/version') return reply({ release: 'v-test', git_commit: 'fixture-commit', built_at: '2026-09-11T00:00:00Z', consistent: true });
    if (!user) return reply({ detail: 'Authentication required' }, 401);
    if (url.pathname === '/api/status') { if (expireStatus) { user = null; return reply({ detail: 'Authentication required' }, 401); } return reply({ service: 'running', model_exists: false }); }
    if (url.pathname === '/api/user/preferences/tasks') return reply({ exists: true, pinned_task_ids: [], archived_task_ids: [] });
    if (url.pathname === '/api/config/summary') return reply({ confidence_threshold: 0.5 });
    if (url.pathname.endsWith('/extraction-capabilities')) return reply({ enabled: false, ai_available: false });
    if (url.pathname === '/api/text-inspection/standards') return reply({ items: [{ id: 'standard-'+user.id, name: '订单-'+user.id, standard_type: 'label', status: 'confirmed', asset_count: 1, revision_number: 1 }] });
    if (url.pathname === '/api/pipeline/tasks') return reply({ items: [] });
    if (url.pathname === '/api/training/resources') return reply({ ai_detection_tasks: [] });
    return reply({ items: [], enabled: false, configured: false });
  });
  // Public routes work even when authentication is unavailable, and never query it.
  await page.goto(base+'/');
  await page.locator('#hero-title').waitFor();
  await page.waitForFunction(() => Number(getComputedStyle(document.querySelector('.hero-visual')).opacity) === 1);
  assert.equal(requests.length, 0);
  await page.screenshot({ path: path.join(output, '01-public-desktop.png'), fullPage: false });
  await page.getByRole('link', { name: '使用文档', exact: true }).first().click();
  await page.getByRole('heading', { name: '从第一张图片开始' }).waitFor();
  await page.getByRole('link', { name: '常见问题', exact: true }).focus();
  await page.keyboard.press('Enter');
  assert.equal(new URL(page.url()).hash, '#help');
  const help = page.getByText('提示没有配置 Key，怎么办？', { exact: true });
  await help.focus(); await page.keyboard.press('Enter');
  assert.equal(await help.evaluate(el => el.parentElement.open), true);
  await page.evaluate(() => scrollTo(0, 0));
  assert.equal(requests.length, 0);
  await page.screenshot({ path: path.join(output, '02-documentation.png'), fullPage: true });
  // Auth failure stays a retryable error, not a landing-page detour.
  await page.goto(base+'/workspace/about');
  await page.getByRole('button', { name: '重试', exact: true }).waitFor();
  assert.equal(new URL(page.url()).pathname, '/workspace/about');
  authUnavailable = false;
  await page.getByRole('button', { name: '重试', exact: true }).click();
  await page.getByLabel('Workspace username').waitFor();
  assert.equal(new URL(page.url()).searchParams.get('next'), '/workspace/about');
  // Old deep links migrate, including query/hash, before login.
  const target = '/workspace/text-compare-beta?order=fixture#photo';
  await page.goto(base+'/text-compare-beta?order=fixture#photo');
  await page.getByLabel('Workspace username').waitFor();
  assert.equal(new URL(page.url()).searchParams.get('next'), target);
  await page.getByLabel('Workspace username').fill('operator-a');
  await page.getByLabel('Password', { exact: true }).fill('test-password');
  await page.getByRole('button', { name: 'Continue to workspace' }).click();
  await page.getByRole('heading', { name: '文字检验', exact: true }).waitFor();
  assert.equal(page.url(), base+target);
  await page.getByText('订单-operator-a', { exact: true }).waitFor();
  assert.equal(await page.getByRole('link', { name: '文字检验', exact: true }).getAttribute('aria-current'), 'page');
  // Public resources live only inside About, not as duplicate sidebar links.
  assert.equal(await page.getByRole('link', { name: /产品官网|使用文档/ }).count(), 0);
  await page.getByRole('link', { name: '关于与帮助', exact: true }).click();
  await page.getByText('fixture-commit', { exact: true }).waitFor();
  assert.equal(await page.locator('.sidebar').getByRole('link', { name: /产品官网|使用文档/ }).count(), 0);
  // Both About cards open new tabs without replacing the About page.
  await page.evaluate(() => { window.__navigationSentinel = 'unsaved-work'; });
  for (const [name, destination, ready] of [
    ['使用文档', '/docs', 'h1'], ['产品官网', '/', '#hero-title']
  ]) {
    const link = page.locator('.about-resources').getByRole('link', { name: new RegExp(name) });
    assert.equal(await link.count(), 1);
    const popupWait = context.waitForEvent('page');
    await link.click();
    const popup = await popupWait;
    await popup.locator(ready).waitFor();
    assert.equal(new URL(popup.url()).pathname, destination);
    assert.equal(page.url(), base+'/workspace/about');
    assert.equal(await page.evaluate(() => window.__navigationSentinel), 'unsaved-work');
    assert.equal(await popup.evaluate(() => window.opener === null), true);
    await popup.close();
  }
  await page.screenshot({ path: path.join(output, '03-about-desktop.png'), fullPage: true });
  await page.reload();
  await page.getByText('fixture-commit', { exact: true }).waitFor();
  await page.goBack();
  await page.getByRole('heading', { name: '文字检验', exact: true }).waitFor();
  await page.goForward();
  await page.getByRole('heading', { name: '关于与帮助', exact: true }).waitFor();
  // Ordinary users can see About but cannot open administrator pages.
  await page.goto(base+'/workspace/users');
  await page.getByText('没有权限访问此页面', { exact: true }).waitFor();
  assert.equal(await page.getByRole('link', { name: '用户管理', exact: true }).count(), 0);
  // Failed logout does not claim success; successful logout stays on /login.
  logoutFails = true;
  await page.getByRole('button', { name: '退出登录', exact: true }).click();
  await page.getByText('退出登录未完成，请重试', { exact: true }).waitFor();
  assert.equal(new URL(page.url()).pathname, '/workspace/users');
  logoutFails = false;
  await page.getByRole('button', { name: '退出登录', exact: true }).click();
  await page.getByLabel('Workspace username').waitFor();
  assert.equal(new URL(page.url()).pathname, '/login');
  assert.equal(new URL(page.url()).search, '', 'explicit logout must discard the previous page return link');
  // Account change must not display the prior account's cached standard library.
  await page.getByLabel('Workspace username').fill('operator-b');
  await page.getByLabel('Password', { exact: true }).fill('test-password');
  await page.getByRole('button', { name: 'Continue to workspace' }).click();
  await page.getByRole('heading', { name: '总览', exact: true }).waitFor();
  await page.locator('.side-nav').getByRole('link', { name: '文字检验', exact: true }).click();
  await page.getByText('订单-operator-b', { exact: true }).waitFor();
  assert.equal(await page.getByText('订单-operator-a', { exact: true }).count(), 0);
  // Root stays public even when authenticated. Open app skips login.
  await page.goto(base+'/');
  await page.locator('#hero-title').waitFor();
  await page.getByRole('link', { name: '进入工作台', exact: true }).first().click();
  await page.getByRole('heading', { name: '总览', exact: true }).waitFor();
  assert.equal(new URL(page.url()).pathname, '/workspace');
  // Session expiration rechecks auth; no write is replayed.
  expireStatus = true;
  await page.getByRole('button', { name: '刷新', exact: true }).click();
  await page.getByLabel('Workspace username').waitFor();
  assert.equal(new URL(page.url()).searchParams.get('next'), '/workspace');
  expireStatus = false;
  // Safe next rejects external destinations.
  await page.goto(base+'/login?next='+encodeURIComponent('//evil.invalid'));
  await page.getByLabel('Workspace username').fill('operator-b');
  await page.getByLabel('Password', { exact: true }).fill('test-password');
  await page.getByRole('button', { name: 'Continue to workspace' }).click();
  await page.getByRole('heading', { name: '总览', exact: true }).waitFor();
  assert.equal(new URL(page.url()).pathname, '/workspace');
  for (const url of ['/no-such-page', '/workspace/no-such-page']) {
    await page.goto(base+url); await page.getByRole('heading', { name: '页面不存在', exact: true }).waitFor();
    assert.equal(new URL(page.url()).pathname, url);
  }
  await page.goto(base+'/tasks/pipeline%3Amissing/inspect?source=old#detail');
  await page.getByText('任务不存在或没有访问权限', { exact: true }).waitFor();
  assert.equal(new URL(page.url()).pathname, '/workspace/tasks/pipeline%3Amissing/inspect');
  assert.equal(new URL(page.url()).search, '?source=old');
  assert.equal(new URL(page.url()).hash, '#detail');
  // Narrow-screen docs, public navigation and About have no horizontal overflow.
  await page.setViewportSize({ width: 390, height: 844 });
  for (const [url, name] of [['/', '04-public-mobile'], ['/docs', '05-docs-mobile'], ['/workspace/about', '06-about-mobile']]) {
    await page.goto(base+url);
    if (url === '/') await page.locator('#hero-title').waitFor();
    else if (url === '/docs') await page.getByRole('heading', { name: '从第一张图片开始' }).waitFor();
    else await page.getByText('fixture-commit', { exact: true }).waitFor();
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth+1), true, url);
    await page.screenshot({ path: path.join(output, name+'.png'), fullPage: true });
  }
  assert.deepEqual(errors, []);
  assert.equal(await page.evaluate(() => window.__deviceCalls), 0);
  assert.ok(writes.every(url => ['/api/auth/login', '/api/auth/logout'].includes(url)), writes.join(', '));
  fs.writeFileSync(path.join(output, 'result.json'), JSON.stringify({ passed: true, assertions: 'public/auth/legacy/next/permissions/cache/expiry/mobile/no-device-write', writes, errors }, null, 2));
  console.log('navigation browser tests: passed; screenshots: '+output);
})().catch(async error => {
  console.error(error);
  if (browser) for (const context of browser.contexts()) for (const page of context.pages()) await page.screenshot({ path: path.join(output, 'failure.png'), fullPage: true }).catch(() => {});
  process.exitCode = 1;
}).finally(async () => { if (browser) await browser.close(); vite.kill('SIGTERM'); });
