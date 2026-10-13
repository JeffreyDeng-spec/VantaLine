import { TaskProcessDrawer } from "./TaskProcessDrawer";
import { useEffect, useState } from "react";
import { useQuery, useQueryClient, useMutation } from "@tanstack/react-query";
import { apiClient } from "../../api/client";
import { useAuth } from "../auth/auth-context";

type Box = { class_id: string; bbox: number[] };
type Sample = { current_status?: string; sample_id: string; source_group?: string; source_group_confirmed?: boolean; geometry: { width: number; height: number }; annotation?: null | {status: string; version: number; objects: Box[]; error_code?: string; error_type?: string}; review?: null | {decision: string; reason: string} };
type CallStats = {attempts: number; failures: number; elapsed_seconds: number; usage: Record<string, number>; unknown_usage_count: number; unknown_elapsed_count: number; estimated_cost: number | null};
export type RealPhotoStatus = {available: boolean; selected?: boolean; enabled: boolean; candidate_count: number; approved_count: number; unconfirmed_source_count?: number; positive_count: number; negative_count: number; pending_annotation_count: number; pending_review_count: number; excluded_count: number; agent_filtered_count?: number; datasets?: {id: string; real_source_count: number; sample_count: number; snapshot_fingerprint: string}[]; failed_annotation_count: number; review_trigger?: number; approved_real_target?: number; pause_reason?: string; initialization?: {reason: string}; assessment?: {action: string; reason: string; next_increment: number; gaps: string[]}; samples: Sample[]; jobs: {id: string; kind: string; status: string; model?: string; result?: {error_code?: string; error_type?: string}}[]; candidate_models?: {model_id: string; status: string; unsupported_by_real_data: string[]; real_source_count:number; positive_image_count:number; negative_image_count:number; split_image_counts:Record<string,number>; metrics?: Record<string,{status:string; reason?:string; metrics?:Record<string,number>}>}[]; reference_cache?: {status?: string; expires_at?: number; generation?: number}; call_statistics?: Record<string, CallStats>};

function SourceGroup({sample, save, pending}: {sample: Sample; pending: boolean; save: (value: string, confirmed: boolean) => void}) {
  const group = (sample.source_group || "").trim().toLowerCase();
  const savedConfirmed = sample.source_group_confirmed ?? Boolean(group && group !== "unconfirmed" && !group.endsWith("-unconfirmed"));
  const [value, setValue] = useState(sample.source_group || "");
  const [confirmed, setConfirmed] = useState(savedConfirmed);
  useEffect(() => { setValue(sample.source_group || ""); setConfirmed(savedConfirmed); }, [sample.source_group, savedConfirmed]);
  return <div>
    <label>拍摄分组 <input aria-label="拍摄分组" value={value} onChange={e => setValue(e.target.value)} maxLength={200}/></label>
    <label><input type="checkbox" aria-label="拍摄来源已核实" checked={confirmed} onChange={e => setConfirmed(e.target.checked)}/>拍摄来源已核实</label>
    {!savedConfirmed && <p>来源待核实，不计入合格实拍；请按真实拍摄批次核对。</p>}
    <button type="button" disabled={pending || !value.trim() || (value === sample.source_group && confirmed === savedConfirmed)} onClick={() => save(value, confirmed)}>保存分组</button>
  </div>;
}


export type RealPhotoDrawerKind = "collection" | "manual" | "dataset";
const labels: Record<string, string> = {
  pending_annotation: "等待自动标注", pending_review: "等待 Agent 审核", annotation_failed: "标注失败",
  unconfirmed_source: "来源待核实", accept_positive: "合格正样本", accept_negative: "合格负样本",
  exclude: "Agent 排除", uncertain: "Agent 不确定", usage_disabled: "训练用途已禁用"
};
export function useRealPhotoFeedback(taskId: string) {
  const auth = useAuth();
  const client = useQueryClient();
  const path = `/api/ai/tasks/${encodeURIComponent(taskId)}/real-photo`;
  const key = ["real-photo", auth.user.id, taskId];
  const query = useQuery({ queryKey: key, queryFn: () => apiClient.get<RealPhotoStatus>(path),
    enabled: Boolean(taskId), refetchInterval: 5000 });
  const mutation = useMutation({ mutationFn: ({url, body, post}: {url: string; body?: unknown; post?: boolean}) =>
    post ? apiClient.post<RealPhotoStatus>(url, body) : apiClient.patch<RealPhotoStatus>(url, body),
    onSuccess: async value => {
      client.setQueryData(key, value);
      await client.invalidateQueries({queryKey: key});
    }
  });
  return { query, mutation, path, key };
}
type Feedback = ReturnType<typeof useRealPhotoFeedback>;

