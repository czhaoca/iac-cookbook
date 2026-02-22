import { Cloud, Activity, AlertTriangle, CheckCircle, Settings } from "lucide-react";
import { Link } from "react-router-dom";
import { useHealth } from "@/hooks/useApi";
import "./Header.css";

export function Header() {
  const { data: health } = useHealth();
  const connected = health?.status === "ok";

  return (
    <header className="header">
      <div className="header-left">
        <Cloud size={28} className="header-icon" />
        <h1 className="header-title">Nimbus</h1>
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
        <Link to="/settings" className="header-settings-link" title="Settings">
          <Settings size={18} />
        </Link>
      </div>
    </header>
  );
}
