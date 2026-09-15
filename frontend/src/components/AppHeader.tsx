import { useEffect, useState } from "react";
import type { AuthState } from "../hooks/useAuth";
import type { SystemReadiness } from "../types";

export function AppHeader({ auth, readiness }: { auth: AuthState; readiness: SystemReadiness }) {
  const [now, setNow] = useState(new Date());
  const [showLogin, setShowLogin] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");

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
        <span><strong>CITYEYE AI</strong><small>Traffic Intelligence Command Center</small></span>
      </div>
      <div className="header-operations">
        <span className={`operational-state ${operational ? "online" : readiness.status === "degraded" ? "degraded" : "offline"}`}>
          <i />{healthLabel}
        </span>
        <time dateTime={now.toISOString()}>{now.toLocaleDateString()} · {now.toLocaleTimeString()}</time>
        <button className="identity-button" type="button" onClick={() => setShowLogin((value) => !value)}>
          <span>{auth.user?.username?.slice(0, 2).toUpperCase() ?? "--"}</span>
          <span><strong>{identityName}</strong><small>{auth.user?.role ?? "READ ONLY"}</small></span>
        </button>
      </div>
      {showLogin && (
        <div className="identity-popover">
          {auth.authRequired && !auth.user ? (
            <form onSubmit={(event) => {
              event.preventDefault();
              void auth.login(username, password).then((success) => {
                setPassword("");
                if (success) setShowLogin(false);
              });
            }}>
              <strong>Municipal sign in</strong>
              <label>Username<input value={username} autoComplete="username" onChange={(event) => setUsername(event.target.value)} required /></label>
              <label>Password<input value={password} type="password" autoComplete="current-password" onChange={(event) => setPassword(event.target.value)} required /></label>
              <button type="submit" disabled={auth.loading}>Sign in</button>
            </form>
          ) : (
            <div><strong>{identityName}</strong><small>{auth.user?.role ?? "READ ONLY"}</small>{auth.authRequired && auth.user && <button type="button" onClick={() => void auth.logout()}>Sign out</button>}</div>
          )}
          {auth.error && <p role="alert">{auth.error}</p>}
        </div>
      )}
    </header>
  );
}