export function RealPhotoControls({feedback, onResults}: {feedback: Feedback; onResults: () => void}) {
  const {query, mutation, path} = feedback;
  const state = query.data;
  if (query.isError) return <div role="alert">回流状态加载失败 <button onClick={() => query.refetch()}>重试</button></div>;
  if (!state) return null;
  if (!state.available) return null;
  const status = state.pause_reason ? "已阻塞" : !state.selected ? "未启用" : !state.enabled ? "已暂停" : "运行中";
  return <div className="task-detail-section task-inline-controls">
    <div className="real-photo-controls">
      <strong>实拍回流训练</strong><span className="pill neutral">{status}</span>
      <button className="secondary compact-action" disabled={mutation.isPending}
        onClick={() => mutation.mutate({url:path, body:{enabled:!state.enabled}})}>{state.enabled ? "暂停实拍回流" : "启用实拍回流"}</button>
      {state.selected && <button className="secondary compact-action" onClick={onResults}>排除 / 不确定 {state.agent_filtered_count ?? 0} 张</button>}
    </div>
    {state.pause_reason && <p className="hint-line" role="status">已阻塞：{state.pause_reason}</p>}
    {mutation.isError && <p role="alert">{String(mutation.error)}</p>}
  </div>;
}

function SamplePreview({sample, url}: {sample: Sample; url: string}) {
  return <svg viewBox={`0 0 ${sample.geometry.width} ${sample.geometry.height}`} role="img" aria-label="实拍原图与当前 bbox" style={{width:"100%",maxHeight:320,background:"#111"}}>
    <image href={url} width={sample.geometry.width} height={sample.geometry.height}/>
    {(sample.annotation?.objects || []).map((o,i) => <g key={i}>
      <rect x={o.bbox[0]} y={o.bbox[1]} width={o.bbox[2]-o.bbox[0]} height={o.bbox[3]-o.bbox[1]} fill="none" stroke="#ffbf00" strokeWidth={Math.max(sample.geometry.width/400,1)}/>
      <text x={o.bbox[0]} y={Math.max(o.bbox[1],16)} fill="#ffbf00" fontSize={Math.max(sample.geometry.width/45,12)}>{o.class_id}</text>
    </g>)}
  </svg>;
}
function SampleDetail({sample, feedback, close}: {sample: Sample; feedback: Feedback; close: () => void}) {
  const {path, key, mutation} = feedback;
  const versions = useQuery({queryKey:[...key,"versions",sample.sample_id],
    queryFn:() => apiClient.get<{annotations:unknown[]; reviews:unknown[]; source_groups?:unknown[]; masks:{job_id:string;mapping_status:string}[]}>(path+`/samples/${encodeURIComponent(sample.sample_id)}/versions`)});
  const samplePath = path+`/samples/${encodeURIComponent(sample.sample_id)}`;
  return <>
    <button className="secondary compact-action" onClick={close}>返回列表</button>
    <h3>{labels[sample.current_status || ""] || "样本详情"} · {sample.sample_id}</h3>
    <SamplePreview sample={sample} url={samplePath+"/image"}/>
    <p>{sample.review?.reason || "等待自动流程生成筛选结果"}</p>
    {sample.annotation?.error_code && <p role="status">标注失败阶段：{sample.annotation.error_code}</p>}
    <details><summary>标注与审核版本</summary>
      {versions.isPending ? <p>正在加载历史</p> : versions.isError ? <p role="alert">历史加载失败 <button onClick={() => versions.refetch()}>重试</button></p> : <>
        <pre style={{whiteSpace:"pre-wrap",overflowWrap:"anywhere"}}>{JSON.stringify({annotations:versions.data.annotations,reviews:versions.data.reviews,source_groups:versions.data.source_groups},null,2)}</pre>
        {versions.data.masks.map(m=><figure key={m.job_id}><img alt="附加 mask，不能改变训练准入" style={{maxWidth:"100%"}} src={samplePath+`/masks/${encodeURIComponent(m.job_id)}/image`}/><figcaption>{m.mapping_status} · 不改变框和训练准入</figcaption></figure>)}
      </>}
    </details>
    <details><summary>高级操作</summary>
      <p>仅用于异常恢复。冻结来源和审核中的编辑限制由服务端执行；重标会创建新版本。</p>
      <SourceGroup sample={sample} pending={mutation.isPending} save={(value, confirmed) => mutation.mutate({url:samplePath+"/group",body:{source_group:value,source_group_confirmed:confirmed}})}/>
      <div className="card-action-row">
        <button disabled={mutation.isPending} onClick={() => mutation.mutate({url:samplePath+"/relabel",post:true})}>重新出框（新版本）</button>
        <button disabled={mutation.isPending} onClick={() => mutation.mutate({url:samplePath+"/mask",post:true})}>按需生成 mask 附件</button>
      </div>
    </details>
  </>;
}

