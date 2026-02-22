/** Mirrors engine Pydantic schemas */

export interface Provider {
  id: string;
  provider_type: string;
  display_name: string;
  region: string;
  credentials_path: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ProviderCreate {
  id: string;
  provider_type: string;
  display_name: string;
  region?: string;
  credentials_path?: string;
}

export interface Resource {
  id: string;
  provider_id: string;
  resource_type: string;
  external_id: string;
  display_name: string;
  name_prefix: string;
  status: string;
  tags: Record<string, string>;
  protection_level: "critical" | "standard" | "ephemeral";
  auto_terminate: boolean;
  monthly_cost_estimate: number;
  created_at: string;
  updated_at: string;
  last_seen_at: string | null;
}

export interface ActionResult {
  resource_id: string;
  action: string;
  status: string;
  detail: string;
}

export interface SyncResult {
  provider_id: string;
  created: number;
  updated: number;
  total: number;
}

export interface HealthStatus {
  status: string;
  app: string;
  version: string;
}

export interface BudgetRule {
  id: string;
  provider_id: string | null;
  monthly_limit: number;
  alert_threshold: number;
  action_on_exceed: string;
  is_active: boolean;
  created_at: string;
}

export interface BudgetRuleCreate {
  provider_id?: string | null;
  monthly_limit: number;
  alert_threshold?: number;
  action_on_exceed?: string;
}

export interface SpendingRecord {
  id: string;
  provider_id: string;
  period: string;
  amount: number;
  currency: string;
  recorded_at: string;
}

export interface BudgetStatus {
  provider_id: string | null;
  period: string;
  total_spent: number;
  monthly_limit: number;
  utilization: number;
  status: "ok" | "warning" | "exceeded";
  action_on_exceed: string;
  alerts: string[];
}

export type ResourceAction = "stop" | "start" | "terminate" | "health_check";
