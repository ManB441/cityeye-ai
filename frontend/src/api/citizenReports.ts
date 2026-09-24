import { apiFetch } from "./auth";
import type { CitizenReport } from "../types";

export async function fetchCitizenReports(signal?: AbortSignal): Promise<CitizenReport[]> {
  const response = await apiFetch("/api/citizen-reports", { signal });
  if (!response.ok) throw new Error(`Citizen report request failed with HTTP ${response.status}`);
  const payload = await response.json() as { reports: CitizenReport[] };
  return payload.reports;
}
