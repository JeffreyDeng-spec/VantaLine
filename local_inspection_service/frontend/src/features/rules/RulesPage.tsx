import { lazy, Suspense } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../auth/auth-context";
import { workspacePath } from "../../app/paths";
import { LocalPlcControls } from "../plc/LocalPlcControls";
import { LoadingState } from "../../components/LoadingState";

const AdminSettings = lazy(() => import("./AdminSettings"));
export function RulesPage() {
  const { user } = useAuth();
  if (user.role === "admin") return <Suspense fallback={<LoadingState />}><AdminSettings /></Suspense>;
  return <section className="view active"><header className="page-head"><h2>个人与设备</h2></header>
    <section className="panel page-panel"><h3>本机设备</h3><p>相机与生产检测在检测工作页进行。</p>
    {(user.permissions?.includes("inspection") || user.permissions?.includes("ai_detection")) && <LocalPlcControls />}
    <Link to={workspacePath("/inspect")}>打开检测中心</Link></section></section>;
}
