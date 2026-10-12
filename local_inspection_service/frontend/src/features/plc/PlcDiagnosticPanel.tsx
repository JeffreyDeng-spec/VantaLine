import { FormEvent, useContext, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiClient } from "../../api/client";
import { AuthContext } from "../auth/auth-context";
import { DiagnosticEvent, diagnosticMessages } from "./diagnosticLog";
type Row=DiagnosticEvent & {received_at:number;username:string;station_name:string;owner_user_id:string;evidence_source:string;server_lease_observation?:{state:string;lease_epoch:number;config_generation:number}};
type Page={items:Row[];next_offset:number|null;limited?:boolean};
const steps:Record<DiagnosticEvent["step"],string>={selection:"选择串口",workstation:"工作站配置",lease:"申请租约",open:"打开串口",quiet:"检查残留数据",read:"读取 PLC",activate:"激活连接",heartbeat:"心跳",write:"写入结果",disconnect:"断开",summary:"生产汇总"};
const results:Record<DiagnosticEvent["result"],string>={started:"开始",ok:"成功",failed:"失败",cancelled:"取消",uncertain:"不确定",summary:"汇总"};
function date(value:number){return new Date(value).toLocaleString("zh-CN",{hour12:false});}
export function PlcDiagnosticPanel() {
  const auth=useContext(AuthContext);const admin=auth?.user.role==="admin";
  const [open,setOpen]=useState(false);const [filters,setFilters]=useState({account:"",station:"",code:"",since:"",until:""});
  const [offset,setOffset]=useState(0);const [selected,setSelected]=useState<Row|null>(null);const [detailOffset,setDetailOffset]=useState(0);
  const params=new URLSearchParams({account:filters.account,station:filters.station,code:filters.code,offset:String(offset)});
  if(filters.since)params.set("since",String(new Date(filters.since).getTime()));if(filters.until)params.set("until",String(new Date(filters.until).getTime()));
  const query=useQuery({queryKey:["plcDiagnostics",auth?.user.id,filters,offset],queryFn:()=>apiClient.get<Page>(`/api/plc/diagnostic-events?${params}`),enabled:open,retry:false,refetchOnWindowFocus:false,refetchOnReconnect:false,staleTime:Infinity});
  const detail=useQuery({queryKey:["plcDiagnosticAttempt",auth?.user.id,selected?.owner_user_id,selected?.attempt_id,detailOffset],queryFn:()=>apiClient.get<Page>(`/api/plc/diagnostic-events?${new URLSearchParams({account:selected?.owner_user_id||"",attempt:selected?.attempt_id||"",offset:String(detailOffset)})}`),enabled:open&&Boolean(selected),retry:false,refetchOnWindowFocus:false,refetchOnReconnect:false,staleTime:Infinity});
  function search(event:FormEvent<HTMLFormElement>){event.preventDefault();const f=new FormData(event.currentTarget);setFilters({account:String(f.get("account")||""),station:String(f.get("station")||""),code:String(f.get("code")||""),since:String(f.get("since")||""),until:String(f.get("until")||"")});setOffset(0);setSelected(null);}
  const terminal=detail.data?.items.some(e=>e.step==="activate"&&e.result==="ok" || e.step==="disconnect" || e.result==="failed"&&e.step!=="summary");
  return <details className="plc-diagnostic-panel" onToggle={e=>setOpen(e.currentTarget.open)}><summary>诊断日志</summary>
    {open && <><p className="hint-line">浏览器报告用于排查；物理执行以现有写入审计为准。默认显示最近 30 天，每页 50 条，手动刷新。</p>
      <form className="button-row" onSubmit={search}>
        {admin&&<label>账号<input name="account" placeholder="用户名或账号 ID" maxLength={80}/></label>}
        <label>工作站<input name="station" placeholder="工作站 ID" maxLength={80}/></label>
        <label>错误类型<select name="code"><option value="">全部</option>{Object.entries(diagnosticMessages).filter(([code])=>code).map(([code,label])=><option value={code} key={code}>{label}</option>)}</select></label>
        <label>开始时间<input type="datetime-local" name="since"/></label><label>结束时间<input type="datetime-local" name="until"/></label>
        <button type="submit">查询</button><button type="button" onClick={()=>void query.refetch()}>刷新</button>
      </form>
      {query.isFetching&&<p role="status">正在读取诊断记录…</p>}{query.isError&&<p role="alert">诊断记录暂时不可用，PLC 生产不受日志查询控制。</p>}
      {query.data&&!query.data.items.length&&<p>暂无诊断记录；未启用采集或未上传的连接不会出现在这里。</p>}
      <div className="plc-diagnostic-table"><table><thead><tr><th>接收时间</th><th>账号</th><th>工作站</th><th>步骤</th><th>结果</th><th>详情</th></tr></thead><tbody>{query.data?.items.map(row=><tr key={`${row.owner_user_id}:${row.event_id}`}><td>{date(row.received_at)}</td><td>{row.username}</td><td>{row.station_name || row.station_id || "绑定前"}</td><td>{steps[row.step]}</td><td>{results[row.result]} {row.code&&diagnosticMessages[row.code]}</td><td><button type="button" onClick={()=>{setSelected(row);setDetailOffset(0);}}>查看时间线</button></td></tr>)}</tbody></table></div>
      {query.data?.limited&&<p>已达到查询窗口上限，请缩小时间范围。</p>}
      <div className="button-row"><button type="button" disabled={!offset} onClick={()=>setOffset(Math.max(0,offset-50))}>上一页</button><button type="button" disabled={query.data?.next_offset==null} onClick={()=>setOffset(query.data!.next_offset!)}>下一页</button></div>
      {selected&&<section aria-label="PLC 连接时间线"><h4>连接尝试 {selected.attempt_id}</h4><p>{terminal?"已收到结果事件；按步骤查看失败或激活结果。":"结果未知：本页未收到结束事件，可能仍在进行或日志丢失。"}</p>
        {detail.isError&&<p role="alert">时间线加载失败。</p>}
        <ol>{[...(detail.data?.items||[])].sort((a,b)=>a.sequence-b.sequence).map(row=><li key={row.event_id}><strong>{steps[row.step]} · {results[row.result]}</strong> — {date(row.client_time_ms)} · {row.duration_ms}ms {row.code&&diagnosticMessages[row.code]} {row.target&&`${row.target}，收到 ${row.actual_bytes}/${row.expected_bytes} 字节`}<br/><small>浏览器报告 · 配置版本 {row.config_generation} · 网页 {row.bundle_version} {row.dispatch_id&&`· 写入编号 ${row.dispatch_id}`}</small>{row.config&&<p>连接配置：{row.config.baudrate}/{row.config.data_bits}{row.config.parity}{row.config.stop_bits}；输入 {row.config.input_register}，结果 {row.config.result_register}，Y {row.config.output_control_point||"留空"}；超时 {row.config.timeout_ms}ms；自动拍照 {row.config.capture_enabled?"开":"关"}，触发值 {row.config.trigger_value}</p>}{row.trigger_state&&<p>到位状态：{row.trigger_state==="high"?"触发电平":"复位电平"}（不记录寄存器原值）</p>}{row.step==="summary"&&<p>成功读取 {row.reads_ok} · 心跳 {row.heartbeats_ok} · 写入 ACK {row.writes_ok} · 累计丢弃 {row.dropped}</p>}{row.server_lease_observation&&<p>服务端在收录时观察到租约：{row.server_lease_observation.state} / epoch {row.server_lease_observation.lease_epoch}，不代表这条历史指令已执行。</p>}</li>)}</ol>
        <div className="button-row"><button type="button" disabled={!detailOffset} onClick={()=>setDetailOffset(Math.max(0,detailOffset-50))}>较新事件</button><button type="button" disabled={detail.data?.next_offset==null} onClick={()=>setDetailOffset(detail.data!.next_offset!)}>较早事件</button><button type="button" onClick={()=>void detail.refetch()}>刷新时间线</button><button type="button" onClick={()=>setSelected(null)}>收起</button></div>
      </section>}
    </>}
  </details>;
}
