import { useState, useMemo } from "react";
import { useProviders, useResources, useResourceAction, useSyncResources, useBudgetStatus, useEnforceBudget, useSpending, useProviderStatus } from "@/hooks/useApi";
import { ProviderBadge } from "@/components/ProviderBadge";
import { ProviderForm, ProviderDeleteButton } from "@/components/ProviderForm";
import { ResourceCard } from "@/components/ResourceCard";
import { BudgetOverview } from "@/components/BudgetOverview";
import { SpendingChart } from "@/components/SpendingChart";
import { ConfirmModal } from "@/components/ConfirmModal";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { showToast } from "@/components/Toasts";
import type { ResourceAction } from "@/types";
import "./Dashboard.css";

export function Dashboard() {
  const [showProviderForm, setShowProviderForm] = useState(false);
  const [pendingAction, setPendingAction] = useState<{ id: string; action: ResourceAction; name: string } | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [providerFilter, setProviderFilter] = useState<string | null>(null);
  const { data: providers = [], isLoading: loadingProviders } = useProviders();
  const { data: resources = [], isLoading: loadingResources } = useResources();
  const actionMut = useResourceAction();
  const syncMut = useSyncResources();
  const { data: budgetStatuses = [] } = useBudgetStatus();
  const { data: spending = [] } = useSpending();
  const enforceMut = useEnforceBudget();
  const { data: providerStatusData } = useProviderStatus();

  // Map provider_id → status for badge display
  const providerStatusMap = useMemo(() => {
    const map: Record<string, "connected" | "degraded" | "down" | "unknown"> = {};
    for (const ps of providerStatusData?.providers ?? []) {
      map[ps.provider_id] = ps.status;
    }
    return map;
  }, [providerStatusData]);

  const filteredResources = useMemo(
    () => providerFilter ? resources.filter((r) => r.provider_id === providerFilter) : resources,
    [resources, providerFilter],
  );

  const providerStats = useMemo(() => {
    const stats: Record<string, { total: number; running: number; stopped: number }> = {};
    for (const r of resources) {
      const pid = r.provider_id;
      if (!stats[pid]) stats[pid] = { total: 0, running: 0, stopped: 0 };
      stats[pid].total++;
      if (r.status === "running") stats[pid].running++;
      if (r.status === "stopped") stats[pid].stopped++;
    }
    return stats;
  }, [resources]);

  const destructiveActions = new Set<ResourceAction>(["stop", "terminate"]);

  const handleAction = (id: string, action: ResourceAction) => {
    if (destructiveActions.has(action)) {
      const res = resources.find((r) => r.id === id);
      setPendingAction({ id, action, name: res?.display_name ?? id });
    } else {
      actionMut.mutate({ id, action }, {
        onSuccess: () => showToast(`${action} completed`, "success"),
      });
    }
  };

  const confirmAction = () => {
    if (!pendingAction) return;
    actionMut.mutate(
      { id: pendingAction.id, action: pendingAction.action },
      {
        onSuccess: () => {
          showToast(`${pendingAction.action} completed on ${pendingAction.name}`, "success");
          setPendingAction(null);
        },
        onError: (err: Error) => {
          showToast(err.message, "error");
          setPendingAction(null);
        },
      },
    );
  };

  const toggleSelect = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (selected.size === filteredResources.length) {
      setSelected(new Set());
    } else {
      setSelected(new Set(filteredResources.map((r) => r.id)));
    }
  };

  const bulkAction = (action: ResourceAction) => {
    for (const id of selected) {
      handleAction(id, action);
    }
    setSelected(new Set());
  };

  const handleSync = (providerId: string) => {
    syncMut.mutate(providerId);
  };

  const running = resources.filter((r) => r.status === "running").length;
  const stopped = resources.filter((r) => r.status === "stopped").length;
  const critical = resources.filter((r) => r.protection_level === "critical").length;

  return (
    <main className="dashboard">
      {pendingAction && (
        <ConfirmModal
          title={`${pendingAction.action === "terminate" ? "Terminate" : "Stop"} Resource`}
          message={<>Are you sure you want to <strong>{pendingAction.action}</strong> <strong>{pendingAction.name}</strong>? This action cannot be easily undone.</>}
          confirmLabel={pendingAction.action === "terminate" ? "Terminate" : "Stop"}
          confirmVariant="danger"
          onConfirm={confirmAction}
          onCancel={() => setPendingAction(null)}
        />
      )}

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
            {providers.map((p) => {
              const stats = providerStats[p.id];
              return (
                <div
                  key={p.id}
                  className={`provider-card-wrapper${providerFilter === p.id ? " provider-active-filter" : ""}`}
                  onClick={() => setProviderFilter(providerFilter === p.id ? null : p.id)}
                  role="button"
                  tabIndex={0}
                >
                  <ProviderBadge
                    provider={p}
                    onSync={handleSync}
                    syncing={syncMut.isPending}
                    status={providerStatusMap[p.id]}
                  />
                  {stats && (
                    <div className="provider-resource-counts">
                      <span>{stats.total} resources</span>
                      <span className="count-running">{stats.running} running</span>
                      <span className="count-stopped">{stats.stopped} stopped</span>
                    </div>
                  )}
                  <ProviderDeleteButton providerId={p.id} />
                </div>
              );
            })}
          </div>
        )}
        {providerFilter && (
          <button className="btn-sm btn-secondary filter-clear" onClick={() => setProviderFilter(null)}>
            Clear filter: {providers.find((p) => p.id === providerFilter)?.display_name ?? providerFilter}
          </button>
        )}
        {syncMut.isSuccess && (
          <p className="success-text">
            Synced: {syncMut.data.created} created, {syncMut.data.updated} updated
          </p>
        )}
      </section>

      {/* Budget */}
      <ErrorBoundary fallback={<section className="section"><h2 className="section-title">Budget</h2><p className="error-text">⚠️ Budget data unavailable</p></section>}>
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
      </ErrorBoundary>

      {/* Resources */}
      <ErrorBoundary fallback={<section className="section"><h2 className="section-title">Resources</h2><p className="error-text">⚠️ Resource list unavailable</p></section>}>
      <section className="section">
        <div className="section-header">
          <h2 className="section-title">
            Resources{providerFilter ? ` — ${providers.find((p) => p.id === providerFilter)?.display_name ?? providerFilter}` : ""}
          </h2>
          {filteredResources.length > 0 && (
            <div className="bulk-actions">
              <label className="bulk-select-all">
                <input type="checkbox" checked={selected.size === filteredResources.length && filteredResources.length > 0} onChange={toggleSelectAll} />
                Select all
              </label>
              {selected.size > 0 && (
                <>
                  <span className="bulk-count">{selected.size} selected</span>
                  <button className="btn-sm btn-secondary" onClick={() => bulkAction("health_check")}>Health Check</button>
                  <button className="btn-sm btn-danger" onClick={() => bulkAction("stop")}>Stop Selected</button>
                </>
              )}
            </div>
          )}
        </div>
        {loadingResources ? (
          <p className="loading-text">Loading resources…</p>
        ) : filteredResources.length === 0 ? (
          <p className="empty-text">{providerFilter ? "No resources for this provider." : "No resources tracked yet. Sync a provider to get started."}</p>
        ) : (
          <div className="resource-grid">
            {filteredResources.map((r) => (
              <ResourceCard
                key={r.id}
                resource={r}
                onAction={handleAction}
                actionPending={actionMut.isPending}
                selected={selected.has(r.id)}
                onSelect={() => toggleSelect(r.id)}
              />
            ))}
          </div>
        )}
        {actionMut.isError && (
          <p className="error-text">{actionMut.error.message}</p>
        )}
      </section>
      </ErrorBoundary>
    </main>
  );
}
