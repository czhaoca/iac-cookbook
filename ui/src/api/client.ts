import type {
  Provider,
  ProviderCreate,
  Resource,
  ActionResult,
  SyncResult,
  HealthStatus,
  ResourceAction,
  BudgetRule,
  BudgetRuleCreate,
  BudgetStatus,
  SpendingRecord,
  ActionLogEntry,
} from "@/types";

const BASE = "/api";

let _authToken: string | null = null;

/** Set the API key for all subsequent requests. */
export function setAuthToken(token: string | null) {
  _authToken = token;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init?.headers as Record<string, string>),
  };
  if (_authToken) {
    headers["Authorization"] = `Bearer ${_authToken}`;
  }
  const res = await fetch(`${BASE}${path}`, { ...init, headers });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(
      (body as { detail?: string }).detail ?? `HTTP ${res.status}`,
    );
  }
  return res.json() as Promise<T>;
}

// Health — endpoint is at root, not under /api
export const getHealth = () =>
  fetch("/health").then((r) => r.json() as Promise<HealthStatus>);

// Providers
export const listProviders = () => request<Provider[]>("/providers");
export const getProvider = (id: string) => request<Provider>(`/providers/${id}`);
export const createProvider = (data: ProviderCreate) =>
  request<Provider>("/providers", {
    method: "POST",
    body: JSON.stringify(data),
  });
export const deleteProvider = (id: string) =>
  request<void>(`/providers/${id}`, { method: "DELETE" });

// Resources
export const listResources = (providerId?: string) => {
  const params = providerId ? `?provider_id=${providerId}` : "";
  return request<Resource[]>(`/resources${params}`);
};
export const getResource = (id: string) =>
  request<Resource>(`/resources/${id}`);
export const performAction = (id: string, action: ResourceAction) =>
  request<ActionResult>(`/resources/${id}/action`, {
    method: "POST",
    body: JSON.stringify({ action }),
  });
export const syncResources = (providerId: string) =>
  request<SyncResult>(`/resources/sync/${providerId}`, { method: "POST" });

// Budget Rules
export const listBudgetRules = () =>
  request<BudgetRule[]>("/budget/rules?active_only=false");
export const createBudgetRule = (data: BudgetRuleCreate) =>
  request<BudgetRule>("/budget/rules", {
    method: "POST",
    body: JSON.stringify(data),
  });
export const deleteBudgetRule = (id: string) =>
  request<void>(`/budget/rules/${id}`, { method: "DELETE" });

// Budget Status & Spending
export const getBudgetStatus = () => request<BudgetStatus[]>("/budget/status");
export const listSpending = (providerId?: string) => {
  const params = providerId ? `?provider_id=${providerId}` : "";
  return request<SpendingRecord[]>(`/budget/spending${params}`);
};
export const enforceBudget = () =>
  request<{ period: string; actions_taken: number; details: unknown[] }>(
    "/budget/enforce",
    { method: "POST" },
  );

// Orchestration
export const orchestrateLockdown = (providerId: string) =>
  request<{ stopped: number; skipped: number; steps: unknown[] }>(
    "/orchestrate/lockdown",
    { method: "POST", body: JSON.stringify({ provider_id: providerId }) },
  );

// Action Logs
export const getActionLogs = (resourceId: string) =>
  request<ActionLogEntry[]>(`/resources/${resourceId}/logs`);

// Audit Log (global)
export const getAuditLogs = (params?: {
  provider_id?: string;
  action_type?: string;
  limit?: number;
}) => {
  const qs = new URLSearchParams();
  if (params?.provider_id) qs.set("provider_id", params.provider_id);
  if (params?.action_type) qs.set("action_type", params.action_type);
  if (params?.limit) qs.set("limit", String(params.limit));
  const q = qs.toString();
  return request<ActionLogEntry[]>(`/audit${q ? `?${q}` : ""}`);
};

// Settings
export const getSettings = () =>
  request<Record<string, string>>("/settings");
export const updateSetting = (key: string, value: string) =>
  request<{ key: string; value: string }>(`/settings/${key}`, {
    method: "PUT",
    body: JSON.stringify({ value }),
  });

// Spending
export const syncSpending = () =>
  request<{ synced: number }>("/budget/sync-spending", { method: "POST" });

// Alert Config
export interface AlertConfigData {
  webhooks: string[];
  email_to: string[];
  email_from: string;
  smtp_host: string;
  smtp_port: number;
}
export const getAlertConfig = () => request<AlertConfigData>("/alerts/config");
export const updateAlertConfig = (data: AlertConfigData) =>
  request<AlertConfigData>("/alerts/config", {
    method: "PUT",
    body: JSON.stringify(data),
  });
export const testAlert = () =>
  request<Record<string, unknown>>("/alerts/test", { method: "POST", body: JSON.stringify({}) });

// Provider resilience status
export interface ProviderStatus {
  provider_id: string;
  provider_type: string;
  display_name: string;
  circuit_breaker: { state: string; failure_count: number; failure_threshold: number };
  recent_errors: number;
  status: "connected" | "degraded" | "down" | "unknown";
}
export const getProviderStatus = () =>
  request<{ providers: ProviderStatus[]; total_errors: number }>("/providers/status/resilience");

// Error log
export interface ErrorEntry {
  timestamp: number;
  source: string;
  error_type: string;
  message: string;
  context: Record<string, unknown>;
}
export const getErrors = (source?: string, limit?: number) => {
  const qs = new URLSearchParams();
  if (source) qs.set("source", source);
  if (limit) qs.set("limit", String(limit));
  const q = qs.toString();
  return request<{ errors: ErrorEntry[]; total: number }>(`/errors${q ? `?${q}` : ""}`);
};
export const clearErrors = () =>
  request<void>("/errors", { method: "DELETE" });
