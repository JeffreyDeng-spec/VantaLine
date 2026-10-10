// Real browser + real shared controls/controller; synthetic serial device and API.
import assert from 'node:assert/strict';
import { mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createServer } from 'vite';
import react from '@vitejs/plugin-react';
import { chromium } from 'playwright';
const root = fileURLToPath(new URL('../', import.meta.url));
const server = await createServer({ root, configFile: false, optimizeDeps: { include: ['react','react-dom/client','@tanstack/react-query'] }, server: { host: '127.0.0.1', port: 0 }, plugins: [react(), {
  name: 'plc-test-harness', enforce: 'pre',
  resolveId(id) { if(id.endsWith('/__plc_entry.tsx')) return id; },
  load(id) { if(id.endsWith('/__plc_entry.tsx')) return `
    import React from 'react';
    import {createRoot} from 'react-dom/client';
    import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
    import '/src/styles/global.css';
    import {LocalPlcControls} from '/src/features/plc/LocalPlcControls.tsx';
    createRoot(document.getElementById('root')).render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}><LocalPlcControls /></QueryClientProvider>);
  `; },
  configureServer(server) {
    server.middlewares.use(async (req, res, next) => {
      if (req.url !== '/__plc_test') return next();
      const html = await server.transformIndexHtml(req.url, '<html><body><div id="root"></div><script type="module" src="/__plc_entry.tsx"></script></body></html>');
      res.setHeader('Content-Type', 'text/html'); res.end(html);
    });
  }
}] });
await server.listen();
const browser = await chromium.launch({ headless: true, channel: process.env.PLC_TEST_BROWSER || undefined });
const base = `http://127.0.0.1:${server.httpServer.address().port}`;
const defaults = {schema_version:5,transport_mode:'web_serial',profile_id:'mitsubishi_fx3ga_40mr',enabled:true,protocol:'fx_programming_port_ascii',checksum_mode:'include_etx',baudrate:9600,parity:'E',data_bits:7,stop_bits:1,result_register:'D206',output_control_point:'',capture_trigger_enabled:true,capture_input_register:'D205',capture_trigger_value:1,capture_poll_interval_ms:200,ack_timeout_ms:500,retries:0};
async function scenario(mode, paired = false) {
  const context = await browser.newContext();
  const page = await context.newPage();
  const errors = []; page.on('pageerror', e => errors.push(e.message));
  let config = {...defaults}, station = paired ? {id:'line1',name:'产线电脑'} : null;
  const requests = [];
  await context.addInitScript(({mode}) => {
    window.serialEvidence = { calls: [], writes: [], closed: 0, reads: 0 };
    const evidence = window.serialEvidence;
    let pending, disconnected = false, eventTarget = new EventTarget();
    const response = new Uint8Array([2,48,48,48,48,3,67,51]);
    const reader = {
      read: () => new Promise(resolve => { pending = resolve; }),
      cancel: async () => { if (pending) { pending({done:true}); pending = null; } }, releaseLock() {}
    };
    const port = {
      getInfo: () => ({usbVendorId:1000,usbProductId:2000}),
      open: async () => { evidence.calls.push('open'); if (mode==='occupied') throw new Error('串口已被占用'); },
      close: async () => { disconnected=true; evidence.closed++; },
      readable: {getReader:()=>reader},
      writable: {getWriter:()=>({releaseLock(){},write:async data=>{
        evidence.writes.push(Array.from(data)); evidence.reads++;
        if (mode==='timeout'||mode==='navigate') return;
        let bytes = response.slice();
        if (mode==='checksum') bytes[7]=48;
        if (mode==='short') bytes=bytes.slice(0,4);
        if (mode==='extra') bytes=new Uint8Array([...bytes,6]);
        queueMicrotask(()=>{ if(pending) { const resolve=pending; pending=null; resolve({value:bytes,done:false}); } });
        if (mode==='residual') setTimeout(()=>{if(pending){const resolve=pending;pending=null;resolve({value:new Uint8Array([6]),done:false});}},25);
      }})}
    };
    const serial = {
      requestPort: async () => { evidence.calls.push('choose'); if(mode==='cancel'||mode==='no-device') throw new DOMException('no selection','NotFoundError'); return port; },
      addEventListener: (...args)=>eventTarget.addEventListener(...args), removeEventListener:(...args)=>eventTarget.removeEventListener(...args)
    };
    window.unplug = () => {const event=new Event('disconnect');Object.defineProperty(event,'target',{value:port});eventTarget.dispatchEvent(event);};
    Object.defineProperty(navigator,'serial',{configurable:true,value:serial});
  }, {mode});
  await context.route('**/api/plc/**', async route => {
    const req=route.request(), path=new URL(req.url()).pathname;
    requests.push(path);
    await req.frame().page().evaluate(path=>window.serialEvidence.calls.push(path),path);
    const payload=req.method()==='POST'?req.postDataJSON():null;
    const ws=()=>({paired:Boolean(station),station,config:station?config:null,config_generation:1,lease:null,release_consistent:true});
    if(path.endsWith('/self-pair')) { station ||= {id:'line1',name:payload.name||'产线电脑'}; return route.fulfill({json:ws()}); }
    if(path.endsWith('/self-config')) {config=payload;return route.fulfill({json:ws()});}
    if(path.endsWith('/connect')) return route.fulfill({json:{station_id:'line1',session_id:'session',lease_epoch:1,config_generation:1,state:'connecting',connection_check:{id:'check',deadline_at:Math.floor(Date.now()/1000)+60,timeout_ms:500,frames:[{target:'D205',frame_hex:'0230313139413032033731'},{target:'D206',frame_hex:'0230313139433032033733'}]}}});
    if(path.endsWith('/activate')) {
      assert.equal(payload.connection_check_id,'check');assert.equal(payload.connection_reads.length,2);
      return route.fulfill({json:{station_id:'line1',session_id:'session',lease_epoch:1,config_generation:1,state:'active',communication_verified:true}});
    }
    if(path.endsWith('/disconnect')) return route.fulfill({json:{state:'released'}});
    if(path.endsWith('/heartbeat')) return route.fulfill({json:{station_id:'line1',session_id:'session',lease_epoch:1,config_generation:1,state:'active',communication_verified:true}});
    return route.fulfill({json:ws()});
  });
  await page.goto(`${base}/__plc_test`);
  await page.getByRole('button',{name:'连接 PLC',exact:true}).waitFor();
  await page.getByRole('button',{name:'连接 PLC',exact:true}).click();
  if(mode==='duplicate') await page.getByRole('button',{name:'连接中…',exact:true}).dispatchEvent('click');
  if(!paired) {
    await page.getByRole('dialog',{name:'本机 PLC 配置'}).waitFor();
    assert.equal(await page.locator('input[name=input]').inputValue(),'D205');
    assert.equal(await page.locator('input[name=result]').inputValue(),'D206');
    assert.equal(await page.locator('input[name=auto]').isChecked(),true);
    if(process.env.PLC_UI_OUTPUT) {mkdirSync(process.env.PLC_UI_OUTPUT,{recursive:true});await page.screenshot({path:join(process.env.PLC_UI_OUTPUT,'first-use.png')});}
    await page.getByRole('button',{name:'确认并连接'}).click();
  }
  if(['success','unplug','edit','refresh','duplicate','tabs'].includes(mode)) {
    await page.getByRole('button',{name:'断开 PLC'}).waitFor();
    assert.match(await page.getByRole('status').innerText(),/通信正常.*等待相机/);
    if(mode==='success'&&process.env.PLC_UI_OUTPUT) await page.screenshot({path:join(process.env.PLC_UI_OUTPUT,'connected.png')});
    if(mode==='tabs') {
      const other=await context.newPage();await other.goto(`${base}/__plc_test`);
      await other.getByRole('button',{name:'连接 PLC',exact:true}).click();
      await other.waitForFunction(()=>document.querySelector('[role=status]')?.textContent.includes('另一个标签页'));
      assert.match(await page.getByRole('status').innerText(),/通信正常/);await other.close();
    }
    if(mode==='edit') {
      await page.getByRole('button',{name:'本机 PLC 设置'}).click();
      await page.locator('input[name=result]').fill('D207');
      await page.getByRole('button',{name:'确认并保存'}).click();
      await page.getByRole('button',{name:'连接 PLC',exact:true}).waitFor();
      assert(requests.indexOf('/api/plc/workstation/lease/disconnect')<requests.indexOf('/api/plc/workstation/self-config'));
    }
    if(mode==='refresh') {
      await page.reload();await page.getByRole('button',{name:'连接 PLC',exact:true}).waitFor();
      assert.match(await page.getByRole('status').innerText(),/未连接/);
    }
    if(mode==='unplug') {await page.evaluate(()=>window.unplug());await page.getByRole('button',{name:'连接 PLC',exact:true}).waitFor();assert.match(await page.getByRole('status').innerText(),/未连接/);}
  } else if(mode==='navigate') {
    await page.waitForFunction(()=>window.serialEvidence.writes.length===1);
    await page.reload();await page.getByRole('button',{name:'连接 PLC',exact:true}).waitFor();
    await new Promise(resolve=>setTimeout(resolve,650));
    assert(!requests.some(x=>x.endsWith('/activate')),'unload must not activate');
  } else {
    await page.waitForFunction(()=>document.querySelector('[role=status]')?.textContent.includes('未连接')&&!document.querySelector('[role=status]')?.textContent.includes('请选择'));
    assert(!requests.some(x=>x.endsWith('/activate')),mode+' must never activate');
  }
  const evidence=await page.evaluate(()=>window.serialEvidence);
  const choose=evidence.calls.indexOf('choose');
  if(mode!=='refresh'&&mode!=='navigate') assert(choose>=0);
  assert(!evidence.calls.slice(0,choose).some(x=>x!=='/api/plc/workstation'),'chooser must precede registration/network writes');
  assert(evidence.writes.length<=2);
  if(mode==='success') assert.equal(evidence.writes.length,2);
  if(mode==='duplicate') assert.equal(evidence.calls.filter(x=>x==='choose').length,1);
  assert.deepEqual(errors,[]);
  await context.close(); console.log(`PLC browser ${mode} ${paired?'saved':'first-use'}: PASS`);
}
try {
  await scenario('success'); await scenario('success',true);
  for(const mode of ['cancel','no-device','occupied','checksum','short','extra','residual','timeout','unplug','edit','refresh','duplicate','tabs','navigate']) await scenario(mode,true);
} finally {await browser.close();await server.close();}
