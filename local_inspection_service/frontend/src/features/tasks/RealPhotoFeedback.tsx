import { useEffect, useState } from "react";
import { useQuery, useQueryClient, useMutation } from "@tanstack/react-query";
import { apiClient, withAuthScope } from "../../api/client";
import { useAuth } from "../auth/auth-context";

type Box = { class_id: string; bbox: number[] };
type Sample = { sample_id: string; source_group?: string; geometry: { width: number; height: number }; annotation?: {status: string; version: number; objects: Box[]}; review?: {decision: string; reason: string} };
type CallStats = {attempts: number; failures: number; elapsed_seconds: number; usage: Record<string, number>; unknown_usage_count: number; unknown_elapsed_count: number; estimated_cost: number | null};
export type RealPhotoStatus = {available: boolean; selected?: boolean; enabled: boolean; candidate_count: number; approved_count: number; positive_count: number; negative_count: number; pending_annotation_count: number; pending_review_count: number; excluded_count: number; failed_annotation_count: number; review_trigger?: number; approved_real_target?: number; pause_reason?: string; initialization?: {reason: string}; assessment?: {action: string; reason: string; next_increment: number; gaps: string[]}; samples: Sample[]; jobs: {id: string; kind: string; status: string; model?: string}[]; candidate_models?: {model_id: string; status: string; unsupported_by_real_data: string[]; real_source_count:number; positive_image_count:number; negative_image_count:number; split_image_counts:Record<string,number>; metrics?: Record<string,{status:string; reason?:string; metrics?:Record<string,number>}>}[]; call_statistics?: Record<string, CallStats>};

function SourceGroup({sample, save}: {sample: Sample; save: (value: string) => void}) {
  const [value, setValue] = useState(sample.source_group || "");
  useEffect(() => setValue(sample.source_group || ""), [sample.source_group]);
  return <label>拍摄分组 <input aria-label="拍摄分组" value={value} onChange={e => setValue(e.target.value)} maxLength={200}/><button type="button" disabled={!value.trim() || value === sample.source_group} onClick={() => save(value)}>保存分组</button></label>;
}