export function RealPhotoDrawer({feedback, kind, title, close}: {feedback: Feedback; kind: RealPhotoDrawerKind; title: string; close: () => void}) {
  const {query, mutation, path, key} = feedback;
  const state = query.data!;
  const [decision, setDecision] = useState("");
  const [cursors, setCursors] = useState<(string | null)[]>([null]);
  const [detail, setDetail] = useState<Sample | null>(null);
  const category = kind === "manual" ? "agent_filtered" : kind === "dataset" ? "approved" : "all";
  const cursor = cursors[cursors.length-1];
  const list = useQuery({queryKey:[...key,"samples",category,decision,cursor],
    queryFn:() => apiClient.get<{samples:Sample[]; total:number; next_cursor:string | null}>(path+"/samples?"+new URLSearchParams({category,limit:"24",...(decision ? {decision}:{}),...(cursor ? {cursor}:{})})),
    refetchInterval: detail ? false : 10000});
  // Refresh an open detail from its own filtered-independent page; mutations can move it out of the current category.
  const detailQuery = useQuery({queryKey:[...key,"sample-detail",detail?.sample_id],
    queryFn:() => apiClient.get<{samples:Sample[]}>(path+"/samples?category=all&sample_id="+encodeURIComponent(detail!.sample_id)), enabled:Boolean(detail), refetchInterval:10000});

  return <TaskProcessDrawer title={title} context="任务过程数据" close={close}>
        {detail && detailQuery.isError && <p role="alert">详情刷新失败 <button onClick={()=>detailQuery.refetch()}>重试</button></p>}
        {detail ? <SampleDetail key={detail.sample_id} sample={detailQuery.data?.samples.find(s=>s.sample_id===detail.sample_id) || detail} feedback={feedback} close={()=>setDetail(null)}/> : <>
          {kind === "dataset" && <>
            <div className="task-drawer-summary"><strong>当前合格样本 {state.approved_count} 张</strong><span>正样本 {state.positive_count} · 负样本 {state.negative_count}</span></div>
            <h3>已冻结训练集</h3>
            {(state.datasets || []).length ? state.datasets!.map(d=><p key={d.id}>{d.id} · {d.real_source_count ?? d.sample_count} 张 · 快照 {d.snapshot_fingerprint}</p>) : <p>尚未生成训练集</p>}
      <p>审核触发点 {state.review_trigger ?? "等待 Agent 初始化"} · 合格实拍目标 {state.approved_real_target ?? "待确定"}（至少 20 张，且训练集有正样本、至少 3 个来源组）</p>
      <p>{state.assessment?.reason || state.initialization?.reason}</p>
      {state.assessment?.gaps?.length ? <p>需补充：{state.assessment.gaps.join("；")} · 下一轮新增 {state.assessment.next_increment} 张</p> : null}

      <details><summary>参考图缓存</summary><p>参考图缓存：{state.reference_cache?.status || "待创建"} · 第 {state.reference_cache?.generation ?? 0} 次创建{state.reference_cache?.expires_at ? ` · 到期 ${new Date(state.reference_cache.expires_at * 1000).toLocaleString()}` : ""}。命中时每次仅上传 1 张压缩实拍；实际 token 命中与缓存创建费用见调用统计。</p></details>
      <details><summary>Agent 与标注任务</summary>{state.jobs.map(j => <p key={j.id}>{j.kind} · {j.status} · {j.model}{j.result?.error_code && ` · ${j.result.error_code}`}{j.result?.error_type && ` · ${j.result.error_type}`}</p>)}</details>
      <details><summary>调用耗时与费用</summary>{Object.entries(state.call_statistics || {}).map(([kind,v]) => <p key={kind}>{kind}：{v.attempts} 次调用，{v.failures} 次失败，已记录耗时 {v.elapsed_seconds.toFixed(1)} 秒，token {JSON.stringify(v.usage)}，缺少 usage {v.unknown_usage_count} 次，缺少耗时 {v.unknown_elapsed_count} 次（Agent 次数为 CLI 会话数）。费用{v.estimated_cost === null ? "缺少计价依据，不可估算" : v.estimated_cost}</p>)}</details>
      <h3>训练状态</h3><p>{state.jobs.filter(j=>j.kind === "train").map(j=>`${j.id} · ${j.status}`).join("；") || "尚无训练任务"}</p>
      <h3>候选模型（手动选择）</h3><p>在检测工作台模型选择器切换，训练完成不会自动上线。</p>{(state.candidate_models || []).map(c => <article key={c.model_id}><p>{c.model_id} · {c.status} · 实拍 {c.real_source_count} 张（正 {c.positive_image_count} / 负 {c.negative_image_count}），train/val/test {JSON.stringify(c.split_image_counts)}。按来源组划分，实际比例可能偏离 80/10/10；缺少实拍或测试实例的类别不可评估。无实拍支持类别：{c.unsupported_by_real_data.join("、") || "无"}。请在检测工作台模型选择器切换。</p>{c.metrics && <details><summary>评估指标</summary><pre style={{whiteSpace:"pre-wrap"}}>{JSON.stringify(c.metrics,null,2)}</pre></details>}</article>)}

            <details><summary>高级操作</summary><p>{state.pause_reason || "无阻塞"}</p><button disabled={mutation.isPending || !state.enabled} onClick={() => mutation.mutate({url:path+"/restart",post:true})}>处理后重新审核</button></details>
            <h3>当前合格样本预览</h3><p className="hint-line">以下是当前准入结果，历史冻结训练集以其快照为准。</p>
          </>}
          {kind === "manual" && <label className="field">筛选结论<select value={decision} onChange={e=>{setDecision(e.target.value);setCursors([null]);}}><option value="">排除与不确定</option><option value="exclude">Agent 排除</option><option value="uncertain">Agent 不确定</option></select></label>}
          <div className="card-action-row"><span>共 {list.data?.total ?? "—"} 张 · 第 {cursors.length} 页</span><button className="secondary compact-action" onClick={()=>{setCursors([null]);void list.refetch();}}>刷新列表</button></div>
          {list.isPending ? <p>正在加载样本</p> : list.isError ? <p role="alert">样本加载失败 <button onClick={()=>list.refetch()}>重试</button></p> : <>
            {!list.data.samples.length && <div className="empty-panel compact-empty">暂无符合条件的样本。</div>}
            <div className="manual-review-grid">{list.data.samples.map(sample=><article className="manual-review-card" key={sample.sample_id}>
              <div className="image-processing-review-head"><strong>{sample.sample_id}</strong><span className="pill neutral">{labels[sample.current_status || ""] || "等待自动处理"}</span></div>
              <SamplePreview sample={sample} url={path+`/samples/${encodeURIComponent(sample.sample_id)}/image`}/>
              <p className="record-meta">{sample.review?.reason || (sample.annotation?.error_code ? `标注失败：${sample.annotation.error_code}` : "等待自动流程")}</p>
              <button className="secondary compact-action" onClick={()=>setDetail(sample)}>查看样本详情</button>
            </article>)}</div>
            <div className="card-action-row"><button disabled={cursors.length===1} onClick={()=>setCursors(cursors.slice(0,-1))}>上一页</button><button disabled={!list.data.next_cursor} onClick={()=>setCursors([...cursors,list.data.next_cursor])}>下一页</button></div>
          </>}
        </>}
        {mutation.isError && <p role="alert">{String(mutation.error)}</p>}
  </TaskProcessDrawer>;
}
