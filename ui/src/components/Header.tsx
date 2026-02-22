import { Cloud, Activity, AlertTriangle, CheckCircle, Settings, ScrollText, LogOut } from "lucide-react";
import { Link } from "react-router-dom";
import { useHealth } from "@/hooks/useApi";
import "./Header.css";

export function Header({ onLogout }: { onLogout?: () => void }) {
  const { data: health } = useHealth();
  const connected = health?.status === "ok";

  return (
    <header className="header">
      <div className="header-left">
        <Link to="/" className="header-home-link">
          <Cloud size={28} className="header-icon" />
          <h1 className="header-title">Nimbus</h1>
        </Link>
        <span className="header-version">v{health?.version ?? "..."}</span>
      </div>
      <div className="header-right">
        <span className={`engine-status ${connected ? "connected" : "disconnected"}`}>
          {connected ? (
            <><CheckCircle size={14} /> Engine Connected</>
          ) : (
            <><AlertTriangle size={14} /> Engine Unreachable</>
          )}
        </span>
        <Activity size={18} className="header-pulse" />
        <Link to="/audit" className="header-settings-link" title="Audit Log">
          <ScrollText size={18} />
        </Link>
        <Link to="/settings" className="header-settings-link" title="Settings">
          <Settings size={18} />
        </Link>
        {onLogout && (
          <button className="header-logout-btn" onClick={onLogout} title="Logout">
            <LogOut size={18} />
          </button>
        )}
      </div>
    </header>
  );
}
