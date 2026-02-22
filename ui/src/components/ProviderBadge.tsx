import { Server, RefreshCw } from "lucide-react";
import type { Provider } from "@/types";
import "./ProviderBadge.css";

interface Props {
  provider: Provider;
  onSync: (id: string) => void;
  syncing: boolean;
  status?: "connected" | "degraded" | "down" | "unknown";
}

const STATUS_LABEL: Record<string, string> = {
  connected: "●",
  degraded: "◐",
  down: "○",
  unknown: "?",
};

export function ProviderBadge({ provider, onSync, syncing, status }: Props) {
  return (
    <div className={`provider-badge ${provider.is_active ? "active" : "inactive"}`}>
      <Server size={16} />
      <div className="badge-info">
        <span className="badge-name">
          {provider.display_name}
          {status && (
            <span className={`provider-status-dot status-${status}`} title={status}>
              {STATUS_LABEL[status] ?? "?"}
            </span>
          )}
        </span>
        <span className="badge-detail">
          {provider.provider_type} · {provider.region || "—"}
        </span>
      </div>
      <button
        className="badge-sync"
        disabled={syncing || !provider.is_active}
        onClick={() => onSync(provider.id)}
        title="Sync resources"
      >
        <RefreshCw size={14} className={syncing ? "spinning" : ""} />
      </button>
    </div>
  );
}
