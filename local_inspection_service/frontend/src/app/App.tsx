import { MutationCache, QueryCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createBrowserRouter, RouterProvider } from "react-router-dom";
import { VersionBoundary } from "../features/version/VersionBoundary";
import { SiteRoutes } from "./SiteRoutes";
import { ApiError } from "../api/client";
import { queryKeys } from "../api/queries";
import { AppToastProvider } from "../components/ToastProvider";

function recheckSession(error: Error) {
  if (error instanceof ApiError && [401, 403].includes(error.status) && !error.path.startsWith("/api/auth/")) {
    void queryClient.invalidateQueries({ queryKey: queryKeys.authStatus });
  }
}

const queryClient = new QueryClient({
  queryCache: new QueryCache({ onError: recheckSession }),
  mutationCache: new MutationCache({ onError: recheckSession }),
  defaultOptions: {
    queries: {
      staleTime: 15_000,
      retry: 1,
      refetchOnWindowFocus: false
    }
  }
});

const routerBasename = (import.meta.env.VITE_ROUTER_BASENAME || "/react-preview").replace(/\/+$/, "") || "/";

const router = createBrowserRouter([{ path: "*", element: <><VersionBoundary /><SiteRoutes /></> }], { basename: routerBasename });

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AppToastProvider>
        <RouterProvider router={router} />
      </AppToastProvider>
    </QueryClientProvider>
  );
}
