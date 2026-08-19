import { Link } from "react-router-dom";
import { RefreshCw } from "lucide-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { navItems } from "../../app/navigation";
import { hasPermission } from "../../app/permissions";
import { getConfigSummary, getServiceStatus, queryKeys } from "../../api/queries";
import { ErrorState, LoadingState } from "../../components/LoadingState";
import { MetricCard } from "../../components/MetricCard";
import { useAuth } from "../auth/auth-context";

function countModels(status?: { available_models?: unknown[]; specialized_models?: unknown[] }) {
  return (status?.available_models?.length || 0) + (status?.specialized_models?.length || 0);
}

export function Dashboard() {
  const auth = useAuth();
  const queryClient = useQueryClient();
  const statusQuery = useQuery({
    queryKey: queryKeys.serviceStatus(auth.dataUserId),
    queryFn: () => getServiceStatus(auth)
  });
  const configQuery = useQuery({
    queryKey: queryKeys.configSummary(auth.dataUserId),
    queryFn: () => getConfigSummary(auth)
  });

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: queryKeys.serviceStatus(auth.dataUserId) });
    queryClient.invalidateQueries({ queryKey: queryKeys.configSummary(auth.dataUserId) });
  };

  if (statusQuery.isLoading || configQuery.isLoading) return <LoadingState label="正在加载总览" />;
  if (statusQuery.isError) return <ErrorState error={statusQuery.error} action={<button onClick={refresh}>重试</button>} />;

  const status = statusQuery.data;
  const config = configQuery.data;
  const cards = navItems.filter((item) => item.path !== "/" && hasPermission(auth.user, item.permission));

  return (
    <section className="view active">
      <header className="page-head">
        <div>
          <h2>总览</h2>
          <p className="page-desc">React/Vite 已作为生产入口，根路径由 production bundle 提供。</p>
        </div>
        <button className="secondary compact-action" type="button" onClick={refresh}>
          <RefreshCw size={16} aria-hidden="true" />
          刷新
        </button>
      </header>

      <section className="metric-grid four">
        <MetricCard
          label="检测服务"
          value={status?.service === "running" ? "运行中" : status?.service || "未知"}
          tone={status?.service === "running" ? "ok" : "warn"}
        />
        <MetricCard
          label="检测模型"
          value={status?.model_exists ? "模型已加载" : "模型缺失"}
          tone={status?.model_exists ? "ok" : "fail"}
          detail={status?.active_model_id || "-"}
        />
        <MetricCard label="可用模型" value={countModels(status)} detail="基础模型与专用模型" />
        <MetricCard
          label="置信阈值"
          value={config?.confidence_threshold ?? status?.rule?.confidence_threshold ?? "-"}
          detail="当前规则摘要"
        />
      </section>

      <section className="panel page-panel">
        <div className="section-title">
          <h3>迁移入口</h3>
          <span className="pill neutral">Phase 1</span>
        </div>
        <div className="route-grid">
          {cards.map((item) => {
            const Icon = item.icon;
            return (
              <Link className="route-card" to={item.path} key={item.path}>
                <Icon size={20} aria-hidden="true" />
                <div>
                  <strong>{item.label}</strong>
                  <span>{item.phase === "phase-1" ? "已接入" : item.phase === "phase-2" ? "低风险页" : "复杂工作流"}</span>
                </div>
              </Link>
            );
          })}
        </div>
      </section>
    </section>
  );
}
