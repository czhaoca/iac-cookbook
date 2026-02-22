import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getSettings, updateSetting, getAlertConfig, updateAlertConfig, testAlert, type AlertConfigData } from "@/api/client";
import { showToast } from "@/components/Toasts";
import "./Settings.css";

interface SettingDef {
  key: string;
  label: string;
  description: string;
  unit: string;
}

const SETTING_DEFS: SettingDef[] = [
  { key: "spending_sync_interval", label: "Spending Sync Interval", description: "How often to sync spending from providers", unit: "seconds" },
  { key: "budget_enforce_interval", label: "Budget Enforce Interval", description: "How often to check and enforce budget rules", unit: "seconds" },
  { key: "health_check_interval", label: "Health Check Interval", description: "How often to check provider health", unit: "seconds" },
];

export function Settings() {
  const queryClient = useQueryClient();
  const { data: settings = {} } = useQuery({ queryKey: ["settings"], queryFn: getSettings });
  const { data: alertConfig } = useQuery({ queryKey: ["alert-config"], queryFn: getAlertConfig });
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [alertDraft, setAlertDraft] = useState<AlertConfigData>({
    webhooks: [], email_to: [], email_from: "", smtp_host: "", smtp_port: 587,
  });

  useEffect(() => {
    const d: Record<string, string> = {};
    for (const def of SETTING_DEFS) {
      d[def.key] = String(settings[def.key] ?? "");
    }
    setDraft(d);
  }, [settings]);

  useEffect(() => {
    if (alertConfig) setAlertDraft(alertConfig);
  }, [alertConfig]);

  const mutation = useMutation({
    mutationFn: ({ key, value }: { key: string; value: string }) => updateSetting(key, value),
    onSuccess: (_data, vars) => {
      queryClient.invalidateQueries({ queryKey: ["settings"] });
      showToast(`Updated ${vars.key}`, "success");
    },
    onError: (err: Error) => showToast(err.message, "error"),
  });

  const alertMutation = useMutation({
    mutationFn: (data: AlertConfigData) => updateAlertConfig(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["alert-config"] });
      showToast("Alert config saved", "success");
    },
    onError: (err: Error) => showToast(err.message, "error"),
  });

  const testMut = useMutation({
    mutationFn: () => testAlert(),
    onSuccess: () => showToast("Test alert sent", "success"),
    onError: (err: Error) => showToast(err.message, "error"),
  });

  const handleSave = (key: string) => {
    const value = draft[key];
    if (value !== undefined && value !== String(settings[key] ?? "")) {
      mutation.mutate({ key, value });
    }
  };

  return (
    <main className="settings-page">
      <h1>Settings</h1>

      <h2 className="settings-section-title">Intervals</h2>
      <div className="settings-grid">
        {SETTING_DEFS.map((def) => (
          <div key={def.key} className="setting-card">
            <label className="setting-label">{def.label}</label>
            <p className="setting-desc">{def.description}</p>
            <div className="setting-input-row">
              <input
                type="number"
                className="setting-input"
                value={draft[def.key] ?? ""}
                onChange={(e) => setDraft({ ...draft, [def.key]: e.target.value })}
                onBlur={() => handleSave(def.key)}
              />
              <span className="setting-unit">{def.unit}</span>
              <button
                className="btn-primary btn-sm"
                onClick={() => handleSave(def.key)}
                disabled={mutation.isPending}
              >
                Save
              </button>
            </div>
          </div>
        ))}
      </div>

      <h2 className="settings-section-title">Notifications</h2>
      <div className="settings-grid">
        <div className="setting-card">
          <label className="setting-label">Webhook URLs</label>
          <p className="setting-desc">One URL per line — receives JSON POST on alerts</p>
          <textarea
            className="setting-textarea"
            rows={3}
            value={alertDraft.webhooks.join("\n")}
            onChange={(e) => setAlertDraft({ ...alertDraft, webhooks: e.target.value.split("\n").filter(Boolean) })}
          />
        </div>
        <div className="setting-card">
          <label className="setting-label">Email Recipients</label>
          <p className="setting-desc">One email per line</p>
          <textarea
            className="setting-textarea"
            rows={2}
            value={alertDraft.email_to.join("\n")}
            onChange={(e) => setAlertDraft({ ...alertDraft, email_to: e.target.value.split("\n").filter(Boolean) })}
          />
        </div>
        <div className="setting-card">
          <label className="setting-label">SMTP Configuration</label>
          <p className="setting-desc">For email alerts</p>
          <div className="setting-input-row">
            <input className="setting-input setting-input-wide" placeholder="SMTP host" value={alertDraft.smtp_host} onChange={(e) => setAlertDraft({ ...alertDraft, smtp_host: e.target.value })} />
            <input className="setting-input" type="number" placeholder="Port" value={alertDraft.smtp_port} onChange={(e) => setAlertDraft({ ...alertDraft, smtp_port: Number(e.target.value) })} />
          </div>
          <div className="setting-input-row" style={{ marginTop: "0.5rem" }}>
            <input className="setting-input setting-input-wide" placeholder="From address" value={alertDraft.email_from} onChange={(e) => setAlertDraft({ ...alertDraft, email_from: e.target.value })} />
          </div>
        </div>
        <div className="setting-card-actions">
          <button className="btn-primary" onClick={() => alertMutation.mutate(alertDraft)} disabled={alertMutation.isPending}>
            Save Alert Config
          </button>
          <button className="btn-secondary" onClick={() => testMut.mutate()} disabled={testMut.isPending}>
            Send Test Alert
          </button>
        </div>
      </div>
    </main>
  );
}
