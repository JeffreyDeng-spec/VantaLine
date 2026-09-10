// Discovery is asynchronous. page.waitForFunction treats a Promise as truthy in
// Playwright 1.62.1, even when it resolves to false. Await each observation here.
// Only discovery is polled: business operations are never retried by this helper.
const {setTimeout: sleep} = require('node:timers/promises');

async function waitForNativeTools(page, {present = [], absent = [], empty = false, ready = false, timeout = 10000} = {}) {
  let last;
  const deadline = performance.now() + timeout;
  let timer;
  const expired = new Promise((_, reject) => {
    timer = setTimeout(() => reject(new Error(`Native tool discovery timed out: ${JSON.stringify({present, absent, empty, ready, last})}`)), timeout);
  });
  try {
    while (performance.now() < deadline) {
      last = await Promise.race([page.evaluate(async () => ({
        supported: typeof document.modelContext?.getTools === 'function',
        ready: document.querySelector('[data-agent-ready="true"]') !== null,
        names: typeof document.modelContext?.getTools === 'function'
          ? (await document.modelContext.getTools()).map(tool => tool.name) : []
      })), expired]);
      if (last.supported && (!ready || last.ready) && (!empty || last.names.length === 0)
        && present.every(name => last.names.includes(name)) && absent.every(name => !last.names.includes(name))) return last;
      await Promise.race([sleep(25), expired]);
    }
    throw new Error(`Native tool discovery timed out: ${JSON.stringify({present, absent, empty, ready, last})}`);
  } finally { clearTimeout(timer); }
}
module.exports = {waitForNativeTools};
