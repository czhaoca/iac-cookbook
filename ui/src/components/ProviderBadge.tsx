import { Server, RefreshCw } from "lucide-react";
import type { Provider } from "@/types";
import "./ProviderBadge.css";

interface Props {
  provider: Provider;
  onSync: (id: string) => void;
  syncing: boolean;
}

export function ProviderBadge({ provider, onSync, syncing }: Props) {
  return (
    <div className={`provider-badge ${provider.is_active ? "active" : "inactive"}`}>
      <Server size={16} />
      <div className="badge-info">
        <span className="badge-name">{provider.display_name}</span>
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
