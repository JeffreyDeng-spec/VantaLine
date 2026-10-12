// Best-effort bounded diagnostic evidence. This module never performs PLC I/O.
export type DiagnosticStep = "selection"|"workstation"|"lease"|"open"|"quiet"|"read"|"activate"|"heartbeat"|"write"|"disconnect"|"summary";
export type DiagnosticCode = ""|"unsupported"|"cancelled"|"occupied"|"serial_error"|"timeout"|"partial_response"|"invalid_frame"|"invalid_checksum"|"residual_data"|"permission_denied"|"lease_rejected"|"lease_lost"|"config_changed"|"background"|"nak"|"uncertain"|"unplugged"|"user_disconnect"|"connection_failed"|"transport_error";
export type DiagnosticEvent = {
  event_id:string; attempt_id:string; sequence:number; station_id:string|null; step:DiagnosticStep;
  result:"started"|"ok"|"failed"|"cancelled"|"uncertain"|"summary"; code:DiagnosticCode;
  client_time_ms:number; duration_ms:number; config_generation:number; lease_epoch:number; bundle_version:string;
  dispatch_id:string; target:string; trigger_state:""|"high"|"reset"; expected_bytes:number; actual_bytes:number;
  reads_ok:number; heartbeats_ok:number; writes_ok:number; dropped:number;
  config?:{baudrate:9600;data_bits:7;parity:"E";stop_bits:1;input_register:string;result_register:string;output_control_point:string;timeout_ms:500;capture_enabled:boolean;trigger_value:number};
};
type ErrorDetail = {code:DiagnosticCode;expected_bytes?:number;actual_bytes?:number};
const errorDetails = new WeakMap<object, ErrorDetail>();
export function diagnosticError<T extends Error>(error:T, detail:ErrorDetail):T {try {errorDetails.set(error,detail);}catch {/* diagnostic metadata is optional */}return error;}
export function diagnosticErrorDetail(error:unknown):ErrorDetail {
  if(error && typeof error==="object") {
    const stored=errorDetails.get(error); if(stored) return stored;
    const e=error as {name?:string;status?:number};
    if(e.name==="TimeoutError") return {code:"timeout"};
    if(e.name==="NotFoundError") return {code:"cancelled"};
    if(e.name==="InvalidStateError"||e.name==="NetworkError") return {code:"occupied"};
    if(e.status===403) return {code:"permission_denied"};
    if(e.status===409) return {code:"lease_rejected"};
  }
  return {code:"serial_error"};
}
export const diagnosticMessages:Record<DiagnosticCode,string> = {
  "":"成功",unsupported:"浏览器不支持安全串口连接",cancelled:"未选择串口",occupied:"串口无法打开，请检查是否被其他程序占用",
  serial_error:"串口通信异常",timeout:"等待 PLC 响应超时",partial_response:"PLC 返回数据不完整",invalid_frame:"PLC 返回帧格式错误",
  invalid_checksum:"PLC 返回校验和错误",residual_data:"串口存在残留数据",permission_denied:"账号无连接权限",lease_rejected:"工作站租约申请被拒绝",
  lease_lost:"工作站租约失效",config_changed:"工作站配置已变化",background:"页面在后台或连接校验已过期",nak:"PLC 拒绝指令（NAK）",
  uncertain:"PLC 执行结果不确定",unplugged:"串口设备已拔出",user_disconnect:"人工断开",connection_failed:"PLC 连接失败",transport_error:"回执上传失败"
};

