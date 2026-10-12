const assert = require('node:assert/strict');
const test = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('../local_inspection_service/frontend/node_modules/typescript');
const source = fs.readFileSync(path.join(__dirname, '../local_inspection_service/frontend/src/features/version/coordinator.ts'), 'utf8');
const code = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.ESNext } }).outputText;
const modulePromise = import('data:text/javascript;base64,' + Buffer.from(code).toString('base64'));
const local = { release: 'v2026.10.100', git_commit: 'a'.repeat(40) };
const newer = { release: 'v2026.10.101', git_commit: 'b'.repeat(40), consistent: true };
const tick = () => new Promise(resolve => setImmediate(resolve));
async function fixture(value = newer) {
  const { VersionCoordinator } = await modulePromise;
  const output = [], attempts = new Set();
  let calls = 0, now = 0, accept = true;
  const coordinator = new VersionCoordinator(local, {
    now: () => now, currentUrl: () => 'https://fixture.test/inspect?task=one',
    fetchVersion: async () => { ++calls; if (value instanceof Error) throw value; return typeof value === 'function' ? value() : value; },
    readAttempt: key => attempts.has(key), writeAttempt: key => attempts.add(key),
    confirmDiscard: () => accept, reload: url => output.push(url)
  });
  return { coordinator, output, attempts, calls: () => calls, value: v => { value = v; }, accept: v => { accept = v; }, advance: ms => { now += ms; } };
}
test('same identity continues without refresh', async () => {
  const f = await fixture({ ...local, consistent: true });
  assert.equal(await f.coordinator.guard(), true); assert.deepEqual(f.output, []);
});
test('a tab loaded before deployment compares its compiled identity, then preserves navigation URL', async () => {
  const f = await fixture(); await f.coordinator.check(); assert.equal(f.coordinator.snapshot().pending, true);
  assert.deepEqual(f.output, []);
  assert.equal(await f.coordinator.guard('https://fixture.test/tasks/two?mode=video#result'), false);
  assert.deepEqual(f.output, ['https://fixture.test/tasks/two?mode=video#result']);
});
test('rollback is a changed identity even with a lower release number', async () => {
  const f = await fixture({ ...newer, release: 'v2026.09.50' });
  await f.coordinator.guard(); assert.equal(f.output.length, 1);
});
test('failures and inconsistent/malformed responses never authorize reload', async () => {
  for (const value of [new Error('timeout'), new Error('offline'), { ...newer, consistent: false }, { ...newer, git_commit: 'unknown' }, null, {}]) {
    const f = await fixture(value); assert.equal(await f.coordinator.guard(), true); assert.equal(f.output.length, 0);
  }
});
test('failed recheck invalidates a previous pending update', async () => {
  const f = await fixture(); await f.coordinator.check(); f.value(new Error('offline')); f.advance(15_001);
  assert.equal(await f.coordinator.guard(), true); assert.equal(f.coordinator.snapshot().pending, false);
});
test('checks coalesce and a fresh result suppresses redundant entry requests', async () => {
  let release; const gate = new Promise(resolve => { release = resolve; });
  const f = await fixture(() => gate);
  const one = f.coordinator.check(), two = f.coordinator.check(true); assert.equal(f.calls(), 1);
  release({ ...local, consistent: true }); await Promise.all([one, two]);
  await f.coordinator.guard(); assert.equal(f.calls(), 1); f.advance(15_001); await f.coordinator.guard(); assert.equal(f.calls(), 2);
});
test('retain a form/file/annotation cancels navigation and cleanup', async () => {
  const f = await fixture(); let cleaned = 0;
  f.coordinator.register({ dirty: () => true, cleanup: () => { ++cleaned; } }); f.accept(false);
  assert.equal(await f.coordinator.guard(), false); assert.equal(cleaned, 0); assert.equal(f.output.length, 0);
  assert.equal(f.coordinator.snapshot().preparing, false);
});
test('discard authorizes cleanup and refresh without replaying the business action', async () => {
  const f = await fixture(); const order = [];
  f.coordinator.register({ dirty: () => true, cleanup: () => { order.push('closed'); } });
  let submissions = 0; if (await f.coordinator.guard()) ++submissions;
  assert.equal(submissions, 0); assert.deepEqual(order, ['closed']); assert.equal(f.output.length, 1);
});
test('pause new captures, drain current operation/receipt, then clean up and reload once', async () => {
  const f = await fixture(); const order = []; let busy = true;
  const finish = f.coordinator.beginOperation();
  f.coordinator.register({ busy: () => busy, pause: () => order.push('pause'), cleanup: () => order.push('close') });
  const pending = f.coordinator.guard(); await tick();
  assert.deepEqual(order, ['pause']); assert.equal(f.output.length, 0);
  assert.equal(await f.coordinator.guard(), false);
  busy = false; f.coordinator.signal(); await tick(); assert.equal(f.output.length, 0);
  order.push('receipt'); finish(); await pending;
  assert.deepEqual(order, ['pause', 'receipt', 'close']); assert.equal(f.output.length, 1);
});
test('latest identity is revalidated after a long operation', async () => {
  const f = await fixture(); const finish = f.coordinator.beginOperation(); const pending = f.coordinator.guard(); await tick();
  f.value({ ...local, consistent: true }); finish(); assert.equal(await pending, true); assert.equal(f.output.length, 0);
});
test('same target after reload is stalled until an explicit retry', async () => {
  const f = await fixture(); f.attempts.add(`${newer.release}:${newer.git_commit}`);
  assert.equal(await f.coordinator.guard(), false); assert.equal(f.coordinator.snapshot().stalled, true); assert.equal(f.output.length, 0);
  await f.coordinator.guard(undefined, true); assert.equal(f.output.length, 1);
});
test('cleanup rejection preserves the page', async () => {
  const f = await fixture(); f.coordinator.register({ cleanup: () => { throw new Error('not closed'); } });
  await f.coordinator.guard(); assert.equal(f.output.length, 0); assert.equal(f.coordinator.snapshot().preparing, false);
});
test('gesture path is synchronous only while version is current and fresh', async () => {
  const f = await fixture({ ...local, consistent: true }); assert.equal(f.coordinator.gestureReady(), false);
  await f.coordinator.check(); assert.equal(f.coordinator.gestureReady(), true); f.advance(15_001); assert.equal(f.coordinator.gestureReady(), false);
});
