import { RefreshCw } from "lucide-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { getConfigSummary, getServiceStatus, queryKeys } from "../../api/queries";
import { ErrorState, LoadingState } from "../../components/LoadingState";
import { MetricCard } from "../../components/MetricCard";
import { useAuth } from "../auth/auth-context";

function asJson(value: unknown) {
  return JSON.stringify(value ?? {}, null, 2);
}

export function StatusOverview() {
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

  if (statusQuery.isLoading || configQuery.isLoading) return <LoadingState label="正在加载系统概况" />;
  if (statusQuery.isError) return <ErrorState error={statusQuery.error} action={<button onClick={refresh}>重试</button>} />;

  const status = statusQuery.data;
  const config = configQuery.data;
  const canViewDiagnostics = auth.user.role === "admin";

  return (
    <section className="view active">
      <header className="page-head">
        <div>
          <h2>系统概况</h2>
          <p className="page-desc">Phase 1 已接入 `/api/status` 与 `/api/config/summary`。</p>
        </div>
        <button className="secondary compact-action" type="button" onClick={refresh}>
          <RefreshCw size={16} aria-hidden="true" />
          刷新
        </button>
      </header>

      <section className="metric-grid">
        <MetricCard label="服务" value={status?.service || "-"} tone={status?.service === "running" ? "ok" : "warn"} />
        <MetricCard label="模型" value={status?.model_exists ? "已加载" : "缺失"} tone={status?.model_exists ? "ok" : "fail"} />
        <MetricCard label="类目" value={status?.classes?.length || 0} />
      </section>

      {canViewDiagnostics ? (
        <details className="panel page-panel developer-diagnostics">
          <summary>开发诊断</summary>
          <section className="status-grid">
            <article>
              <div className="section-title">
                <h3>服务响应</h3>
              </div>
              <pre className="json-panel">{asJson(status)}</pre>
            </article>
            <article>
              <div className="section-title">
                <h3>配置摘要</h3>
              </div>
              <pre className="json-panel">{asJson(config)}</pre>
            </article>
          </section>
        </details>
      ) : null}
    </section>
  );
}
