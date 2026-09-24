export type UserRole = "CITIZEN" | "EMPLOYEE" | "ADMIN";

export interface AuthUser {
  user_id: string;
  username: string;
  role: UserRole;
  active?: boolean;
}

export interface SessionInfo {
  auth_required: boolean;
  user: AuthUser | null;
}

export function authorizationHeaders(): HeadersInit | undefined {
  return undefined;
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
    credentials: "same-origin",
  }), "Access service is unavailable. Operator actions are disabled.");
}

export async function login(username: string, password: string): Promise<SessionInfo> {
  const response = await parse<{ user: AuthUser }>(
    await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({ username, password }),
    }),
    "Unable to sign in. Check the service and try again.",
  );
  return { auth_required: true, user: response.user };
}

export async function logout(): Promise<void> {
  const response = await fetch("/api/auth/logout", { method: "POST", credentials: "same-origin" });
  if (!response.ok && response.status !== 401) throw new Error("Unable to sign out");
}

export async function apiFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const response = await fetch(input, init);
  if (response.status === 401) window.dispatchEvent(new Event("cityeye:session-ended"));
  return response;
}
