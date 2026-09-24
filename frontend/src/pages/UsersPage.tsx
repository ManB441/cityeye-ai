import { useEffect, useState } from "react";
import { apiFetch, type AuthUser, type UserRole } from "../api/auth";
import { PageTitle } from "./CamerasPage";

export function AccessRestricted() {
  return <main className="operations-page access-restricted"><span aria-hidden="true">◇</span><p className="eyebrow">Role-based access</p><h1>Access restricted</h1><p>Your role does not include user administration. Contact your municipal administrator if your responsibilities have changed.</p><a href="/command-center">Return to Command Center →</a></main>;
}

export function UsersPage() {
  const [users, setUsers] = useState<AuthUser[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<UserRole>("CITIZEN");
  const [notice, setNotice] = useState("");
  async function load() {
    const response = await apiFetch("/api/users");
    if (!response.ok) throw new Error("User access is unavailable.");
    const data = await response.json() as { users: AuthUser[] };
    setUsers(data.users);
    setLoaded(true);
  }
  useEffect(() => { void load().catch(() => setError("User access is unavailable.")); }, []);
  async function create(event: React.FormEvent) {
    event.preventDefault();
    if (busy) return;
    setBusy(true); setError(null); setNotice("");
    try {
      const response = await apiFetch("/api/users", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username: username.trim(), password, role }) });
      if (!response.ok) throw new Error(response.status === 409 ? "That username or email is already in use." : "The account could not be created.");
      setPassword(""); setUsername(""); setNotice("Account created. Share access details through your approved secure channel.");
      await load();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "User access is unavailable."); }
    finally { setBusy(false); }
  }
  async function update(user: AuthUser, changes: { role?: UserRole; active?: boolean }) {
    if (busy) return;
    setBusy(true); setError(null); setNotice("");
    try {
      const response = await apiFetch(`/api/users/${encodeURIComponent(user.user_id)}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(changes) });
      if (!response.ok) throw new Error(response.status === 409 ? "Keep at least one active administrator." : "Access could not be updated.");
      await load(); setNotice("Access updated. Disabled accounts have their sessions revoked.");
      window.dispatchEvent(new Event("focus"));
    } catch (reason) { setError(reason instanceof Error ? reason.message : "User access is unavailable."); }
    finally { setBusy(false); }
  }
  return <main className="operations-page users-page">
    <PageTitle label="ADMINISTRATION" title="User access" copy="Manage the people authorized to operate CityEye. Access changes are audited." />
    {error && <p className="command-error" role="alert">{error}</p>}
    {notice && <p role="status">{notice}</p>}
    <div className="users-layout"><section className="users-list" aria-label="Municipal accounts">
      <h2>Municipal accounts</h2>{!loaded && !error && <p role="status">Loading accounts…</p>}
      {users.map((user) => <article className="user-access-row" key={user.user_id}>
        <div><strong>{user.username}</strong><small>{user.active ? "Active account" : "Access disabled"}</small></div>
        <label><span className="sr-only">Role for {user.username}</span><select aria-label={`Role for ${user.username}`} disabled={busy || !user.active} value={user.role} onChange={(e) => void update(user, { role: e.target.value as UserRole })}>{["CITIZEN", "EMPLOYEE", "ADMIN"].map((item) => <option key={item} value={item}>{item === "ADMIN" ? "Admin — مدير" : item === "EMPLOYEE" ? "Employee — موظف" : "Citizen — مواطن"}</option>)}</select></label>
        <button disabled={busy} type="button" onClick={() => void update(user, { active: !user.active })}>{user.active ? "Disable" : "Enable"}<span className="sr-only"> {user.username}</span></button>
      </article>)}
    </section><section className="create-account"><h2>Create an account</h2><p>Admin: full access. Employee: operational access without account administration. Citizen: map only.</p><form onSubmit={(event) => void create(event)}>
      <label>Username or email<input required maxLength={80} autoComplete="off" value={username} onChange={(e) => setUsername(e.target.value)} /></label>
      <label>Initial password<input required type="password" minLength={12} maxLength={256} autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} /></label>
      <small>At least 12 characters. Passwords are never displayed after creation.</small>
      <label>Role<select value={role} onChange={(e) => setRole(e.target.value as UserRole)}><option value="CITIZEN">Citizen — مواطن</option><option value="EMPLOYEE">Employee — موظف</option><option value="ADMIN">Admin — مدير</option></select></label>
      <button className="login-submit" disabled={busy} type="submit">{busy ? "Saving…" : "Create account"}</button>
    </form></section></div>
  </main>;
}
