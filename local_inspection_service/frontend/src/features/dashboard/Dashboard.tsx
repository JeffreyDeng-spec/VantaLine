import { useRef } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, BrainCircuit, Box, RefreshCw, Server, SlidersHorizontal } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { detectionCenterNavItem, navItems, textCompareBetaNavItem } from "../../app/navigation";
import { hasPermission } from "../../app/permissions";
import { getConfigSummary, getServiceStatus, queryKeys } from "../../api/queries";
import { useToast } from "../../components/ToastProvider";
import { useAuth } from "../auth/auth-context";
import { OverviewTools } from "./OverviewTools";
import detectionImage from "./assets/detection-illustration.webp";
import textImage from "./assets/text-illustration.webp";
import "./dashboard.css";

const primaryEntries = [
  { item: detectionCenterNavItem, description: "识别配件，核验种类与数量", image: detectionImage },
  { item: textCompareBetaNavItem, description: "对照标准，检查文字与印刷差异", image: textImage }
];
const resourceViews = ["taskLibrary", "accessories", "trainingDatasets", "trainingLibrary"];
const toolGroups = [
  { label: "辅助检测", views: ["smartCompare", "aiInspect"] },
  { label: "分析与训练", views: ["dataAnalysis", "pipeline"] },
  { label: "系统", views: ["rules", "userManagement", "about"] }
];
const serviceLabels: Record<string, string> = { running: "运行中", stopped: "未运行", starting: "启动中", error: "状态异常" };

export function Dashboard() {
  const auth = useAuth();
  const { notify } = useToast();
  const refreshing = useRef(false);
  const statusQuery = useQuery({ queryKey: queryKeys.serviceStatus(auth.user.id), queryFn: () => getServiceStatus(auth) });
  const configQuery = useQuery({ queryKey: queryKeys.configSummary(auth.user.id), queryFn: () => getConfigSummary(auth) });
  const busy = statusQuery.isFetching || configQuery.isFetching;

  const refresh = async () => {
    if (refreshing.current || busy) return;
    refreshing.current = true;
    try {
      const results = await Promise.all([statusQuery.refetch(), configQuery.refetch()]);
      notify(results.some((result) => result.isError)
        ? { title: "部分状态未能更新，请重试", tone: "error" }
        : { title: "状态已更新", tone: "success" });
    } finally { refreshing.current = false; }
  };

  // Do not present a cached healthy state as current after a failed refresh.
  const status = statusQuery.isError ? undefined : statusQuery.data;
  const config = configQuery.isError ? undefined : configQuery.data;
  const pending = statusQuery.isPending;
  const service = pending ? "读取中" : statusQuery.isError ? "暂不可用" : serviceLabels[status?.service || ""] || "未知";
  const model = pending ? "读取中" : status?.model_exists === false ? "模型缺失" : status?.active_model_id || "—";
  const models = status && (Array.isArray(status.available_models) || Array.isArray(status.specialized_models))
    ? (status.available_models?.length || 0) + (status.specialized_models?.length || 0) : "—";
  const threshold = config?.confidence_threshold ?? status?.rule?.confidence_threshold;
  const visible = navItems.filter((item) => item.view !== "home" && hasPermission(auth.user, item.permission));
  const primary = primaryEntries.filter(({ item }) => hasPermission(auth.user, item.permission));
  const resources = resourceViews.flatMap((view) => visible.filter((item) => item.view === view));
  const groups = toolGroups.map((group) => ({ label: group.label, items: group.views.flatMap((view) => visible.filter((item) => item.view === view)) })).filter((group) => group.items.length);
  const grouped = new Set([...primaryEntries.map(({ item }) => item.view), ...resourceViews, ...toolGroups.flatMap((group) => group.views)]);
  const remaining = visible.filter((item) => !grouped.has(item.view));
  if (remaining.length) groups.push({ label: "其他", items: remaining });

  return <section className="view active overview-page">
    <header className="overview-head">
      <div><h2>总览</h2><p>选择工作方式，开始本次检验。</p></div>
      <button className="overview-refresh" type="button" disabled={busy} aria-busy={busy} onClick={() => void refresh()}>
        <RefreshCw size={20} aria-hidden="true" /><span>{busy ? "刷新中" : "刷新"}</span>
      </button>
    </header>
    {primary.length ? <section className={`overview-primary${primary.length === 1 ? " overview-primary-single" : ""}`} aria-label="开始检验">
      {primary.map(({ item, description, image }) => {
        const Icon = item.icon;
        return <Link className={`overview-launch${item.view === "textCompareBeta" ? " overview-launch-text" : ""}`} to={item.path} key={item.view}
          aria-labelledby={`overview-title-${item.view}`} aria-describedby={`overview-desc-${item.view}`}>
          <div className="overview-launch-copy"><Icon className="overview-feature-icon" size={48} aria-hidden="true" />
            <h3 id={`overview-title-${item.view}`}>{item.label}</h3>
            <p id={`overview-desc-${item.view}`}>{description}</p>
            <span className="overview-launch-cta">进入{item.label}<ArrowRight size={22} aria-hidden="true" /></span>
          </div>
          <div className="overview-launch-media"><img src={image} alt="" width="900" height="1000" decoding="async" /></div>
        </Link>;
      })}
    </section> : <p className="overview-no-primary">当前账号暂无检测入口权限，可从下方查看可用资源。</p>}
    <section className="overview-status" aria-label="检测服务与配置摘要" aria-busy={busy}>
      <div className="overview-status-item"><Server size={26} aria-hidden="true" /><div><span className="overview-status-label">检测服务</span>
        <strong className={`overview-service ${status?.service === "running" ? "is-running" : ""}`} title="仅表示检测服务状态">{service}</strong></div></div>
      <div className="overview-status-item"><BrainCircuit size={26} aria-hidden="true" /><div><span className="overview-status-label">当前模型</span><strong className="overview-model" title={model}>{model}</strong></div></div>
      <div className="overview-status-item"><Box size={26} aria-hidden="true" /><div><span className="overview-status-label">可用模型</span><strong>{pending ? "读取中" : models}</strong></div></div>
      <div className="overview-status-item"><SlidersHorizontal size={26} aria-hidden="true" /><div><span className="overview-status-label">置信阈值</span><strong>{typeof threshold === "number" && Number.isFinite(threshold) ? threshold : configQuery.isPending && pending ? "读取中" : "—"}</strong></div></div>
    </section>
    {statusQuery.isError || configQuery.isError ? <p className="overview-status-notice" role="status">
      {statusQuery.isError ? "检测服务状态暂不可用。" : ""}{configQuery.isError ? "配置摘要暂不可用。" : ""}可以继续进入工作区，或点击刷新重试。
    </p> : null}
    {resources.length || groups.length ? <section className="overview-resources" aria-labelledby="overview-resources-title">
      <h3 id="overview-resources-title">资源与管理</h3>
      <div className="overview-resource-row"><div className="overview-resource-links">
        {resources.map((item) => { const Icon = item.icon; return <Link to={item.path} key={item.view}><Icon size={24} aria-hidden="true" />{item.label}</Link>; })}
      </div>{groups.length ? <OverviewTools groups={groups} /> : null}</div>
    </section> : null}
  </section>;
}
