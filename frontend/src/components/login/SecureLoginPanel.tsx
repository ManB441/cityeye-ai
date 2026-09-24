import { useState } from "react";
import type { AuthState } from "../../hooks/useAuth";
import type { EyePhase } from "./CityEyeVisual";

export function SecureLoginPanel({ auth, phase, granted, onSubmit, onFocusChange, onEngage, onPress }: {
  auth: AuthState; phase: EyePhase; granted: boolean;
  onSubmit: (username: string, password: string) => void;
  onFocusChange: (field: "email" | "password" | "none") => void;
  onEngage: (engaged: boolean) => void;
  onPress: (pressed: boolean) => void;
}) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [visible, setVisible] = useState(false);
  const busy = auth.loading || phase === "verifying" || phase === "success";
  const status = phase === "success" ? granted ? "Access granted" : "Identity verified" : phase === "verifying" ? "Verifying access" : phase === "failure" ? "Access not verified" : "";
  return <section className="awaken-access" aria-labelledby="access-title">
    <div className="access-section-mark" aria-hidden="true"><span />CITYEYE / ACCESS</div>
    <div className="access-content">
      <p className="awaken-kicker">Secure municipal access</p>
      <h2 id="access-title">Enter the<br />command center.</h2>
      <p className="access-description">Authorized access to CityEye’s<br className="desktop-break" /> traffic intelligence network.</p>
      <form onSubmit={event => { event.preventDefault(); if (!busy) onSubmit(username.trim(), password); }} aria-busy={busy}>
        <div className="access-field">
          <label htmlFor="access-email">Email</label>
          <input id="access-email" aria-label="Username or email" name="username" type="text" inputMode="email" autoComplete="username" autoCapitalize="none" spellCheck={false} maxLength={80} placeholder="Your municipal email" value={username} onChange={event => setUsername(event.target.value)} onFocus={() => onFocusChange("email")} onBlur={() => onFocusChange("none")} required readOnly={busy} />
        </div>
        <div className="access-field">
          <label htmlFor="access-password">Password</label>
          <div className="access-password"><input id="access-password" name="password" type={visible ? "text" : "password"} autoComplete="current-password" maxLength={256} placeholder="Enter your password" value={password} onChange={event => setPassword(event.target.value)} onFocus={() => onFocusChange("password")} onBlur={() => onFocusChange("none")} required readOnly={busy} />
            <button className="access-reveal" type="button" aria-label={visible ? "Hide password" : "Show password"} aria-pressed={visible} onClick={() => setVisible(value => !value)}>{visible ? "Hide" : "Show"}</button>
          </div>
        </div>
        {auth.error && <p className="access-error" role="alert">{auth.error}</p>}
        <button className="access-submit" type="submit" disabled={busy} onPointerEnter={() => onEngage(true)} onPointerLeave={() => { onEngage(false); onPress(false); }} onFocus={() => onEngage(true)} onBlur={() => onEngage(false)} onPointerDown={() => onPress(true)} onPointerUp={() => onPress(false)} onPointerCancel={() => onPress(false)}>
          <span>{phase === "success" ? "Access granted" : busy ? "Verifying access…" : "Enter command center"}</span><span className="access-arrow" aria-hidden="true">→</span>
        </button>
        <div className="access-feedback" role="status" aria-live="polite" aria-atomic="true">{status && <><i aria-hidden="true" />{status}</>}</div>
      </form>
      <p className="access-policy"><svg viewBox="0 0 20 22" aria-hidden="true"><path d="m10 1 8 3v6c0 5-8 10-8 10S2 15 2 10V4z"/><path d="m6 10 3 3 5-6"/></svg><span>Authorized personnel only<br /><span>Activity is audited</span></span></p>
    </div>
    <div className="access-bottom"><span>BUILT FOR THE CITY.</span><span>GUIDED BY PEOPLE.</span></div>
  </section>;
}
