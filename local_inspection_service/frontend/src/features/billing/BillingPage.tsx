import { useEffect, useRef, useState } from "react";
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient, ApiError } from "../../api/client";
import { queryKeys } from "../../api/queries";
import { useAuth } from "../auth/auth-context";
import { useToast } from "../../components/ToastProvider";
import { LoadingState, ErrorState } from "../../components/LoadingState";
import type { Account, Entry, EntryPage, Money, Overview, Point } from "./types";
import "./billing.css";

const API = "/api/admin/billing";
const reasons: Record<string, string> = {
  credentials_missing: "财务只读凭据未配置", billing_source_unverified: "计费来源待验证",
  not_synced: "尚未同步", provider_denied: "财务查询权限不足", provider_unavailable: "服务暂时不可用",
  provider_rate_limited: "供应商查询限流", billing_store_unavailable: "财务存储暂不可用",
  billing_configuration_invalid: "财务账户配置需检查", billing_currency_mismatch: "账户币种不匹配",
  payer_identity_mismatch: "付款账户不匹配", official_summary_unavailable: "官方汇总口径待验证",
  invalid_provider_record: "供应商数据格式待核验", invalid_provider_amount: "供应商金额待核验",
  incomplete_provider_pagination: "账单分页未完整获取", conflicting_provider_record: "账单记录存在冲突",
  billing_sync_limit: "本次同步超过查询上限", billing_scope_mismatch: "账单范围不匹配",
  billing_sync_failed: "财务同步暂时失败", billing_lease_lost: "同步租约已变更",
  cached_read_unavailable: "读取失败，保留上次成功快照",
  billing_reconciliation_pending: "账单差额待核对",
};
const reason = (code: string | null) => code ? reasons[code] || "同步状态待核验" : "";
const project = (value: string) => ({ vantaline: "VantaLine", other: "其他项目", unknown: "未归属" })[value] || "未归属";
const dateTime = (value?: number) => value ? new Date(value * 1000).toLocaleString("zh-CN", { hour12: false }) : "尚未采集";
function currentMonth() {
  const parts = new Intl.DateTimeFormat("en", { timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit" }).formatToParts(new Date());
  return `${parts.find(p => p.type === "year")!.value}-${parts.find(p => p.type === "month")!.value}`;
}

// Decimal strings stay exact for display; Number is used only for plot geometry.
function money(value: Money | undefined, currency: string) {
  if (value == null) return "—";
  const negative = value.startsWith("-");
  const [whole, fractional = ""] = value.replace(/^-/, "").split(".");
  let minor = BigInt(whole) * 100n + BigInt((fractional + "00").slice(0, 2));
  if (Number(fractional[2] || 0) >= 5) minor += 1n;
  const sign = { CNY: "¥", USD: "US$", JPY: "JP¥" }[currency] || `${currency} `;
  return `${negative && minor ? "−" : ""}${sign}${(minor / 100n).toLocaleString("zh-CN")}.${String(minor % 100n).padStart(2, "0")}`;
}

function useVisible() {
  const [visible, set] = useState(document.visibilityState === "visible");
  useEffect(() => {
    const update = () => set(document.visibilityState === "visible");
    document.addEventListener("visibilitychange", update);
    return () => document.removeEventListener("visibilitychange", update);
  }, []);
  return visible;
}

function Spark({ points, large = false, currency = "CNY" }: { points: Point[]; large?: boolean; currency?: string }) {
  if (!points.length) return <div className="billing-chart-empty">消耗数据不足，暂无趋势</div>;
  const values = points.map(p => Number(p.amount));
  const low = Math.min(...values, 0), high = Math.max(...values, .01);
  const coordinates = values.map((v, i) => [12 + i * 316 / Math.max(1, values.length - 1), 110 - (v - low) / (high - low) * 90]);
  const mean = values.reduce((a, b) => a + b, 0) / values.length;
  const path = coordinates.map(p => p.join(",")).join(" ");
  return <svg className={`billing-spark ${large ? "large" : ""}`} viewBox={`0 0 340 ${large ? 143 : 120}`} preserveAspectRatio={large ? "xMidYMid meet" : "none"} role="img" aria-label={`${currency}已入账消耗趋势`}>
    {large && [20, 65, 110].map(y => <line key={y} x1="12" y1={y} x2="328" y2={y} stroke="#e7edf6" />)}
    <polygon points={`12,110 ${path} 328,110`} fill="currentColor" opacity=".09" />
    {large && <line x1="12" x2="328" y1={110 - (mean - low) / (high - low) * 90} y2={110 - (mean - low) / (high - low) * 90} stroke="currentColor" strokeDasharray="3 4" opacity=".5" />}
    <polyline points={path} fill="none" stroke="currentColor" strokeWidth="2" vectorEffect="non-scaling-stroke" />
    {large && coordinates.map(([x, y], i) => <g key={points[i].date}><circle cx={x} cy={y} r="3" fill="currentColor"><title>{points[i].date} · {money(points[i].amount, currency)}</title></circle><text x={x} y="135" textAnchor="middle" fontSize="10" fill="#8390a3">{points[i].date.slice(5)}</text></g>)}
  </svg>;
}

function Speed({ account: a }: { account: Account }) {
  return <div className="billing-speed"><div className="billing-speed-stats"><div><small>{a.consumption_stale && a.daily_average !== null ? "上次完整区间日均" : "近 7 个完整账单日日均"}</small><strong>{a.daily_average === "0" ? "无消耗" : money(a.daily_average, a.currency)}{a.daily_average !== null && a.daily_average !== "0" && <em> / 天</em>}</strong></div><div><small>按当前速度预计可用</small><strong>{a.runway_days === null ? "—" : Number(a.runway_days) < 1 ? "不足 1 天" : `${a.runway_days} 天`}</strong></div></div><Spark points={a.trend} currency={a.currency} /><p>{a.consumption_window ? `${a.consumption_window.from}–${a.consumption_window.to}${a.consumption_stale ? " · 消耗快照过期" : " · 预测仅供参考"}` : "账单区间不完整，暂不预测可用天数"}</p></div>;
}

function status(a: Account) {
  if (a.urgency === "critical") return "余额紧急";
  if (a.balance_stale || a.bill_stale) return "同步过期";
  if (a.reason) return a.balance ? "同步异常" : "待接入";
  return a.urgency === "warning" ? "余额需关注" : a.urgency === "normal" ? "余额充足" : "数据待确认";
}

function staleAccount(a: Account): Account {
  return { ...a, balance_stale: !!a.balance, bill_stale: !!a.bills, consumption_stale: true, runway_days: null,
    urgency: a.urgency === "critical" ? "critical" : a.balance ? "warning" : "pending", reason: a.reason || "cached_read_unavailable" };
}

export function BillingPage() {
  const { user } = useAuth();
  const client = useQueryClient();
  const { notify } = useToast();
  const visible = useVisible();
  const [period, setPeriod] = useState(currentMonth);
  const [attention, setAttention] = useState(false), [selected, setSelected] = useState<string | null>(null);
  const [currency, setCurrency] = useState("CNY"), [denied, setDenied] = useState(false);
  const [pendingJobs, setPendingJobs] = useState<string[]>([]);
  const opener = useRef<HTMLElement | null>(null);
  const allowed = user.role === "admin" && !denied;
  const key = ["billing", user.id, period];
  const query = useQuery({ queryKey: [...key, "overview"], queryFn: ({ signal }) => apiClient.get<Overview>(`${API}/overview?period=${period}`, { signal }), enabled: allowed, retry: false, refetchInterval: visible ? 30_000 : false, refetchIntervalInBackground: false });
  const detail = useQuery({ queryKey: [...key, "account", selected], queryFn: ({ signal }) => apiClient.get<Account>(`${API}/accounts/${selected}?period=${period}`, { signal }), enabled: allowed && !!selected, retry: false, refetchInterval: visible ? 30_000 : false });
  const jobs = useQuery({ queryKey: ["billing", user.id, "jobs", pendingJobs], queryFn: ({ signal }) => Promise.all(pendingJobs.map(id => apiClient.get<{ status: string; error_code: string | null }>(`${API}/jobs/${id}`, { signal }))), enabled: allowed && pendingJobs.length > 0, retry: false, refetchInterval: visible ? 3000 : false });
  const refresh = useMutation({ mutationFn: (id: string | null) => apiClient.post<{ job_ids: string[]; pending_accounts: number }>(`${API}/refresh`, { account_id: id, period }), onSuccess: async data => { setPendingJobs(data.job_ids); notify({ title: data.job_ids.length ? "已提交财务同步；重复请求会合并" : "账户待接入，暂无可同步数据" }); await client.invalidateQueries({ queryKey: ["billing", user.id] }); }, onError: e => notify({ title: "同步未提交", description: e instanceof ApiError ? reason(e.message) : "财务服务暂时不可用", tone: "error" }) });
  useEffect(() => {
    if (!pendingJobs.length) return;
    if (jobs.error) { setPendingJobs([]); return; }
    if (jobs.data?.every(job => ["succeeded", "failed"].includes(job.status))) {
      const failed = jobs.data.filter(job => job.status === "failed");
      setPendingJobs([]);
      notify({ title: failed.length ? "部分财务同步失败，已保留上次快照" : "财务快照已更新", description: failed.length ? reason(failed[0].error_code) : undefined, tone: failed.length ? "error" : "success" });
      void client.invalidateQueries({ queryKey: ["billing", user.id] });
    }
  }, [jobs.data, jobs.error, pendingJobs.length, client, user.id, notify]);
  // Financial data must disappear immediately after role/session rejection,
  // rather than retaining React Query's stale successful result on an error.
  useEffect(() => {
    const error = [query.error, detail.error, refresh.error, jobs.error].find(e => e instanceof ApiError && (e.status === 401 || e.status === 403));
    if (user.role !== "admin" || error) { setDenied(true); setSelected(null); void client.cancelQueries({ queryKey: ["billing"] }); client.removeQueries({ queryKey: ["billing"] }); void client.invalidateQueries({ queryKey: queryKeys.authStatus }); }
  }, [user.role, query.error, detail.error, refresh.error, jobs.error, client]);
  const forbidden = [query.error, detail.error, refresh.error, jobs.error].some(e => e instanceof ApiError && (e.status === 401 || e.status === 403));
  if (!allowed || forbidden) return <p className="hint-line">仅管理员可访问用量与成本。</p>;
  const accounts = (query.data?.accounts || []).map(a => query.isError ? staleAccount(a) : a), shown = attention ? accounts.filter(a => a.urgency !== "normal") : accounts;
  const totals = (query.data?.totals || []).map(t => query.isError ? { ...t, stale: true } : t);
  const cohort = accounts.filter(a => a.currency === currency && a.bills?.scope === "payer" && a.bills.official_total !== null);
  const currencyTotal = totals.find(t => t.currency === currency);
  const trend = currencyTotal?.trend || [];
  const dates = trend.map(p => p.date);
  function open(a: Account, trigger: HTMLElement) { opener.current = trigger; setSelected(a.id); }
  const [currentYear, currentMonthNumber] = currentMonth().split("-").map(Number);
  const months = Array.from({ length: 18 }, (_, i) => new Date(Date.UTC(currentYear, currentMonthNumber - 1 - i, 1)).toISOString().slice(0, 7));
  return <section className="billing-page" aria-label="用量与成本">
    <header className="billing-heading"><div><h3>用量与成本</h3><p>按付款账户展示余额与费用。</p></div><div className="billing-tools"><label>账期 <select aria-label="账期" value={period} onChange={e => { setPeriod(e.target.value); setSelected(null); }}>{months.map(m => <option key={m}>{m}</option>)}</select></label><button className="primary" disabled={refresh.isPending || pendingJobs.length > 0} onClick={() => refresh.mutate(null)}>{refresh.isPending ? "提交中…" : pendingJobs.length ? "同步中…" : "刷新数据"}</button></div></header>
    {query.isLoading ? <LoadingState label="正在读取财务快照" /> : query.isError && !query.data ? <ErrorState error={new Error(reason(query.error instanceof ApiError ? query.error.message : null) || "财务数据暂时不可用")} /> : <>
      {(query.isError || query.data?.worker_error) && <p className="billing-notice" role="status">{query.isError ? "读取失败，保留上次成功快照。" : reason(query.data!.worker_error)} 不完整数据不会作为零费用展示。</p>}
      <div className="billing-section-head"><h4>账户余额</h4><div className="billing-segments"><button aria-pressed={!attention} onClick={() => setAttention(false)}>全部账户 {accounts.length}</button><button aria-pressed={attention} onClick={() => setAttention(true)}>需关注 {accounts.filter(a => a.urgency !== "normal").length}</button></div></div>
      <div className="billing-legend"><span>🔴 不足 3 天 / 余额耗尽</span><span>🟡 不足 14 天 / 同步异常</span><span>🟢 充足</span><span>⚪ 待确认</span></div>
      <div className="billing-accounts">{shown.map(a => <button key={a.id} className={`billing-account ${a.urgency}`} aria-label={`查看${a.name}账户详情`} onClick={e => open(a, e.currentTarget)}><div className="billing-account-top"><strong>{a.name}</strong><span className="billing-badge">{status(a)}</span></div><small className="billing-alias">{a.alias} · {a.currency}</small><small>{a.provider === "ali" ? "官方可用额度" : "官方可用余额"}</small><strong className="billing-balance">{money(a.balance?.value, a.currency)}</strong><p className="billing-account-note">{(a.reason === "billing_source_unverified" ? a.provider === "gemini" ? "余额接口待验证" : a.provider === "codex" ? "计费方式待确认" : reason(a.reason) : reason(a.reason)) || (a.balance_stale ? "保留上次成功余额" : "按付款账户展示")}</p><Speed account={a} /><div className="billing-spent"><span>{period}已入账费用</span><strong>{money(a.bills?.official_total, a.currency)}</strong></div><div className="billing-card-footer"><span>{a.balance ? `${a.balance_stale ? "过期快照" : "采集"} ${dateTime(a.balance.synced_at)}` : "余额尚未接入"}</span><span>查看详情</span></div></button>)}</div>
      <p className="billing-footnote">同一付款账户余额不重复累计。缺少完整费用来源的账户不纳入合计；当前余额不随历史账期改变。</p>
      <section className="billing-overview"><h4>费用概览</h4><div className="billing-totals">{totals.map(t => <div key={t.currency}><small>{t.currency} · {period}官方费用</small><strong>{money(t.amount, t.currency)}</strong><p>覆盖 {t.covered} / {t.total_accounts} 个账户{t.stale ? " · 含过期快照" : ""}</p></div>)}</div><div className="billing-section-head"><h4>消耗趋势</h4><div className="billing-segments">{totals.map(t => <button key={t.currency} aria-pressed={currency === t.currency} onClick={() => setCurrency(t.currency)}>{t.currency}</button>)}</div></div><p className="billing-footnote">{dates.length ? `${dates[0]}–${dates[dates.length - 1]} · ${currency} · 覆盖 ${cohort.length} 个账户` : "所选币种暂无完整账单区间"}</p><div className="billing-trend-average"><small>这段账单区间日均消耗</small><strong>{money(currencyTotal?.daily_average, currency)} / 天</strong></div><Spark points={trend} large currency={currency} /><p className="billing-footnote">虚线为图示日均。账单存在入账延迟，预测不代表实时扣费或保证可用时长。</p><div className="billing-distribution">{totals.map(t => <div key={t.currency}>{accounts.filter(a => a.currency === t.currency && a.bills?.official_total !== null && a.bills).map(a => { const shareAllowed = !!t.amount && Number(t.amount) > 0 && accounts.filter(p => p.currency === t.currency && p.bills?.official_total != null).every(p => Number(p.bills!.official_total) >= 0); const ratio = shareAllowed ? Math.max(0, Math.min(100, Number(a.bills!.official_total) / Number(t.amount) * 100)) : 0; return <button key={a.id} onClick={e => open(a, e.currentTarget)} className="billing-share"><span>{a.name} {shareAllowed && <small>{ratio.toFixed(1)}%</small>}<strong>{money(a.bills!.official_total, a.currency)}</strong></span>{shareAllowed && <i><b style={{ width: `${ratio}%` }} /></i>}</button>; })}</div>)}</div></section>
    </>}
    {selected && <AccountDrawer key={`${user.id}:${selected}:${period}`} account={detail.isError && detail.data ? staleAccount(detail.data) : detail.data} loading={detail.isLoading} error={detail.error} userId={user.id} identifier={selected} period={period} visible={visible} onClose={() => { setSelected(null); opener.current?.focus(); }} onRefresh={() => refresh.mutate(selected)} busy={refresh.isPending || pendingJobs.length > 0} onDenied={() => { setDenied(true); setSelected(null); client.removeQueries({ queryKey: ["billing"] }); void client.invalidateQueries({ queryKey: queryKeys.authStatus }); }} />}
  </section>;
}

function AccountDrawer({ account: a, loading, error, userId, identifier, period, visible, onClose, onRefresh, busy, onDenied }: { account?: Account; loading: boolean; error: unknown; userId: string; identifier: string; period: string; visible: boolean; onClose: () => void; onRefresh: () => void; busy: boolean; onDenied: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [tab, setTab] = useState("bills"), [entry, setEntry] = useState<Entry | null>(null);
  const pages = useInfiniteQuery({ queryKey: ["billing", userId, period, "entries", identifier, a?.bills?.snapshot_id], queryFn: ({ pageParam, signal }) => apiClient.get<EntryPage>(`${API}/accounts/${identifier}/entries?period=${period}&snapshot_id=${a?.bills?.snapshot_id}${pageParam ? `&cursor=${encodeURIComponent(pageParam)}` : ""}`, { signal }), initialPageParam: "", getNextPageParam: page => page.next_cursor || undefined, enabled: !!a?.bills && tab === "bills", retry: false });
  useEffect(() => { dialog.current?.showModal(); return () => dialog.current?.close(); }, []);
  useEffect(() => { if (pages.error instanceof ApiError && [401, 403].includes(pages.error.status)) onDenied(); }, [pages.error, onDenied]);
  const items = pages.data?.pages.flatMap(p => p.items) || [];
  const bills = a?.bills;
  const close = () => { dialog.current?.close(); onClose(); };
  return <dialog ref={dialog} className="billing-drawer" aria-labelledby="billing-drawer-title" onCancel={e => { e.preventDefault(); close(); }} onKeyDown={e => {
    if (e.key !== "Tab") return;
    const controls = Array.from(dialog.current!.querySelectorAll<HTMLElement>('button,select,input,a[href],[tabindex]')).filter(el => !el.hasAttribute("disabled") && el.tabIndex >= 0 && el.getClientRects().length);
    if (!controls.length) return;
    const index = controls.indexOf(document.activeElement as HTMLElement);
    e.preventDefault(); controls[index < 0 ? e.shiftKey ? controls.length - 1 : 0 : (index + (e.shiftKey ? controls.length - 1 : 1)) % controls.length].focus();
  }}><div className="billing-drawer-layout"><header><div><small>付款账户详情</small><h3 id="billing-drawer-title">{a?.name || "账户详情"}</h3><p>{a?.alias} · {period}</p></div><button autoFocus onClick={close}>关闭</button></header><div className="billing-drawer-body">{loading ? <LoadingState label="正在读取账户详情" /> : error && !a ? <ErrorState error={new Error("账户详情暂时不可用")} /> : a && <>
    {(error || a.reason || a.balance_stale || a.bill_stale) && <p className="billing-notice">{reason(a.reason) || "保留上次成功财务快照"}</p>}
    <div className="billing-drawer-stats"><div><small>官方可用余额 / 额度</small><strong>{money(a.balance?.value, a.currency)}</strong></div><div><small>所选账期官方费用</small><strong>{money(bills?.official_total, a.currency)}</strong></div></div><p className="billing-footnote">余额采集：{dateTime(a.balance?.synced_at)}<br />账单采集：{dateTime(bills?.synced_at)} · 完整账单日截至：{bills?.complete_until || "未确认"}<br />{bills?.scope === "supported_resources" ? "RunPod 当前覆盖 Pod、Serverless 和网络盘，尚未核实整个付款账户总额。" : "当前账期可能存在迟到账单、退款与调账。"}</p><Speed account={a} />
    <div className="billing-tabs" role="tablist" aria-label="账户详情">{[["bills", "账单"], ["resources", "资源费用"], ["projects", "项目归属"], ["reconcile", "对账"]].map(([id, label], index, all) => <button key={id} role="tab" id={`billing-tab-${id}`} aria-controls="billing-detail-panel" aria-selected={tab === id} tabIndex={tab === id ? 0 : -1} onClick={() => { setTab(id); setEntry(null); }} onKeyDown={e => { if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) return; e.preventDefault(); const next = e.key === "Home" ? 0 : e.key === "End" ? all.length - 1 : (index + (e.key === "ArrowRight" ? 1 : all.length - 1)) % all.length; setTab(all[next][0]); document.getElementById(`billing-tab-${all[next][0]}`)?.focus(); }}>{label}</button>)}</div>
    <div id="billing-detail-panel" role="tabpanel" aria-labelledby={`billing-tab-${tab}`}>{!bills ? <p className="billing-empty">尚无已同步账单。{reason(a.reason)}</p> : <>
      {tab === "bills" && <><p className="billing-footnote">冻结快照内共 {pages.data?.pages[0]?.total ?? bills.entry_count} 条记录 · 资源汇总不等同于交易条目</p>{pages.isLoading ? <LoadingState label="正在读取账单分页" /> : pages.isError ? <ErrorState error={new Error("账单分页读取失败，已加载记录保留")} action={<button onClick={() => pages.refetch()}>重试</button>} /> : null}<div className="billing-table-wrap"><table><thead><tr><th>日期 / 服务</th><th>净费用</th><th>详情</th></tr></thead><tbody>{items.map(row => <tr key={row.id}><td>{row.granularity === "monthly_resource" ? row.day.slice(0, 7) : row.day}<small>{row.service}{row.granularity === "monthly_resource" ? " · 按月汇总" : row.granularity === "daily_resource" ? " · 按日汇总" : ""}</small></td><td>{money(row.net, row.currency)}</td><td><button onClick={() => setEntry(entry?.id === row.id ? null : row)} aria-expanded={entry?.id === row.id} aria-label={`查看${row.service}账单条目`}>查看</button></td></tr>)}</tbody></table></div>{entry && <div className="billing-entry"><p>{entry.provider_record_id ? `官方条目标识：${entry.provider_record_id}` : `统计条目标识：${entry.id}`}</p><p>资源：{entry.resource || "未提供"}</p><p>归属：{project(entry.project)}</p><p>原价：{money(entry.gross, entry.currency)} · 折扣：{money(entry.discount, entry.currency)}</p></div>}{pages.hasNextPage && <button disabled={pages.isFetchingNextPage} onClick={() => pages.fetchNextPage()}>{pages.isFetchingNextPage ? "读取中…" : "加载更多"}</button>}</>}
      {tab === "resources" && bills.services.map(row => <div className="billing-detail-row" key={row.name}><span>{row.name}</span><strong>{money(row.amount, a.currency)}</strong></div>)}
      {tab === "projects" && <>{bills.projects.map(row => <div className="billing-detail-row" key={row.name}><span>{project(row.name)}</span><strong>{money(row.amount, a.currency)}</strong></div>)}<p className="billing-footnote">仅按服务器已核实的资源关联归属；没有证据的费用保留“未归属”。项目内估算在页面下方单独展示。</p></>}
      {tab === "reconcile" && <>{[["官方账期汇总", bills.official_total], ["完整记录合计", bills.entries_total], ["差额（记录 − 官方）", bills.reconciliation_delta], ["原价", bills.gross], ["折扣", bills.discount]].map(([label, value]) => <div className="billing-detail-row" key={label}><span>{label}</span><strong>{money(value, a.currency)}</strong></div>)}<p className="billing-footnote">{bills.reconciliation_delta === null ? "覆盖范围尚未核实，待对账。" : Number(bills.reconciliation_delta) === 0 ? "记录与官方汇总在当前快照口径下一致；当月账单仍可能调整。" : "存在差额，需核对供应商的入账时间与统计口径。"} 充值不是消费，不从费用差额反推余额。</p><details className="billing-components"><summary>余额组成与来源</summary>{Object.entries(a.balance?.components || {}).map(([name, value]) => <div className="billing-detail-row" key={name}><span>{({ CashBalance: "现金余额", CreditLimit: "信用额度", FreezeAmount: "冻结金额", ArrearsBalance: "欠费", AvailableCashAmount: "现金余额", CreditAmount: "信用额度", MybankCreditAmount: "网商银行额度", CashAccountBalance: "现金余额", PresentAccountBalance: "赠送余额", OweAmount: "欠费", RealCreditBalance: "可用信用额度" } as Record<string, string>)[name] || name}</span><strong>{money(value, a.currency)}</strong></div>)}<p>{a.balance?.source}<br />{bills.source}</p></details></>}
    </>}</div>
    </>}</div><footer><small>仅同步财务数据，不执行资源操作</small><button disabled={busy} onClick={onRefresh}>刷新此账户</button></footer></div></dialog>;
}
