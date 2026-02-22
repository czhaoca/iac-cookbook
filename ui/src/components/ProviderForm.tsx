import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createProvider, deleteProvider } from "@/api/client";
import type { ProviderCreate } from "@/types";
import "./ProviderForm.css";

const PROVIDER_TYPES = ["oci", "cloudflare", "proxmox", "azure", "gcp", "aws"];

export function ProviderForm({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<ProviderCreate>({
    id: "",
    provider_type: "oci",
    display_name: "",
    region: "",
    credentials_path: "",
  });

  const mutation = useMutation({
    mutationFn: createProvider,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["providers"] });
      onClose();
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.id || !form.display_name) return;
    mutation.mutate(form);
  };

  const update = (field: keyof ProviderCreate, value: string) =>
    setForm((prev) => ({ ...prev, [field]: value }));

  return (
    <div className="provider-form-overlay" onClick={onClose}>
      <form
        className="provider-form"
        onClick={(e) => e.stopPropagation()}
        onSubmit={handleSubmit}
      >
        <h3>Add Provider</h3>

        <label>
          ID
          <input
            value={form.id}
            onChange={(e) => update("id", e.target.value)}
            placeholder="my-oci"
            required
          />
        </label>

        <label>
          Type
          <select
            value={form.provider_type}
            onChange={(e) => update("provider_type", e.target.value)}
          >
            {PROVIDER_TYPES.map((t) => (
              <option key={t} value={t}>
                {t.toUpperCase()}
              </option>
            ))}
          </select>
        </label>

        <label>
          Display Name
          <input
            value={form.display_name}
            onChange={(e) => update("display_name", e.target.value)}
            placeholder="My OCI Account"
            required
          />
        </label>

        <label>
          Region
          <input
            value={form.region ?? ""}
            onChange={(e) => update("region", e.target.value)}
            placeholder="us-ashburn-1"
          />
        </label>

        <label>
          Credentials Path
          <input
            value={form.credentials_path ?? ""}
            onChange={(e) => update("credentials_path", e.target.value)}
            placeholder="local/config/oci-api-key.pem"
          />
          <span className="hint">Path to credentials file in local/config/</span>
        </label>

        <div className="form-actions">
          <button type="button" className="btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="btn-primary" disabled={mutation.isPending}>
            {mutation.isPending ? "Adding..." : "Add Provider"}
          </button>
        </div>

        {mutation.isError && (
          <p className="form-error">{(mutation.error as Error).message}</p>
        )}
      </form>
    </div>
  );
}

export function ProviderDeleteButton({
  providerId,
}: {
  providerId: string;
}) {
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: () => deleteProvider(providerId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["providers"] }),
  });

  return (
    <button
      className="btn-danger btn-sm"
      onClick={() => {
        if (confirm(`Delete provider "${providerId}"?`)) mutation.mutate();
      }}
      disabled={mutation.isPending}
    >
      {mutation.isPending ? "..." : "✕"}
    </button>
  );
}
