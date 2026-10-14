import { useEffect, useRef, useState, type PointerEvent } from "react";

export type ZoomImage = { preview: string; full: string };
type View = { scale: number; x: number; y: number };
const fittedView: View = { scale: 1, x: 0, y: 0 };

export function ImageZoom({ image, onClose }: { image: ZoomImage; onClose: () => void }) {
  const [loaded, setLoaded] = useState(image.preview === image.full);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [natural, setNatural] = useState({ width: 1, height: 1 });
  const [space, setSpace] = useState({ width: 1, height: 1 });
  const [view, setView] = useState<View>(fittedView);
  const [dragging, setDragging] = useState(false);
  const stage = useRef<HTMLDivElement>(null);
  const dialog = useRef<HTMLDivElement>(null);
  const closeButton = useRef<HTMLButtonElement>(null);
  const opener = useRef(document.activeElement as HTMLElement | null);
  const fullLoaded = useRef(image.preview === image.full);
  const suppressClick = useRef(false);
  const gesture = useRef<{ id: number; x: number; y: number; origin: View; moved: boolean } | null>(null);
  const fit = Math.min(space.width / natural.width, space.height / natural.height);
  const size = { width: natural.width * fit, height: natural.height * fit };
  const geometry = useRef({ space, size });
  geometry.current = { space, size };
  const currentView = useRef(view);
  currentView.current = view;

  function bounded(next: View): View {
    const { space, size } = geometry.current;
    const maxX = Math.max(0, (size.width * next.scale - space.width) / 2);
    const maxY = Math.max(0, (size.height * next.scale - space.height) / 2);
    return { scale: next.scale, x: Math.max(-maxX, Math.min(maxX, next.x)), y: Math.max(-maxY, Math.min(maxY, next.y)) };
  }
  function update(next: View) {
    const limited = bounded(next);
    currentView.current = limited;
    setView(limited);
  }
  useEffect(() => {
    const element = stage.current;
    if (!element) return;
    const resize = new ResizeObserver(([entry]) => {
      setSpace({ width: entry.contentRect.width, height: entry.contentRect.height });
      // A viewport resize starts from a complete fitted image.
      currentView.current = fittedView;
      setView(fittedView);
    });
    resize.observe(element);
    closeButton.current?.focus({ preventScroll: true });
    const wheel = (event: WheelEvent) => {
      event.preventDefault();
      const rect = element.getBoundingClientRect();
      const delta = event.deltaY * (event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? rect.height : 1);
      const before = currentView.current;
      const scale = Math.max(1, Math.min(8, before.scale * Math.exp(-delta * 0.002)));
      const x = event.clientX - rect.left - rect.width / 2;
      const y = event.clientY - rect.top - rect.height / 2;
      update({ scale, x: x - (x - before.x) * scale / before.scale, y: y - (y - before.y) * scale / before.scale });
    };
    element.addEventListener("wheel", wheel, { passive: false });
    return () => {
      resize.disconnect();
      element.removeEventListener("wheel", wheel);
      const source = opener.current;
      if (source?.isConnected) source.focus({ preventScroll: true });
    };
  }, []);
  // A higher-resolution copy retains the same view; only legal pan bounds change.
  useEffect(() => { update(currentView.current); }, [natural.width, natural.height]);

  function release(event: PointerEvent<HTMLDivElement>) {
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
    gesture.current = null;
    setDragging(false);
  }
  function close() {
    onClose();
  }
  return (
    <div
      ref={dialog}
      className="li-modal li-photo-viewer"
      role="dialog"
      aria-modal="true"
      aria-label="图片放大"
      onClick={(event) => {
        event.stopPropagation();
        event.preventDefault();
        if (event.button !== 0) return;
        if (suppressClick.current) { suppressClick.current = false; return; }
        close();
      }}
      onKeyDown={(event) => {
        if (event.key === "Escape") { event.stopPropagation(); close(); }
        if (event.key === "0" && !event.ctrlKey && !event.metaKey && !event.altKey) {
          event.preventDefault(); update(fittedView);
        }
        if (event.key === "Tab") {
          const controls = [...(dialog.current?.querySelectorAll<HTMLElement>('button:not(:disabled), [tabindex="0"]') || [])];
          const first = controls[0], last = controls[controls.length - 1];
          if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
          else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
        }
      }}
    >
      <div className="li-zoom-toolbar">
        <span>滚轮缩放 · 拖动查看 · 单击关闭 · 0 还原</span>
        <button ref={closeButton} autoFocus onClick={(event) => { event.stopPropagation(); close(); }}>关闭放大</button>
      </div>
      <div
        ref={stage}
        className="li-zoom-images"
        tabIndex={0}
        data-scale={view.scale}
        style={{ cursor: view.scale > 1 ? dragging ? "grabbing" : "grab" : "zoom-out" }}
        onPointerDown={(event) => {
          if (event.button !== 0) return;
          event.currentTarget.focus({ preventScroll: true });
          suppressClick.current = false;
          gesture.current = { id: event.pointerId, x: event.clientX, y: event.clientY, origin: currentView.current, moved: false };
          event.currentTarget.setPointerCapture(event.pointerId);
        }}
        onPointerMove={(event) => {
          const drag = gesture.current;
          if (!drag || drag.id !== event.pointerId) return;
          const x = event.clientX - drag.x, y = event.clientY - drag.y;
          if (Math.hypot(x, y) > 6) drag.moved = true;
          if (drag.moved && drag.origin.scale > 1) {
            setDragging(true);
            update({ scale: drag.origin.scale, x: drag.origin.x + x, y: drag.origin.y + y });
          }
        }}
        onPointerUp={(event) => {
          if (gesture.current?.id !== event.pointerId) return;
          suppressClick.current = gesture.current.moved;
          release(event);
        }}
        onPointerCancel={(event) => { suppressClick.current = false; release(event); }}
      >
        <div className="li-zoom-photo" style={{ width: size.width, height: size.height, marginLeft: -size.width / 2, marginTop: -size.height / 2, transform: `translate(${view.x}px, ${view.y}px) scale(${view.scale})` }}>
          <img
            src={image.preview}
            alt="图片预览"
            draggable={false}
            style={{ visibility: loaded && image.preview !== image.full ? "hidden" : "visible" }}
            onLoad={(event) => {
              if (image.preview === image.full || !fullLoaded.current)
                setNatural({ width: event.currentTarget.naturalWidth, height: event.currentTarget.naturalHeight });
            }}
          />
          {image.preview !== image.full && (
            <img
              key={attempt}
              src={image.full}
              alt="原尺寸图片"
              draggable={false}
              style={{ visibility: loaded ? "visible" : "hidden" }}
              onLoad={(event) => {
                fullLoaded.current = true;
                setNatural({ width: event.currentTarget.naturalWidth, height: event.currentTarget.naturalHeight });
                setLoaded(true); setFailed(false);
              }}
              onError={() => setFailed(true)}
            />
          )}
        </div>
      </div>
      {!loaded && (
        <div className="li-zoom-status">
          {failed ? <>
            <span>高清图加载失败，当前显示预览图。</span>
            <button onClick={(event) => { event.stopPropagation(); setFailed(false); setAttempt(value => value + 1); }}>重试高清图</button>
          </> : <span role="status">正在加载高清图…</span>}
        </div>
      )}
    </div>
  );
}
