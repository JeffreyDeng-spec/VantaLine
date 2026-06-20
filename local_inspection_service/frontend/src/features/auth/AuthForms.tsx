import { FormEvent, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { apiClient } from "../../api/client";
import { queryKeys } from "../../api/queries";
import type { AuthMutationResponse } from "../../api/types";
import { useToast } from "../../components/ToastProvider";

type AuthMode = "login" | "setup";

export function AuthForms({ mode, initialError = "" }: { mode: AuthMode; initialError?: string }) {
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const [error, setError] = useState(initialError);

  const loginMutation = useMutation({
    mutationFn: (payload: { username: string; password: string }) =>
      apiClient.post<AuthMutationResponse>("/api/auth/login", payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.authStatus });
      notify({ title: "已登录", tone: "success" });
    },
    onError: (nextError: Error) => setError(nextError.message)
  });

  const setupMutation = useMutation({
    mutationFn: (payload: { username: string; display_name: string; password: string }) =>
      apiClient.post<AuthMutationResponse>("/api/auth/bootstrap", payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.authStatus });
      notify({ title: "管理员已创建", tone: "success" });
    },
    onError: (nextError: Error) => setError(nextError.message)
  });

  function handleLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    const form = new FormData(event.currentTarget);
    loginMutation.mutate({
      username: String(form.get("username") || "").trim(),
      password: String(form.get("password") || "")
    });
  }

  function handleSetup(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    const form = new FormData(event.currentTarget);
    setupMutation.mutate({
      username: String(form.get("username") || "").trim(),
      display_name: String(form.get("display_name") || "").trim(),
      password: String(form.get("password") || "")
    });
  }

  const pending = loginMutation.isPending || setupMutation.isPending;

  return (
    <main className="auth-shell">
      <section className="auth-panel" aria-live="polite">
        <div className="auth-brand">
          <div className="brand-mark" aria-hidden="true">
            <img src="/static/brand-logo.png?v=20260614-logo" alt="" width="36" height="36" decoding="async" />
          </div>
          <div>
            <h1>VantaLine</h1>
            <p>{mode === "setup" ? "创建首个管理员" : "登录视觉质检平台"}</p>
          </div>
        </div>

        {mode === "setup" ? (
          <form className="auth-form" onSubmit={handleSetup}>
            <label>
              管理员用户名
              <input name="username" type="text" autoComplete="username" required />
            </label>
            <label>
              显示名称
              <input name="display_name" type="text" autoComplete="name" />
            </label>
            <label>
              管理员密码
              <input name="password" type="password" autoComplete="new-password" minLength={8} required />
            </label>
            <button className="primary" type="submit" disabled={pending}>
              {pending ? <Loader2 className="spin" size={16} aria-hidden="true" /> : null}
              创建管理员
            </button>
          </form>
        ) : (
          <form className="auth-form" onSubmit={handleLogin}>
            <label>
              用户名
              <input name="username" type="text" autoComplete="username" required />
            </label>
            <label>
              密码
              <input name="password" type="password" autoComplete="current-password" required />
            </label>
            <button className="primary" type="submit" disabled={pending}>
              {pending ? <Loader2 className="spin" size={16} aria-hidden="true" /> : null}
              登录
            </button>
          </form>
        )}

        <p className="auth-error" role="alert">
          {error}
        </p>
      </section>
    </main>
  );
}