export function RealPhotoFeedback({taskId, onSelection}: {taskId: string; onSelection: (selected: boolean) => void}) {
  const auth = useAuth(); const client = useQueryClient(); const [error, setError] = useState(""); const [historyId,setHistoryId]=useState<string | null>(null);
  const path = `/api/ai/tasks/${encodeURIComponent(taskId)}/real-photo`;
  const scoped = (value: string) => withAuthScope(value, auth.user, auth.dataUserId);
  const key = ["real-photo", auth.user.id, auth.dataUserId, taskId];
  const query = useQuery({queryKey: key, queryFn: () => apiClient.get<RealPhotoStatus>(scoped(path)), enabled: Boolean(taskId), refetchInterval: 5000});
  const mutation = useMutation({mutationFn: ({url, body, post}: {url: string; body?: unknown; post?: boolean}) => post ? apiClient.post<RealPhotoStatus>(scoped(url), body) : apiClient.patch<RealPhotoStatus>(scoped(url), body), onSuccess: value => {setError("");client.setQueryData(key, value);void client.invalidateQueries({queryKey:[...key,"versions"]});}, onError: e => setError(String(e))});
  const versions = useQuery({queryKey:[...key,"versions",historyId],queryFn:() => apiClient.get<{annotations:unknown[]; reviews:unknown[]; masks:{job_id:string;mapping_status:string}[]}>(scoped(path+`/samples/${historyId}/versions`)),enabled:Boolean(historyId)});
  const state = query.data;
  useEffect(() => onSelection(Boolean(state?.selected)), [state?.selected, onSelection]);
  if (!state?.available) return null;
  return <section className="task-detail-section">
    <h3>实拍回流训练</h3>
    <p>实拍原图 → 豆包出框 → Agent 筛选整图 → 实拍数据集 → YOLO 候选模型。候选模型由你手动切换。</p>
    <button disabled={mutation.isPending} onClick={() => mutation.mutate({url:path, body:{enabled:!state.enabled}})}>{state.enabled ? "暂停实拍回流" : "启用实拍 VLM 回流"}</button>
    {state.selected && <>
      <p>去重候选 {state.candidate_count} · 待标注 {state.pending_annotation_count} · 标注失败 {state.failed_annotation_count} · 待审核 {state.pending_review_count} · 合格正样本 {state.positive_count} / 负样本 {state.negative_count} · 排除或不确定 {state.excluded_count}</p>
      <p>审核触发点 {state.review_trigger ?? "等待 Agent 初始化"} · 合格实拍目标 {state.approved_real_target ?? "待确定"}（至少 20 张，且训练集有正样本、至少 3 个来源组）</p>
      <p>{state.assessment?.reason || state.initialization?.reason}</p>
      {state.assessment?.gaps?.length ? <p>需补充：{state.assessment.gaps.join("；")} · 下一轮新增 {state.assessment.next_increment} 张</p> : null}
      {state.pause_reason && <p role="status">已阻塞：{state.pause_reason} <button disabled={mutation.isPending} onClick={() => mutation.mutate({url:path+"/restart",post:true})}>处理后重新审核</button></p>}
      <details><summary>Agent 与标注任务</summary>{state.jobs.map(j => <p key={j.id}>{j.kind} · {j.status} · {j.model}</p>)}</details>
      <details><summary>调用耗时与费用</summary>{Object.entries(state.call_statistics || {}).map(([kind,v]) => <p key={kind}>{kind}：{v.attempts} 次调用，{v.failures} 次失败，已记录耗时 {v.elapsed_seconds.toFixed(1)} 秒，token {JSON.stringify(v.usage)}，缺少 usage {v.unknown_usage_count} 次，缺少耗时 {v.unknown_elapsed_count} 次（Agent 次数为 CLI 会话数）。费用{v.estimated_cost === null ? "缺少计价依据，不可估算" : v.estimated_cost}</p>)}</details>
      <details><summary>候选模型（手动选择）</summary>{(state.candidate_models || []).map(c => <p key={c.model_id}>{c.model_id} · {c.status} · 实拍 {c.real_source_count} 张（正 {c.positive_image_count} / 负 {c.negative_image_count}），train/val/test {JSON.stringify(c.split_image_counts)}。按来源组划分，实际比例可能偏离 80/10/10；缺少实拍或测试实例的类别不可评估。无实拍支持类别：{c.unsupported_by_real_data.join("、") || "无"}。请在检测工作台模型选择器切换。{c.metrics && <pre style={{whiteSpace:"pre-wrap"}}>{JSON.stringify(c.metrics,null,2)}</pre>}</p>)}</details>
      <div className="real-photo-grid" style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(280px,1fr))",gap:16}}>{state.samples.slice().reverse().map(s => <article key={s.sample_id}>
        <svg viewBox={`0 0 ${s.geometry.width} ${s.geometry.height}`} role="img" aria-label="实拍原图与当前 bbox" style={{width:"100%",maxHeight:280,background:"#111"}}>
          <image href={scoped(path+`/samples/${s.sample_id}/image`)} width={s.geometry.width} height={s.geometry.height}/>
          {(s.annotation?.objects || []).map((o,i) => <g key={i}><rect x={o.bbox[0]} y={o.bbox[1]} width={o.bbox[2]-o.bbox[0]} height={o.bbox[3]-o.bbox[1]} fill="none" stroke="#ffbf00" strokeWidth={Math.max(s.geometry.width/400,1)}/><text x={o.bbox[0]} y={Math.max(o.bbox[1],16)} fill="#ffbf00" fontSize={Math.max(s.geometry.width/45,12)}>{o.class_id}</text></g>)}
        </svg>
        <p>{s.annotation?.status || "待标注"} · v{s.annotation?.version ?? "-"} · {s.review?.decision || "待审核"}</p><p>{s.review?.reason}</p>
        <SourceGroup sample={s} save={value => mutation.mutate({url:path+`/samples/${s.sample_id}/group`,body:{source_group:value}})}/>
        <button disabled={mutation.isPending} onClick={() => mutation.mutate({url:path+`/samples/${s.sample_id}/relabel`,post:true})}>重新出框（新版本）</button>
        <button disabled={mutation.isPending} onClick={() => mutation.mutate({url:path+`/samples/${s.sample_id}/mask`,post:true})}>按需生成 mask 附件</button>
        <button onClick={() => setHistoryId(historyId===s.sample_id ? null : s.sample_id)}>查看历史标注与审核</button>
        {historyId===s.sample_id && versions.data && <details open><summary>标注与审核版本</summary><pre style={{whiteSpace:"pre-wrap",overflowWrap:"anywhere"}}>{JSON.stringify({annotations:versions.data.annotations,reviews:versions.data.reviews},null,2)}</pre>{versions.data.masks.map(m=><figure key={m.job_id}><img alt="附加 mask，不能改变训练准入" style={{maxWidth:"100%"}} src={scoped(path+`/samples/${s.sample_id}/masks/${m.job_id}/image`)}/><figcaption>{m.mapping_status} · 不改变框和训练准入</figcaption></figure>)}</details>}
      </article>)}</div>
    </>}
    {error && <p role="alert">{error}</p>}
  </section>;
}
