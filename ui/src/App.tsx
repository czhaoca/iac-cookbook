import { useState, useEffect, useCallback, lazy, Suspense } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Header } from "@/components/Header";
import { ToastContainer } from "@/components/Toasts";
import { useWebSocket } from "@/hooks/useWebSocket";
import { setAuthToken } from "@/api/client";
import "./App.css";
import "./responsive.css";

const Dashboard = lazy(() => import("@/pages/Dashboard").then((m) => ({ default: m.Dashboard })));
const ResourceDetail = lazy(() => import("@/pages/ResourceDetail").then((m) => ({ default: m.ResourceDetail })));
const Settings = lazy(() => import("@/pages/Settings").then((m) => ({ default: m.Settings })));
const AuditLog = lazy(() => import("@/pages/AuditLog").then((m) => ({ default: m.AuditLog })));
const ErrorLog = lazy(() => import("@/pages/ErrorLog").then((m) => ({ default: m.ErrorLog })));
const Login = lazy(() => import("@/pages/Login").then((m) => ({ default: m.Login })));

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 10_000,
    },
  },
});

function PageLoader() {
  return <div className="page-loader">Loading…</div>;
}

function AppInner({ onLogout }: { onLogout: () => void }) {
  useWebSocket();
  return (
    <div className="app">
      <Header onLogout={onLogout} />
      <Suspense fallback={<PageLoader />}>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/resource/:id" element={<ResourceDetail />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/audit" element={<AuditLog />} />
          <Route path="/errors" element={<ErrorLog />} />
        </Routes>
      </Suspense>
      <ToastContainer />
    </div>
  );
}

export default function App() {
  const [authChecked, setAuthChecked] = useState(false);
  const [needsAuth, setNeedsAuth] = useState(false);

  useEffect(() => {
    const saved = sessionStorage.getItem("nimbus_api_key");
    if (saved) setAuthToken(saved);

    fetch("/api/providers").then((r) => {
      if (r.status === 401) {
        setNeedsAuth(true);
      }
      setAuthChecked(true);
    }).catch(() => setAuthChecked(true));
  }, []);

  const handleLogin = useCallback((token: string) => {
    sessionStorage.setItem("nimbus_api_key", token);
    setAuthToken(token);
    setNeedsAuth(false);
  }, []);

  const handleLogout = useCallback(() => {
    sessionStorage.removeItem("nimbus_api_key");
    setAuthToken(null);
    setNeedsAuth(true);
  }, []);

  if (!authChecked) return null;

  if (needsAuth) {
    return (
      <Suspense fallback={<PageLoader />}>
        <Login onLogin={handleLogin} />
      </Suspense>
    );
  }

  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AppInner onLogout={handleLogout} />
      </BrowserRouter>
    </QueryClientProvider>
  );
}
