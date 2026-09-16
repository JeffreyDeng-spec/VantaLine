import { Navigate, useSearchParams } from "react-router-dom";
export function LegacyManualRedirect() {
  const [params] = useSearchParams();
  const id = params.get("page_id") || params.get("session_id") || params.get("session") || params.get("standard_id") || params.get("standard") || params.get("record") || params.get("inspection_id");
  return <Navigate replace to={`/workspace/label-inspection${id ? `?task=${encodeURIComponent("legacy-manual:"+id)}` : ""}`} />;
}
