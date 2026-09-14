import { useEffect, useRef, useState } from 'react';
import { useInfiniteQuery, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useSearchParams } from 'react-router-dom';
import { ArrowLeft, Plus, RefreshCw, ScanLine, AlertTriangle } from 'lucide-react';
import { apiClient } from '../../api/client';
import { listTextInspectionStandards } from '../../api/queries';
import { workspacePath } from '../../app/paths';
import { useAuth } from '../auth/auth-context';
import { FileDropZone } from '../../components/FileDropZone';
import { Capture, Detail } from './CodexComparePage';
import { LabelReport, ReferenceRegion } from './LabelReport';
import { ROOT, capabilities, labels, mediaURL, terminal, type Box, type Evidence, type Task, type Decision } from './api';
import './batch-workspace.css';

interface Reference { id: string; name: string; media: Evidence | null; error?: string; sources: { id: string; ordinal?: number }[] }
interface BatchLabel {
  id: string; name: string; actual: Evidence; outcome: string; finalized: boolean;
  match: { status: string; reason: string; reference_id: string | null; candidate_ids: string[] };
  summary: Task['summary']; progress: {total: number; settled: number; elements: number}; progress_message?: string;
  inputs: Task['inputs']; elements?: Task['elements']; checks?: Task['checks']; issues?: Task['issues']; artifacts?: Task['artifacts']; reviews?: Task['reviews'];
}
interface Batch {
  report_version: 'label-batch-v3';
  id: string; status: string; sequence: number; created_at: number; parent_id?: string; error?: string; import_state?: string;
  model?: string; session_id?: string; skill_version?: string; skill_sha256?: string; summary: Task['summary']; progress_message?: string;
  inputs: { standard_id?: string; standard_name?: string; standard_revision_number?: number; references: Record<string, Reference> };
  references: { id: string; asset_id: string; name: string; region: Box }[];
  labels: BatchLabel[]; counts: Record<string, number>;
}
const BATCHES = ROOT + '/batches';
const stateName = (s: string) => ({draft: '草稿', extracting: '正在提取图片', ready: '图片已就绪', needs_confirmation: '需要人工确认', matched: '已匹配', pending: '未完成', uncertain: '需要确认', difference: '存在差异', match: '一致'}[s] || labels[s] || s);
const errorText = (e: unknown) => e instanceof Error ? e.message : '操作失败，请重试';
const request = () => ({request_id: crypto.randomUUID()});
const rank: Record<string, number> = {difference: 0, uncertain: 1, pending: 2, match: 3};
type InspectionTask = Batch | Task;
const isBatch = (task: InspectionTask): task is Batch => task.report_version === 'label-batch-v3';
const taskParams = (task: InspectionTask): Record<string,string> => isBatch(task) ? {batch:task.id, ...(task.status==='draft'?{view:'new'}:{})} : {task:task.id};

function TaskList({items, loading, onSelect, onNew, canCreate}: {items:InspectionTask[]; loading:boolean; onSelect:(task:InspectionTask)=>void; onNew:()=>void; canCreate:boolean}) {
  const active = (task:InspectionTask) => !terminal(task.status) && task.status!=='draft';
  const ordered=[...items].sort((a,b)=>Number(active(b))-Number(active(a))||b.created_at-a.created_at);
  return <section className="bw-task-list">
    <header className="bw-list-heading"><div><span className="bw-eyebrow">标签检查 BETA</span><h1>任务列表</h1><p>查看正在进行的检查、继续草稿，或打开历史报告。</p></div><button className="bw-primary" disabled={!canCreate} onClick={onNew}><Plus size={18}/>新建任务</button></header>
    <div className="bw-task-rows">{ordered.map(task=>{
      const count=isBatch(task)?task.labels.length:1;
      const progress=isBatch(task)?task.labels.reduce((p,e)=>({total:p.total+e.progress.total,settled:p.settled+e.progress.settled}),{total:0,settled:0}):task.progress||{total:Object.values(task.counts).reduce((a,b)=>a+b,0),settled:task.counts.match+task.counts.difference+task.counts.uncertain};
      return <button className="bw-task-row" key={task.id} onClick={()=>onSelect(task)}>
        <span className="bw-task-title"><strong>{task.inputs.standard_name||'未命名任务'}</strong><small>{new Date(task.created_at*1000).toLocaleString()} · {count} 枚标签</small></span>
        <span className="bw-task-result">{task.summary?.message||task.error||(task.status==='draft'?'继续选择订单与上传实拍':active(task)?'检查进行中，点击查看实时进展':'查看已保存的检查报告')}<small>{progress&&progress.total>0?`已处理 ${progress.settled}/${progress.total} 项`:'尚无检查项'}</small></span>
        <span className={`bw-badge ${active(task)?'active':task.status}`}>{stateName(task.status)}</span><span className="bw-task-open">{task.status==='draft'?'继续编辑':'查看详情'} →</span>
      </button>;
    })}</div>
    {!items.length&&<p className="bw-empty">{loading?'正在读取任务…':'还没有检查任务，点击“新建任务”开始。'}</p>}
  </section>;
}

