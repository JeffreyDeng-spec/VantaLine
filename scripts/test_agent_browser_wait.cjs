const assert = require('node:assert/strict');
const test = require('node:test');
const {waitForNativeTools} = require('./agent_browser_wait.cjs');
const snapshot = names => ({supported:true, ready:true, names});

test('awaits discovery snapshots until every required name is present', async () => {
  let calls = 0;
  const page = {async evaluate() { calls++; return snapshot(calls < 3 ? [] : ['core', 'text']); }};
  const result = await waitForNativeTools(page, {present:['core','text'], ready:true, timeout:1000});
  assert.equal(calls, 3); assert.deepEqual(result.names, ['core','text']);
});
test('does not finish removal until the native list is actually empty', async () => {
  let calls = 0;
  const page = {async evaluate() { return snapshot(++calls < 3 ? ['pending'] : []); }};
  await waitForNativeTools(page, {empty:true, timeout:1000}); assert.equal(calls, 3);
});
test('false and stalled observations time out rather than passing', async () => {
  await assert.rejects(waitForNativeTools({evaluate:async()=>snapshot([])}, {present:['missing'],timeout:60}), /timed out/);
  await assert.rejects(waitForNativeTools({evaluate:()=>new Promise(()=>{})}, {timeout:60}), /timed out/);
});
test('native discovery errors propagate without hiding a broken browser API', async () => {
  await assert.rejects(waitForNativeTools({evaluate:async()=>{throw Error('native failure');}}, {timeout:100}), /native failure/);
});
