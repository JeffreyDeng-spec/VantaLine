// Isolated React/browser acceptance. No customer media, provider calls or physical PLC.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { spawn } = require('node:child_process');
let playwright;
try { playwright = require('../local_inspection_service/frontend/node_modules/playwright'); } catch { playwright = require('playwright'); }
const frontend = path.resolve(__dirname, '../local_inspection_service/frontend');
const cache = path.join(frontend, 'node_modules/.cache');
fs.mkdirSync(cache, { recursive: true });
const harness = path.join(cache, 'version-harness.tsx');
fs.writeFileSync(harness, `
import React, {useState, useRef} from 'react';
import {createRoot} from 'react-dom/client';
import {createBrowserRouter, RouterProvider, Link, useLocation} from 'react-router-dom';
import {QueryClient, QueryClientProvider} from '@tanstack/react-query';
import {VersionBoundary} from '/src/features/version/VersionBoundary';
import {versionCoordinator, runVersionAction, guardPlcConnectionGesture} from '/src/features/version/runtime';
import {useVersionParticipant} from '/src/features/version/hooks';
import {FileDropZone} from '/src/components/FileDropZone';
import {apiClient} from '/src/api/client';
import {PlcWebSerialClient} from '/src/features/plc/webSerialClient';
window.fixture = {versionCoordinator};
function Bench() {
 const [draft,setDraft]=useState(''), [file,setFile]=useState(null), [art,setArt]=useState(false), [busy,setBusy]=useState(false);
 const client=useRef(new PlcWebSerialClient());
 const order=message=>sessionStorage.setItem('order', (sessionStorage.getItem('order')||'')+message+',');
 client.current.disconnect=async()=>order('disconnect');
 useVersionParticipant({busy:()=>busy, dirty:()=>art, pause:()=>order('pause'), cleanup:async()=>{await client.current.drainForReload(); order('camera-stop');}});
 const location=useLocation();
 return <><VersionBoundary/><h1>Version bench</h1><p data-testid="location">{location.pathname+location.search+location.hash}</p>
 <Link to="/__version_fixture?tab=next#detail">下一页</Link>
 <form onSubmit={event=>{event.preventDefault(); void apiClient.post('/api/fixture/save').then(()=>order('saved'));}}>
 <label>草稿<input aria-label="草稿" value={draft} onChange={e=>setDraft(e.target.value)}/></label><button type="submit">保存</button></form>
 <button onClick={()=>setArt(!art)}>标注</button>
 <FileDropZone ariaLabel="选择文件" onFiles={files=>setFile(files[0]||null)}>选择文件</FileDropZone>
 <button onClick={()=>{void runVersionAction(async()=>{setBusy(true); const promise=apiClient.post('/api/fixture/start'); client.current.queue=promise.then(()=>{order('receipt');}); try {await promise;} finally {setBusy(false);}});}}>开始检测</button>
 <button onClick={()=>{void runVersionAction(async()=>{const form=new FormData();if(file) form.append('file',file); await apiClient.upload('/api/fixture/upload',form);});}}>上传</button>
 <button onClick={()=>{if(guardPlcConnectionGesture()){order(navigator.userActivation.isActive?'gesture-ok':'gesture-lost');}}}>连接 PLC</button>
 </>;
}
const router=createBrowserRouter([{path:'*',element:<Bench/>}]);
createRoot(document.getElementById('root')).render(<QueryClientProvider client={new QueryClient()}><RouterProvider router={router}/></QueryClientProvider>);
`);
const base = 'http://127.0.0.1:5192';
const local = { release: 'v2026.10.100', git_commit: 'a'.repeat(40), consistent: true };
const changed = { release: 'v2026.10.101', git_commit: 'b'.repeat(40), consistent: true };
const vite = spawn(process.execPath, [path.join(frontend, 'node_modules/vite/bin/vite.js'), '--host', '127.0.0.1', '--port', '5192', '--strictPort', '--base', '/'], {
 cwd: frontend, env: { ...process.env, VITE_ROUTER_BASENAME: '/', VITE_RELEASE_ID: local.release, VITE_GIT_COMMIT: local.git_commit }, stdio: 'pipe'
});
vite.stderr.on('data', data => { if (!String(data).includes('[console.warn]')) process.stderr.write(data); });
let browser;
const html = `<div id="root"></div><script type="module">import RefreshRuntime from '/@react-refresh';RefreshRuntime.injectIntoGlobalHook(window);window.$RefreshReg$=()=>{};window.$RefreshSig$=()=>type=>type;window.__vite_plugin_react_preamble_installed__=true;</script><script type="module" src="/node_modules/.cache/version-harness.tsx"></script>`;
(async () => {
 for (let i=0;i<100;i++) { try { if ((await fetch(base)).ok) break; } catch {} await new Promise(resolve=>setTimeout(resolve,100)); }
 browser = await playwright.chromium.launch({ headless: true, args: ["--disable-features=LocalNetworkAccessChecks,LocalNetworkAccessChecksWebSockets"], ...(process.env.VERSION_TEST_BROWSER ? { channel: process.env.VERSION_TEST_BROWSER } : {}) });
 async function bench(version=changed) {
  const context = await browser.newContext(); const page = await context.newPage(); const errors=[]; let identity=version, documents=0, writes=0, gate=null;
  page.on('pageerror', error=>{errors.push(error.message);console.error(error.message);});
  page.on('console', message=>{if(message.type()==='error')console.error(message.text());});
  await page.route('**/__version_fixture**', route=>{++documents;return route.fulfill({contentType:'text/html',body:html});});
  await page.route('**/api/version', route=>route.fulfill({json:identity}));
  await page.route('**/api/fixture/**', async route=>{++writes;if(gate)await gate;return route.fulfill({json:{ok:true}});});
  await page.goto(base+'/__version_fixture'); await page.getByRole('heading',{name:'Version bench'}).waitFor();
  await page.waitForFunction(()=>window.fixture?.versionCoordinator.snapshot().pending || window.fixture?.versionCoordinator.gestureReady());
  return {context,page,errors, documents:()=>documents,writes:()=>writes,version:v=>identity=v,hold:p=>gate=p, check:()=>page.evaluate(()=>window.fixture.versionCoordinator.check(true))};
 }
 // Background discovery must never reload; navigation goes to the requested path/query/hash exactly once.
 {
  const f=await bench(); assert.equal(f.documents(),1); await f.page.getByRole('link',{name:'下一页'}).click();
  await f.page.waitForURL('**/__version_fixture?tab=next#detail'); await f.page.getByRole('heading',{name:'Version bench'}).waitFor();
  assert.equal(f.documents(),2); await f.page.getByRole('button',{name:'重试更新'}).waitFor();
  await f.page.getByRole('button',{name:'开始检测',exact:true}).click(); assert.equal(f.writes(),0); assert.equal(f.documents(),2); assert.deepEqual(f.errors,[]);await f.context.close();
 }
 // A fresh business-entry click updates without sending any request or replaying after navigation.
 {
  const f=await bench();await f.page.getByRole('button',{name:'开始检测',exact:true}).click();
  await f.page.getByRole('button',{name:'重试更新'}).waitFor();assert.equal(f.documents(),2);assert.equal(f.writes(),0);await f.context.close();
 }
 // Back navigation also retains its intended destination while updating.
 {
  const f=await bench(local);await f.page.getByRole('link',{name:'下一页'}).click();await f.page.waitForURL('**/__version_fixture?tab=next#detail');assert.equal(f.documents(),1);
  f.version(changed);await f.check();await f.page.evaluate(()=>history.back());await f.page.getByRole('button',{name:'重试更新'}).waitFor();assert.equal(f.documents(),2);assert.equal(new URL(f.page.url()).search,'');await f.context.close();
 }
 // Real editor events: cancellation keeps the draft; save acknowledges only the successful draft.
 {
  const f=await bench(); await f.page.getByLabel('草稿').fill('keep this');
  let dialogs=0; f.page.on('dialog', async dialog=>{++dialogs;await dialog.dismiss();});
  await f.page.getByRole('link',{name:'下一页'}).click(); await f.page.getByText('已保留未保存内容', {exact:false}).waitFor();
  assert.equal(dialogs,1); assert.equal(await f.page.getByLabel('草稿').inputValue(),'keep this'); assert.equal(f.documents(),1);
  await f.page.getByRole('button',{name:'保存',exact:true}).click(); await f.page.waitForFunction(()=>sessionStorage.getItem('order')?.includes('saved'));
  await f.page.getByRole('link',{name:'下一页'}).click(); await f.page.waitForURL('**/__version_fixture?tab=next#detail'); assert.equal(dialogs,1);await f.context.close();
 }
 // Selected file and manual annotation protect unsaved browser state.
 for (const mode of ['file','annotation']) {
  const f=await bench(); if(mode==='file') await f.page.locator('input[type=file]').setInputFiles({name:'fixture.png',mimeType:'image/png',buffer:Buffer.from('synthetic')}); else await f.page.getByRole('button',{name:'标注',exact:true}).click();
  let dialogs=0; f.page.on('dialog',async dialog=>{++dialogs;await dialog.dismiss();});await f.page.getByRole('link',{name:'下一页'}).click();await f.page.getByText('已保留未保存内容',{exact:false}).waitFor();assert.equal(dialogs,1);assert.equal(f.documents(),1);await f.context.close();
 }
 // A started submission and simulated PLC queue/receipt drain before real client's disconnect.
 {
  const f=await bench(local);let finish;f.hold(new Promise(resolve=>finish=resolve));
  await f.page.getByRole('button',{name:'开始检测',exact:true}).click();await f.page.waitForFunction(()=>document.body.textContent.includes('Version bench'));while(!f.writes())await new Promise(resolve=>setTimeout(resolve,10));
  f.version(changed);await f.check();await f.page.getByRole('link',{name:'下一页'}).click();await f.page.getByText('正在等待当前操作安全结束',{exact:false}).waitFor();
  assert.equal(f.documents(),1);await f.page.getByRole('button',{name:'开始检测',exact:true}).click();assert.equal(f.writes(),1);finish();
  await f.page.waitForURL('**/__version_fixture?tab=next#detail');await f.page.getByRole('heading',{name:'Version bench'}).waitFor();const order=await f.page.evaluate(()=>sessionStorage.getItem('order'));
  assert.ok(order.indexOf('pause')<order.indexOf('receipt'));assert.ok(order.indexOf('receipt')<order.indexOf('disconnect'));assert.ok(order.indexOf('disconnect')<order.indexOf('camera-stop'));assert.equal(f.writes(),1);assert.deepEqual(f.errors,[]);await f.context.close();
 }
 // Current/fresh connection continues in the original click activation; stale check requests another click.
 {
  const f=await bench(local);await f.page.getByRole('button',{name:'连接 PLC',exact:true}).click();assert.match(await f.page.evaluate(()=>sessionStorage.getItem('order')),/gesture-ok/);
  await f.page.clock.install();await f.page.clock.fastForward(16_000);await f.page.getByRole('button',{name:'连接 PLC',exact:true}).click();await f.page.getByText('版本已核对，请再次点击连接 PLC',{exact:false}).waitFor();assert.equal((await f.page.evaluate(()=>sessionStorage.getItem('order'))).split('gesture-ok').length,2);
  await f.page.getByRole('button',{name:'连接 PLC',exact:true}).click();assert.equal((await f.page.evaluate(()=>sessionStorage.getItem('order'))).split('gesture-ok').length,3);await f.context.close();
 }
 // The shipped App/data router also mounts the guard on its public/login routes.
 {
  const context=await browser.newContext(),page=await context.newPage();const errors=[];page.on('pageerror',e=>{errors.push(e.message);console.error('App error:',e.message);});
  page.on('console',m=>{if(m.type()==='error')console.error('App console:',m.text());});
  await page.route('**/api/**',route=>{ if (!new URL(route.request().url()).pathname.startsWith('/api/')) return route.continue(); return route.fulfill({json:route.request().url().endsWith('/api/version')?local:{authenticated:false,setup_required:false,user:null,features:{}}}); });
  await page.goto(base+'/login');try { await page.locator('input[type=password]').waitFor({timeout:10000}); } catch (error) { console.error('App DOM:', await page.locator('body').innerText()); throw error; } await page.goto(base+'/workspace');await page.waitForURL('**/login?next=*');await page.locator('input[type=password]').waitFor();assert.deepEqual(errors,[]);await context.close();
 }
 console.log('PASS: version navigation, no replay, draft/file/annotation protection, safe drain, loop suppression, PLC gesture, real App login');
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(async()=>{await browser?.close();vite.kill('SIGTERM');fs.rmSync(harness,{force:true});});
