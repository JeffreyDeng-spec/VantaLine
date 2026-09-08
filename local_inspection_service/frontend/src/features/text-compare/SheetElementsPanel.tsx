import { useEffect, useRef, useState } from "react";
import { apiClient } from "../../api/client";
import "./sheet-elements.css";

type Box = [number,number,number,number];
type Item = {id:string; type:"text"|"parameter"|"code"|"graphic"; expected:string; box:Box; required:boolean; ignore_reason:string; match:"exact"|"whitespace"};
type Evidence = {text:string;box:Box;confidence:number};
type Finding = {element_id:string;expected:string;state:string;reason:string;standard_box:Box;evidence:Evidence[];conflicts?:Evidence[]};
type Resource = {id:string;root_id:string;status:string;version:number;standard_revision_id:string;elements?:Item[];media:Record<string,string>;error_code?:string;result?:{decision:string;gate_reason?:string;elements:Finding[]};diagnostics?:unknown};
const API="/api/text-inspection/sheet";
const finished=(v:Resource)=>["draft","confirmed","completed","review"].includes(v.status);
const states:Record<string,string>={queued:"排队",detecting:"单轮文字检测",recognizing:"分批识别与匹配",matching:"核对",reviewing:"复核",draft:"待确认",confirmed:"已确认",completed:"完成",review:"待复核"};
const reasons:Record<string,string>={not_detected:"未检出（不代表漏印）",conflicting_parameter:"存在冲突参数",consistent_parameter_mismatch:"多个位置识别到一致的不同参数",graphic_not_commissioned:"图形核验未完成验收",local_evidence:"找到本地证据"};

function EvidenceImage({src,boxes,select,zoom}:{src:string;boxes:{id:string;box:Box;state?:string}[];select:(id:string)=>void;zoom:()=>void}) {
  return <div className="sheet-image"><img src={src} alt="核对证据图" onClick={zoom}/>{boxes.map(v=><button key={v.id} type="button" aria-label={`定位元素 ${v.id}`} className={`sheet-box ${v.state||"editing"}`} onClick={()=>select(v.id)} style={{left:`${v.box[0]*100}%`,top:`${v.box[1]*100}%`,width:`${v.box[2]*100}%`,height:`${v.box[3]*100}%`}}/>)}</div>;
}

