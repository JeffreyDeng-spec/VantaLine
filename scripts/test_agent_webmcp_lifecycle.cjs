// Real Chrome + the production adapter/registry, on a synthetic same-origin page.
// No API replacement, application account, external model or physical device.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('../local_inspection_service/frontend/node_modules/typescript');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const {waitForNativeTools} = require('./agent_browser_wait.cjs');
const origin = 'http://127.0.0.1:5199';
const sourceRoot = path.resolve(__dirname, '../local_inspection_service/frontend/src/features/agent');

(async () => {
  const browser = await chromium.launch({headless:true,
    ...(process.env.AGENT_CHROME_PATH ? {executablePath:process.env.AGENT_CHROME_PATH} : {}),
    args:['--enable-blink-features=WebMCP,WebMCPTesting']});
  try {
    const page = await browser.newPage();
    const errors = []; page.on('pageerror', error => errors.push(error.message));
    await page.route('**/*', route => {
      const url = new URL(route.request().url());
      if (url.origin !== origin) return route.abort();
      if (url.pathname === '/') return route.fulfill({contentType:'text/html', body:'<!doctype html><title>Native lifecycle fixture</title>'});
      const modules = {'/registry.js':'registry.ts', '/webmcpAdapter.js':'webmcpAdapter.ts', '/validation':'validation.ts'};
      if (!modules[url.pathname]) return route.fulfill({status:404,body:'Missing fixture'});
      const source = fs.readFileSync(path.join(sourceRoot, modules[url.pathname]), 'utf8');
      return route.fulfill({contentType:'text/javascript',body:ts.transpileModule(source, {
        compilerOptions:{module:ts.ModuleKind.ES2020,target:ts.ScriptTarget.ES2020}
      }).outputText});
    });
    await page.goto(origin);
    assert.equal(await page.evaluate(() => typeof document.modelContext?.registerTool), 'function');

    // Begin with no tools. A timeout must fail, even though getTools is async.
    await assert.rejects(waitForNativeTools(page, {present:['vantaline_context'],timeout:100}), /timed out/);
    await page.evaluate(async () => {
      const {ActionRegistry} = await import('/registry.js');
      const {connectWebMCP} = await import('/webmcpAdapter.js');
      const registry = new ActionRegistry(); registry.configure(() => true, async () => {});
      const state = window.fixture = {registry,domain:'text',resolvers:[],calls:0,errors:[],ready:false};
      const action = (name, domain, execute) => ({name,domain,description:name,readOnly:true,
        inputSchema:{type:'object',properties:{},additionalProperties:false},execute});
      registry.register([
        action('context','core',() => ({domain:state.domain})),
        action('pending','text',() => {state.calls++;return new Promise(resolve => state.resolvers.push(resolve));}),
        action('training','training',() => ({ready:true}))
      ]);
      state.connect = () => {
        state.adapter = connectWebMCP(document.modelContext,registry,() => state.domain,
          message => state.errors.push(message),ready => {state.ready=ready;});
      };
      // Registration deliberately occurs later; discovery cannot pass early.
      setTimeout(state.connect,150);
    });
    await waitForNativeTools(page, {present:['vantaline_context','vantaline_pending']});
    assert.equal(await page.evaluate(() => window.fixture.ready), true);

    // Two simultaneous native reads retain both result channels during routing.
    const pendingCall = () => page.evaluate(async () => {
      const tool = (await document.modelContext.getTools()).find(tool => tool.name === 'vantaline_pending');
      return JSON.parse(await document.modelContext.executeTool(tool,'{}'));
    });
    const first = pendingCall();
    await page.waitForFunction(() => window.fixture.calls === 1);
    const second = pendingCall();
    await page.waitForFunction(() => window.fixture.calls === 2);
    await page.evaluate(() => {window.fixture.domain='training';window.fixture.adapter.refresh();});
    await waitForNativeTools(page, {present:['vantaline_context','vantaline_training','vantaline_pending']});
    await page.evaluate(() => window.fixture.resolvers.shift()({id:1}));
    const one = await Promise.race([first,second]); assert.equal(one.status,'completed');
    assert.ok((await page.evaluate(async()=> (await document.modelContext.getTools()).map(t=>t.name))).includes('vantaline_pending'));
    await page.evaluate(() => window.fixture.resolvers.shift()({id:2}));
    assert.deepEqual((await Promise.all([first,second])).map(r=>r.data.id).sort(),[1,2]);
    await waitForNativeTools(page, {present:['vantaline_context','vantaline_training'],absent:['vantaline_pending']});

    // Session revocation rejects new calls immediately, while an in-flight read
    // returns an explicit unknown result without exposing the previous session.
    await page.evaluate(() => {window.fixture.domain='text';window.fixture.adapter.refresh();});
    await waitForNativeTools(page, {present:['vantaline_pending']});
    const revoked = pendingCall();
    await page.waitForFunction(() => window.fixture.calls === 3);
    await page.evaluate(() => {window.fixture.registry.reset();void window.fixture.adapter.close();});
    await page.evaluate(() => window.fixture.resolvers.shift()({private:'previous-session-value'}));
    const result = await revoked;
    assert.equal(result.status,'outcome_unknown'); assert.equal(JSON.stringify(result).includes('previous-session-value'),false);
    await waitForNativeTools(page, {empty:true});
    assert.equal(await page.evaluate(() => window.fixture.calls),3);

    // Repeated close/reconnect cycles exercise ownership and duplicate-name races.
    await page.evaluate(() => {
      window.fixture.registry.configure(()=>true,async()=>{});
      for(let i=0;i<10;i++){window.fixture.connect();void window.fixture.adapter.close();}
      window.fixture.connect();
    });
    await waitForNativeTools(page, {present:['vantaline_context','vantaline_pending']});
    assert.deepEqual(await page.evaluate(() => window.fixture.errors),[]);
    await page.evaluate(() => window.fixture.adapter.close());
    await waitForNativeTools(page, {empty:true});
    assert.deepEqual(errors,[]);
    console.log(JSON.stringify({browser:await browser.version(),result:'PASS',scope:'delayed discovery, negative timeout, concurrent native reads, routing, session revocation, remount ownership'}));
  } finally {await browser.close();}
})().catch(error => {console.error(error);process.exitCode=1;});
