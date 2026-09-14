import { useEffect, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useSearchParams } from 'react-router-dom';
import { useAuth } from '../auth/auth-context';
import { apiClient } from '../../api/client';
import { getTextInspectionStandard, listTextInspectionStandards } from '../../api/queries';
import { FileDropZone } from '../../components/FileDropZone';
import { workspacePath } from '../../app/paths';
import { capabilities, getTask, labels, listTasks, mediaURL, post, ROOT, terminal, type Box, type Decision, type Task } from './api';
import './codex-compare.css';
import { LabelReport, ReferenceRegion } from './LabelReport';

const date = (value: number) => new Date(value * 1000).toLocaleString();
const message = (error: unknown) => error instanceof Error ? error.message : '请求失败，请重试';

export function Capture({ onCapture }: { onCapture: (file: File) => void }) {
  const video = useRef<HTMLVideoElement>(null);
  const generation = useRef(0);
  const stream = useRef<MediaStream | null>(null);
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([]);
  const [device, setDevice] = useState('');
  const [active, setActive] = useState(false);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    if (!active) return;
    let disposed = false;
    const refresh = async () => {
      const entries = (await navigator.mediaDevices.enumerateDevices()).filter(x => x.kind === 'videoinput');
      if (disposed) return;
      setDevices(entries);
      if (device && !entries.some(x => x.deviceId === device)) setDevice(entries[0]?.deviceId || '');
    };
    void refresh().catch(() => setError('无法读取摄像头列表'));
    navigator.mediaDevices.addEventListener('devicechange', refresh);
    return () => { disposed = true; navigator.mediaDevices.removeEventListener('devicechange', refresh); };
  }, [active, device]);
  useEffect(() => {
    const request = ++generation.current;
    setReady(false); setError('');
    stream.current?.getTracks().forEach(x => x.stop());
    if (active) {
      void navigator.mediaDevices.getUserMedia({ video: device ? {deviceId: {exact: device}} : {width: {ideal: 1920}, height: {ideal: 1080}}, audio: false }).then(async value => {
        if (generation.current !== request) { value.getTracks().forEach(x => x.stop()); return; }
        stream.current = value;
        if (video.current) { video.current.srcObject = value; await video.current.play(); }
        if (generation.current !== request) return;
        setReady(true);
        const entries = (await navigator.mediaDevices.enumerateDevices()).filter(x => x.kind === 'videoinput');
        if (generation.current === request) setDevices(entries);
      }).catch(() => { if (generation.current === request) { setReady(false); setError('摄像头不可用，请检查权限或上传图片'); } });
    }
    return () => { ++generation.current; stream.current?.getTracks().forEach(x => x.stop()); };
  }, [active, device]);
  function capture() {
    const source = video.current;
    if (!ready || !source?.videoWidth) return;
    const canvas = document.createElement('canvas');
    canvas.width = source.videoWidth; canvas.height = source.videoHeight;
    canvas.getContext('2d')?.drawImage(source, 0, 0);
    const request = generation.current;
    canvas.toBlob(blob => { if (blob && generation.current === request) { onCapture(new File([blob], 'capture.jpg', {type: 'image/jpeg'})); setActive(false); } }, 'image/jpeg', .95);
  }
  return <div className="cc-camera">
    <button type="button" onClick={() => setActive(!active)} disabled={!navigator.mediaDevices?.getUserMedia}>{active ? '关闭摄像头' : '打开摄像头'}</button>
    {active && <><select aria-label="选择摄像头" value={device} onChange={e => setDevice(e.target.value)}><option value="">默认摄像头</option>{devices.map((x,i) => <option key={x.deviceId} value={x.deviceId}>{x.label || `摄像头 ${i+1}`}</option>)}</select><video ref={video} muted playsInline /><button type="button" disabled={!ready} onClick={capture}>拍摄标签</button></>}
    {error && <p role="alert">{error}</p>}
  </div>;
}

function LocatedImage({ task, side, box }: { task: Task; side: 'reference'|'actual'; box?: Box | null }) {
  const evidence = task.inputs[side];
  return <figure><a href={mediaURL(task.id, evidence.image)} target="_blank" rel="noreferrer" title="查看原始尺寸图片">
    <span className="cc-image"><img src={mediaURL(task.id, evidence.preview)} alt={side === 'reference' ? '标准原图' : '实拍原图'} />
      {box && <span className="cc-box" style={{left: `${box[0]*100}%`,top: `${box[1]*100}%`,width: `${box[2]*100}%`,height: `${box[3]*100}%`}} />}
    </span></a><figcaption>{side === 'reference' ? '标准' : '实拍'} · 点击查看原图</figcaption></figure>;
}