export class DiagnosticTransport {
  private owner=""; private generation=0; private enabled:boolean|null=null;
  private queue:Array<{event:DiagnosticEvent;bytes:number}>=[]; private bytes=0;
  private timer:ReturnType<typeof setInterval>|null=null; private controller:AbortController|null=null;
  private flushRequested=false; private deferred:ReturnType<typeof setTimeout>|null=null;
  private pausedControllers=new WeakSet<AbortController>();
  private busy=0; private inFlight=false; private nextAttempt=0; private backoff=10000; private configAt=0;
  private listeners=new Set<()=>void>(); dropped=0;
  constructor(private send:typeof fetch=(...args)=>fetch(...args)) {}
  setIdentity(owner:string) {
    if(this.owner===owner) return;
    this.generation++; this.controller?.abort(); this.owner=owner; this.queue=[]; this.bytes=0;
    this.enabled=null; this.dropped=0; this.configAt=0; this.nextAttempt=0;this.backoff=10000;
    if(this.timer) clearInterval(this.timer);this.timer=null;
    if(this.deferred) clearTimeout(this.deferred);this.deferred=null;this.flushRequested=false;
    if(owner) this.timer=setInterval(()=>{void this.tick();},10000);
    this.notify();
  }
  subscribe(fn:()=>void) {this.listeners.add(fn);return ()=>{this.listeners.delete(fn);};}
  pending(attempt:string) {return this.queue.some(x=>x.event.attempt_id===attempt);}
  private notify() {for(const fn of this.listeners) {try {fn();}catch {/* UI cannot affect I/O */}}}
  private deferFlush() {
    if(!this.owner||this.busy||this.inFlight||!this.flushRequested||this.deferred) return;
    this.deferred=setTimeout(()=>{this.deferred=null;void this.tick();},0);
  }
  enter() {
    this.busy++;
    if(this.controller) {this.pausedControllers.add(this.controller);this.flushRequested=true;this.controller.abort();}
  }
  leave() {this.busy=Math.max(0,this.busy-1);this.deferFlush();}
  enqueue(event:DiagnosticEvent) {
    try {
      if(!this.owner||this.enabled===false) return;
      // Conservative fixed reservation exceeds the maximum encoded size of
      // this fixed-field event; no stringify/TextEncoder in the physical path.
      const bytes=2048;
      while(this.queue.length>=200 || this.bytes+bytes>256*1024) {
        let index=this.queue.findIndex(x=>x.event.result==="summary");if(index<0) index=0;
        const [old]=this.queue.splice(index,1);this.bytes-=old.bytes;this.dropped=Math.min(2147483647,this.dropped+1);
      }
      this.queue.push({event:{...event,dropped:this.dropped},bytes});this.bytes+=bytes;
      // Subscribers are notified only by the uploader, outside serial work.
    } catch {/* Logging never propagates into production. */}
  }
  async tick() {
    if(!this.owner||this.inFlight||Date.now()<this.nextAttempt) return;
    if(this.busy) {this.flushRequested=true;return;}
    this.flushRequested=false;
    this.inFlight=true;const generation=this.generation;const controller=new AbortController();this.controller=controller;
    const timeout=setTimeout(()=>controller.abort(),2000);
    try {
      if(this.enabled===null||Date.now()-this.configAt>=60000) {
        const response=await this.send("/api/plc/diagnostic-events/config",{credentials:"same-origin",signal:controller.signal});
        if(!response.ok) throw new Error("diagnostic config unavailable");
        const data=await response.json();
        if(generation!==this.generation) return;
        if(data.account_id!==this.owner) {this.setIdentity("");return;}
        this.enabled=data.enabled===true;this.configAt=Date.now();
        if(!this.enabled) {this.queue=[];this.bytes=0;return;}
      }
      if(this.busy||controller.signal.aborted||!this.queue.length) return;
      const batch=this.queue.slice(0,20);const body=JSON.stringify({events:batch.map(x=>x.event)});
      if(new TextEncoder().encode(body).byteLength>32768) throw new Error("diagnostic batch too large");
      const response=await this.send("/api/plc/diagnostic-events/batch",{method:"POST",credentials:"same-origin",headers:{"Content-Type":"application/json"},body,signal:controller.signal});
      if(!response.ok) throw new Error("diagnostic upload unavailable");
      const data=await response.json();if(generation!==this.generation) return;
      if(data.enabled===false) {this.enabled=false;this.queue=[];this.bytes=0;return;}
      const accepted=new Set<string>(data.accepted||[]);
      this.queue=this.queue.filter(x=>!accepted.has(x.event.event_id));this.bytes=this.queue.reduce((n,x)=>n+x.bytes,0);
      this.backoff=10000;this.nextAttempt=Date.now()+10000;
    } catch {
      if(generation===this.generation && !this.pausedControllers.has(controller)) {this.nextAttempt=Date.now()+this.backoff;this.backoff=Math.min(60000,this.backoff*2);}
    } finally {
      clearTimeout(timeout);
      if(this.controller===controller) this.controller=null;
      this.inFlight=false;this.notify();this.deferFlush();
    }
  }
}
export const diagnosticTransport=new DiagnosticTransport();

export class PlcDiagnosticLog {
  lastFailure:Partial<DiagnosticEvent>|null=null;
  attemptId=""; private sequence=0;private station:string|null=null; private epoch=0;private configGeneration=0;
  private reads=0;private heartbeats=0;private writes=0;private summaryAt=performance.now();
  private version=import.meta.env.VITE_PLC_BUNDLE_VERSION || "development";
  constructor(private transport=diagnosticTransport) {}
  begin() {
    try {this.attemptId=`plcdiag_${crypto.randomUUID()}`;this.sequence=0;this.lastFailure=null;this.station=null;this.epoch=0;this.configGeneration=0;this.reads=0;this.heartbeats=0;this.writes=0;this.summaryAt=performance.now();}
    catch {this.attemptId="";}
    this.record("selection","started");return this.attemptId;
  }
  bind(station:string,generation:number,epoch=0) {this.station=station;this.configGeneration=generation;this.epoch=epoch;}
  setVersion(version:string) {this.version=version.replace(/[^A-Za-z0-9._-]/g,"").slice(0,100);}
  enter() {try {this.transport.enter();}catch {/* isolated */}}
  leave() {try {this.transport.leave();}catch {/* isolated */}}
  record(step:DiagnosticStep,result:DiagnosticEvent["result"],fields:Partial<DiagnosticEvent>={}) {
    try {
      if(!this.attemptId) return;
      this.transport.enqueue({event_id:`plcevt_${crypto.randomUUID()}`,attempt_id:this.attemptId,sequence:this.sequence++,station_id:this.station,step,result,code:"",client_time_ms:Date.now(),duration_ms:0,config_generation:this.configGeneration,lease_epoch:this.epoch,bundle_version:this.version,dispatch_id:"",target:"",trigger_state:"",expected_bytes:0,actual_bytes:0,reads_ok:0,heartbeats_ok:0,writes_ok:0,dropped:0,...fields});
    }catch {/* isolated */}
  }
  failure(step:DiagnosticStep,error:unknown,fields:Partial<DiagnosticEvent>={}) {
    this.lastFailure={step,...diagnosticErrorDetail(error),...fields};
    this.record(step,"failed",this.lastFailure);
  }
  count(kind:"reads"|"heartbeats"|"writes") {
    if(kind==="reads")this.reads++;if(kind==="heartbeats")this.heartbeats++;if(kind==="writes")this.writes++;
    if(performance.now()-this.summaryAt>=60000)this.summary();
  }
  summary() {
    if(this.reads||this.heartbeats||this.writes)this.record("summary","summary",{reads_ok:this.reads,heartbeats_ok:this.heartbeats,writes_ok:this.writes});
    this.reads=0;this.heartbeats=0;this.writes=0;this.summaryAt=performance.now();
  }
}
