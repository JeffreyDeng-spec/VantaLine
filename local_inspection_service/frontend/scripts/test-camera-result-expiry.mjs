// Actual React workbench and hook with synthetic APIs/media; no production or serial I/O.
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { mkdirSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { chromium } from 'playwright';

const frontend = fileURLToPath(new URL('../', import.meta.url));
const base = 'http://127.0.0.1:8801';
const evidence = process.env.CAMERA_RESULT_TEST_OUTPUT || join(tmpdir(), 'vantaline-camera-result-expiry');
mkdirSync(evidence, { recursive: true });
mkdirSync(frontend + 'node_modules/.cache', { recursive: true });
writeFileSync(frontend + 'node_modules/.cache/camera-result-hook.tsx', `
import React, {useState} from 'react';
import {createRoot} from 'react-dom/client';
import {useDetectionResultDisplay} from '/src/features/detection/useDetectionResultDisplay';
export function mount() {
 const host=document.createElement('div');document.body.append(host);const root=createRoot(host);
 function Bench(){const [context,setContext]=useState('task-a:model-a');const state=useDetectionResultDisplay(context);
  window.__hookFixture={publish:state.setResult,change:setContext,unmount:()=>root.unmount()};
  return <div id="hook-fixture"><span data-raw>{state.result?.request_id || '-'}</span><span data-display>{state.displayResult?.request_id || '-'}</span></div>;
 }root.render(<Bench/>);
}
`);
const fixture = spawn(process.execPath, [fileURLToPath(new URL('./preview-normal-inspection.mjs', import.meta.url))], { cwd: frontend, stdio: 'pipe' });
fixture.stderr.on('data', data => process.stderr.write(data));
let browser;
const errors = [];
let scenarios = 0;
try {
  for (let i = 0; i < 150; i++) {
    if (fixture.exitCode !== null) throw Error('Inspection fixture exited');
    try { if ((await fetch(base + '/workspace/tasks/ai%3Ademo/inspect')).ok) break; } catch {}
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  browser = await chromium.launch({ headless: true, ...((process.env.CAMERA_RESULT_TEST_BROWSER || process.env.PLC_TEST_BROWSER) ? { channel: process.env.CAMERA_RESULT_TEST_BROWSER || process.env.PLC_TEST_BROWSER } : {}) });
  const page = await browser.newPage({ viewport: { width: 1366, height: 768 } });
  page.on('pageerror', error => errors.push(error.message));
  // Playwright's in-page polling uses the paused clock; poll from Node instead.
  const waitFor = async (predicate, argument) => {
    for (let i = 0; i < 300; i++) {
      if (await page.evaluate(predicate, argument)) return;
      await new Promise(resolve => setTimeout(resolve, 20));
    }
    throw Error('Fixture state did not settle: ' + predicate.toString() + '\n' + await page.locator('body').innerText());
  };
  await page.addInitScript(() => {
    window.__inspectionFixtureConfig = { capture_trigger_enabled: false };
    window.__outcome = 'pass'; window.__sequence = 0; window.__analysisCalls = [];
    window.__inspectionFixtureAnalyze = async (name, original) => {
      window.__analysisCalls.push(name);
      if (window.__outcome === 'hold') await new Promise(resolve => { window.__finishAnalysis = resolve; });
      if (window.__outcome === 'error') throw Error('Synthetic inspection error');
      return { ...original, passed: window.__outcome === 'pass', request_id: 'result-' + (++window.__sequence),
        detections: original.detections.map(item => ({ ...item, present: window.__outcome === 'pass' || item.present })) };
    };
  });
  await page.goto(base + '/workspace/tasks/ai%3Ademo/inspect?role=admin');
  await page.mouse.move(1300, 700);
  await page.getByRole('tab', { name: '摄像头' }).click();
  await page.getByRole('button', { name: '检测摄像头', exact: true }).click();
  await waitFor(() => document.querySelector('.camera-preview video')?.readyState >= 2);
  // Camera capture waits for two real animation frames; freeze timeout deadlines only.
  await page.evaluate(() => { window.__nativeRAF = window.requestAnimationFrame.bind(window); });
  await page.clock.install();
  await page.clock.pauseAt(new Date());
  await page.evaluate(() => { window.requestAnimationFrame = window.__nativeRAF; });
  const capture = async (outcome = 'pass', fullscreen = false) => {
    await page.evaluate(value => { window.__outcome = value; }, outcome);
    const sequence = await page.evaluate(() => window.__sequence);
    const scope = fullscreen ? page.getByRole('dialog', { name: '全屏检测' }) : page.locator('.camera-actions');
    await scope.getByRole('button', { name: '拍照 AI 检测', exact: true }).click();
    if (outcome !== 'hold' && outcome !== 'error') await waitFor(value => window.__sequence > value, sequence);
    if (outcome === 'hold') await waitFor(() => Boolean(window.__finishAnalysis));
    if (outcome === 'error') await page.locator('.hint-line').filter({ hasText: 'Synthetic inspection error' }).first().waitFor({ state: 'attached' });
  };
  const normalBadge = page.locator('.page-head .result-badge');
  const normalImage = page.locator('.result-panel .preview-frame img');
  const badgeText = async (locator, expected) => {
    for (let i = 0; i < 300; i++) {
      if (await locator.innerText() === expected) return;
      await new Promise(resolve => setTimeout(resolve, 20));
    }
    assert.equal(await locator.innerText(), expected);
  };

  // Exact deadline, all presentation fields clear, while evidence and last time remain.
  await capture();
  await badgeText(normalBadge, '通过');
  await page.clock.runFor(4_999);
  assert.equal(await normalImage.count(), 1);
  await badgeText(normalBadge, '通过');
  const lastTime = await page.locator('.normal-runtime-status').innerText();
  await page.screenshot({ path: evidence + '/pass-before-expiry.png' });
  await page.clock.runFor(1);
  await badgeText(normalBadge, '已就绪');
  assert.equal(await normalImage.count(), 0);
  assert.equal(await page.locator('.normal-detection-metrics tbody tr').innerText(), '暂无检测结果。');
  assert.ok((await page.locator('.normal-runtime-status').innerText()).includes(lastTime.match(/最近检测 [\d:]+/)[0]));
  assert.ok((await page.locator('.normal-write-status').innerText()).length > 0);
  await page.getByRole('button', { name: '开发诊断', exact: true }).click();
  assert.match(await page.locator('.json-panel').innerText(), /result-1/);
  await page.getByRole('button', { name: '关闭', exact: true }).click();
  await page.screenshot({ path: evidence + '/ready-after-expiry.png' });
  scenarios++; console.log(`PASS camera display scenario ${scenarios}`);

  // FAIL never expires, and is retained while the next detection is pending.
  await capture('fail'); await page.clock.runFor(10_000); await badgeText(normalBadge, '不通过');
  await capture('hold'); await page.clock.runFor(6_000); await badgeText(normalBadge, '不通过');
  await page.evaluate(() => { window.__outcome = 'fail'; window.__finishAnalysis(); window.__finishAnalysis = null; });
  await waitFor(() => window.__sequence === 3); scenarios++; console.log(`PASS camera display scenario ${scenarios}`);

  // A stale PASS deadline must not erase its replacement FAIL.
  await capture(); await page.clock.runFor(2_000); await capture('fail');
  await page.clock.runFor(4_000); await badgeText(normalBadge, '不通过'); scenarios++; console.log(`PASS camera display scenario ${scenarios}`);

  // A new PASS has its own full deadline.
  await capture(); await page.clock.runFor(3_000); await capture();
  await page.clock.runFor(2_000); await badgeText(normalBadge, '通过');
  await page.clock.runFor(2_999); await badgeText(normalBadge, '通过');
  await page.clock.runFor(1); await badgeText(normalBadge, '已就绪'); scenarios++; console.log(`PASS camera display scenario ${scenarios}`);

  // Fullscreen shares the current deadline, without resetting it on entry or exit.
  await capture(); await page.clock.runFor(2_000);
  await page.getByRole('button', { name: '全屏检测', exact: true }).click();
  const fullscreen = page.getByRole('dialog', { name: '全屏检测' });
  await page.clock.runFor(2_999); await badgeText(fullscreen.locator('.result-badge'), '通过');
  await page.clock.runFor(1); await badgeText(fullscreen.locator('.result-badge'), '已就绪');
  assert.equal(await fullscreen.locator('.inspection-fullscreen-result img').count(), 0);
  assert.equal(await fullscreen.locator('.result-pass').count(), 0);
  await capture('pass', true); await page.clock.runFor(2_000);
  await fullscreen.getByRole('button', { name: '退出全屏' }).click();
  await page.clock.runFor(3_000); await badgeText(normalBadge, '已就绪'); scenarios++; console.log(`PASS camera display scenario ${scenarios}`);

  // Expiry during the next request keeps processing, and an error cannot claim ready.
  await capture(); await page.clock.runFor(1_000); await capture('hold');
  await page.clock.runFor(4_000); await badgeText(normalBadge, '检测中…'); assert.equal(await normalImage.count(), 0);
  await page.evaluate(() => { window.__outcome = 'error'; window.__finishAnalysis(); window.__finishAnalysis = null; });
  await badgeText(normalBadge, '检测异常');
  await capture(); await capture('error'); await page.clock.runFor(5_000); await badgeText(normalBadge, '检测异常'); scenarios++; console.log(`PASS camera display scenario ${scenarios}`);

  // An ended camera is not ready after expiry.
  await capture(); await page.evaluate(() => document.querySelector('.camera-preview video').srcObject.getTracks().forEach(track => track.stop()));
  await page.clock.runFor(5_000); await badgeText(normalBadge, '未就绪'); scenarios++; console.log(`PASS camera display scenario ${scenarios}`);

  // Ordinary image/video successes retain their existing lifetime.
  for (const source of ['图片', '视频']) {
    await page.getByRole('tab', { name: source }).click();
    const drop = page.getByRole('button', { name: new RegExp('拖拽或选择.*' + source) });
    await drop.locator('input[type=file]').setInputFiles({ name: source === '图片' ? 'synthetic.png' : 'synthetic.mp4', mimeType: source === '图片' ? 'image/png' : 'video/mp4', buffer: Buffer.from('synthetic') });
    await page.evaluate(() => { window.__outcome = 'pass'; });
    const sequence = await page.evaluate(() => window.__sequence);
    await page.getByRole('button', { name: source === '图片' ? '开始 AI 检测' : '分析视频', exact: true }).click();
    await waitFor(value => window.__sequence > value, sequence);
    await page.clock.runFor(10_000); await badgeText(normalBadge, '通过'); assert.equal(await normalImage.count(), 1); scenarios++; console.log(`PASS camera display scenario ${scenarios}`);
  }

  // Exercise the real hook's task/model invalidation and cleanup with its raw evidence intact.
  await page.evaluate(async () => { const module = await import('/node_modules/.cache/camera-result-hook.tsx'); module.mount(); });
  await page.locator('#hook-fixture').waitFor();
  const hookDisplay = page.locator('#hook-fixture [data-display]');
  await page.evaluate(() => window.__hookFixture.publish({ passed: true, request_id: 'task-pass' }, 'camera'));
  await page.clock.runFor(2_000);
  await page.evaluate(() => window.__hookFixture.change('task-b:model-b'));
  await badgeText(hookDisplay, '-');
  assert.equal(await page.locator('#hook-fixture [data-raw]').innerText(), 'task-pass');
  await page.evaluate(() => window.__hookFixture.change('task-a:model-a'));
  await badgeText(hookDisplay, '-'); // Returning to the old model cannot resurrect its PASS.
  await page.evaluate(() => window.__hookFixture.change('task-b:model-b'));
  await page.evaluate(() => window.__hookFixture.publish({ passed: false, request_id: 'new-fail' }, 'camera'));
  await page.clock.runFor(10_000); await badgeText(hookDisplay, 'new-fail');
  await page.evaluate(() => window.__hookFixture.publish({ passed: true, request_id: 'unmount-pass' }, 'camera'));
  await page.evaluate(() => window.__hookFixture.unmount());
  await page.clock.runFor(6_000); assert.equal(await page.locator('#hook-fixture').count(), 0); scenarios++; console.log(`PASS camera display scenario ${scenarios}`);

  assert.deepEqual(errors, []);
  assert.equal(await page.evaluate(() => Boolean(navigator.serial)), false);
  console.log(JSON.stringify({ scenarios, errors, physicalSerial: false, screenshots: evidence }));
} finally {
  await browser?.close();
  fixture.kill();
}