export function Detail({ id, owner }: { id: string; owner: string }) {
  const queryClient = useQueryClient();
  const [selected, setSelected] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [decision, setDecision] = useState<Decision>('REVIEW_REQUIRED');
  const [note, setNote] = useState('');
  const [, setParams] = useSearchParams();
  const reviewKey = useRef(crypto.randomUUID());
  const retryKey = useRef(crypto.randomUUID());
  const task = useQuery({ queryKey: ['codex-compare', owner, id], queryFn: () => getTask(id), refetchInterval: q => (q.state.error && 'status' in q.state.error && [401,403,404].includes(Number(q.state.error.status))) || terminal(q.state.data?.status || '') ? false : 2000, retry: false });
  const events = useQuery({ queryKey: ['codex-events', owner, id, task.data?.sequence], queryFn: () => apiClient.get<{items: {sequence: number; kind: string; created_at: number; payload: {value?: {message?: string}}}[]}>(`${ROOT}/tasks/${id}/events?after=${Math.max(0,(task.data?.sequence || 0)-50)}`), enabled: !!task.data, retry: false });
  const inaccessible = task.error && 'status' in task.error && [401,403,404].includes(Number(task.error.status));
  const value = inaccessible ? undefined : task.data;
  const selectedItem = value?.items?.find(x => x.id === selected);
  async function action(name: string, body = {}) {
    setBusy(true); setError('');
    try {
      const result = await post<Task>(id, name, body);
      await queryClient.invalidateQueries({ queryKey: ['codex-compare', owner] });
      if (name === 'retry') setParams({task: result.id});
      if (name === 'review') reviewKey.current = crypto.randomUUID();
    } catch (e) { setError(message(e)); } finally { setBusy(false); }
  }
  return <section className="cc-detail">
    <Link to={workspacePath('/text-compare-codex')}>← 返回任务卡片</Link>
    {task.error && <p role="alert">{message(task.error)} <button onClick={() => void task.refetch()}>重新读取</button></p>}
    {!value ? <p>正在读取报告…</p> : <>
      <header><div><h2>{value.inputs.standard_name}</h2><p>{date(value.created_at)} · 标准版本 {value.inputs.standard_revision_number} · {labels[value.status]}</p></div>
        <button disabled={busy} onClick={() => void action(terminal(value.status) ? 'retry' : 'cancel', terminal(value.status) ? {request_id: retryKey.current} : {})}>{terminal(value.status) ? '重新对比（新任务）' : '取消任务'}</button></header>
      {value.status !== 'completed' && <p className="cc-notice">{terminal(value.status) ? '本次未完成；以下为已保留的部分报告。' : '初步结果 · 内容会随核对进展更新'}</p>}
      {value.error && <p role="alert">{value.error}</p>}
      {value.parent_id && <Link to={`?task=${value.parent_id}`}>查看上一次报告</Link>}
      <div className="cc-summary"><h3>{value.summary ? labels[value.summary.decision] : '等待核对结果'}</h3><p>{value.summary?.message}</p><p>已检查：{value.summary?.checked_scope || '尚未提交范围'}</p><p>未确认：{value.summary?.unchecked_scope || (value.summary ? '无未确认范围' : '尚未提交')}</p><small>{value.report_version === 'label-v2' ? '视觉检查建议仅供人工复核；待确认不代表通过，不承诺精确色差或实际毫米尺寸。' : '历史文字报告：图形、颜色和印刷质量不在结论范围。'}</small></div>
      {value.report_version === 'label-v2' ? <LabelReport task={value}/> : <><div className="cc-pair"><LocatedImage task={value} side="reference" box={selectedItem?.reference_box}/><LocatedImage task={value} side="actual" box={selectedItem?.actual_box}/></div>
      <div className="cc-items">{value.items?.map(entry => <article key={entry.id} className={`cc-item ${entry.status} ${selected === entry.id ? 'selected' : ''}`}>
        <button onClick={() => setSelected(entry.id)} aria-pressed={selected === entry.id}>{labels[entry.status]} · {entry.reference_text || '（标准无此文字）'}</button>
        <p>实拍：{entry.actual_text || '（未读到文字）'}</p><p>{entry.explanation}</p>
        {(!entry.reference_box || !entry.actual_box) && <small>部分位置无法可靠定位</small>}
        <div className="cc-crops">{entry.artifact_ids.map(aid => { const a = value.artifacts?.find(x => x.id === aid); return a ? <a key={aid} href={mediaURL(id,a.image)} target="_blank" rel="noreferrer"><img src={mediaURL(id,a.preview)} alt={`${a.source === 'reference' ? '标准' : '实拍'}局部证据`} /><span>{a.source === 'reference' ? '标准' : '实拍'}</span></a> : null; })}</div>
      </article>)}</div></>}
      <details><summary>核对进展与运行信息</summary><p>模型：{value.model || '排队等待分配'} · 会话：{value.session_id || '尚未启动'}</p><ol>{events.data?.items.map(e => <li key={e.sequence}>{date(e.created_at)} · {e.kind === 'progress' ? e.payload.value?.message : labels[e.kind] || e.kind}</li>)}</ol></details>
      <section><h3>人工复核</h3>{value.reviews?.map(review => <p key={review.key}>{date(review.created_at)} · {labels[review.value.decision]} · {review.value.note}</p>)}
        <select aria-label="人工结论" value={decision} disabled={!terminal(value.status) || busy} onChange={e => {setDecision(e.target.value as Decision);reviewKey.current = crypto.randomUUID();}}>{(['REVIEW_REQUIRED','MATCH','DIFFERENCES'] as const).map(x => <option key={x} value={x}>{labels[x]}</option>)}</select>
        <textarea aria-label="复核备注" placeholder="复核备注" maxLength={4000} value={note} onChange={e => {setNote(e.target.value);reviewKey.current = crypto.randomUUID();}} />
        <button disabled={!terminal(value.status) || busy} onClick={() => void action('review', {request_id: reviewKey.current, decision, note})}>保存人工复核</button>
      </section>
    </>}{error && <p role="alert">{error}</p>}
  </section>;
}

