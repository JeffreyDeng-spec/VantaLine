import { useEffect } from "react";
import { Link, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { AuthGate } from "../features/auth/AuthGate";
import { PublicLandingPage } from "../features/public/PublicLandingPage";
import { DocumentationPage } from "../features/public/DocumentationPage";
import { isWorkspacePage, legacyWorkspaceDestination, WORKSPACE_PATH } from "./paths";
import { navItems } from "./navigation";

export function NotFoundPage() {
  return <section className="navigation-not-found" aria-labelledby="not-found-title">
    <p>404</p><h1 id="not-found-title">页面不存在</h1>
    <p>链接可能已失效，请从工作台或产品介绍继续。</p>
    <Link to={WORKSPACE_PATH}>进入工作台</Link><Link to="/">产品介绍</Link>
  </section>;
}

function LegacyRoute() {
  const location = useLocation();
  const destination = legacyWorkspaceDestination(location.pathname);
  return destination ? <Navigate to={`${destination}${location.search}${location.hash}`} replace /> : <NotFoundPage />;
}

function WorkspaceRoute() {
  const { pathname } = useLocation();
  return isWorkspacePage(pathname) ? <AuthGate /> : <NotFoundPage />;
}

function PageTitle() {
  const location = useLocation();
  const pathname = location.pathname.replace(/\/+$/, "") || "/";
  useEffect(() => {
    const item = navItems.find((item) => item.path.split("?")[0] === pathname);
    const title = pathname === "/" ? "AI 视觉质检" : pathname === "/docs" ? "使用文档"
      : pathname === "/login" ? "登录工作台" : item?.label
        || (pathname.includes("/tasks/") ? "任务" : "页面不存在");
    document.title = `${title} · VantaLine`;
  }, [pathname]);
  return null;
}

export function SiteRoutes() {
  return <><PageTitle /><Routes>
    <Route path="/" element={<PublicLandingPage />} />
    <Route path="/docs" element={<DocumentationPage />} />
    <Route path="/login" element={<AuthGate loginPage />} />
    <Route path="/workspace/*" element={<WorkspaceRoute />} />
    <Route path="*" element={<LegacyRoute />} />
  </Routes></>;
}
