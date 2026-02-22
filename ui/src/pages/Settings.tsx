import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getSettings, updateSetting } from "@/api/client";
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
  const [draft, setDraft] = useState<Record<string, string>>({});

  useEffect(() => {
    const d: Record<string, string> = {};
    for (const def of SETTING_DEFS) {
      d[def.key] = String(settings[def.key] ?? "");
    }
    setDraft(d);
  }, [settings]);

  const mutation = useMutation({
    mutationFn: ({ key, value }: { key: string; value: string }) => updateSetting(key, value),
    onSuccess: (_data, vars) => {
      queryClient.invalidateQueries({ queryKey: ["settings"] });
      showToast(`Updated ${vars.key}`, "success");
    },
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
    </main>
  );
}
