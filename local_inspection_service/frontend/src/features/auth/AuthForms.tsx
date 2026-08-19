import { FormEvent, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { Link } from "react-router-dom";
import { apiClient } from "../../api/client";
import { queryKeys } from "../../api/queries";
import type { AuthMutationResponse } from "../../api/types";
import { useToast } from "../../components/ToastProvider";
import "../public/vantaline-public.css";

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

  if (mode === "login") {
    return (
      <div className="vl-source-page">
        <main className="login-page">
          <header className="login-header">
            <Link className="brand" to="/" aria-label="VantaLine home">
              <span className="brand-mark" aria-hidden="true">
                <i />
                <i />
                <i />
              </span>
              <span>VantaLine</span>
            </Link>
            <Link to="/">← Back to overview</Link>
          </header>

          <section className="login-shell" aria-labelledby="login-title">
            <div className="login-context">
              <p className="eyebrow">VANTALINE WORKSPACE</p>
              <h1>Continue the work behind every result.</h1>
              <p>
                Review inspections, prepare datasets, follow training runs, and manage deployed models from one
                production workspace.
              </p>
              <div className="login-proof">
                <span>01</span>
                <p>
                  <strong>Inspection evidence</strong>
                  <small>Review annotated results in context.</small>
                </p>
              </div>
              <div className="login-proof">
                <span>02</span>
                <p>
                  <strong>Model improvement</strong>
                  <small>Grow datasets from real production decisions.</small>
                </p>
              </div>
              <div className="login-proof">
                <span>03</span>
                <p>
                  <strong>Operational traceability</strong>
                  <small>Keep ownership and history attached.</small>
                </p>
              </div>
            </div>

            <div className="login-card" aria-live="polite">
              <div className="login-card-heading">
                <p className="eyebrow">SECURE WORKSPACE ACCESS</p>
                <h2 id="login-title">Log in to VantaLine</h2>
                <p>Use the credentials provided by your workspace administrator.</p>
              </div>
              <form onSubmit={handleLogin}>
                <label htmlFor="username">Workspace username</label>
                <input
                  id="username"
                  name="username"
                  type="text"
                  autoComplete="username"
                  placeholder="Enter your username"
                  required
                />
                <div className="password-label">
                  <label htmlFor="password">Password</label>
                  <a href="mailto:support@vantaline.ai?subject=VantaLine%20access%20help">Need help?</a>
                </div>
                <input
                  id="password"
                  name="password"
                  type="password"
                  autoComplete="current-password"
                  placeholder="Enter your password"
                  required
                />
                <button className="button button-primary login-submit" type="submit" disabled={pending}>
                  {pending ? "Signing in…" : "Continue to workspace"} <span aria-hidden="true">→</span>
                </button>
              </form>
              {error ? (
                <p className="login-error" role="alert">
                  {error}
                </p>
              ) : null}
              <p className="access-note">
                <i /> Access is managed by your organization.
              </p>
            </div>
          </section>

          <footer className="login-footer">
            <span>© 2026 VantaLine</span>
            <span>AI-assisted inspection with human review</span>
          </footer>
        </main>
      </div>
    );
  }

  return (
    <main className="auth-shell">
      <section className="auth-panel" aria-live="polite">
        <div className="auth-brand">
          <div className="brand-mark" aria-hidden="true">
            <img src="/static/brand-logo.png?v=20260614-logo" alt="" width="36" height="36" decoding="async" />
          </div>
          <div>
            <h1>VantaLine</h1>
            <p>{mode === "setup" ? "Create the first administrator" : "Log in to the quality workspace"}</p>
          </div>
        </div>

        <form className="auth-form" onSubmit={handleSetup}>
          <label>
            Administrator username
            <input name="username" type="text" autoComplete="username" required />
          </label>
          <label>
            Display name
            <input name="display_name" type="text" autoComplete="name" />
          </label>
          <label>
            Administrator password
            <input name="password" type="password" autoComplete="new-password" minLength={8} required />
          </label>
          <button className="primary" type="submit" disabled={pending}>
            {pending ? <Loader2 className="spin" size={16} aria-hidden="true" /> : null}
            Create administrator
          </button>
        </form>

        <p className="auth-error" role="alert">
          {error}
        </p>
      </section>
    </main>
  );
}
