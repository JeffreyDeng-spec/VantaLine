import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "../../api/client";
import { getAuthStatus, queryKeys } from "../../api/queries";
import { LoadingState, ErrorState } from "../../components/LoadingState";
import { useToast } from "../../components/ToastProvider";
import { useUiStore } from "../../store/uiStore";
import { AuthContext } from "./auth-context";
import { AuthForms } from "./AuthForms";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { loginPath, safeWorkspaceNext } from "../../app/paths";

import { AppShell } from "../../components/AppShell";
import { useLayoutEffect, useState } from "react";

export function AuthGate({ loginPage = false }: { loginPage?: boolean }) {
  const location = useLocation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const dataUserId = useUiStore((state) => state.dataUserId);
  const setDataUserId = useUiStore((state) => state.setDataUserId);
  const authQuery = useQuery({
    queryKey: queryKeys.authStatus,
    queryFn: getAuthStatus,
    retry: false,
    staleTime: 0,
    refetchOnMount: "always",
    refetchOnWindowFocus: true
  });

  // Data query keys predate account-scoped routing. Clear them before mounting
  // another identity, but never remove the workstation cookie or task preferences.
  const identity = authQuery.data?.authenticated ? authQuery.data.user?.id || "" : "";
  const [cacheIdentity, setCacheIdentity] = useState<string | null>(null);
  useLayoutEffect(() => {
    const privateQueries = { predicate: (query: { queryKey: readonly unknown[] }) => JSON.stringify(query.queryKey) !== JSON.stringify(queryKeys.authStatus) };
    void queryClient.cancelQueries(privateQueries);
    queryClient.removeQueries(privateQueries);
    setDataUserId("");
    setCacheIdentity(identity);
  }, [identity, queryClient, setDataUserId]);

  const logoutMutation = useMutation({
    mutationFn: () => apiClient.post<{ status: string }>("/api/auth/logout"),
    onSuccess: async () => {
      setDataUserId("");
      navigate("/login", { replace: true });
      queryClient.setQueryData(queryKeys.authStatus, { authenticated: false, setup_required: false });
      await queryClient.invalidateQueries({ queryKey: queryKeys.authStatus });
      notify({ title: "已退出登录" });
    },
    onError: () => notify({ title: "退出登录未完成，请重试", tone: "error" })
  });

  if (authQuery.isLoading || (!authQuery.isFetchedAfterMount && !authQuery.isError)) {
    return (
      <main className="auth-loading">
        <div className="brand-mark" aria-hidden="true">
          <img src="/static/brand-logo.png?v=20260614-logo" alt="" width="36" height="36" decoding="async" />
        </div>
        <LoadingState label="正在确认工作台访问权限" />
      </main>
    );
  }

  if (authQuery.isError) {
    return (
      <main className="auth-shell">
        <ErrorState error={authQuery.error} action={<button onClick={() => authQuery.refetch()}>重试</button>} />
      </main>
    );
  }

  const auth = authQuery.data;
  const destination = safeWorkspaceNext(new URLSearchParams(location.search).get("next"));
  if (!auth) return <ErrorState error={new Error("无法确认登录状态，请刷新重试")} />;
  if (!loginPage && (!auth.authenticated || !auth.user)) {
    return <Navigate to={loginPath(`${location.pathname}${location.search}${location.hash}`)} replace />;
  }
  if (auth.setup_required) return <AuthForms mode="setup" />;
  if (!auth.authenticated || !auth.user) {
    return <AuthForms mode="login" />;
  }
  if (loginPage) return <Navigate to={destination} replace />;
  if (cacheIdentity !== identity) return <LoadingState label="正在切换工作台" />;

  return (
    <AuthContext.Provider
      value={{
        user: auth.user,
        features: auth.features || {},
        defaultUserPermissions: auth.default_user_permissions || [],
        legacyOwnerId: auth.legacy_owner_id,
        dataUserId,
        setDataUserId,
        logout: async () => {
          await logoutMutation.mutateAsync().catch(() => undefined);
        }
      }}
    >
      <AppShell key={identity} />
    </AuthContext.Provider>
  );
}
