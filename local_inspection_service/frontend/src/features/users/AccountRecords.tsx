import { useState } from "react";
import { useInfiniteQuery } from "@tanstack/react-query";
import { apiClient } from "../../api/client";
import { AdminDialog } from "./AdminDialog";

type Row = Record<string, string | number | boolean | null> & { id: string };
type Page = { items: Row[]; total: number; next_cursor: string | null; available: boolean };
const plc = [["connections", "当前 / 最近连接"], ["stations", "关联工作站"], ["diagnostics", "连接诊断"]];
const business = [["plc_executions", "PLC 执行证据"], ["text_inspection_records", "文字检测"], ["incoming_text_inspections", "包材检测"], ["data_analysis_records", "检测分析"], ["label_inspection_objects", "标签检测与准备"], ["codex_comparison_tasks", "文字对比任务"], ["text_inspection_standards", "文字标准 / 订单"]];
const fields: Record<string, string> = { id: "记录 ID", name: "名称", title: "标题", display_name: "名称", station_id: "工作站 ID", status: "状态", state: "保存的租约状态", created_at: "记录时间", updated_at: "更新时间", heartbeat_at: "最近心跳", expires_at: "租约到期", model_id: "模型", lease_epoch: "租约代次", config_generation: "配置版本", bundle_version: "浏览器版本", task_id: "任务 ID", standard_id: "标准 ID", kind: "类型", passed: "检测合格", decision: "结论", auto_decision: "自动结论", final_decision: "最终结论", step: "步骤", result: "结果", code: "诊断代码", target: "控制点", duration_ms: "耗时 (ms)", expected_bytes: "预期字节", actual_bytes: "实际字节", ownership_basis: "归属依据", registered_by_target: "该账号注册" };
const states: Record<string, string> = { active: "租约有效", connecting: "连接中", draining: "等待结算", expired: "租约已到期", released: "已释放", closed: "已关闭", completed: "已完成", failed: "失败", detecting: "检测中", planned: "已生成计划", browser_attempt_declared: "已声明浏览器执行", uncertain: "结果不确定", ok: "成功", cancelled: "已取消", saved_owner: "执行时保存的账号", matching_lease: "与保存租约精确匹配" };
function display(key: string, value: Row[string]) {
  if (value === null || value === undefined || value === "") return "—";
  if (["created_at", "updated_at", "heartbeat_at", "expires_at"].includes(key)) return Number(value) ? new Date(Number(value) * 1000).toLocaleString() : "—";
  if (typeof value === "boolean") return value ? "是" : "否";
  return states[String(value)] || String(value);
}
export function AccountRecords({ owner, mode }: { owner: string; mode: "plc" | "business" }) {
  const categories = mode === "plc" ? plc : business;
  const [category, setCategory] = useState(categories[0][0]);
  const [detail, setDetail] = useState<Row | null>(null);
  const query = useInfiniteQuery({
    queryKey: ["admin-account-records", owner, category], initialPageParam: null as string | null,
    queryFn: ({ pageParam }) => apiClient.get<Page>(`/api/auth/users/${encodeURIComponent(owner)}/data/records?category=${category}&limit=24${pageParam ? `&cursor=${encodeURIComponent(pageParam)}` : ""}`),
    getNextPageParam: (page) => page.next_cursor || undefined,
  });
  const rows = query.data?.pages.flatMap(p => p.items) || [];
  return <section className="panel page-panel">
    <h3>{mode === "plc" ? "PLC 连接记录" : "业务记录"}</h3>
    <p className="hint-line">{mode === "plc" ? "连接按实际账号租约归属；共享工作站不代表该账号正在连接。这里只读取记录，不连接、断开或写入 PLC。租约有效不等于设备在线。诊断保留 30 天，最近租约不是完整连接历史。" : "原始业务证据只读。PLC 旧记录仅在账号明确或租约精确匹配时展示；无法可靠归属的记录不计入该账号。结果不确定的写入不得重试。"}</p>
    <nav className="admin-tabs" aria-label="记录分类">{categories.map(([key, label]) => <button key={key} type="button" className={key === category ? "active" : ""} aria-current={key === category ? "page" : undefined} onClick={() => {setCategory(key); setDetail(null);}}>{label}</button>)}</nav>
    <div className="action-row"><span>匹配记录：{query.data?.pages[0]?.total ?? "—"} 条</span><button type="button" disabled={query.isFetching} onClick={() => void query.refetch()}>刷新记录</button></div>
    {query.isPending && <p role="status">正在加载记录…</p>}
    {query.isError && <p role="alert" className="admin-error">{query.error instanceof Error ? query.error.message : "记录读取失败"} <button type="button" onClick={() => void query.refetch()}>重试读取</button></p>}
    {query.data?.pages[0]?.available === false && <p role="status">诊断存储尚不可用。</p>}
    {!query.isPending && !query.isError && query.data?.pages[0]?.available !== false && !rows.length && <p className="hint-line">该账号暂无此类记录。</p>}
    {!!rows.length && <div className="admin-table-wrap"><table><thead><tr><th>记录 / 工作站</th><th>状态 / 结论</th><th>时间</th><th>详情</th></tr></thead><tbody>{rows.map(row => <tr key={row.id}><td>{String(row.name || row.title || row.display_name || row.id)}{row.station_id && row.station_id !== row.id && <small>{String(row.station_id)}</small>}</td><td>{display("status", row.final_decision || row.decision || row.status || row.result || row.state)}</td><td>{display("created_at", row.created_at || row.heartbeat_at)}</td><td><button type="button" onClick={() => setDetail(row)}>查看详情</button></td></tr>)}</tbody></table></div>}
    {query.hasNextPage && <button type="button" disabled={query.isFetching} onClick={() => void query.fetchNextPage()}>{query.isFetchingNextPage ? "正在加载…" : "加载更多记录"}</button>}
    {detail && <AdminDialog title="记录详情" onClose={() => setDetail(null)}><div className="admin-dialog-body"><p className="hint-line">目标账号：{owner} · 只读证据</p><dl>{Object.entries(detail).map(([key, value]) => <div key={key}><dt>{fields[key] || key}</dt><dd style={{ overflowWrap: "anywhere" }}>{display(key, value)}</dd></div>)}</dl></div><footer><button type="button" onClick={() => setDetail(null)}>关闭</button></footer></AdminDialog>}
  </section>;
}