function LabelDetail({batch, lid, onBack, onRerun}: {batch: Batch; lid: string; onBack:()=>void; onRerun:(ids:string[], matches?:Record<string,unknown>)=>Promise<void>}) {
  const owner = useAuth().user.id;
  const queryClient = useQueryClient();
  const [error, setError] = useState(''), [busy, setBusy] = useState(false);
  const [reference, setReference] = useState(''), [region, setRegion] = useState<Box>([0,0,1,1]);
  const [decision, setDecision] = useState<Decision>('REVIEW_REQUIRED'), [note, setNote] = useState('');
  const reviewRequest = useRef(request());
  const result = useQuery({queryKey:['batch-label',owner,batch.id,lid], queryFn:()=>apiClient.get<BatchLabel>(`${BATCHES}/${batch.id}/labels/${lid}`), refetchInterval:terminal(batch.status)?false:2000});
  const entry = result.data;
  async function review() {
    setBusy(true);setError('');
    try {await apiClient.post(`${BATCHES}/${batch.id}/labels/${lid}/review`, {...reviewRequest.current,decision,note});reviewRequest.current=request();await queryClient.invalidateQueries({queryKey:['batch-label',owner,batch.id,lid]});}
    catch(e){setError(errorText(e));}finally{setBusy(false);}
  }
  const view: Task | undefined = entry?.inputs.reference ? {...entry, id:batch.id, report_version:'label-v2', skill_version:batch.skill_version, skill_sha256:batch.skill_sha256,
    status:batch.status, created_at:batch.created_at, sequence:batch.sequence, counts:{difference:entry.checks?.filter(x=>x.status==='difference').length||0, uncertain:entry.checks?.filter(x=>x.status==='uncertain').length||0,match:entry.checks?.filter(x=>x.status==='match').length||0}} : undefined;
  return <section className="bw-label-detail"><button onClick={onBack}><ArrowLeft size={16}/> 返回批次</button>
    {result.error && <p role="alert">{errorText(result.error)}</p>}
    {!entry ? <p>正在读取标签报告…</p> : <>
      <header><div><span className={`bw-badge ${entry.outcome}`}>{stateName(entry.outcome)}</span><h1>{entry.name}</h1><p>{entry.match.reason || '等待 Codex 发布匹配结果'}</p></div>
        {terminal(batch.status)&&<button disabled={busy} onClick={()=>void onRerun([lid])}><RefreshCw size={16}/> 重新检查此标签</button>}</header>
      {batch.status!=='completed'&&<p className="cc-notice">{terminal(batch.status)?'本批次未完整结束；已保留发现及未检项目。':'初步结果 · 检查过程中会持续更新'}</p>}
      {entry.summary&&<div className="bw-conclusion"><h2>{labels[entry.summary.decision]}</h2><p>{entry.summary.message}</p><p>已检：{entry.summary.checked_scope}</p><p>未确认：{entry.summary.unchecked_scope||'无'}</p></div>}
      {view?<LabelReport task={view}/>:<div className="bw-unmatched"><img src={mediaURL(batch.id,entry.actual.preview)} alt={entry.name}/><p>尚未确定标准，未进行标签对比；该图片始终计入本批次。</p></div>}
      {terminal(batch.status)&&<details className="bw-correction"><summary>人工指定标准并重新检查</summary><p>选择本批次冻结的标准图片，必要时框选一枚标签。原报告会保留，新检查使用新的 session。</p>
        <select aria-label="人工指定标准" value={reference} onChange={e=>{setReference(e.target.value);setRegion([0,0,1,1]);}}><option value="">选择标准图片</option>{Object.values(batch.inputs.references).filter(r=>r.media).map(r=><option key={r.id} value={r.id}>{r.name}</option>)}</select>
        {reference&&batch.inputs.references[reference]?.media&&<ReferenceRegion url={mediaURL(batch.id,batch.inputs.references[reference].media!.preview)} value={region} onChange={setRegion} disabled={busy}/>}
        <button disabled={!reference||busy} onClick={()=>void onRerun([lid],{[lid]:{asset_id:reference,region}})}>按此标准新建检查</button>
      </details>}
      <section className="bw-review"><h2>人工复核</h2>{entry.reviews?.map(r=><p key={r.key}>{new Date(r.created_at*1000).toLocaleString()} · {labels[r.value.decision]} · {r.value.note}</p>)}
        <select aria-label="人工结论" disabled={!terminal(batch.status)||busy} value={decision} onChange={e=>{setDecision(e.target.value as Decision);reviewRequest.current=request();}}>{(['REVIEW_REQUIRED','DIFFERENCES','MATCH'] as const).map(d=><option key={d} value={d}>{labels[d]}</option>)}</select>
        <textarea aria-label="人工复核备注" placeholder="填写独立人工结论与备注" maxLength={4000} value={note} onChange={e=>{setNote(e.target.value);reviewRequest.current=request();}}/>
        <button disabled={!terminal(batch.status)||busy} onClick={()=>void review()}>保存复核</button>
      </section>{error&&<p role="alert">{error}</p>}
    </>}
  </section>;
}

