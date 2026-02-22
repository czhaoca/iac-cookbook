import { useState } from "react";
import { useProviders, useResources, useResourceAction, useSyncResources, useBudgetStatus, useEnforceBudget, useSpending } from "@/hooks/useApi";
import { ProviderBadge } from "@/components/ProviderBadge";
import { ProviderForm, ProviderDeleteButton } from "@/components/ProviderForm";
import { ResourceCard } from "@/components/ResourceCard";
import { BudgetOverview } from "@/components/BudgetOverview";
import { SpendingChart } from "@/components/SpendingChart";
import type { ResourceAction } from "@/types";
import "./Dashboard.css";

export function Dashboard() {
  const [showProviderForm, setShowProviderForm] = useState(false);
  const { data: providers = [], isLoading: loadingProviders } = useProviders();
  const { data: resources = [], isLoading: loadingResources } = useResources();
  const actionMut = useResourceAction();
  const syncMut = useSyncResources();
  const { data: budgetStatuses = [] } = useBudgetStatus();
  const { data: spending = [] } = useSpending();
  const enforceMut = useEnforceBudget();

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
        <div className="section-header">
          <h2 className="section-title">Providers</h2>
          <button className="btn-primary btn-sm" onClick={() => setShowProviderForm(true)}>
            + Add Provider
          </button>
        </div>
        {showProviderForm && <ProviderForm onClose={() => setShowProviderForm(false)} />}
        {loadingProviders ? (
          <p className="loading-text">Loading providers…</p>
        ) : providers.length === 0 ? (
          <p className="empty-text">
            No providers registered. Click "Add Provider" or use <code>nimbus providers add</code>.
          </p>
        ) : (
          <div className="provider-grid">
            {providers.map((p) => (
              <div key={p.id} className="provider-card-wrapper">
                <ProviderBadge
                  provider={p}
                  onSync={handleSync}
                  syncing={syncMut.isPending}
                />
                <ProviderDeleteButton providerId={p.id} />
              </div>
            ))}
          </div>
        )}
        {syncMut.isSuccess && (
          <p className="success-text">
            Synced: {syncMut.data.created} created, {syncMut.data.updated} updated
          </p>
        )}
      </section>

      {/* Budget */}
      <section className="section">
        <h2 className="section-title">Budget</h2>
        <BudgetOverview
          statuses={budgetStatuses}
          onEnforce={() => enforceMut.mutate()}
          enforcing={enforceMut.isPending}
        />
        <h3 className="section-subtitle">Spending Over Time</h3>
        <SpendingChart records={spending} />
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
