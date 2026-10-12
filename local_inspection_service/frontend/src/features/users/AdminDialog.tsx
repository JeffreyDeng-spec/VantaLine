import { ReactNode, useEffect, useRef, useState } from "react";

export function AdminDialog({
  title,
  children,
  onClose,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const el = ref.current;
    el?.showModal();
    return () => {
      el?.close();
    };
  }, []);
  return (
    <dialog
      ref={ref}
      className="admin-dialog"
      aria-label={title}
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
    >
      <header>
        <h3>{title}</h3>
        <button type="button" onClick={onClose} aria-label="关闭">
          ×
        </button>
      </header>
      {children}
    </dialog>
  );
}
export type AdminConfirmation = {
  title: string;
  impact: string;
  operation: (reason: string) => Promise<unknown>;
  username?: string;
};
export function AdminConfirm({
  value,
  onClose,
  onDone,
}: {
  value: AdminConfirmation;
  onClose: () => void;
  onDone?: () => void;
}) {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <AdminDialog
      title={value.title}
      onClose={() => {
        if (!busy) onClose();
      }}
    >
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          const f = new FormData(e.currentTarget);
          const reason = String(f.get("reason") || "").trim();
          if (!reason) { setError("请填写操作原因"); return; }
          setBusy(true);
          setError("");
          try {
            await value.operation(reason);
            onDone?.();
            onClose();
          } catch (err) {
            setError(
              err instanceof Error ? err.message : "操作失败，请核查状态",
            );
          } finally {
            setBusy(false);
          }
        }}
      >
        <div className="admin-dialog-body">
          <p className="admin-impact">{value.impact}</p>
          {value.username && (
            <label className="field">
              输入用户名确认删除
              <input
                required
                name="username"
                autoComplete="off"
                onChange={(e) =>
                  e.target.setCustomValidity(
                    e.target.value === value.username ? "" : "用户名不匹配",
                  )
                }
              />
            </label>
          )}
          <label className="field">
            操作原因
            <textarea
              name="reason"
              required
              maxLength={300}
              placeholder="说明此次管理操作的原因"
            />
          </label>
          {error && (
            <p role="alert" className="admin-error">
              {error}
            </p>
          )}
        </div>
        <footer>
          <button type="button" disabled={busy} onClick={onClose}>
            取消
          </button>
          <button className="primary" disabled={busy} type="submit">
            {busy ? "正在提交…" : "确认操作"}
          </button>
        </footer>
      </form>
    </AdminDialog>
  );
}
