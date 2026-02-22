import { useState, useEffect, useCallback } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Header } from "@/components/Header";
import { Dashboard } from "@/pages/Dashboard";
import { ResourceDetail } from "@/pages/ResourceDetail";
import { Settings } from "@/pages/Settings";
import { Login } from "@/pages/Login";
import { ToastContainer } from "@/components/Toasts";
import { useWebSocket } from "@/hooks/useWebSocket";
import { setAuthToken } from "@/api/client";
import "./App.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 10_000,
    },
  },
});

function AppInner() {
  useWebSocket();
  return (
    <div className="app">
      <Header />
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/resource/:id" element={<ResourceDetail />} />
        <Route path="/settings" element={<Settings />} />
      </Routes>
      <ToastContainer />
    </div>
  );
}

export default function App() {
  const [authChecked, setAuthChecked] = useState(false);
  const [needsAuth, setNeedsAuth] = useState(false);

  useEffect(() => {
    // Restore token from sessionStorage
    const saved = sessionStorage.getItem("nimbus_api_key");
    if (saved) setAuthToken(saved);

    // Check if auth is required
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

  if (!authChecked) return null;

  if (needsAuth) {
    return <Login onLogin={handleLogin} />;
  }

  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AppInner />
      </BrowserRouter>
    </QueryClientProvider>
  );
}
