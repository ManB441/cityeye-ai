export type UserRole = "OPERATOR" | "REVIEWER" | "ADMIN";

export interface AuthUser {
  user_id: string;
  username: string;
  role: UserRole;
}

export interface SessionInfo {
  auth_required: boolean;
  user: AuthUser | null;
}

const TOKEN_KEY = "cityeye_access_token";

export function getAccessToken(): string | null {
  return window.sessionStorage.getItem(TOKEN_KEY);
}

export function authorizationHeaders(): HeadersInit | undefined {
  const token = getAccessToken();
  return token ? { Authorization: `Bearer ${token}` } : undefined;
}

async function parse<T>(response: Response, fallbackMessage: string): Promise<T> {
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as { detail?: string } | null;
    const safeDetail = response.status === 401 && payload?.detail === "Invalid username or password"
      ? payload.detail
      : fallbackMessage;
    throw new Error(safeDetail);
  }
  return response.json() as Promise<T>;
}

export async function fetchSession(signal?: AbortSignal): Promise<SessionInfo> {
  return parse<SessionInfo>(await fetch("/api/auth/session", {
    signal,
    headers: authorizationHeaders(),
  }), "Access service is unavailable. Operator actions are disabled.");
}

export async function login(username: string, password: string): Promise<SessionInfo> {
  const response = await parse<{ access_token: string; user: AuthUser }>(
    await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    }),
    "Unable to sign in. Check the service and try again.",
  );
  window.sessionStorage.setItem(TOKEN_KEY, response.access_token);
  return { auth_required: true, user: response.user };
}

export async function logout(): Promise<void> {
  const headers = authorizationHeaders();
  try {
    await fetch("/api/auth/logout", { method: "POST", headers });
  } finally {
    window.sessionStorage.removeItem(TOKEN_KEY);
  }
}
