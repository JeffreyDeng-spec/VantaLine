import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import { dirname, resolve, join } from 'node:path';
import { tmpdir } from 'node:os';
import { createServer } from 'vite';
import { chromium } from 'playwright';
const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const server = await createServer({root,configFile:false,server:{host:'127.0.0.1',port:0},plugins:[{
  name:'plc-values-test',
  resolveId(id) { if(id==='/__values.tsx') return id; },
  load(id) { if(id==='/__values.tsx') return `
    import React from 'react'; import {createRoot} from 'react-dom/client';
    import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
    import {LocalPlcControls} from '/src/features/plc/LocalPlcControls.tsx';
    import {DeviceSettings} from '/src/features/rules/DeviceSettings.tsx';
    import {AppToastProvider} from '/src/components/ToastProvider.tsx';
    import '/src/styles/global.css';
    createRoot(document.getElementById('root')).render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}><AppToastProvider>{location.search.includes('admin')?<DeviceSettings/>:<LocalPlcControls/>}</AppToastProvider></QueryClientProvider>);
  `; },
  configureServer(s) {s.middlewares.use(async(req,res,next)=>{
    if(!req.url.startsWith('/__values?')) return next();
    const html=await s.transformIndexHtml(req.url,'<html><body><div id="root"></div><script type="module" src="/__values.tsx"></script></body></html>');
    res.setHeader('Content-Type','text/html');res.end(html);
  });}
}]});
await server.listen();
const browser = await chromium.launch({headless:true,channel:process.env.PLC_TEST_BROWSER||undefined});
try {
  for(const mode of ['local','admin']) {
    const context=await browser.newContext({viewport:{width:1280,height:800}});
    const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));page.on('dialog',d=>d.accept());
    // Omit the new fields to exercise an existing workstation's defaults.
    let config={schema_version:5,transport_mode:'web_serial',profile_id:'mitsubishi_fx3ga_40mr',enabled:true,protocol:'fx_programming_port_ascii',checksum_mode:'include_etx',baudrate:9600,parity:'E',data_bits:7,stop_bits:1,result_register:'D206',output_control_point:'',capture_trigger_enabled:false,capture_input_register:'D205',capture_trigger_value:1,capture_poll_interval_ms:200,ack_timeout_ms:500,retries:0};
    const writes=[];let generation=1;
    const ws=()=>({paired:true,station:{id:'fixture',name:'产线电脑',profile_verified:false},config,config_generation:generation,resolved_addresses:{},recent_dispatches:[],lease:null,release_consistent:true});
    await page.route('**/api/**',async route=>{
      const req=route.request(),path=new URL(req.url()).pathname;
      if(!path.startsWith('/api/'))return route.continue();
      if(path.endsWith('/config')||path.endsWith('/self-config')) {assert.equal(req.method(),'POST');config=req.postDataJSON();writes.push(config);generation++;return route.fulfill({json:ws()});}
      if(path.endsWith('/self-pair'))return route.fulfill({json:ws()});
      if(path.endsWith('/workstations'))return route.fulfill({json:{items:[]}});
      if(path.endsWith('/workstation'))return route.fulfill({json:ws()});
      throw new Error('Unexpected request '+path);
    });
    const open=async()=>{if(mode==='local')await page.getByRole('button',{name:'本机 PLC 设置'}).click();else await page.locator('input[name=result_pass_value]').waitFor();};
    const save=()=>page.getByRole('button',{name:mode==='local'?'确认并保存':'保存 PLC 设置',exact:true}).click();
    await page.goto(`http://127.0.0.1:${server.httpServer.address().port}/__values?${mode}`);await open();
    const good=()=>page.locator('input[name=result_pass_value]'),bad=()=>page.locator('input[name=result_fail_value]');
    assert.equal(await good().inputValue(),'1');assert.equal(await bad().inputValue(),'0');
    for(const [yes,no] of [[2,3],[0,1],[0,65535],[42,42]]) {
      await good().fill(String(yes));await bad().fill(String(no));const n=writes.length;
      await save();await page.waitForFunction(()=>!document.querySelector('button[type=submit]')?.disabled);
      await assertEventually(()=>writes.length===n+1);
      assert.equal(config.result_pass_value,yes);assert.equal(config.result_fail_value,no);
      await page.reload();await open();assert.equal(await good().inputValue(),String(yes));assert.equal(await bad().inputValue(),String(no));
    }
    for(const value of ['', '-1','65536','0.5']) {
      await good().fill(value);assert.equal(await good().evaluate(el=>el.checkValidity()),false);
      const n=writes.length;await save();assert.equal(writes.length,n);
    }
    await good().fill('0');await page.setViewportSize({width:390,height:780});
    assert.equal(await good().isVisible(),true);assert.equal(await bad().isVisible(),true);
    const rect=await good().boundingBox();assert(rect.x>=0&&rect.x+rect.width<=390);
    if(mode==='local')await page.screenshot({path:join(tmpdir(),'plc-result-values-dialog.png')});
    assert.deepEqual(errors,[]);await context.close();
  }
  console.log('PASS real React local/admin output values: defaults, persistence, zero, boundaries, equal values, invalid input and narrow layout');
} finally {await browser.close();await server.close();}
async function assertEventually(predicate) {for(let i=0;i<100;i++){if(predicate())return;await new Promise(r=>setTimeout(r,20));}assert(predicate());}
