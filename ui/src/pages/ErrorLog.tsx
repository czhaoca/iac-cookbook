import { useErrors } from "@/hooks/useApi";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { clearErrors as clearErrorsApi } from "@/api/client";
import "./ErrorLog.css";

export function ErrorLog() {
  const { data, isLoading } = useErrors();
  const qc = useQueryClient();
  const clearMut = useMutation({
    mutationFn: clearErrorsApi,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["errors"] }),
  });

  const errors = data?.errors ?? [];

  return (
    <main className="error-log-page">
      <div className="section-header">
        <h1>Error Log</h1>
        {errors.length > 0 && (
          <button className="btn-sm btn-danger" onClick={() => clearMut.mutate()} disabled={clearMut.isPending}>
            Clear All ({data?.total ?? 0})
          </button>
        )}
      </div>

      {isLoading ? (
        <p className="loading-text">Loading errors…</p>
      ) : errors.length === 0 ? (
        <p className="empty-text">No errors recorded. ✅</p>
      ) : (
        <div className="error-list">
          {errors.map((e, i) => (
            <div key={i} className="error-entry">
              <div className="error-header">
                <span className="error-type">{e.error_type}</span>
                <span className="error-source">{e.source}</span>
                <span className="error-time">{new Date(e.timestamp * 1000).toLocaleString()}</span>
              </div>
              <p className="error-message">{e.message}</p>
              {Object.keys(e.context).length > 0 && (
                <details className="error-context">
                  <summary>Context</summary>
                  <pre>{JSON.stringify(e.context, null, 2)}</pre>
                </details>
              )}
            </div>
          ))}
        </div>
      )}
    </main>
  );
}
