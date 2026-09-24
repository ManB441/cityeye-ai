import { useEffect, useState } from "react";
import type { AuthState } from "../hooks/useAuth";
import type { SystemReadiness } from "../types";

export function AppHeader({ auth, readiness }: { auth: AuthState; readiness: SystemReadiness }) {
  const [now, setNow] = useState(new Date());
  const [showLogin, setShowLogin] = useState(false);

  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 1_000);
    return () => window.clearInterval(timer);
  }, []);

  const operational = readiness.status === "ready";
  const healthLabel = operational
    ? "SYSTEM OPERATIONAL"
    : readiness.status === "degraded"
      ? readiness.components?.readiness?.status === "unknown" ? "API ONLINE · READINESS UNKNOWN" : "SYSTEM DEGRADED"
      : "SYSTEM UNAVAILABLE";
  const identityName = auth.user?.username ?? (auth.loading ? "Checking access" : auth.authRequired ? "Sign in required" : auth.error ? "Access unavailable" : "Demo access");
  return (
    <header className="command-header">
      <div className="command-brand">
        <span className="command-logo" aria-hidden="true">CE</span>
        <span><strong>CITYEYE AI</strong><small>{auth.user?.role === "CITIZEN" ? "Citizen Map" : "Traffic Intelligence Command Center"}</small></span>
      </div>
      <div className="header-operations">
        {auth.user?.role !== "CITIZEN" && <span className={`operational-state ${operational ? "online" : readiness.status === "degraded" ? "degraded" : "offline"}`}>
          <i />{healthLabel}
        </span>}
        <time dateTime={now.toISOString()}>{now.toLocaleDateString()} · {now.toLocaleTimeString()}</time>
        <button className="identity-button" type="button" aria-expanded={showLogin} aria-controls="account-menu" onClick={() => setShowLogin((value) => !value)}>
          <span>{auth.user?.username?.slice(0, 2).toUpperCase() ?? "--"}</span>
          <span><strong>{identityName}</strong><small>{auth.user?.role ?? "READ ONLY"}</small></span>
        </button>
      </div>
      {showLogin && (
        <div className="identity-popover" id="account-menu" onKeyDown={(event) => { if (event.key === "Escape") setShowLogin(false); }}>
          <div><strong>{identityName}</strong><small>{auth.user?.role ?? "READ ONLY"}</small>{auth.authRequired && auth.user && <button type="button" disabled={auth.loading} onClick={() => void auth.logout()}>{auth.loading ? "Signing out…" : "Sign out securely"}</button>}</div>
          {auth.error && <p role="alert">{auth.error}</p>}
        </div>
      )}
    </header>
  );
}