export function SheetElementsPanel({assetId,revision,referenceUrl,file,capture,onCaptured,onZoom}:{assetId:string;revision:string;referenceUrl:string;file:File|null;capture:()=>Promise<File>;onCaptured:(v:File)=>void;onZoom:(src:string,alt:string)=>void}) {
  const epoch=useRef(0), mounted=useRef(true);
  const loadEpoch=useRef(0);
  const busyRef=useRef(false);
  const templateRequest=useRef<{asset:string;revision:string;id:string}|null>(null);
  const lastFile=useRef(file);
  const retry=useRef<{file:File;templateId:string;id:string}|null>(null);
  const [template,setTemplate]=useState<Resource|null>(null),[job,setJob]=useState<Resource|null>(null);
  const [history,setHistory]=useState<Resource[]>([]);
  const [turns,setTurns]=useState(0),[directionConfirmed,setDirectionConfirmed]=useState(false),[inputPreview,setInputPreview]=useState("");
  useEffect(()=>{setTurns(0);setDirectionConfirmed(false);if(!file){setInputPreview("");return;}const url=URL.createObjectURL(file);setInputPreview(url);return()=>URL.revokeObjectURL(url);},[file]);
  const [items,setItems]=useState<Item[]>([]),[selected,setSelected]=useState("");
  const [editing,setEditing]=useState(false),[dirty,setDirty]=useState(false),[inventory,setInventory]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState("");
  useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;++epoch.current;};},[]);
  useEffect(()=>{
    ++epoch.current;const version=++loadEpoch.current;setTemplate(null);setItems([]);setJob(null);setHistory([]);setDirty(false);setBusy(false);busyRef.current=false;setInventory(false);retry.current=null;templateRequest.current=null;
    if(!assetId)return;
    apiClient.get<{items:Resource[]}>(`${API}/templates?standard_asset_id=${encodeURIComponent(assetId)}`).then(data=>{
      if(!mounted.current||version!==loadEpoch.current)return;
      const value=data.items.find(v=>v.standard_revision_id===revision);if(value){setTemplate(value);setItems(value.elements||[]);}
    }).catch(e=>{if(mounted.current&&version===loadEpoch.current)setError(e.message);});
  },[assetId,revision]);
  useEffect(()=>{if(lastFile.current===file)return;lastFile.current=file;++epoch.current;setJob(null);setBusy(false);busyRef.current=false;retry.current=null;},[file]);
  async function action(work:(version:number)=>Promise<void>) {
    if(busyRef.current)return;busyRef.current=true;
    ++loadEpoch.current;
    const version=++epoch.current;setBusy(true);setError("");
    try{await work(version);}catch(e){if(mounted.current&&version===epoch.current)setError((e as Error).message);}
    finally{if(mounted.current&&version===epoch.current){setBusy(false);busyRef.current=false;}}
  }
  async function poll(value:Resource,version:number,apply:(v:Resource)=>void){
    for(let i=0;i<150;i++){
      if(!mounted.current||version!==epoch.current)return;apply(value);if(finished(value))return;
      await new Promise(resolve=>setTimeout(resolve,1000));if(version!==epoch.current)return;
      value=await apiClient.get<Resource>(`${API}/resources/${value.root_id}`);
    }
    throw new Error("状态查询超时；请查询原任务，勿重复新建任务。");
  }
  function edited(next:Item[]){setItems(next);setDirty(true);setInventory(false);setJob(null);}
  function update(id:string,changes:Partial<Item>){edited(items.map(v=>v.id===id?{...v,...changes}:v));}
  function add(){const v:Item={id:crypto.randomUUID(),type:"text",expected:"",box:[.1,.1,.3,.1],required:true,ignore_reason:"",match:"whitespace"};edited([...items,v]);setSelected(v.id);}
  function merge(){const i=items.findIndex(v=>v.id===selected);if(i<0||i>=items.length-1)return;const a=items[i],b=items[i+1],x=Math.min(a.box[0],b.box[0]),y=Math.min(a.box[1],b.box[1]);const v:Item={...a,type:"text",match:"whitespace",expected:`${a.expected} ${b.expected}`,box:[x,y,Math.max(a.box[0]+a.box[2],b.box[0]+b.box[2])-x,Math.max(a.box[1]+a.box[3],b.box[1]+b.box[3])-y]};edited(items.flatMap((o,n)=>n===i?[v]:n===i+1?[]:[o]));}
  function split(){const a=items.find(v=>v.id===selected);if(!a)return;const parts=a.expected.split("|");if(parts.length!==2||parts.some(v=>!v.trim())){setError("在文字中插入一个 | 标记后拆分，再调整两个框的位置。");return;}edited(items.flatMap(v=>v.id!==a.id?[v]:parts.map((text,n)=>({...v,id:n?crypto.randomUUID():v.id,expected:text.trim(),box:[v.box[0],v.box[1]+n*v.box[3]/2,v.box[2],v.box[3]/2] as Box}))));}
  async function save(confirm:boolean,version:number){if(!template)return;const next=await apiClient.post<Resource>(`${API}/templates/${template.root_id}/revise`,{version:template.version,elements:items,confirm,inventory_confirmed:inventory});if(version!==epoch.current)return;setTemplate(next);setItems(next.elements||[]);setDirty(false);setJob(null);retry.current=null;if(confirm)setEditing(false);}
  const active=items.find(v=>v.id===selected),finding=job?.result?.elements.find(v=>v.element_id===selected);
  return <section className="sheet-elements" aria-label="整页元素核对">
    <div className="sheet-toolbar"><strong>整页同款标签 · 核对试验</strong><span>不检查每张标签的独立漏印</span>
      <button type="button" disabled={!assetId||busy} onClick={()=>void action(async version=>{if(!templateRequest.current||templateRequest.current.asset!==assetId||templateRequest.current.revision!==revision)templateRequest.current={asset:assetId,revision,id:crypto.randomUUID()};const value=await apiClient.post<Resource>(`${API}/templates`,{standard_asset_id:assetId,request_id:templateRequest.current.id});await poll(value,version,v=>{setTemplate(v);setItems(v.elements||[]);setEditing(true);setDirty(false);});})}>解析／查询模板</button>
      <button type="button" disabled={!template||busy} onClick={()=>setEditing(true)}>编辑／确认模板</button>
      <button type="button" disabled={!template||template.status!=="confirmed"||dirty||busy||Boolean(file&&!directionConfirmed)} onClick={()=>{
        if(!template)return;
        if(!file){void capture().then(onCaptured).catch(e=>setError(e.message));return;}
        void action(async version=>{if(!retry.current||retry.current.file!==file||retry.current.templateId!==template.id)retry.current={file,templateId:template.id,id:crypto.randomUUID()};const form=new FormData();form.set("template_id",template.id);form.set("request_id",retry.current.id);form.set("file",file);form.set("quarter_turns",String(turns));form.set("orientation_confirmed",String(directionConfirmed));await poll(await apiClient.upload<Resource>(`${API}/jobs`,form),version,setJob);});
      }}>{file?"开始整页核对":"拍摄整页照片"}</button>
    </div>
    {file?<div className="sheet-direction"><img src={inputPreview} alt="实拍方向预览" style={{width:120,height:120,objectFit:"contain",transform:`rotate(${-90*turns}deg)`}}/><label>阅读方向<select disabled={busy} value={turns} onChange={event=>{setTurns(Number(event.target.value));setDirectionConfirmed(false);setJob(null);retry.current=null;++epoch.current;}}><option value={0}>原方向</option><option value={1}>向左 90°</option><option value={2}>旋转 180°</option><option value={3}>向右 90°</option></select></label><label><input type="checkbox" disabled={busy} checked={directionConfirmed} onChange={event=>setDirectionConfirmed(event.target.checked)}/>已确认主要文字方向；正反混排由文字行方向模块处理</label></div>:null}
    {busy?<p role="status">{states[job?.status||template?.status||"queued"]}…15 秒为目标，慢任务继续等待，120 秒结束为待复核。</p>:null}
    {error?<p role="alert">{error}</p>:null}
    <details onToggle={event=>{if(event.currentTarget.open&&assetId){const version=epoch.current;void apiClient.get<{items:Resource[]}>(`${API}/jobs?standard_asset_id=${encodeURIComponent(assetId)}`).then(data=>{if(mounted.current&&version===epoch.current)setHistory(data.items);}).catch(e=>{if(mounted.current&&version===epoch.current)setError(e.message);});}}}><summary>最近核对记录（查询不重复识别）</summary>{history.map(v=><button type="button" disabled={busy} key={v.root_id} onClick={()=>void action(version=>poll(v,version,setJob))}>{v.root_id.slice(-8)} · {states[v.status]}</button>)}</details>
    {template?.error_code?<p>标准解析未完成（{template.error_code}）。可手工建立模板，不会忽略未识别的图形。</p>:null}
    {job?<div><h3>{job.result?.decision==="MATCH"?"通过":job.result?.decision==="DIFFERENCES"?"不通过":finished(job)?"待复核":states[job.status]}</h3>{job.result?.gate_reason?<p>自动判断尚未完成正式验收，当前结果需人工复核。</p>:null}{job.error_code?<p>识别未完成：{job.error_code}</p>:null}
      <div className="sheet-result-grid"><EvidenceImage src={job.media.reference||referenceUrl} boxes={(job.result?.elements||[]).map(v=>({id:v.element_id,box:v.standard_box,state:v.state}))} select={setSelected} zoom={()=>onZoom(job.media.standard_overlay||job.media.reference,"标准结果")}/>{job.media.source?<EvidenceImage src={job.media.source} boxes={[...(finding?.evidence||[]),...(finding?.conflicts||[])].map((v,i)=>({id:String(i),box:v.box,state:finding?.state}))} select={()=>{}} zoom={()=>onZoom(job.media.actual_overlay||job.media.source,"整页证据")}/>:null}</div>
      <div className="sheet-findings">{job.result?.elements.map((v,i)=><button type="button" key={v.element_id} className={v.element_id===selected?"selected":""} onClick={()=>setSelected(v.element_id)}>{i+1}. {v.expected||"图形"} · {reasons[v.reason]||v.reason}</button>)}</div>
      {finding?<p>标准：{finding.expected}　实拍：{finding.evidence.map(v=>v.text).join("；")||"无可靠匹配"}</p>:null}
      <details><summary>Raw Output（默认折叠）</summary><pre>{JSON.stringify(job,null,2).slice(0,40000)}</pre></details>
    </div>:null}
    {editing&&template?<div className="sheet-editor-backdrop"><section className="sheet-editor" role="dialog" aria-modal="true" aria-label="标准元素编辑"><header><h3>标准模板 v{template.version} · {states[template.status]}</h3><button type="button" onClick={()=>setEditing(false)}>关闭</button></header><p>核对全部文字、编码和图形；坐标为原图比例。保存修改会取消旧确认。</p>
      <div className="sheet-editor-grid"><EvidenceImage src={template.media.source||referenceUrl} boxes={items.map(v=>({id:v.id,box:v.box}))} select={setSelected} zoom={()=>onZoom(template.media.source||referenceUrl,"标准原图")}/><div className="sheet-editor-list"><div className="sheet-toolbar"><button type="button" disabled={busy} onClick={add}>添加</button><button type="button" disabled={busy||!selected} onClick={merge}>与下一项合并</button><button type="button" disabled={busy||!selected} onClick={split}>按 | 拆分</button></div>
        {items.map((v,i)=><button type="button" key={v.id} className={v.id===selected?"selected":""} onClick={()=>setSelected(v.id)}>{i+1}. {v.expected||"未命名图形"} · {v.required?"必检":"忽略"}</button>)}
        {active?<fieldset disabled={busy}><legend>编辑选中元素</legend><label>类型<select value={active.type} onChange={e=>update(active.id,{type:e.target.value as Item["type"],match:e.target.value==="text"?"whitespace":"exact"})}><option value="text">文字</option><option value="parameter">关键参数</option><option value="code">二维码／条码</option><option value="graphic">图形／Logo</option></select></label><label>内容<textarea value={active.expected} onChange={e=>update(active.id,{expected:e.target.value})}/></label><label>规则<select value={active.match} onChange={e=>update(active.id,{match:e.target.value as Item["match"]})}><option value="exact">严格</option>{active.type==="text"?<option value="whitespace">忽略换行及多余空格</option>:null}</select></label><div className="sheet-box-fields">{["左","上","宽","高"].map((label,i)=><label key={label}>{label}<input type="number" min="0" max="1" step="0.001" value={active.box[i]} onChange={e=>{const box=[...active.box] as Box;box[i]=Number(e.target.value);update(active.id,{box});}}/></label>)}</div><label><input type="checkbox" checked={active.required} onChange={e=>update(active.id,{required:e.target.checked})}/>必检</label>{!active.required?<label>忽略原因<input value={active.ignore_reason} onChange={e=>update(active.id,{ignore_reason:e.target.value})}/></label>:null}<button type="button" onClick={()=>{edited(items.filter(v=>v.id!==active.id));setSelected("");}}>删除元素（旧版本保留）</button></fieldset>:null}
      </div></div><footer><button type="button" disabled={busy||!items.length} onClick={()=>void action(v=>save(false,v))}>保存草稿</button><label><input type="checkbox" checked={inventory} onChange={e=>setInventory(e.target.checked)}/>已核对全部文字、编码及图形，无遗漏</label><button type="button" disabled={busy||dirty||!inventory||template.status!=="draft"} onClick={()=>void action(v=>save(true,v))}>确认模板</button></footer>{error?<p role="alert">{error}</p>:null}</section></div>:null}
  </section>;
}
