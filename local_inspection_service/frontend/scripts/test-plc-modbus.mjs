// Actual browser/controller with synthetic serial/API. Never connects to hardware.
import assert from 'node:assert/strict';
import {fileURLToPath} from 'node:url';
import {createServer} from 'vite';
import {chromium} from 'playwright';
const root=fileURLToPath(new URL('../',import.meta.url));
const server=await createServer({root,configFile:false,server:{host:'127.0.0.1',port:0},plugins:[{
  name:'modbus-harness',resolveId(id){if(id==='/__entry.ts')return id;},
  load(id){if(id==='/__entry.ts')return `import {PlcWebSerialClient} from '/src/features/plc/webSerialClient.ts';window.client=new PlcWebSerialClient();`;},
  configureServer(s){s.middlewares.use(async(req,res,next)=>{if(req.url!=='/__test')return next();res.setHeader('Content-Type','text/html');res.end(await s.transformIndexHtml(req.url,'<html><body><script type="module" src="/__entry.ts"></script></body></html>'));});}
}]});
await server.listen();
const browser=await chromium.launch({headless:true,channel:process.env.PLC_TEST_BROWSER||undefined});
const base=`http://127.0.0.1:${server.httpServer.address().port}`;
const crc=data=>{let c=65535;for(const b of data){c^=b;for(let i=0;i<8;i++)c=(c>>>1)^(c&1?40961:0);}return c;};
const frame=data=>{const c=crc(data);return [...data,c&255,c>>>8];};
const hex=data=>Buffer.from(data).toString('hex').toUpperCase();
const readFrames=[205,206].map(n=>({target:`D${n}`,frame_hex:hex(frame([1,3,0,n,0,1]))}));
const write=hex(frame([1,6,0,206,0,1]));
const active={station_id:'line',session_id:'session',lease_epoch:1,config_generation:1,state:'active',communication_verified:true};
async function scenario(mode){
 const context=await browser.newContext();const page=await context.newPage();let activated=0,receipt;const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await context.addInitScript(({mode})=>{
   let pending,options;window.evidence={opens:[],writes:[],closed:0};
   const crc=data=>{let c=65535;for(const b of data){c^=b;for(let i=0;i<8;i++)c=(c>>>1)^(c&1?40961:0);}return c;};
   const wrap=data=>{const c=crc(data);return new Uint8Array([...data,c&255,c>>>8]);};
   const reader={read:()=>new Promise(r=>pending=r),cancel:async()=>{pending?.({done:true});pending=null;},releaseLock(){}};
   const writer={releaseLock(){},write:async data=>{
     window.evidence.writes.push(Array.from(data));
     let response;
     if(options.baudRate===9600){if(mode==='fx')response=new Uint8Array([2,48,48,48,48,3,67,51]);else if(mode==='fx-noise')response=new Uint8Array([7]);else return;}
     else if(data[1]===3){response=wrap([mode==='wrong-unit'?2:1,3,2,0x12,0x34]);if(mode==='crc')response[6]^=1;if(mode==='partial')response=response.slice(0,3);if(mode==='extra')response=new Uint8Array([...response,6]);if(mode==='exception')response=wrap([1,0x83,2]);}
     else {if(mode==='write-timeout')return;response=new Uint8Array(data);if(mode==='write-wrong-echo')response[3]^=1;}
     queueMicrotask(()=>{const r=pending;pending=null;r?.({done:false,value:response});});
   }};
   window.port={getInfo:()=>({usbVendorId:1000,usbProductId:2000}),open:async o=>{window.evidence.opens.push(o);options=o;if(mode==='occupied')throw new DOMException('occupied','NetworkError');},close:async()=>{window.evidence.closed++;},readable:{getReader:()=>reader},writable:{getWriter:()=>writer}};
   Object.defineProperty(navigator,'serial',{value:{requestPort:async()=>window.port,addEventListener(){},removeEventListener(){}}});
 },{mode});
 await context.route('**/api/plc/**',async route=>{
  const path=new URL(route.request().url()).pathname;
  const payload=route.request().method()==='POST'?route.request().postDataJSON():null;
  const rtu={id:'rtu',deadline_at:Math.floor(Date.now()/1000)+60,timeout_ms:50,config:{protocol:'modbus_rtu'},serial_options:{baudRate:19200,dataBits:8,stopBits:1,parity:'even',flowControl:'none'},frames:readFrames};
  if(path.endsWith('/connect')){const check=['fallback','fx','fx-noise','occupied'].includes(mode)?{...rtu,id:'fx',config:{protocol:'fx_programming_port_ascii'},serial_options:{baudRate:9600,dataBits:7,stopBits:1,parity:'even',flowControl:'none'},frames:[{target:'D205',frame_hex:'0230313139413032033731'},{target:'D206',frame_hex:'0230313139433032033733'}],alternatives:[rtu]}:rtu;return route.fulfill({json:{...active,state:'connecting',connection_check:check}});}
  if(path.endsWith('/activate')){activated++;assert.equal(payload.connection_reads.length,2);assert.equal(payload.connection_check_id,mode==='fx'?'fx':'rtu');return route.fulfill({json:active});}
  if(path.endsWith('/attempt'))return route.fulfill({json:{dispatch_id:'dispatch',execution_window_ms:2000,ack_timeout_ms:50,frames:[{target:'D206',frame_hex:write,frame_sha256:'d',expected_response_hex:write}]}});
  if(path.endsWith('/receipt')){receipt=payload;return route.fulfill({json:{dispatch_id:'dispatch',status:'done'}});}
  return route.fulfill({json:active});
 });
 await page.goto(`${base}/__test`);await page.waitForFunction(()=>window.client);
 const result=await page.evaluate(async()=>{try{await window.client.connect('line','',()=>{},window.port);return {connected:!!window.client.state()};}catch(e){return {connected:false,error:e.message};}});
 const successful=['rtu','fallback','fx','write-ok','write-timeout','write-wrong-echo'].includes(mode);
 assert.equal(result.connected,successful,`${mode}: ${JSON.stringify(result)}`);assert.equal(activated,successful?1:0);
 if(mode.startsWith('write-')){await page.evaluate(()=>window.client.execute({dispatch_id:'dispatch'},()=>{}));assert.equal(receipt.operations.length,1);assert.equal(receipt.operations[0].status,mode==='write-ok'?'acknowledged':mode==='write-timeout'?'timeout':'unexpected_response');assert.equal(await page.evaluate(()=>!!window.client.state()),mode==='write-ok');}
 const evidence=await page.evaluate(()=>window.evidence);
 assert.equal(evidence.opens.length,mode==='fallback'?2:1);
 assert(evidence.writes.length<=4);
 assert.equal(evidence.writes.filter(f=>f[0]===1&&f[1]===6).length,mode.startsWith('write-')?1:0,'no physical write during identification or retry');
 if(mode==='fallback')assert.deepEqual(evidence.opens.map(o=>[o.baudRate,o.dataBits]),[[9600,7],[19200,8]]);
 assert.deepEqual(errors,[]);await context.close();console.log(`Modbus browser ${mode}: PASS`);
}
try{for(const mode of ['rtu','fallback','fx','fx-noise','occupied','crc','partial','extra','exception','wrong-unit','write-ok','write-timeout','write-wrong-echo'])await scenario(mode);}finally{await browser.close();await server.close();}
