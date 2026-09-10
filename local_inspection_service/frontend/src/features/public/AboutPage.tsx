import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { apiClient } from "../../api/client";
import { LoadingState, ErrorState } from "../../components/LoadingState";
import "./navigation-pages.css";

interface VersionInfo { release: string; git_commit: string; built_at: string; consistent: boolean }

export function AboutPage() {
  const version = useQuery({ queryKey: ["release-version"], queryFn: () => apiClient.get<VersionInfo>("/api/version") });
  return <section className="view active about-page" aria-labelledby="about-title">
    <header className="page-head"><div><h2 id="about-title">关于与帮助</h2><p className="page-desc">VantaLine · 视觉质检工作台</p></div></header>
    <div className="about-resources">
      <Link className="about-resource" to="/" target="_blank" rel="noopener noreferrer"><strong>产品官网 ↗</strong><span>了解产品功能与工作流程（新标签页）</span></Link>
      <Link className="about-resource" to="/docs" target="_blank" rel="noopener noreferrer"><strong>使用文档 ↗</strong><span>操作指南、设备说明与常见问题（新标签页）</span></Link>
    </div>
    <section className="about-version" aria-labelledby="version-title"><h3 id="version-title">当前版本</h3>
      {version.isLoading ? <LoadingState label="正在读取版本" /> : version.isError ? <ErrorState error={version.error} action={<button onClick={() => version.refetch()}>重试</button>} /> : <dl>
        <dt>发布版本</dt><dd>{version.data?.release || "未知"}</dd>
        <dt>提交</dt><dd>{version.data?.git_commit || "未知"}</dd>
        <dt>构建时间</dt><dd>{version.data?.built_at || "未知"}</dd>
        <dt>版本校验</dt><dd>{version.data?.consistent ? "前后端版本一致" : "版本未验证，请联系管理员"}</dd>
      </dl>}
    </section>
    <section><h3>问题反馈</h3><p>请联系工作区管理员，提供版本号、记录编号、发生时间及错误提示。不要发送密码、API Key 或未经授权的客户图片。</p></section>
  </section>;
}
