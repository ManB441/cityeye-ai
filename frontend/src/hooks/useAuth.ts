import { useCallback, useEffect, useState } from "react";
import { fetchSession, login as requestLogin, logout as requestLogout } from "../api/auth";
import type { AuthUser } from "../api/auth";

export type AuthState = {
  user: AuthUser | null;
  authRequired: boolean;
  loading: boolean;
  error: string | null;
  login: (username: string, password: string) => Promise<boolean>;
  logout: () => Promise<void>;
};

export function useAuth(): AuthState {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [authRequired, setAuthRequired] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    void fetchSession(controller.signal)
      .then((session) => {
        setUser(session.user);
        setAuthRequired(session.auth_required);
      })
      .catch((requestError) => {
        if (requestError instanceof DOMException && requestError.name === "AbortError") return;
        setError(requestError instanceof Error ? requestError.message : "Unable to check session");
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    setLoading(true);
    try {
      const session = await requestLogin(username, password);
      setUser(session.user);
      setAuthRequired(session.auth_required);
      setError(null);
      return true;
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Login failed");
      return false;
    } finally {
      setLoading(false);
    }
  }, []);

  const logout = useCallback(async () => {
    await requestLogout();
    setUser(null);
  }, []);

  return { user, authRequired, loading, error, login, logout };
}
