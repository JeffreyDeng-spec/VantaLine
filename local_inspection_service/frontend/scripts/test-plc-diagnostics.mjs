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
    import {PlcWebSerialClient} from '/src/features/plc/webSerialClient.ts';
    import {DiagnosticTransport,PlcDiagnosticLog,diagnosticTransport} from '/src/features/plc/diagnosticLog.ts';
    const client=new PlcWebSerialClient();
    diagnosticTransport.setIdentity('operator');
    window.plcDiagnosticTest={client,transport:diagnosticTransport,DiagnosticTransport,PlcDiagnosticLog};
    createRoot(document.getElementById('root')).render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}><LocalPlcControls client={client} /></QueryClientProvider>);
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
  const requests = []; const logged=[];
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
    const ws=()=>({paired:Boolean(station),station,config:station?config:null,config_generation:config.enabled?1:0,lease:null,release_consistent:true});
    if(path.endsWith('/diagnostic-events/config')) return route.fulfill({json:{enabled:true,account_id:'operator'}});
    if(path.endsWith('/diagnostic-events/batch')) { logged.push(...payload.events);return route.fulfill({json:{enabled:true,accepted:payload.events.map(e=>e.event_id)}}); }
    if(path.endsWith('/self-pair')) { if(!station){station={id:'line1',name:payload.name||'产线电脑'};config={...defaults,enabled:false,capture_trigger_enabled:false};} return route.fulfill({json:ws()}); }
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
    await page.getByRole('button',{name:'断开 PLC'}).waitFor();
    assert.equal(await page.getByRole('dialog',{name:'本机 PLC 配置'}).count(),0);
    assert.equal(config.capture_trigger_enabled,false);
  }
  if(['success','unplug','edit','refresh','duplicate','tabs'].includes(mode)) {
    await page.getByRole('button',{name:'断开 PLC'}).waitFor();
    assert.match(await page.getByRole('status').innerText(),paired?/通信正常.*等待相机/:/通信正常.*已关闭到位自动拍照/);
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
  await page.evaluate(()=>window.plcDiagnosticTest.transport.tick());
  assert(logged.length>0,'diagnostic events must upload');
  assert(logged.every(e=>JSON.stringify(e).length<2048),'reservation must bound event size');
  assert(!JSON.stringify(logged).match(/frame_hex|response_hex|token|cookie|stack/));
  if(mode==='success') assert(logged.some(e=>e.step==='activate'&&e.result==='ok'));
  if(mode==='timeout') assert(logged.some(e=>e.step==='read'&&e.code==='timeout'&&e.actual_bytes===0));
  if(mode==='short') assert(logged.some(e=>e.step==='read'&&e.code==='partial_response'&&e.actual_bytes===4));
  if(mode==='checksum') assert(logged.some(e=>e.code==='invalid_checksum'));
  if(mode==='occupied') assert(logged.some(e=>e.step==='open'&&e.result==='failed'));
  if(mode==='unplug') assert(logged.some(e=>e.code==='unplugged'));
  if(mode==='timeout'&&process.env.PLC_UI_OUTPUT){mkdirSync(process.env.PLC_UI_OUTPUT,{recursive:true});await page.screenshot({path:join(process.env.PLC_UI_OUTPUT,'connection-timeout.png')});}
  assert.deepEqual(errors,[]);
  await context.close(); console.log(`PLC browser ${mode} ${paired?'saved':'first-use'}: PASS`);
}
async function transportContracts() {
  const page=await browser.newPage();await page.goto(`${base}/__plc_test`);
  const result=await page.evaluate(async()=>{
    const {DiagnosticTransport,PlcDiagnosticLog}=window.plcDiagnosticTest;
    const sent=[];let uploads=0;
    const transport=new DiagnosticTransport(async (url,init)=>{
      if(url.endsWith('/config'))return new Response(JSON.stringify({enabled:true,account_id:'operator'}));
      uploads++;const events=JSON.parse(init.body).events;sent.push(...events);
      return new Response(JSON.stringify({enabled:true,accepted:events.map(e=>e.event_id)}));
    });transport.setIdentity('operator');
    const log=new PlcDiagnosticLog(transport);log.begin();
    for(let i=0;i<300;i++)log.record('summary','summary');
    log.record('read','failed',{code:'timeout'});
    const overflow={count:transport.queue.length,bytes:transport.bytes,dropped:transport.dropped,last:transport.queue.at(-1).event.code};
    transport.enter();await transport.tick();const blocked=uploads===0;transport.leave();await transport.tick();
    const batchSize=sent.length;transport.setIdentity('other');const cleared=transport.queue.length===0;
    transport.setIdentity('');
    // Hung uploader must abort after two seconds and retain events.
    const hung=new DiagnosticTransport((url,init)=>url.endsWith('/config')?Promise.resolve(new Response(JSON.stringify({enabled:true,account_id:'operator'}))):new Promise((resolve,reject)=>init.signal.addEventListener('abort',()=>reject(new DOMException('abort','AbortError')))));
    hung.setIdentity('operator');const hlog=new PlcDiagnosticLog(hung);hlog.begin();const start=performance.now();await hung.tick();
    const hang={elapsed:performance.now()-start,pending:hung.queue.length,inFlight:hung.inFlight};hung.setIdentity('');
    const bad=new DiagnosticTransport(async()=>{throw new Error('offline');});bad.setIdentity('operator');const blog=new PlcDiagnosticLog(bad);blog.begin();await bad.tick();
    const offline={pending:bad.queue.length,next:bad.nextAttempt,backoff:bad.backoff};bad.setIdentity('');
    // Enqueue failure cannot escape logging calls.
    const fault=new DiagnosticTransport();fault.enqueue=()=>{throw new Error('injected logger failure');};
    new PlcDiagnosticLog(fault).begin();
    return {overflow,blocked,batchSize,cleared,hang,offline};
  });
  assert(result.overflow.count<=200&&result.overflow.bytes<=256*1024&&result.overflow.dropped>0&&result.overflow.last==='timeout');
  assert(result.blocked&&result.cleared);assert(result.batchSize<=20);assert(result.hang.elapsed>=1900&&result.hang.elapsed<3500&&result.hang.pending>0&&!result.hang.inFlight);
  assert(result.offline.pending>0&&result.offline.backoff===20000);
  await page.close();console.log('Diagnostic bounded queue, idle-only upload, hung/offline upload, identity switch and logger failure: PASS');
}
async function productionCase(mode, enabled=true) {
  const context=await browser.newContext();const page=await context.newPage();const logged=[];
  await context.addInitScript(({mode})=>{
    const evidence={writes:[],closed:0};window.productionEvidence=evidence;
    let pending,reads=0,writes=0;const good=new Uint8Array([2,48,48,48,48,3,67,51]);
    const reader={read:()=>new Promise(resolve=>{pending=resolve;}),cancel:async()=>{pending?.({done:true});pending=null;},releaseLock(){}};
    const port={getInfo:()=>({}),open:async()=>{},close:async()=>{evidence.closed++;},readable:{getReader:()=>reader},writable:{getWriter:()=>({releaseLock(){},write:async bytes=>{
      evidence.writes.push(Array.from(bytes));
      const isWrite=bytes[1]===49;
      let response=isWrite?new Uint8Array([6]):good;
      if(isWrite){writes++;if(mode==='nak')response=new Uint8Array([21]);if(mode==='partial-y'&&writes===2)return;}
      else {reads++;if(mode==='capturetimeout'&&reads>2)return;}
      queueMicrotask(()=>{const resolve=pending;pending=null;resolve?.({done:false,value:response});});
    }})}};
    Object.defineProperty(navigator,'serial',{configurable:true,value:{requestPort:async()=>port,addEventListener(){},removeEventListener(){}}});
  },{mode});
  const ws={paired:true,station:{id:'line1',name:'产线电脑'},config:defaults,config_generation:1};
  const active={station_id:'line1',session_id:'session',lease_epoch:1,config_generation:1,state:'active',communication_verified:true};
  await context.route('**/api/plc/**',async route=>{
    const path=new URL(route.request().url()).pathname;const payload=route.request().method()==='POST'?route.request().postDataJSON():null;
    if(path.endsWith('/diagnostic-events/config'))return route.fulfill({json:{enabled,account_id:'operator'}});
    if(path.endsWith('/diagnostic-events/batch')){logged.push(...payload.events);return route.fulfill({json:{enabled,accepted:payload.events.map(e=>e.event_id)}});}
    if(path.endsWith('/connect'))return route.fulfill({json:{...active,state:'connecting',connection_check:{id:'check',deadline_at:Math.floor(Date.now()/1000)+60,timeout_ms:500,frames:[{target:'D205',frame_hex:'0230313139413032033731'},{target:'D206',frame_hex:'0230313139433032033733'}]}}});
    if(path.endsWith('/activate'))return route.fulfill({json:active});
    if(path.endsWith('/heartbeat'))return mode==='heartbeatfailed'?route.fulfill({status:409,json:{detail:'lost'}}):route.fulfill({json:active});
    if(path.endsWith('/attempt'))return route.fulfill({json:{dispatch_id:'dispatch',execution_window_ms:2000,ack_timeout_ms:500,frames:[{target:'D206',frame_hex:'0231323334033030',frame_sha256:'d'},{target:'Y04',frame_hex:'0231353637033030',frame_sha256:'y'}]}});
    if(path.endsWith('/receipt'))return mode==='receiptlost'?route.fulfill({status:503,json:{detail:'receipt unavailable'}}):route.fulfill({json:{dispatch_id:'dispatch',status:'acknowledged'}});
    if(path.endsWith('/disconnect'))return route.fulfill({json:{state:'released'}});
    return route.fulfill({json:ws});
  });
  await page.goto(`${base}/__plc_test`);
  await page.getByRole('button',{name:'连接 PLC',exact:true}).click();await page.getByRole('button',{name:'断开 PLC'}).waitFor();
  const timing=await page.evaluate(async({mode,enabled})=>{
    const {client,transport}=window.plcDiagnosticTest;transport.enabled=enabled;
    if(mode==='loggerfault')transport.enqueue=()=>{throw new Error('logger unavailable');};
    const plan={target:'D205',frame_hex:'0230313139413032033731',expected_response_bytes:8,read_timeout_ms:500,poll_interval_ms:200,trigger_value:1,config_generation:1,protocol_version:'plc-web-serial-v4'};
    const start=performance.now();
    if(['success','loggerfault'].includes(mode)){
      for(let i=0;i<300;i++)await client.readCaptureInput(plan,()=>{});
      for(let i=0;i<10;i++)await client.execute({dispatch_id:'dispatch'},()=>{});
    }else if(mode==='capturetimeout'){try{await client.readCaptureInput(plan,()=>{});}catch{}}
    else if(mode!=='heartbeatfailed'){try{await client.execute({dispatch_id:'dispatch'},()=>{});}catch{}}
    return performance.now()-start;
  },{mode,enabled});
  if(mode==='heartbeatfailed')await page.getByRole('button',{name:'连接 PLC',exact:true}).waitFor({timeout:7000});
  await page.evaluate(()=>{window.plcDiagnosticTest.client.diagnostics.summary();});
  await page.evaluate(()=>window.plcDiagnosticTest.transport.tick());
  const evidence=await page.evaluate(()=>window.productionEvidence);
  if(mode==='nak'){assert.equal(evidence.writes.length,3,'D NAK must suppress Y');assert(logged.some(e=>e.code==='nak'));}
  if(mode==='partial-y'){assert.equal(evidence.writes.length,4,'Y timeout must not replay');assert(logged.some(e=>e.target==='Y04'&&e.code==='timeout'));}
  if(mode==='capturetimeout'){assert.equal(evidence.writes.length,3);assert(logged.some(e=>e.step==='read'&&e.code==='timeout'));}
  if(mode==='heartbeatfailed')assert(logged.some(e=>e.code==='lease_lost'));
  if(mode==='receiptlost'){assert.equal(evidence.writes.length,4);assert(logged.some(e=>e.code==='transport_error'));}
  if(mode==='success'&&enabled){assert(logged.some(e=>e.step==='summary'&&e.reads_ok===300&&e.writes_ok===20));}
  if(['partial-y','capturetimeout','heartbeatfailed','receiptlost'].includes(mode))assert(evidence.closed>=1);
  if(mode==='nak')assert.equal(evidence.closed,0,'conclusive NAK may keep the connection reusable');
  await context.close();return {timing,trace:evidence.writes};
}
try {
  await scenario('success',true);
  for(const mode of ['occupied','checksum','short','extra','residual','timeout','unplug'])await scenario(mode,true);
  await transportContracts();
  for(const mode of ['nak','partial-y','capturetimeout','heartbeatfailed','receiptlost']){await productionCase(mode);console.log(`Production ${mode}: PASS`);}
  const samples={off:[],on:[]};let baseline;
  for(let i=0;i<3;i++)for(const enabled of [false,true]){
    const run=await productionCase('success',enabled);baseline ||= run.trace;assert.deepEqual(run.trace,baseline,'logging must preserve exact serial trajectory');samples[enabled?'on':'off'].push(run.timing);
  }
  const fault=await productionCase('loggerfault');assert.deepEqual(fault.trace,baseline,'logger failures must preserve exact serial trajectory');
  const median=a=>[...a].sort((x,y)=>x-y)[Math.floor(a.length/2)];
  console.log(JSON.stringify({synthetic_only:true,transactions_per_sample:{reads:300,dispatches:10},physical_frames:baseline.length,samples_ms:samples,median_extra_ms:median(samples.on)-median(samples.off)}));
} finally {await browser.close();await server.close();}
