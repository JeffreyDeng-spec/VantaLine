import { useEffect, useRef, useState } from "react";
import { useIsMutating } from "@tanstack/react-query";
import { useBlocker } from "react-router-dom";
import { versionCoordinator } from "./runtime";
import { useVersionParticipant, useVersionState } from "./hooks";
import { hasEditorDrafts, installDraftTracking } from "./drafts";
import "./version.css";

export function VersionBoundary() {
  const state = useVersionState();
  const blocker = useBlocker(({ currentLocation, nextLocation }) => currentLocation.pathname !== nextLocation.pathname || currentLocation.search !== nextLocation.search);
  const handling = useRef(false);
  const [updated, setUpdated] = useState(false);
  const mutations = useIsMutating();
  useVersionParticipant({ dirty: hasEditorDrafts, busy: () => mutations > 0 });
  useEffect(installDraftTracking, []);
  useEffect(() => {
    try { if (sessionStorage.getItem("vantaline.version.updated")) { setUpdated(true); sessionStorage.removeItem("vantaline.version.updated"); } } catch { /* optional notice */ }
    const check = () => { if (!document.hidden) void versionCoordinator.check(true); };
    check();
    const timer = window.setInterval(check, 60_000);
    document.addEventListener("visibilitychange", check);
    window.addEventListener("online", check);
    return () => { window.clearInterval(timer); document.removeEventListener("visibilitychange", check); window.removeEventListener("online", check); };
  }, []);
  useEffect(() => {
    if (blocker.state !== "blocked" || handling.current) return;
    handling.current = true;
    const { pathname, search, hash } = blocker.location;
    void versionCoordinator.guard(new URL(pathname + search + hash, window.location.origin).href).then(allowed => {
      if (allowed) blocker.proceed(); else blocker.reset();
    }).finally(() => { handling.current = false; });
  }, [blocker]);
  if (!state.message && !updated) return null;
  return <aside className="version-notice" role="status" aria-live="polite">
    <span>{state.message || "页面已更新；如刚才启动了业务功能，请再次点击执行。"}</span>
    {state.stalled && !state.preparing ? <button type="button" onClick={() => { void versionCoordinator.guard(undefined, true); }}>重试更新</button> : null}
    {updated && !state.preparing ? <button type="button" aria-label="关闭版本提示" onClick={() => setUpdated(false)}>关闭</button> : null}
  </aside>;
}
