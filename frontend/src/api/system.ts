import { apiFetch } from "./auth";
import type { SystemReadiness } from "../types";

export async function fetchSystemReadiness(signal?: AbortSignal): Promise<SystemReadiness> {
  const response = await apiFetch("/health/ready", { signal });
  if (response.status === 404) {
    const legacyResponse = await apiFetch("/health", { signal });
    if (legacyResponse.ok) {
      return {
        status: "degraded",
        service: "cityeye-ai-backend",
        components: { readiness: { status: "unknown", detail: "Dependency readiness endpoint is unavailable." } },
      };
    }
  }
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as { detail?: SystemReadiness } | null;
    return payload?.detail ?? { status: "unavailable" };
  }
  const readiness = await response.json() as SystemReadiness;
  if (readiness.status === "ready" && readiness.components?.ai_artifacts && readiness.components.ai_artifacts.status !== "ok") {
    return { ...readiness, status: "degraded" };
  }
  return readiness;
}
