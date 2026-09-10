import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createRequire} from 'node:module';
import vm from 'node:vm';
import ts from 'typescript';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../src/features/agent');
const cache=new Map();
function load(name) {
  const file=path.resolve(root,name.endsWith('.ts')?name:name+'.ts');
  if(cache.has(file)) return cache.get(file);
  const source=ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText;
  const module={exports:{}};cache.set(file,module.exports);
  const require=name=>name.startsWith('.')?load(path.resolve(path.dirname(file),name)):createRequire(import.meta.url)(name);
  vm.runInThisContext(`(function(exports,require,module){${source}\n})`,{filename:file})(module.exports,require,module);
  return module.exports;
}
const {ActionRegistry}=load('registry');
const {connectWebMCP}=load('webmcpAdapter');
const {validate,safeResult}=load('validation');
const action=(name,execute=()=>({id:'ok'}),domain='core')=>({name,domain,description:name,readOnly:false,inputSchema:{type:'object',properties:{},additionalProperties:false},execute});
const deferred=()=>{let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve};};
const flush=()=>new Promise(resolve=>setImmediate(resolve));
const deliverResult=()=>new Promise(resolve=>setTimeout(resolve,0));

test('strict inputs reject unknown fields and unsafe prototypes before side effects',async()=>{
  let count=0;const registry=new ActionRegistry();registry.register([action('edit',()=>count++)]);
  assert.equal((await registry.execute('edit',{})).error.code,'FORBIDDEN');
  registry.configure(()=>true,async()=>{});
  assert.equal((await registry.execute('edit',{sql:'drop'})).status,'failed');
  assert.equal(count,0);
  assert.throws(()=>validate({type:'object',additionalProperties:{}},JSON.parse('{"__proto__":{}}')));
  assert.throws(()=>validate({type:'integer'},1.5));
});
test('concurrent mutation is rejected; logout suppresses delayed result and credentials',async()=>{
  const result=deferred();const registry=new ActionRegistry();registry.configure(()=>true,async()=>{});
  registry.register([action('write',()=>result.promise)]);
  const first=registry.execute('write',{});
  assert.equal((await registry.execute('write',{})).error.code,'BUSY');
  registry.reset();result.resolve({private:'previous user'});
  assert.equal((await first).status,'outcome_unknown');
  assert.deepEqual(safeResult({apiKey:'secret',nested:{password:'secret'},polygon:Array(128).fill([0,0])}),{nested:{},polygon:Array(128).fill([0,0])});
});
test('acknowledged write remains completed when cache refresh fails',async()=>{
  const registry=new ActionRegistry();registry.configure(()=>true,async()=>{throw Error('offline');});
  registry.register([action('save')]);assert.equal((await registry.execute('save',{})).status,'completed');
});
test('acknowledged logout returns only a signed-out result after revocation',async()=>{
  const registry=new ActionRegistry();registry.configure(()=>true,async()=>{});
  registry.register([{...action('logout',()=>{registry.reset();return {secret:'old session'};}),endsSession:true}]);
  assert.deepEqual(await registry.execute('logout',{}),{status:'completed',data:{authenticated:false}});
});
test('registration is atomic when a batch contains duplicate IDs',()=>{
  const registry=new ActionRegistry();assert.throws(()=>registry.register([action('save'),action('save')]));assert.equal(registry.list().length,0);
});
test('document queue survives a delayed registration followed by StrictMode remount',async()=>{
  const tools=new Map(),delay=deferred(),errors=[];
  let first=true;
  const context={async registerTool(tool){if(first){first=false;await delay.promise;}if(tools.has(tool.name))throw Error('duplicate');tools.set(tool.name,tool);},unregisterTool(name){tools.delete(name);}};
  const registry=new ActionRegistry();registry.configure(()=>true,async()=>{});registry.register([action('save')]);
  const old=connectWebMCP(context,registry,()=> 'core',error=>errors.push(error));await flush();
  void old.close();const next=connectWebMCP(context,registry,()=> 'core',error=>errors.push(error));delay.resolve();await flush();await flush();
  assert.equal(tools.size,1);assert.equal(JSON.parse(await tools.get('vantaline_save').execute({})).status,'completed');assert.deepEqual(errors,[]);
  const stale=tools.get('vantaline_save');await next.close();await deliverResult();await flush();assert.equal(tools.size,0);assert.equal(JSON.parse(await stale.execute({})).error.code,'SESSION_CHANGED');
});
test('current signal-based WebMCP API works without unregisterTool',async()=>{
  const tools=new Map();const registry=new ActionRegistry();registry.configure(()=>true,async()=>{});registry.register([action('save')]);
  const adapter=connectWebMCP({registerTool(tool,{signal}){tools.set(tool.name,tool);signal.addEventListener('abort',()=>tools.delete(tool.name),{once:true});}},registry,()=> 'core',assert.fail);
  await flush();assert.equal(tools.size,1);const tool=tools.get('vantaline_save');
  assert.equal(JSON.parse(await tool.execute({}, {signal:AbortSignal.abort()})).error.code,'CANCELLED');
  await adapter.close();assert.equal(tools.size,0);
});
test('workspace changes remove old domain tools while retaining discovery',async()=>{
  const tools=new Map();let domain='text';const registry=new ActionRegistry();registry.configure(()=>true,async()=>{});
  registry.register([action('context'),action('crop',undefined,'text'),action('train',undefined,'training')]);
  const adapter=connectWebMCP({registerTool:t=>tools.set(t.name,t),unregisterTool:n=>tools.delete(n)},registry,()=>domain,assert.fail);
  await flush();assert.deepEqual([...tools.keys()].sort(),['vantaline_context','vantaline_crop']);
  domain='training';adapter.refresh();await flush();assert.deepEqual([...tools.keys()].sort(),['vantaline_context','vantaline_train']);await adapter.close();
});
test('removing a tool preserves every concurrent read result channel',async()=>{
  const tools=new Map(),a=deferred(),b=deferred();let calls=0;
  const registry=new ActionRegistry();registry.configure(()=>true,async()=>{});
  registry.register([{...action('read',()=>++calls===1?a.promise:b.promise,'text'),readOnly:true}]);
  let domain='text';const adapter=connectWebMCP({registerTool(tool,{signal}){tools.set(tool.name,tool);signal.addEventListener('abort',()=>tools.delete(tool.name));}},registry,()=>domain,assert.fail);
  await flush();const tool=tools.get('vantaline_read');const one=tool.execute({}),two=tool.execute({});
  domain='training';adapter.refresh();await flush();assert.equal(tools.size,1);
  a.resolve({id:1});await one;await flush();assert.equal(tools.size,1);
  b.resolve({id:2});await two;await deliverResult();await flush();assert.equal(tools.size,0);await adapter.close();
});

test('native result can be consumed before deferred unregistration',async()=>{
  const tools=new Map(),result=deferred();let domain='text',signal;
  const registry=new ActionRegistry();registry.configure(()=>true,async()=>{});
  registry.register([{...action('pending',()=>result.promise,'text'),readOnly:true}]);
  const adapter=connectWebMCP({registerTool(tool,options){signal=options.signal;tools.set(tool.name,tool);signal.addEventListener('abort',()=>tools.delete(tool.name));}},registry,()=>domain,assert.fail);
  await flush();
  const delivered=tools.get('vantaline_pending').execute({}).then(value=>{
    // Models Chrome's result consumption after the callback promise resolves.
    assert.equal(signal.aborted,false,'registration aborted before result delivery');
    return JSON.parse(value);
  });
  domain='training';adapter.refresh();await flush();
  result.resolve({id:'verified'});assert.equal((await delivered).status,'completed');
  await deliverResult();await flush();assert.equal(signal.aborted,true);assert.equal(tools.size,0);
  await adapter.close();
});
