import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { LogOut, ShieldCheck } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { navGroups, navItems } from "../app/navigation";
import { hasPermission } from "../app/permissions";
import { getServiceStatus, getUsers, queryKeys } from "../api/queries";
import { useAuth } from "../features/auth/auth-context";
import { Dashboard } from "../features/dashboard/Dashboard";
import { DetectionWorkbenchPage } from "../features/detection/DetectionWorkbenchPage";
import { LabelSheetPage } from "../features/label/LabelSheetPage";
import { LocateAnythingPage } from "../features/locate/LocateAnythingPage";
import { PlaceholderPage } from "../features/placeholder/PlaceholderPage";
import { TrainingPipelinePage } from "../features/pipeline/TrainingPipelinePage";
import { AccessoriesPage } from "../features/accessories/AccessoriesPage";
import { DataAnalysisPage } from "../features/data-analysis/DataAnalysisPage";
import { RulesPage } from "../features/rules/RulesPage";
import { TrainingLibraryPage } from "../features/training/TrainingLibraryPage";
import { UsersPage } from "../features/users/UsersPage";

function PermissionRoute({ permission, children }: { permission?: string; children: React.ReactNode }) {
  const auth = useAuth();
  if (!hasPermission(auth.user, permission)) {
    return (
      <section className="view active">
        <div className="empty-panel">
          <ShieldCheck size={22} aria-hidden="true" />
          <strong>没有权限访问此页面</strong>
        </div>
      </section>
    );
  }
  return <>{children}</>;
}

export function AppShell() {
  const auth = useAuth();
  const statusQuery = useQuery({
    queryKey: queryKeys.serviceStatus(auth.dataUserId),
    queryFn: () => getServiceStatus(auth),
    refetchInterval: 30_000
  });
  const usersQuery = useQuery({
    queryKey: queryKeys.users,
    queryFn: getUsers,
    enabled: auth.user.role === "admin"
  });

  const visibleNavGroups = navGroups
    .map((group) => ({
      ...group,
      items: group.items.filter((item) => hasPermission(auth.user, item.permission))
    }))
    .filter((group) => group.items.length > 0);

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-block">
          <div className="brand-mark" aria-hidden="true">
            <img src="/static/brand-logo.png?v=20260614-logo" alt="" width="36" height="36" decoding="async" />
          </div>
          <div className="brand-copy">
            <h1>VantaLine</h1>
            <p>React Preview</p>
          </div>
        </div>

        <div className="account-card">
          <div>
            <span>{auth.user.role === "admin" ? "Admin" : "普通用户"}</span>
            <strong>{auth.user.display_name || auth.user.username}</strong>
          </div>
          <button className="icon-button" type="button" title="退出登录" aria-label="退出登录" onClick={auth.logout}>
            <LogOut size={18} aria-hidden="true" />
          </button>
        </div>

        <nav className="side-nav" aria-label="主导航">
          {visibleNavGroups.map((group) => (
            <div className="nav-group" key={group.label || "root"}>
              {group.label ? <p className="nav-group-label">{group.label}</p> : null}
              {group.items.map((item) => {
                const Icon = item.icon;
                return (
                  <NavLink className="nav-item" key={item.path} to={item.path} end={item.path === "/"}>
                    <Icon size={18} aria-hidden="true" />
                    <span>{item.label}</span>
                  </NavLink>
                );
              })}
            </div>
          ))}
        </nav>

        <div className="system-card">
          <span>服务</span>
          <strong className={`pill ${statusQuery.data?.service === "running" ? "ok" : "neutral"}`}>
            {statusQuery.data?.service === "running" ? "运行中" : "检查中"}
          </strong>
          <span>模型</span>
          <strong className={`pill ${statusQuery.data?.model_exists ? "ok" : "neutral"}`}>
            {statusQuery.data?.model_exists ? "模型已加载" : "模型"}
          </strong>
        </div>
      </aside>

      <main className="workspace">
        {auth.user.role === "admin" ? (
          <div className="top-scope-bar">
            <label>
              数据范围
              <select value={auth.dataUserId} onChange={(event) => auth.setDataUserId(event.currentTarget.value)}>
                <option value="">全部用户与历史数据</option>
                <option value="legacy_admin">历史数据</option>
                {(usersQuery.data?.users || []).map((user) => (
                  <option value={user.id} key={user.id}>
                    {user.display_name || user.username}
                  </option>
                ))}
              </select>
            </label>
          </div>
        ) : null}

        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/status" element={<Navigate to="/" replace />} />
          <Route
            path="/inspect"
            element={
              <PermissionRoute permission="inspection">
                <DetectionWorkbenchPage mode="inspect" />
              </PermissionRoute>
            }
          />
          <Route
            path="/ai-inspect"
            element={
              <PermissionRoute permission="ai_detection">
                <DetectionWorkbenchPage mode="ai" />
              </PermissionRoute>
            }
          />
          <Route
            path="/label-sheet"
            element={
              <PermissionRoute permission="label_sheet">
                <LabelSheetPage />
              </PermissionRoute>
            }
          />
          <Route
            path="/locate-anything"
            element={
              <PermissionRoute permission="locate_anything">
                <LocateAnythingPage />
              </PermissionRoute>
            }
          />
          <Route
            path="/accessories"
            element={
              <PermissionRoute permission="accessory_library">
                <AccessoriesPage />
              </PermissionRoute>
            }
          />
          <Route
            path="/data-analysis"
            element={
              <PermissionRoute permission="ai_detection">
                <DataAnalysisPage />
              </PermissionRoute>
            }
          />
          <Route
            path="/training-library"
            element={
              <PermissionRoute permission="model_library">
                <TrainingLibraryPage />
              </PermissionRoute>
            }
          />
          <Route
            path="/pipeline"
            element={
              <PermissionRoute permission="training_pipeline">
                <TrainingPipelinePage />
              </PermissionRoute>
            }
          />
          <Route
            path="/rules"
            element={
              <PermissionRoute permission="system_settings">
                <RulesPage />
              </PermissionRoute>
            }
          />
          <Route
            path="/users"
            element={
              <PermissionRoute permission="user_management">
                <UsersPage />
              </PermissionRoute>
            }
          />
          {navItems
            .filter((item) => !["home", "inspect", "aiInspect", "labelSheet", "locateAnything", "accessories", "dataAnalysis", "trainingLibrary", "pipeline", "rules", "userManagement"].includes(item.view))
            .map((item) => (
              <Route
                key={item.path}
                path={item.path}
                element={
                  <PermissionRoute permission={item.permission}>
                    <PlaceholderPage item={item} />
                  </PermissionRoute>
                }
              />
            ))}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}
