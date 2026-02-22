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