export function BatchWorkspace() {
  const {user} = useAuth();
  const owner = user.id;
  const [params,setParams] = useSearchParams();
  const queryClient = useQueryClient();
  const cap = useQuery({queryKey:['codex-capabilities',owner],queryFn:capabilities,retry:false});
  const bid = params.get('batch') || '';
  const lid = params.get('label') || '';
  const legacy = params.get('task') === 'history' ? '' : params.get('task');
  const creating = params.get('view')==='new';
  const listing = !bid && !legacy && !creating;
  const history = useInfiniteQuery({queryKey:['inspection-tasks',owner],initialPageParam:'',queryFn:({pageParam})=>apiClient.get<{items:InspectionTask[];next_cursor:string|null}>(`${ROOT}/tasks?before=${encodeURIComponent(pageParam)}`),getNextPageParam:last=>last.next_cursor||undefined,enabled:cap.isSuccess&&listing,refetchInterval:listing?5000:false});
  const batchQuery = useQuery({queryKey:['batches',owner,bid],queryFn:()=>apiClient.get<Batch>(`${BATCHES}/${bid}`),enabled:!!bid&&cap.isSuccess,refetchInterval:q=>terminal(q.state.data?.status||'')?false:2000,retry:false});
  const standards = useQuery({queryKey:['batch-orders',owner],queryFn:listTextInspectionStandards,enabled:cap.isSuccess&&(creating||!!bid)});
  const [busy,setBusy] = useState(false), [error,setError] = useState(''), [uploadNote,setUploadNote] = useState('');
  const [filter,setFilter] = useState('all');
  const [rename,setRename] = useState('');
  const [failedUploads,setFailedUploads] = useState<{file:File;key:string;reason:string}[]>([]);
  const main = useRef<HTMLElement>(null);
  const scroll = useRef(0);
  const listScroll = useRef(0);
  const createKey = useRef(request());
  const submitKey = useRef(request());
  const retryKey = useRef(request());
  const batch = batchQuery.data;
  const draft = batch?.status==='draft';
  const editable = !busy && !!cap.data?.enabled;
  useEffect(()=>{submitKey.current=request();retryKey.current=request();setFailedUploads([]);setFilter('all');scroll.current=0;},[bid,owner]);
  useEffect(()=>{if(batch?.inputs.standard_name)setRename(batch.inputs.standard_name);},[batch?.inputs.standard_name]);
  useEffect(()=>{
    const pending=sessionStorage.getItem('vantaline-upload:'+owner);
    if(pending)setUploadNote('上次有文件未确认上传完成，请核对图库并重新上传缺少的文件。');
  },[owner]);
  useEffect(()=>{const warn=(e:BeforeUnloadEvent)=>{if(busy){e.preventDefault();e.returnValue='';}};window.addEventListener('beforeunload',warn);return()=>window.removeEventListener('beforeunload',warn);},[busy]);
  useEffect(()=>{if(!lid&&main.current)requestAnimationFrame(()=>main.current?.scrollTo({top:scroll.current}));},[lid]);
  useEffect(()=>{if(listing)requestAnimationFrame(()=>main.current?.scrollTo({top:listScroll.current}));},[listing]);
  async function accept(value:Batch) {queryClient.setQueryData(['batches',owner,value.id],value);await queryClient.invalidateQueries({queryKey:['inspection-tasks',owner]});}
  async function operation(fn:()=>Promise<void>){setBusy(true);setError('');try{await fn();}catch(e){setError(errorText(e));}finally{setBusy(false);}}
  async function ensureDraft():Promise<Batch>{
    if(batch?.status==='draft')return batch;
    const next=await apiClient.post<Batch>(BATCHES,createKey.current);createKey.current=request();await accept(next);setParams({view:'new',batch:next.id},{replace:true});return next;
  }
  function newBatch(){if(listing)listScroll.current=main.current?.scrollTop||0;setParams({view:'new'});setError('');setUploadNote('');setFailedUploads([]);setRename('');main.current?.scrollTo({top:0});}
  function openTask(task:InspectionTask){listScroll.current=main.current?.scrollTop||0;setParams(taskParams(task));main.current?.scrollTo({top:0});}
  function back(){setParams(lid?{batch:bid}:{});}
  async function order(standard_id:string){if(!standard_id)return;await operation(async()=>{const target=await ensureDraft();await accept(await apiClient.post<Batch>(`${BATCHES}/${target.id}/order`,{...request(),standard_id}));});}
  async function document(file:File){await operation(async()=>{
    const target=await ensureDraft();const form=new FormData();form.set('file',file);form.set('request_id',crypto.randomUUID());
    sessionStorage.setItem('vantaline-upload:'+owner,file.name);setUploadNote('正在上传并提取 '+file.name+'…');
    await accept(await apiClient.upload<Batch>(`${BATCHES}/${target.id}/document`,form));sessionStorage.removeItem('vantaline-upload:'+owner);setUploadNote('文档及提取图片已保存');await queryClient.invalidateQueries({queryKey:['batch-orders',owner]});
  });}
  async function photos(files:File[], retain=false, existingKey?:string){if(!files.length)return;await operation(async()=>{
    const target=await ensureDraft();
    for(let i=0;i<files.length;i++){
      const file=files[i],key=existingKey||crypto.randomUUID();const form=new FormData();form.set('file',file);form.set('request_id',key);form.set('allow_duplicate',String(retain));
      sessionStorage.setItem('vantaline-upload:'+owner,file.name);setUploadNote(`正在上传 ${i+1}/${files.length} · ${file.name}`);
      try{await accept(await apiClient.upload<Batch>(`${BATCHES}/${target.id}/photos`,form));setFailedUploads(old=>old.filter(x=>x.file!==file));}
      catch(e){setFailedUploads(old=>[...old.filter(x=>x.file!==file),{file,key,reason:errorText(e)}]);}
    }
    sessionStorage.removeItem('vantaline-upload:'+owner);setUploadNote('上传处理结束；成功图片已保存，失败项可单独重试。');
  });}
  async function rerun(ids:string[],matches:Record<string,unknown>={}){await operation(async()=>{const next=await apiClient.post<Batch>(`${BATCHES}/${bid}/retry`,{...retryKey.current,label_ids:ids,matches});retryKey.current=request();await accept(next);setParams({batch:next.id});scroll.current=0;});}
  const cards = [...(batch?.labels||[])].filter(e=>filter==='all'||e.outcome===filter).sort((a,b)=>rank[a.outcome]-rank[b.outcome]);
  const actualCount=batch?.labels.length||0;
  return <div className="bw-shell">
    <header className="bw-topbar">{listing?<Link className="bw-back" aria-label="返回主界面" to={workspacePath()}><ArrowLeft size={18}/><span>返回主界面</span></Link>:<button className="bw-back" aria-label={lid?'返回任务详情':'返回任务列表'} disabled={busy} onClick={back}><ArrowLeft size={18}/><span>{lid?'返回任务详情':'返回任务列表'}</span></button>}<div className="bw-brand"><ScanLine size={20}/><strong>标签检查</strong><span className="bw-beta">BETA</span></div>
      <span className="bw-session">整批 1 个 session · 最多 10 分钟</span>{!listing&&<button disabled={!editable} onClick={newBatch}><Plus size={16}/>新建任务</button>}</header>
    <nav className="bw-toolbar" aria-label="任务导航">{listing?<strong>任务列表</strong>:<><button disabled={busy} onClick={()=>setParams({})}>任务列表</button><span>/</span>{lid?<><button disabled={busy} onClick={()=>setParams({batch:bid})}>任务详情</button><span>/</span><strong>标签详情</strong></>:<strong>{creating||draft?'新建任务':'任务详情'}</strong>}</>}<span className="bw-saved">{busy?'正在保存…':'已上传的输入与检查进度保存在服务器'}</span></nav>
    <main className="bw-main" ref={main}>
      {(error||cap.error||(listing&&history.error)||batchQuery.error)&&<div role="alert" className="bw-error">{error||errorText(cap.error||(listing&&history.error)||batchQuery.error)}<button onClick={()=>{setError('');if(listing)void history.refetch();else if(bid)void batchQuery.refetch();else void cap.refetch();}}>重新读取</button></div>}
      {cap.isSuccess&&!cap.data.enabled&&<p className="cc-notice">当前账号暂未开放新检查；历史报告仍可读取。</p>}
      {listing?<><TaskList items={[...new Map(history.data?.pages.flatMap(p=>p.items).map(t=>[t.id,t])).values()]} loading={history.isFetching} onSelect={openTask} onNew={newBatch} canCreate={editable}/>{history.hasNextPage&&<button className="bw-load-more" disabled={history.isFetchingNextPage} onClick={()=>void history.fetchNextPage()}>{history.isFetchingNextPage?'正在读取…':'加载更早任务'}</button>}</>:legacy?<Detail key={legacy} id={legacy} owner={owner}/>:batch&&lid?<LabelDetail key={batch.id+lid} batch={batch} lid={lid} onBack={()=>setParams({batch:bid})} onRerun={rerun}/>:bid&&!batch?<p className="bw-empty">{batchQuery.isError?'任务暂时无法读取，请重试或返回任务列表。':'正在读取任务…'}</p>:<>
        <header className="bw-page-heading"><div><span className="bw-eyebrow">{draft||creating?'准备检查':'检查任务'}</span><h1>{draft||creating?'新建任务':batch?.inputs.standard_name||'任务详情'}</h1><p>{draft||creating?'选择已有订单批次，或拖入 Word 新建订单，再上传本次要检查的标签。':`${stateName(batch?.status||'')} · ${actualCount} 枚标签 · 输入已冻结`}</p></div></header>
        <p className="bw-narrow-hint">左右滑动查看订单、标准图和实拍标签</p>
        <section className="bw-bench" aria-label="订单与标签工作区" tabIndex={0}>
          <div className="bw-panel bw-order"><div className="bw-panel-heading"><span className="bw-step">01</span><h2>订单</h2></div>
            {(!batch||draft)&&standards.error&&<p role="alert" className="bw-error">{errorText(standards.error)}<button onClick={()=>void standards.refetch()}>重新读取订单</button></p>}
            {(!batch||draft)&&<select aria-label="选择订单" value={batch?.inputs.standard_id||''} disabled={!editable||!!batch&&!draft} onChange={e=>void order(e.target.value)}><option value="">选择已有标签订单</option>{standards.data?.items.filter(s=>s.standard_type==='label').map(s=><option key={s.id} value={s.id}>{s.name}</option>)}</select>}
            {(!batch||draft)&&<FileDropZone accept=".doc,.docx" disabled={!editable} ariaLabel="拖入 Word 订单" onFiles={files=>{if(files[0])void document(files[0]);}}><strong>拖入 DOC / DOCX</strong><span>自动提取内嵌图片，文件名作为订单名称</span></FileDropZone>}
            {draft&&batch?.inputs.standard_name&&<div className="bw-order-name"><input aria-label="批次订单名称" value={rename} disabled={!draft||!editable} onChange={e=>setRename(e.target.value)}/>{draft&&rename!==batch.inputs.standard_name&&<button disabled={!editable||!rename.trim()} onClick={()=>void operation(async()=>{await accept(await apiClient.post<Batch>(`${BATCHES}/${bid}/name`,{...request(),name:rename}));})}>保存名称</button>}</div>}
            {draft&&batch?.import_state&&<p className="bw-muted">{stateName(batch.import_state)}</p>}
            <div className="bw-order-info"><h3>{batch?.inputs.standard_name||'选择或新建订单批次'}</h3><p>{batch?.inputs.standard_name?'订单及已上传文件保存在当前任务中，可返回任务列表后继续。':'支持选择已有订单，或直接拖入 DOC / DOCX 提取内嵌图片。'}</p>{batch&&<dl><div><dt>任务状态</dt><dd>{stateName(batch.status)}</dd></div><div><dt>标准图片</dt><dd>{Object.keys(batch.inputs.references).length} 张</dd></div><div><dt>实拍标签</dt><dd>{actualCount} 枚</dd></div><div><dt>创建时间</dt><dd>{new Date(batch.created_at*1000).toLocaleString()}</dd></div></dl>}</div>
          </div>
          <div className="bw-panel bw-standard"><div className="bw-panel-heading"><span className="bw-step">02</span><h2>标准图</h2><span>{Object.keys(batch?.inputs.references||{}).length} 张</span></div>
            <div className="bw-gallery bw-standard-gallery">{Object.values(batch?.inputs.references||{}).map(r=><figure key={r.id}>{r.media?<a target="_blank" rel="noreferrer" href={mediaURL(bid,r.media.image)}><img src={mediaURL(bid,r.media.preview)} alt={r.name}/></a>:<div className="bw-image-error"><AlertTriangle size={22}/>{r.error}</div>}<figcaption>{r.name}{r.sources.length>1&&` · ${r.sources.length} 处引用`}</figcaption></figure>)}</div>
            {!Object.keys(batch?.inputs.references||{}).length&&<p className="bw-empty">选择一个订单，或拖入 Word 开始。只检查实拍对应的标签，其他文档图片不计入范围。</p>}
          </div>
          <div className="bw-panel bw-actual"><div className="bw-panel-heading"><span className="bw-step">03</span><h2>实拍标签</h2><span>{actualCount} 枚</span></div>
            {(!batch||draft)&&<><FileDropZone multiple accept="image/*" disabled={!editable} ariaLabel="批量上传实拍标签" onFiles={files=>void photos(files)}><strong>将所有实拍图拖到这里，或点击多选</strong><span>每张一枚标签 · 通常 1–10 张 · 每张不超过 10 MB</span></FileDropZone>
            {!busy&&cap.data?.enabled&&<Capture onCapture={file=>void photos([file])}/>}</>}
            {uploadNote&&<p role="status" className="bw-muted">{uploadNote}</p>}
            {(!batch||draft)&&failedUploads.map(x=><div className="bw-upload-error" key={x.key}><strong>{x.file.name}</strong><span>{x.reason}</span><button disabled={!editable} onClick={()=>void photos([x.file],false,x.key)}>重试上传</button>{x.reason.includes('同一文件')&&<button disabled={!editable} onClick={()=>void photos([x.file],true)}>保留为另一枚样品</button>}</div>)}
            <div className="bw-gallery bw-actual-gallery">{batch?.labels.map((e,i)=><figure key={e.id}><a href={mediaURL(bid,e.actual.image)} target="_blank" rel="noreferrer"><img src={mediaURL(bid,e.actual.preview)} alt={e.name}/></a><figcaption><span>{i+1}. {e.name}</span>{draft?<button aria-label={`删除 ${e.name}`} disabled={!editable} onClick={()=>void operation(async()=>{await accept(await apiClient.post<Batch>(`${BATCHES}/${bid}/labels/${e.id}/remove`,request()));})}>删除</button>:<span className={`bw-dot ${e.outcome}`}>{stateName(e.outcome)}</span>}</figcaption></figure>)}</div>
          </div>
        </section>
        <section className="bw-results"><header className="bw-results-heading"><div><span className="bw-eyebrow">检查报告</span><h2>{batch?.inputs.standard_name||'订单批量检查'}</h2><p>{batch?`${stateName(batch.status)} · ${actualCount} 枚标签`:'上传订单与实拍后开始检查'}{batch?.parent_id&&<> · <Link to={`?batch=${batch.parent_id}`}>查看原批次</Link></>}</p></div>
          {draft?<button className="bw-primary" disabled={!editable||!actualCount||batch.import_state!=='ready'} onClick={()=>void operation(async()=>{await accept(await apiClient.post<Batch>(`${BATCHES}/${bid}/submit`,submitKey.current));setParams({batch:bid},{replace:true});})}><ScanLine size={18}/>开始检查整批</button>:batch&&!terminal(batch.status)?<button disabled={busy} onClick={()=>void operation(async()=>{await accept(await apiClient.post<Batch>(`${ROOT}/tasks/${bid}/cancel`));})}>取消整批</button>:batch&&actualCount>0?<button disabled={!editable} onClick={()=>void rerun(batch.labels.map(e=>e.id))}>整批重新检查</button>:null}</header>
          {batch?.error&&<p role="alert" className="bw-error">{batch.error}</p>}{batch?.progress_message&&<p role="status">{batch.progress_message}</p>}
          {batch?.summary&&<p className="bw-summary">{batch.summary.message}{batch.summary.unchecked_scope&&<span>未确认：{batch.summary.unchecked_scope}</span>}</p>}
          <div className="bw-filters">{[['all','全部'],['difference','存在差异'],['uncertain','需要确认'],['pending','未完成'],['match','一致']].map(([key,name])=><button key={key} className={filter===key?'active':''} onClick={()=>setFilter(key)}>{name}<strong>{key==='all'?actualCount:batch?.counts[key]||0}</strong></button>)}</div>
          <div className="bw-cards">{cards.map((e,i)=><button className={`bw-card ${e.outcome}`} key={e.id} onClick={()=>{scroll.current=main.current?.scrollTop||0;setParams({batch:bid,label:e.id});main.current?.scrollTo({top:0});}}>
            <div className="bw-card-images"><div>{e.inputs.reference?<img src={mediaURL(bid,e.inputs.reference.preview)} alt="对应标准"/>:<span>标准待确认</span>}<small>标准</small></div><div><img src={mediaURL(bid,e.actual.preview)} alt={e.name}/><small>实拍</small></div></div>
            <div className="bw-card-body"><span className={`bw-badge ${e.outcome}`}>{stateName(e.outcome)}</span><h3>{e.name}</h3><p>{e.summary?.message||e.match.reason||'等待匹配与检查'}</p><div className="bw-progress"><span style={{width:`${e.progress.total?100*e.progress.settled/e.progress.total:0}%`}}/></div><small>{e.progress.elements} 个元素 · 已处理 {e.progress.settled}/{e.progress.total} 项 · 查看详情 →</small></div>
          </button>)}</div>
          {!cards.length&&<p className="bw-empty">{actualCount?'当前筛选下没有标签':'每张实拍会生成一张标签卡片；问题和待确认项会优先显示。'}</p>}
          <p className="bw-footnote">视觉检查仅供人工复核。已处理包含待确认及不适用，不代表通过；未检内容始终保留。</p>
        </section>
      </>}
    </main>
  </div>;
}
