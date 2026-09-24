import { useCallback, useEffect, useRef, useState } from "react";
import { fetchSession, login as requestLogin, logout as requestLogout } from "../api/auth";
import type { AuthUser } from "../api/auth";

export type AuthState = {
  user: AuthUser | null;
  authRequired: boolean;
  initialized: boolean;
  loading: boolean;
  error: string | null;
  login: (username: string, password: string) => Promise<boolean>;
  logout: () => Promise<void>;
};

export function useAuth(): AuthState {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [authRequired, setAuthRequired] = useState(true);
  const [initialized, setInitialized] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pending = useRef(false);

  useEffect(() => {
    const controller = new AbortController();
    void fetchSession(controller.signal).then((session) => {
      if (controller.signal.aborted) return;
      setUser(session.user);
      setAuthRequired(session.auth_required);
    }).catch(() => {
      if (!controller.signal.aborted) setError("Access service is unavailable. Please try again.");
    }).finally(() => { if (!controller.signal.aborted) setInitialized(true); });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const expired = () => {
      setUser(null);
      setAuthRequired(true);
      setError("Your session has ended. Please sign in again.");
    };
    window.addEventListener("cityeye:session-ended", expired);
    return () => window.removeEventListener("cityeye:session-ended", expired);
  }, []);

  // Re-resolve roles/revocation on focus and while the console is open.
  useEffect(() => {
    if (!authRequired || !user) return;
    const controller = new AbortController();
    const check = async () => {
      try {
        const session = await fetchSession(controller.signal);
        if (controller.signal.aborted || pending.current) return;
        setUser(session.user);
        if (!session.user) setError("Your session has ended. Please sign in again.");
      } catch {
        if (!controller.signal.aborted && !pending.current) {
          setUser(null);
          setError("Access service is unavailable. Please sign in again when it returns.");
        }
      }
    };
    const timer = window.setInterval(() => void check(), 30_000);
    window.addEventListener("focus", check);
    return () => { controller.abort(); window.clearInterval(timer); window.removeEventListener("focus", check); };
  }, [authRequired, user?.user_id]);

  const login = useCallback(async (username: string, password: string) => {
    if (pending.current) return false;
    pending.current = true;
    setLoading(true);
    setError(null);
    try {
      const session = await requestLogin(username, password);
      setUser(session.user);
      setAuthRequired(session.auth_required);
      return true;
    } catch (requestError) {
      setError(requestError instanceof Error && requestError.message === "Invalid username or password"
        ? requestError.message : "Unable to sign in. Check the service and try again.");
      return false;
    } finally {
      pending.current = false;
      setLoading(false);
    }
  }, []);

  const logout = useCallback(async () => {
    if (pending.current) return;
    pending.current = true;
    setLoading(true);
    try {
      await requestLogout();
      setUser(null);
      setError(null);
    } catch {
      setError("Sign out could not be completed. Please retry.");
    } finally {
      pending.current = false;
      setLoading(false);
    }
  }, []);

  return { user, authRequired, initialized, loading, error, login, logout };
}
