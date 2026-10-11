import { useEffect, useRef, type ReactNode } from "react";
import { X } from "lucide-react";

/** Shared process-data shell for legacy and real-photo adapters. */
export function TaskProcessDrawer({title, context, actions, close, children}: {
  title: string; context: string; actions?: ReactNode; close: () => void; children: ReactNode;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    ref.current?.querySelector<HTMLButtonElement>("button")?.focus();
    return () => previous?.focus();
  }, []);
  return <div ref={ref} className="modal-backdrop" role="dialog" aria-modal="true" aria-label={title} onKeyDown={e => {
    if (e.key === "Escape") close();
    if (e.key !== "Tab") return;
    const controls = Array.from(ref.current?.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), select:not(:disabled), summary, a[href]') || []).filter(el => el.getClientRects().length);
    const first = controls[0], last = controls[controls.length - 1];
    if (e.shiftKey && document.activeElement === first) {e.preventDefault();last?.focus();}
    else if (!e.shiftKey && document.activeElement === last) {e.preventDefault();first?.focus();}
  }}>
    <section className="modal-panel wide task-drawer-modal">
      <header className="modal-head">
        <div><span>{context}</span><h2>{title}</h2></div>
        <div className="modal-head-actions">{actions}<button className="icon-button" type="button" aria-label="关闭" onClick={close}><X size={18} aria-hidden="true"/></button></div>
      </header>
      <div className="modal-body task-drawer-modal-body">{children}</div>
    </section>
  </div>;
}
