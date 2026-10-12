import "./index.css";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { Navigate, Route, RouterProvider, createBrowserRouter, createRoutesFromElements, useLocation } from "react-router-dom";

import { AuthProvider, useAuth } from "@/auth";
import { Layout } from "@/components/Layout";
import { ToastProvider } from "@/components/toast";
import { Loading } from "@/components/ui";
import AuditPage from "@/pages/AuditPage";
import AuditsPage from "@/pages/AuditsPage";
import BriefingPage from "@/pages/BriefingPage";
import CompanyPage from "@/pages/CompanyPage";
import ComparePage from "@/pages/ComparePage";
import DashboardPage from "@/pages/DashboardPage";
import LeadsPage from "@/pages/LeadsPage";
import LoginPage from "@/pages/LoginPage";
import NewSearchPage from "@/pages/NewSearchPage";
import ReportEditorPage from "@/pages/ReportEditorPage";
import ReportsPage from "@/pages/ReportsPage";
import ReviewPage from "@/pages/ReviewPage";
import SearchResultsPage from "@/pages/SearchResultsPage";
import SearchesPage from "@/pages/SearchesPage";
import SettingsPage from "@/pages/SettingsPage";
import SiteBuilderPage from "@/pages/SiteBuilderPage";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
});

function RequireAuth({ children }: { children: ReactNode }) {
  const { me, loading } = useAuth();
  const location = useLocation();
  if (loading) return <Loading />;
  if (!me?.authenticated || !me.verified) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  return <>{children}</>;
}

// Data router: necessário para o useBlocker (aviso de alterações não salvas ao trocar de tela)
const router = createBrowserRouter(
  createRoutesFromElements(
    <>
      <Route path="/login" element={<LoginPage />} />
      <Route
        element={
          <RequireAuth>
            <Layout />
          </RequireAuth>
        }
      >
        <Route index element={<DashboardPage />} />
        <Route path="buscas" element={<SearchesPage />} />
        <Route path="buscas/nova" element={<NewSearchPage />} />
        <Route path="buscas/:id" element={<SearchResultsPage />} />
        <Route path="leads" element={<LeadsPage />} />
        <Route path="leads/:id" element={<CompanyPage />} />
        <Route path="leads/:id/briefing" element={<BriefingPage />} />
        <Route path="leads/:id/site" element={<SiteBuilderPage />} />
        <Route path="auditorias" element={<AuditsPage />} />
        <Route path="auditorias/:id" element={<AuditPage />} />
        <Route path="auditorias/:id/revisao" element={<ReviewPage />} />
        <Route path="auditorias/:id/comparativo" element={<ComparePage />} />
        <Route path="auditorias/:id/relatorio" element={<ReportEditorPage />} />
        <Route path="relatorios" element={<ReportsPage />} />
        <Route path="configuracoes" element={<SettingsPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </>,
  ),
);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <AuthProvider>
          <RouterProvider router={router} />
        </AuthProvider>
      </ToastProvider>
    </QueryClientProvider>
  </StrictMode>,
);
