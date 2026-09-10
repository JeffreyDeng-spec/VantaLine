// Execute the actual TypeScript URL helpers without a browser or network.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('../local_inspection_service/frontend/node_modules/typescript');
const file = require('node:path').join(__dirname, '../local_inspection_service/frontend/src/app/paths.ts');
const compiled = ts.transpileModule(fs.readFileSync(file, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS } });
const target = { exports: {} };
new Function('exports', 'module', compiled.outputText)(target.exports, target);
const { workspacePath, safeWorkspaceNext, legacyWorkspaceDestination, loginPath, legacyWorkspacePages } = target.exports;
assert.equal(workspacePath(), '/workspace');
assert.equal(workspacePath('/training-library?tab=tasks'), '/workspace/training-library?tab=tasks');
for (const value of ['/workspace', '/workspace/about', '/workspace/text-compare-beta?order=one#image', '/workspace/tasks/pipeline%3Aabc/inspect?view=1#crop']) {
  assert.equal(safeWorkspaceNext(value), value);
  assert.equal(new URLSearchParams(loginPath(value).split('?')[1]).get('next'), value);
}
for (const value of [null, '', '/', '//evil.invalid', 'https://evil.invalid', '/workspace-evil', '/workspace//evil.invalid', '/workspace/../login', '/workspace/%2e%2e/login', '/workspace/tasks/a%2fb', '/workspace/tasks/%252e%252e', '/workspace/tasks/a\\b', '/workspace/tasks/a%00b', '/workspace/no-page', '/workspace/tasks', '/workspace/tasks/%zz', '/workspace/tasks/a/../../login']) {
  assert.equal(safeWorkspaceNext(value), '/workspace', String(value));
}
for (const page of legacyWorkspacePages.filter(x => x !== 'tasks')) assert.equal(legacyWorkspaceDestination('/'+page), '/workspace/'+page);
assert.equal(legacyWorkspaceDestination('/tasks/pipeline%3Aone/inspect'), '/workspace/tasks/pipeline%3Aone/inspect');
for (const value of ['/api/status', '/static/file', '/unknown', '/inspect/unexpected', '/login', '/']) assert.equal(legacyWorkspaceDestination(value), null);
console.log('navigation path tests: passed');
