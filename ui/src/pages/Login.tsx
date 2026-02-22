import { useState, FormEvent } from "react";
import "./Login.css";

interface Props {
  onLogin: (token: string) => void;
}

export function Login({ onLogin }: Props) {
  const [apiKey, setApiKey] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");

    try {
      const resp = await fetch("/api/providers", {
        headers: { Authorization: `Bearer ${apiKey}` },
      });
      if (resp.status === 401) {
        setError("Invalid API key");
        return;
      }
      onLogin(apiKey);
    } catch {
      setError("Cannot reach engine");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-page">
      <div className="login-card">
        <h1 className="login-title">☁ Nimbus</h1>
        <p className="login-subtitle">Enter your API key to continue</p>
        <form onSubmit={handleSubmit}>
          <input
            type="password"
            className="login-input"
            placeholder="API Key"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            autoFocus
          />
          {error && <p className="login-error">{error}</p>}
          <button type="submit" className="login-btn" disabled={loading || !apiKey}>
            {loading ? "Verifying…" : "Sign In"}
          </button>
        </form>
        <p className="login-hint">
          Set <code>NIMBUS_API_KEY</code> on the engine to enable auth.
        </p>
      </div>
    </div>
  );
}
