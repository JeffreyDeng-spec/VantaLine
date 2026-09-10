import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "../../api/client";
import { getAuthStatus, queryKeys } from "../../api/queries";
import type { AuthStatusResponse } from "../../api/types";
import { LoadingState, ErrorState } from "../../components/LoadingState";
import { useToast } from "../../components/ToastProvider";
import { useUiStore } from "../../store/uiStore";
import { AppShell } from "../../components/AppShell";
import { AuthContext } from "./auth-context";
import { AuthForms } from "./AuthForms";
import { Route, Routes } from "react-router-dom";
import { PublicLandingPage } from "../public/PublicLandingPage";
import { AgentToolsProvider } from "../agent/AgentToolsProvider";
import { actionRegistry } from "../agent/registry";
import { clearFiles } from "../agent/files";

export function AuthGate() {
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const dataUserId = useUiStore((state) => state.dataUserId);
  const setDataUserId = useUiStore((state) => state.setDataUserId);
  const authQuery = useQuery({
    queryKey: queryKeys.authStatus,
    queryFn: getAuthStatus,
    retry: false
  });

  const logoutMutation = useMutation({
    mutationFn: () => apiClient.post<{ status: string }>("/api/auth/logout"),
    onSuccess: async () => {
      actionRegistry.reset();
      clearFiles();
      setDataUserId("");
      await queryClient.cancelQueries();
      queryClient.removeQueries({predicate:query=>JSON.stringify(query.queryKey)!==JSON.stringify(queryKeys.authStatus)});
      // Preserve the observed auth query: clearing it would leave its observer
      // attached to an orphaned authenticated snapshot with nothing to refetch.
      queryClient.setQueryData<AuthStatusResponse>(queryKeys.authStatus,{authenticated:false,setup_required:false,user:null,features:{},default_user_permissions:[],legacy_owner_id:""});
      notify({ title: "已退出登录" });
    },
    onError: () => notify({title:"退出登录未得到确认",description:"请检查连接后重试。",tone:"error"})
  });

  if (authQuery.isLoading) {
    return (
      <main className="auth-loading">
        <div className="brand-mark" aria-hidden="true">
          <img src="/static/brand-logo.png?v=20260614-logo" alt="" width="36" height="36" decoding="async" />
        </div>
        <LoadingState label="Checking workspace access" />
      </main>
    );
  }

  if (authQuery.isError) {
    return (
      <main className="auth-shell">
        <ErrorState error={authQuery.error} action={<button onClick={() => authQuery.refetch()}>Try again</button>} />
      </main>
    );
  }

  const auth = authQuery.data;
  if (!auth || auth.setup_required) return <AuthForms mode="setup" />;
  if (!auth.authenticated || !auth.user) {
    return (
      <Routes>
        <Route path="/login" element={<AuthForms mode="login" />} />
        <Route path="*" element={<PublicLandingPage />} />
      </Routes>
    );
  }

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
          await logoutMutation.mutateAsync();
        }
      }}
    >
      <AgentToolsProvider />
      <AppShell />
    </AuthContext.Provider>
  );
}
