import { RefreshCw, Shield, ShieldAlert, ShieldOff } from "lucide-react";
import { Link } from "react-router-dom";
import type { Resource, ResourceAction } from "@/types";
import "./ResourceCard.css";

interface Props {
  resource: Resource;
  onAction: (id: string, action: ResourceAction) => void;
  actionPending: boolean;
}

const STATUS_COLORS: Record<string, string> = {
  running: "#4ade80",
  stopped: "#facc15",
  terminated: "#ef4444",
  unknown: "#94a3b8",
};

const PROTECTION_ICONS: Record<string, typeof Shield> = {
  critical: ShieldAlert,
  standard: Shield,
  ephemeral: ShieldOff,
};

export function ResourceCard({ resource, onAction, actionPending }: Props) {
  const statusColor = STATUS_COLORS[resource.status] ?? STATUS_COLORS["unknown"];
  const ProtIcon = PROTECTION_ICONS[resource.protection_level] ?? Shield;

  return (
    <div className="resource-card">
      <div className="card-header">
        <span className="card-type">{resource.resource_type}</span>
        <span className="card-status" style={{ color: statusColor }}>
          ● {resource.status}
        </span>
      </div>

      <Link to={`/resource/${resource.id}`} className="card-name-link">
        <h3 className="card-name">{resource.display_name || resource.external_id}</h3>
      </Link>

      <div className="card-meta">
        <span className="card-provider">{resource.provider_id}</span>
        <span className="card-protection" title={resource.protection_level}>
          <ProtIcon size={14} />
          {resource.protection_level}
        </span>
      </div>

      {resource.external_id && (
        <div className="card-extid" title={resource.external_id}>
          {resource.external_id.length > 24
            ? `${resource.external_id.slice(0, 12)}…${resource.external_id.slice(-8)}`
            : resource.external_id}
        </div>
      )}

      <div className="card-actions">
        {resource.status === "running" && (
          <button
            className="btn btn-warn"
            disabled={actionPending}
            onClick={() => onAction(resource.id, "stop")}
          >
            Stop
          </button>
        )}
        {resource.status === "stopped" && (
          <button
            className="btn btn-ok"
            disabled={actionPending}
            onClick={() => onAction(resource.id, "start")}
          >
            Start
          </button>
        )}
        <button
          className="btn btn-neutral"
          disabled={actionPending}
          onClick={() => onAction(resource.id, "health_check")}
        >
          <RefreshCw size={12} /> Check
        </button>
      </div>
    </div>
  );
}
