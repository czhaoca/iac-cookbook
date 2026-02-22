import { useParams, Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { getResource, getActionLogs } from "@/api/client";
import { useResourceAction } from "@/hooks/useApi";
import type { ResourceAction } from "@/types";
import "./ResourceDetail.css";

export function ResourceDetail() {
  const { id } = useParams<{ id: string }>();
  const { data: resource, isLoading } = useQuery({
    queryKey: ["resource", id],
    queryFn: () => getResource(id!),
    enabled: !!id,
  });
  const { data: logs = [] } = useQuery({
    queryKey: ["action-logs", id],
    queryFn: () => getActionLogs(id!),
    enabled: !!id,
    refetchInterval: 10_000,
  });
  const actionMut = useResourceAction();

  const handleAction = (action: ResourceAction) => {
    if (id) actionMut.mutate({ id, action });
  };

  if (isLoading) return <main className="detail-page"><p>Loading...</p></main>;
  if (!resource) return <main className="detail-page"><p>Resource not found</p></main>;

  return (
    <main className="detail-page">
      <Link to="/" className="back-link">← Dashboard</Link>

      <div className="detail-header">
        <h1>{resource.display_name}</h1>
        <span className={`status-badge status-${resource.status}`}>{resource.status}</span>
      </div>

      <section className="detail-grid">
        <div className="detail-card">
          <h3>Properties</h3>
          <dl>
            <dt>ID</dt><dd className="mono">{resource.id}</dd>
            <dt>Provider</dt><dd>{resource.provider_id}</dd>
            <dt>Type</dt><dd>{resource.resource_type}</dd>
            <dt>External ID</dt><dd className="mono">{resource.external_id || "—"}</dd>
            <dt>Protection</dt><dd><span className={`prot-${resource.protection_level}`}>{resource.protection_level}</span></dd>
            <dt>Auto-terminate</dt><dd>{resource.auto_terminate ? "Yes" : "No"}</dd>
            <dt>Monthly Cost</dt><dd>${resource.monthly_cost_estimate.toFixed(2)}</dd>
            <dt>Created</dt><dd>{new Date(resource.created_at).toLocaleString()}</dd>
            <dt>Last Seen</dt><dd>{resource.last_seen_at ? new Date(resource.last_seen_at).toLocaleString() : "—"}</dd>
          </dl>
        </div>

        <div className="detail-card">
          <h3>Actions</h3>
          <div className="action-buttons">
            <button onClick={() => handleAction("health_check")} disabled={actionMut.isPending}>Health Check</button>
            <button onClick={() => handleAction("stop")} disabled={actionMut.isPending}>Stop</button>
            <button onClick={() => handleAction("start")} disabled={actionMut.isPending}>Start</button>
            <button
              className="btn-danger"
              onClick={() => { if (confirm("Terminate this resource?")) handleAction("terminate"); }}
              disabled={actionMut.isPending || resource.protection_level === "critical"}
            >
              Terminate
            </button>
          </div>
          {actionMut.isError && <p className="error-text">{actionMut.error.message}</p>}
          {resource.tags && Object.keys(resource.tags).length > 0 && (
            <>
              <h3>Tags</h3>
              <dl>
                {Object.entries(resource.tags).map(([k, v]) => (
                  <span key={k}><dt>{k}</dt><dd>{String(v)}</dd></span>
                ))}
              </dl>
            </>
          )}
        </div>
      </section>

      <section className="detail-card">
        <h3>Action History</h3>
        {logs.length === 0 ? (
          <p className="empty-text">No actions recorded yet.</p>
        ) : (
          <table className="log-table">
            <thead>
              <tr>
                <th>Time</th>
                <th>Action</th>
                <th>Status</th>
                <th>By</th>
                <th>Details</th>
              </tr>
            </thead>
            <tbody>
              {logs.map((log) => (
                <tr key={log.id}>
                  <td>{log.created_at ? new Date(log.created_at).toLocaleString() : "—"}</td>
                  <td>{log.action_type}</td>
                  <td><span className={`log-status log-${log.status}`}>{log.status}</span></td>
                  <td>{log.initiated_by}</td>
                  <td className="mono">{Object.keys(log.details).length > 0 ? JSON.stringify(log.details) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </main>
  );
}
