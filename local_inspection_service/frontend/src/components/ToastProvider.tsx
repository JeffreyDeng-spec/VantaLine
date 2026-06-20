import * as ToastPrimitive from "@radix-ui/react-toast";
import { createContext, useCallback, useContext, useMemo, useState } from "react";

type ToastTone = "info" | "success" | "error";

interface ToastPayload {
  title: string;
  description?: string;
  tone?: ToastTone;
}

interface ToastContextValue {
  notify: (payload: ToastPayload) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

export function AppToastProvider({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  const [payload, setPayload] = useState<ToastPayload>({ title: "" });

  const notify = useCallback((next: ToastPayload) => {
    setPayload(next);
    setOpen(false);
    window.setTimeout(() => setOpen(true), 20);
  }, []);

  const value = useMemo(() => ({ notify }), [notify]);

  return (
    <ToastContext.Provider value={value}>
      <ToastPrimitive.Provider swipeDirection="right" duration={3200}>
        {children}
        <ToastPrimitive.Root className={`toast-root ${payload.tone || "info"}`} open={open} onOpenChange={setOpen}>
          <ToastPrimitive.Title className="toast-title">{payload.title}</ToastPrimitive.Title>
          {payload.description ? (
            <ToastPrimitive.Description className="toast-description">
              {payload.description}
            </ToastPrimitive.Description>
          ) : null}
        </ToastPrimitive.Root>
        <ToastPrimitive.Viewport className="toast-viewport" />
      </ToastPrimitive.Provider>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const value = useContext(ToastContext);
  if (!value) throw new Error("useToast must be used inside AppToastProvider");
  return value;
}