function Workspace({ owner }: { owner: string }) {
  const [params, setParams] = useSearchParams();
  const taskId = params.get('task');
  const [standardId, setStandardId] = useState('');
  const [assetId, setAssetId] = useState('');
  const [region, setRegion] = useState<Box>([0,0,1,1]);
  const [file, setFile] = useState<File | null>(null);
  const [url, setUrl] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [cursor, setCursor] = useState('');
  const requestId = useRef(crypto.randomUUID());
  const queryClient = useQueryClient();
  const cap = useQuery({queryKey: ['codex-capabilities', owner], queryFn: capabilities, retry: false});
  const tasks = useQuery({queryKey: ['codex-compare',owner,'list',cursor], queryFn: () => listTasks(cursor), refetchInterval: 3000, retry: false});
  const standards = useQuery({queryKey: ['codex-standards',owner], queryFn: listTextInspectionStandards, enabled: cap.data?.enabled});
  const standard = useQuery({queryKey: ['codex-standard',owner,standardId], queryFn: () => getTextInspectionStandard(standardId), enabled: !!standardId && cap.data?.enabled});
  useEffect(() => { if (!file) { setUrl(''); return; } const u = URL.createObjectURL(file); setUrl(u); return () => URL.revokeObjectURL(u); }, [file]);
  function selectFile(value: File) { if (busy) return; if (!value.size || value.size > 10*1024*1024) {setError('图片必须小于 10MB');return;} setFile(value);requestId.current = crypto.randomUUID();setError(''); }
  async function submit() {
    if (!file || !assetId || !standard.data?.current_revision_id || busy) return;
    setBusy(true);setError('');
    const form = new FormData();form.set('reference_region',JSON.stringify(region));form.set('captured_file',file);form.set('standard_asset_id',assetId);form.set('request_id',requestId.current);form.set('expected_revision',standard.data.current_revision_id);
    try { const result = await apiClient.upload<Task>(`${ROOT}/tasks`,form); await queryClient.invalidateQueries({queryKey:['codex-compare',owner]}); setParams({task:result.id}); }
    catch(e) {setError(message(e));} finally {setBusy(false);}
  }
  if (taskId) return <Detail key={taskId} id={taskId} owner={owner}/>;
  return <>
    <header><div><h1>标签检查 <span className="cc-beta">Beta</span></h1><p>一枚标签，一份可追溯的证据报告。</p></div><Link to={workspacePath('/text-compare-beta')}>管理标准库</Link></header>
    {cap.error && <p role="alert">{message(cap.error)}</p>}
    {cap.data?.enabled ? <section className="cc-compose"><div><h2>1. 选择标准标签</h2><select aria-label="标准订单" value={standardId} disabled={busy} onChange={e => {setStandardId(e.target.value);setAssetId('');requestId.current=crypto.randomUUID();}}><option value="">选择已确认订单</option>{standards.data?.items.filter(x=>x.status==='confirmed' && x.standard_type==='label').map(x=><option value={x.id} key={x.id}>{x.name}</option>)}</select>
      {standard.error && <p role="alert">{message(standard.error)}</p>}
      <div className="cc-gallery">{standard.data?.assets?.filter(x=>x.status==='candidate' && !['packaging','manual','document','product'].includes(x.category || '')).map(x=><button key={x.id} aria-label={`选择标准标签 ${x.ordinal}`} disabled={busy} aria-pressed={x.id===assetId} onClick={()=>{setAssetId(x.id);setRegion([0,0,1,1]);requestId.current=crypto.randomUUID();}}>{x.content_url && <img src={x.original_url || x.content_url} alt={`标准标签 ${x.ordinal}`}/>}标签 {x.ordinal}</button>)}</div>
      {assetId && <ReferenceRegion key={assetId} url={standard.data?.assets?.find(x=>x.id===assetId)?.original_url || standard.data?.assets?.find(x=>x.id===assetId)?.content_url || ''} value={region} disabled={busy} onChange={value=>{setRegion(value);requestId.current=crypto.randomUUID();}}/>}</div>
      <div><h2>2. 拍摄或上传实拍图</h2>{!busy && <Capture onCapture={selectFile}/>}
        <FileDropZone accept="image/*,.heic,.heif,.tif,.tiff,.bmp,.avif" disabled={busy} onFiles={files=>{if(files[0])selectFile(files[0]);}}><p>拖入一张单枚标签图片，或点击选择</p></FileDropZone>
        {url && <img className="cc-upload-preview" src={url} alt="待对比实拍图"/>}
        <button className="cc-primary" disabled={busy||!file||!assetId||!standard.data?.current_revision_id} onClick={()=>void submit()}>{busy?'正在提交…':'开始对比'}</button><p>单任务最多 10 分钟，结果需人工复核。</p>
      </div></section> : <p className="cc-notice">此账号尚未启用新任务，已有报告仍可查看。</p>}
    {error && <p role="alert">{error}（重新提交会复用本次请求标识）</p>}
    <h2>检查报告</h2>{tasks.error && <p role="alert">{message(tasks.error)}</p>}
    <div className="cc-cards">{tasks.data?.items.map(task=><Link className="cc-card" key={task.id} to={`?task=${task.id}`}><div className="cc-thumbs">{(['reference','actual'] as const).map(side=><img key={side} src={mediaURL(task.id,task.inputs[side].preview)} alt={side==='reference'?'标准':'实拍'}/>)}</div><h3>{task.inputs.standard_name}</h3><p>{labels[task.status]} · {date(task.created_at)}</p><p>{task.progress && `检查 ${task.progress.settled}/${task.progress.total} · 元素 ${task.progress.elements} · `}差异 {task.counts.difference} · 待确认 {task.counts.uncertain}</p><p>{task.summary?.message || '报告正在准备中'}</p><strong>查看详情 →</strong></Link>)}</div>
    {tasks.data?.items.length===0 && <p>还没有对比报告。</p>}
    <div className="cc-pagination">{cursor && <button onClick={()=>setCursor('')}>最新任务</button>}{tasks.data?.next_cursor && <button onClick={()=>setCursor(tasks.data!.next_cursor!)}>更早任务</button>}</div>
  </>;
}
export function CodexComparePage() { const auth=useAuth();return <main className="cc-page"><Workspace key={auth.user.id} owner={auth.user.id}/></main>; }
