import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import type { NavItem } from "../../app/navigation";

export function OverviewTools({ groups }: { groups: { label: string; items: NavItem[] }[] }) {
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState({ top: 0, left: 0 });
  const trigger = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);

  useLayoutEffect(() => {
    if (!open) return;
    const place = () => {
      if (!trigger.current || !panel.current) return;
      const rect = trigger.current.getBoundingClientRect();
      const { width, height } = panel.current.getBoundingClientRect();
      setPosition({
        left: Math.max(16, Math.min(rect.right - width, window.innerWidth - width - 16)),
        top: Math.max(16, rect.top - height - 8 >= 16 ? rect.top - height - 8 : Math.min(rect.bottom + 8, window.innerHeight - height - 16))
      });
    };
    place();
    panel.current?.querySelector("a")?.focus();
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);
    return () => {
      window.removeEventListener("resize", place);
      window.removeEventListener("scroll", place, true);
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const outside = (event: Event) => {
      if (event.target instanceof Node && !panel.current?.contains(event.target) && !trigger.current?.contains(event.target)) setOpen(false);
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.preventDefault(); setOpen(false); trigger.current?.focus();
    };
    document.addEventListener("pointerdown", outside);
    document.addEventListener("focusin", outside);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("focusin", outside);
      document.removeEventListener("keydown", escape);
    };
  }, [open]);

  return <>
    <button className="overview-more" type="button" ref={trigger} aria-expanded={open} aria-controls={open ? "overview-tools" : undefined}
      onClick={() => setOpen(!open)} onKeyDown={(event) => {
        if (event.key === "ArrowDown") { event.preventDefault(); setOpen(true); }
      }}>更多工具 <ArrowRight size={20} aria-hidden="true" /></button>
    {open ? createPortal(<div id="overview-tools" className="overview-tools-panel" ref={panel} style={position} onKeyDown={(event) => {
      if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
      event.preventDefault();
      const links = Array.from(panel.current?.querySelectorAll("a") || []);
      const index = links.indexOf(document.activeElement as HTMLAnchorElement);
      const next = event.key === "Home" ? 0 : event.key === "End" ? links.length - 1 : (index + (event.key === "ArrowDown" ? 1 : -1) + links.length) % links.length;
      links[next]?.focus();
    }}>
      <nav aria-label="更多工具">
        {groups.map((group) => <div className="overview-tool-group" key={group.label}>
          <h4>{group.label}</h4>
          {group.items.map((item) => { const Icon = item.icon; return <Link key={item.view} to={item.path} onClick={() => setOpen(false)}><Icon size={19} aria-hidden="true" />{item.label}</Link>; })}
        </div>)}
      </nav>
    </div>, document.body) : null}
  </>;
}
