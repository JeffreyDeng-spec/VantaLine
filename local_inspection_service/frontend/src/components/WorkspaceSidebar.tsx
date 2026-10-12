import { type ReactNode, useEffect, useRef, useState } from "react";
import { Menu, Pin, X } from "lucide-react";
import { useLocation } from "react-router-dom";
import "./workspaceSidebar.css";

const DRAWER_QUERY = "(max-width: 900px), (hover: none)";
function storedPin(key: string) {
  try { return sessionStorage.getItem(key) === "true"; } catch { return false; }
}

export function WorkspaceSidebar({ children, userId, exempt = false }: { children: ReactNode; userId: string; exempt?: boolean }) {
  const location = useLocation();
  const storageKey = `vantaline.sidebar.pin.${userId}`;
  const [pinned, setPinned] = useState(() => storedPin(storageKey));
  const [hovered, setHovered] = useState(false);
  const [focused, setFocused] = useState(false);
  const [mobile, setMobile] = useState(() => matchMedia(DRAWER_QUERY).matches);
  const [drawer, setDrawer] = useState(false);
  const sidebarRef = useRef<HTMLElement>(null);
  const toggleRef = useRef<HTMLButtonElement>(null);
  const enterTimer = useRef<ReturnType<typeof setTimeout>>();
  const leaveTimer = useRef<ReturnType<typeof setTimeout>>();
  const keyboard = useRef(false);
  const open = !exempt && (mobile ? drawer : pinned || hovered || focused);
  useEffect(() => { setPinned(storedPin(storageKey)); }, [storageKey]);
  useEffect(() => {
    const media = matchMedia(DRAWER_QUERY);
    const change = () => { setMobile(media.matches); setDrawer(false); setHovered(false); };
    media.addEventListener("change", change);
    return () => media.removeEventListener("change", change);
  }, []);
  useEffect(() => {
    setDrawer(false);
    if (mobile && drawer && !exempt) toggleRef.current?.focus();
  }, [location.pathname, location.search, exempt]);
  useEffect(() => { if (sidebarRef.current) sidebarRef.current.inert = !exempt && mobile && !drawer; }, [exempt, mobile, drawer]);
  useEffect(() => () => { clearTimeout(enterTimer.current); clearTimeout(leaveTimer.current); }, []);
  useEffect(() => {
    const pointer = (event: PointerEvent) => {
      keyboard.current = false;
      setFocused(false);
      if (mobile && drawer && !sidebarRef.current?.contains(event.target as Node) && !toggleRef.current?.contains(event.target as Node)) setDrawer(false);
    };
    const keydown = (event: KeyboardEvent) => {
      if (event.key === "Tab") { keyboard.current = true; if (sidebarRef.current?.contains(document.activeElement)) setFocused(true); }
      if (mobile && drawer && event.key === "Escape") { event.preventDefault(); setDrawer(false); toggleRef.current?.focus(); }
    };
    document.addEventListener("pointerdown", pointer);
    document.addEventListener("keydown", keydown);
    return () => { document.removeEventListener("pointerdown", pointer); document.removeEventListener("keydown", keydown); };
  }, [mobile, drawer]);
  function closeDrawer() { setDrawer(false); toggleRef.current?.focus(); }
  return <>
    {!exempt && <button ref={toggleRef} className="workspace-navigation-toggle" type="button" aria-label="打开导航" aria-controls="workspace-sidebar" aria-expanded={drawer} onClick={() => setDrawer(value => !value)}><Menu size={17} /><span>VantaLine</span></button>}
    <aside id="workspace-sidebar" ref={sidebarRef} className={`sidebar workspace-sidebar ${exempt ? "sidebar-exempt" : ""} ${open ? "sidebar-open" : ""} ${mobile && drawer ? "sidebar-drawer" : ""}`} aria-label="工作台导航" aria-hidden={!exempt && mobile && !drawer ? true : undefined}
      onPointerEnter={event => { if (exempt || mobile || event.pointerType === "touch") return; clearTimeout(leaveTimer.current); clearTimeout(enterTimer.current); enterTimer.current = setTimeout(() => setHovered(true), 120); }}
      onPointerLeave={() => { clearTimeout(enterTimer.current); clearTimeout(leaveTimer.current); leaveTimer.current = setTimeout(() => setHovered(false), 250); }}
      onFocusCapture={event => { if (keyboard.current || event.target.matches(":focus-visible")) setFocused(true); }}
      onBlurCapture={event => { if (!event.currentTarget.contains(event.relatedTarget as Node)) setFocused(false); }}>
      {children}
      {!exempt && <>
        <button className="workspace-sidebar-pin" type="button" title={pinned ? "取消固定" : "固定展开"} aria-label={pinned ? "取消固定侧栏" : "固定展开侧栏"} aria-pressed={pinned} onClick={() => { const next = !pinned; setPinned(next); try { sessionStorage.setItem(storageKey, String(next)); } catch { /* Pin remains usable when session storage is unavailable. */ } }}><Pin size={16} /></button>
        <button className="workspace-sidebar-close" type="button" aria-label="关闭导航" onClick={closeDrawer}><X size={18} /></button>
      </>}
    </aside>
  </>;
}
