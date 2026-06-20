import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";
import { AuthGate } from "../features/auth/AuthGate";
import { AppToastProvider } from "../components/ToastProvider";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 15_000,
      retry: 1,
      refetchOnWindowFocus: false
    }
  }
});

const routerBasename = (import.meta.env.VITE_ROUTER_BASENAME || "/react-preview").replace(/\/+$/, "") || "/";

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AppToastProvider>
        <BrowserRouter basename={routerBasename}>
          <AuthGate />
        </BrowserRouter>
      </AppToastProvider>
    </QueryClientProvider>
  );
}
