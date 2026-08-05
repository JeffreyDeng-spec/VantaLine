import { Link } from "react-router-dom";
import type { NavItem } from "../../app/navigation";

const endpointGroups: Record<string, string[]> = {
  inspect: ["/api/status", "/api/analyze/image", "/api/analyze/video", "/api/stream/config"],
  aiInspect: ["/api/ai/config", "/api/ai/tasks", "/api/analyze/image", "/api/analyze/video"],
  accessories: [
    "/api/accessories",
    "/api/accessories/preview",
    "/api/accessories/confirm/{candidate_id}",
    "/api/accessories/{accessory_id}/files"
  ],
  dataAnalysis: ["/api/data-analysis/records", "/api/data-analysis/records/{record_id}"],
  pipeline: ["/api/pipeline/tasks", "/api/pipeline/accessories/{accessory_id}", "/api/pipeline/tasks/{task_id}/advance"],
  trainingLibrary: [
    "/api/training/resources",
    "/api/training/resources/datasets/{dataset_id}/detail",
    "/api/training/resources/models/{run_id}"
  ],
  rules: ["/api/config/summary", "/api/config/rules", "/api/training/background-sets", "/api/agent/config"]
};

export function PlaceholderPage({ item }: { item: NavItem }) {
  const Icon = item.icon;
  const endpoints = endpointGroups[item.view] || [];
  return (
    <section className="view active">
      <header className="page-head">
        <div>
          <h2>{item.label}</h2>
          <p className="page-desc">
            {item.phase === "phase-2" ? "低风险页面迁移队列" : "复杂工作流迁移队列"}，入口和权限守卫已接入。
          </p>
        </div>
        <span className="pill neutral">{item.phase.toUpperCase()}</span>
      </header>

      <section className="panel page-panel placeholder-panel">
        <Icon size={24} aria-hidden="true" />
        <div>
          <strong>Parity pending</strong>
          <p>此页面尚未接入主线工作流，将在后续收口阶段替换为真实功能。</p>
        </div>
      </section>

      <section className="panel page-panel">
        <div className="section-title">
          <h3>API 合同</h3>
        </div>
        <div className="endpoint-list">
          {endpoints.map((endpoint) => (
            <code key={endpoint}>{endpoint}</code>
          ))}
        </div>
      </section>

      <Link className="secondary inline-link" to="/">
        返回总览
      </Link>
    </section>
  );
}
