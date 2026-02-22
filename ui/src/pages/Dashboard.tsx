import { useProviders, useResources, useResourceAction, useSyncResources } from "@/hooks/useApi";
import { ProviderBadge } from "@/components/ProviderBadge";
import { ResourceCard } from "@/components/ResourceCard";
import type { ResourceAction } from "@/types";
import "./Dashboard.css";

export function Dashboard() {
  const { data: providers = [], isLoading: loadingProviders } = useProviders();
  const { data: resources = [], isLoading: loadingResources } = useResources();
  const actionMut = useResourceAction();
  const syncMut = useSyncResources();

  const handleAction = (id: string, action: ResourceAction) => {
    actionMut.mutate({ id, action });
  };

  const handleSync = (providerId: string) => {
    syncMut.mutate(providerId);
  };

  const running = resources.filter((r) => r.status === "running").length;
  const stopped = resources.filter((r) => r.status === "stopped").length;
  const critical = resources.filter((r) => r.protection_level === "critical").length;

  return (
    <main className="dashboard">
      {/* Stats */}
      <section className="stats-bar">
        <div className="stat">
          <span className="stat-value">{resources.length}</span>
          <span className="stat-label">Resources</span>
        </div>
        <div className="stat">
          <span className="stat-value running">{running}</span>
          <span className="stat-label">Running</span>
        </div>
        <div className="stat">
          <span className="stat-value stopped">{stopped}</span>
          <span className="stat-label">Stopped</span>
        </div>
        <div className="stat">
          <span className="stat-value critical">{critical}</span>
          <span className="stat-label">Critical</span>
        </div>
      </section>

      {/* Providers */}
      <section className="section">
        <h2 className="section-title">Providers</h2>
        {loadingProviders ? (
          <p className="loading-text">Loading providers…</p>
        ) : providers.length === 0 ? (
          <p className="empty-text">
            No providers registered. Use <code>nimbus providers add</code> to register one.
          </p>
        ) : (
          <div className="provider-grid">
            {providers.map((p) => (
              <ProviderBadge
                key={p.id}
                provider={p}
                onSync={handleSync}
                syncing={syncMut.isPending}
              />
            ))}
          </div>
        )}
        {syncMut.isSuccess && (
          <p className="success-text">
            Synced: {syncMut.data.created} created, {syncMut.data.updated} updated
          </p>
        )}
      </section>

      {/* Resources */}
      <section className="section">
        <h2 className="section-title">Resources</h2>
        {loadingResources ? (
          <p className="loading-text">Loading resources…</p>
        ) : resources.length === 0 ? (
          <p className="empty-text">No resources tracked yet. Sync a provider to get started.</p>
        ) : (
          <div className="resource-grid">
            {resources.map((r) => (
              <ResourceCard
                key={r.id}
                resource={r}
                onAction={handleAction}
                actionPending={actionMut.isPending}
              />
            ))}
          </div>
        )}
        {actionMut.isError && (
          <p className="error-text">{actionMut.error.message}</p>
        )}
      </section>
    </main>
  );
}
