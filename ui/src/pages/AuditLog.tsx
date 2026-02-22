import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getAuditLogs } from "@/api/client";
import "./AuditLog.css";

export function AuditLog() {
  const [providerFilter, setProviderFilter] = useState("");
  const [actionFilter, setActionFilter] = useState("");
  const [limit, setLimit] = useState(50);

  const { data: logs = [], isLoading } = useQuery({
    queryKey: ["audit-logs", providerFilter, actionFilter, limit],
    queryFn: () => getAuditLogs({ provider_id: providerFilter || undefined, action_type: actionFilter || undefined, limit }),
  });

  return (
    <main className="audit-page">
      <h1>Audit Log</h1>
      <div className="audit-filters">
        <input
          type="text"
          placeholder="Filter by provider…"
          value={providerFilter}
          onChange={(e) => setProviderFilter(e.target.value)}
          className="audit-filter-input"
        />
        <select value={actionFilter} onChange={(e) => setActionFilter(e.target.value)} className="audit-filter-select">
          <option value="">All actions</option>
          <option value="stop">Stop</option>
          <option value="start">Start</option>
          <option value="terminate">Terminate</option>
          <option value="health_check">Health Check</option>
          <option value="sync">Sync</option>
          <option value="provision">Provision</option>
        </select>
        <select value={limit} onChange={(e) => setLimit(Number(e.target.value))} className="audit-filter-select">
          <option value={25}>25 entries</option>
          <option value={50}>50 entries</option>
          <option value={100}>100 entries</option>
        </select>
      </div>

      {isLoading ? (
        <p className="loading-text">Loading audit log…</p>
      ) : logs.length === 0 ? (
        <p className="empty-text">No audit entries found.</p>
      ) : (
        <table className="audit-table">
          <thead>
            <tr>
              <th>Time</th>
              <th>Action</th>
              <th>Resource</th>
              <th>Status</th>
              <th>Initiated By</th>
              <th>Details</th>
            </tr>
          </thead>
          <tbody>
            {logs.map((log) => (
              <tr key={log.id}>
                <td className="audit-time">{log.created_at ? new Date(log.created_at).toLocaleString() : "—"}</td>
                <td><span className={`audit-action audit-action-${log.action_type}`}>{log.action_type}</span></td>
                <td className="audit-resource">{log.resource_id ?? "—"}</td>
                <td><span className={`audit-status audit-status-${log.status}`}>{log.status}</span></td>
                <td>{log.initiated_by}</td>
                <td className="audit-details">{JSON.stringify(log.details)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </main>
  );
}
