import { useState, type ReactNode } from "react";
import "./ConfirmModal.css";

interface Props {
  title: string;
  message: ReactNode;
  confirmLabel?: string;
  confirmVariant?: "danger" | "primary";
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmModal({ title, message, confirmLabel = "Confirm", confirmVariant = "primary", onConfirm, onCancel }: Props) {
  const [loading, setLoading] = useState(false);

  const handleConfirm = async () => {
    setLoading(true);
    try {
      onConfirm();
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onCancel}>
      <div className="modal-card" onClick={(e) => e.stopPropagation()}>
        <h3 className="modal-title">{title}</h3>
        <div className="modal-body">{message}</div>
        <div className="modal-actions">
          <button className="btn-secondary" onClick={onCancel} disabled={loading}>Cancel</button>
          <button className={`btn-${confirmVariant}`} onClick={handleConfirm} disabled={loading}>
            {loading ? "Working…" : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
