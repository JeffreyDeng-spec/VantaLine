// Exercise the actual client and parsers against a synthetic serial reader; no hardware/API.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import ts from 'typescript';
const log={enter(){},leave(){},count(){},record(){},failure(){}};
const diagnostic={PlcDiagnosticLog:class {constructor(){Object.assign(this,log)}},diagnosticError:e=>e,diagnosticErrorDetail:()=>({})};
function load(file,imports){const code=ts.transpileModule(readFileSync(new URL(file,import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;const m={exports:{}};new Function('require','module','exports',code)(id=>imports[id]||{},m,m.exports);return m.exports;}
const modbus=load('../src/features/plc/modbusRtu.ts',{'./diagnosticLog':diagnostic});
const {PlcWebSerialClient}=load('../src/features/plc/webSerialClient.ts',{'./diagnosticLog':diagnostic,'./modbusRtu':modbus});
globalThis.window={setTimeout,clearTimeout};globalThis.document={visibilityState:'visible'};
function fx(value){const str=[value&255,value>>8].map(n=>n.toString(16).padStart(2,'0').toUpperCase()).join('');const body=Buffer.from(str+'\x03');return Uint8Array.from([2,...body,...Buffer.from([...body].reduce((a,b)=>(a+b)&255,0).toString(16).padStart(2,'0').toUpperCase())]);}
function rtu(value){const bytes=[1,3,2,value>>8,value&255];const crc=modbus.modbusCrc(Uint8Array.from(bytes));return Uint8Array.from([...bytes,crc&255,crc>>8]);}
function fixture(responses,rtuMode=false){const c=new PlcWebSerialClient();let connected=true,resolveRead;const frames=[];let closes=0,fatals=0;c.state=()=>connected?{configGeneration:7}:null;c.modbus=rtuMode;c.reader={read:()=>new Promise(resolve=>{assert.equal(resolveRead,undefined,'no parallel reader');resolveRead=resolve})};c.writer={write:async bytes=>{frames.push([...bytes]);const respond=resolveRead;resolveRead=undefined;setTimeout(()=>respond({done:false,value:responses.shift()}),1)}};c.disconnect=async()=>{connected=false;closes++};return {c,frames,fatal:()=>fatals++,stats:()=>({closes,fatals,connected})};}
const output={target:'D1',operation:'read_result_register',frame_hex:'010300010001D5CA',expected_response_bytes:8,read_timeout_ms:50,poll_interval_ms:1000,config_generation:7,protocol_version:'plc-web-serial-v4'};
const input={...output,target:'D0',operation:'read_capture_input',frame_hex:'010300000001840A',poll_interval_ms:200,trigger_value:1};
let f=fixture([fx(1),fx(0),fx(65535)]);
const reads=await Promise.all([f.c.readCaptureInput(input,f.fatal),f.c.readResultRegister(output,f.fatal),f.c.readResultRegister(output,f.fatal)]);
assert.deepEqual(reads.map(r=>r.value),[1,0,65535]);assert.equal(f.c.diagnosticTriggerHigh,true,'output must not alter input edge state');assert.equal(f.frames.length,3);assert.deepEqual(f.stats(),{closes:0,fatals:0,connected:true});
f.c.priorityOperations=1;assert.equal(await f.c.readResultRegister(output,f.fatal),null);f.c.priorityOperations=0;document.visibilityState='hidden';assert.equal(await f.c.readResultRegister(output,f.fatal),null);document.visibilityState='visible';assert.equal(f.frames.length,3);
f=fixture([rtu(42)],true);assert.equal((await f.c.readResultRegister({...output,expected_response_bytes:7},f.fatal)).value,42);
for(const [name,plan,response,rtuMode] of [['generation',{...output,config_generation:8},fx(1),false],['checksum',output,Uint8Array.from([2,48,49,48,48,3,48,48]),false],['crc',{...output,expected_response_bytes:7},Uint8Array.from([1,3,2,0,1,0,0]),true],['short',output,Uint8Array.from([2]),false]]){
 f=fixture([response],rtuMode);await assert.rejects(f.c.readResultRegister(plan,f.fatal));assert.deepEqual(f.stats(),{closes:1,fatals:1,connected:false},name);assert.equal(f.frames.length,name==='generation'?0:1,'never retry a read after uncertain framing');
}
console.log('PASS actual PLC client: serialized input/output readback, 0/65535, FX/RTU parsing, write priority, hidden-page skip, generation/checksum/CRC/short-response fail closed and no retry');
