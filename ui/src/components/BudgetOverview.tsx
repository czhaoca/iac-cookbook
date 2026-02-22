import { DollarSign, AlertTriangle, ShieldCheck, Zap } from "lucide-react";
import type { BudgetStatus } from "@/types";
import "./BudgetOverview.css";

interface Props {
  statuses: BudgetStatus[];
  onEnforce: () => void;
  enforcing: boolean;
}

const STATUS_CONFIG: Record<string, { color: string; icon: typeof ShieldCheck }> = {
  ok: { color: "#4ade80", icon: ShieldCheck },
  warning: { color: "#facc15", icon: AlertTriangle },
  exceeded: { color: "#ef4444", icon: AlertTriangle },
};

export function BudgetOverview({ statuses, onEnforce, enforcing }: Props) {
  if (statuses.length === 0) {
    return (
      <div className="budget-empty">
        <DollarSign size={20} />
        <span>No budget rules configured. Add one to start tracking spending.</span>
      </div>
    );
  }

  return (
    <div className="budget-overview">
      {statuses.map((bs, i) => {
        const cfg = STATUS_CONFIG[bs.status] ?? STATUS_CONFIG["ok"]!;
        const Icon = cfg.icon;
        const pct = Math.min(bs.utilization * 100, 100);

        return (
          <div key={i} className={`budget-card budget-${bs.status}`}>
            <div className="budget-header">
              <Icon size={16} style={{ color: cfg.color }} />
              <span className="budget-provider">
                {bs.provider_id ?? "Global"}
              </span>
              <span className="budget-period">{bs.period}</span>
            </div>

            <div className="budget-bar-container">
              <div
                className="budget-bar-fill"
                style={{ width: `${pct}%`, backgroundColor: cfg.color }}
              />
            </div>

            <div className="budget-numbers">
              <span className="budget-spent" style={{ color: cfg.color }}>
                ${bs.total_spent.toFixed(2)}
              </span>
              <span className="budget-limit">/ ${bs.monthly_limit.toFixed(2)}</span>
              <span className="budget-pct">{(bs.utilization * 100).toFixed(0)}%</span>
            </div>

            {bs.alerts.length > 0 && (
              <div className="budget-alerts">
                {bs.alerts.map((a, j) => (
                  <p key={j} className="budget-alert-text">{a}</p>
                ))}
              </div>
            )}

            {bs.status === "exceeded" && bs.action_on_exceed !== "alert" && (
              <div className="budget-action-info">
                <Zap size={12} />
                <span>Auto-action: {bs.action_on_exceed.replace(/_/g, " ")}</span>
              </div>
            )}
          </div>
        );
      })}

      {statuses.some((s) => s.status === "exceeded") && (
        <button
          className="enforce-btn"
          onClick={onEnforce}
          disabled={enforcing}
        >
          <Zap size={14} />
          {enforcing ? "Enforcing…" : "Run Budget Enforcement"}
        </button>
      )}
    </div>
  );
}
