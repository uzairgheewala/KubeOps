import type { ArtifactDetail, RegistrySnapshot, ScenarioFamily, ScenarioInstance, SimulationRun, SystemStatus } from "../types";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "/api/v1";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options?.headers ?? {})
    }
  });
  const payload = await response.json();
  if (!response.ok) {
    const message = Array.isArray(payload.errors)
      ? payload.errors.join("\n")
      : payload.detail ?? `Request failed with ${response.status}`;
    throw new Error(message);
  }
  return payload as T;
}

export const api = {
  status: () => request<SystemStatus>("/system/status"),
  families: () => request<ScenarioFamily[]>("/scenario-families"),
  registry: () => request<RegistrySnapshot>("/registry"),
  compile: (payload: Record<string, unknown>) =>
    request<ScenarioInstance>("/scenarios/compile", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  run: (payload: Record<string, unknown>) =>
    request<SimulationRun>("/scenarios/run", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  runComposition: (payload: Record<string, unknown>) =>
    request<SimulationRun>("/compositions/run", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  schema: (name: string) => request<Record<string, unknown>>(`/schemas/${name}`),
  artifact: (artifactId: string) => request<ArtifactDetail>(`/artifacts/${artifactId}`)
};
