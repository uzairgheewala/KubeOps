import type {
  AccessValidation,
  ArtifactDetail,
  EnvironmentDefinition,
  EnvironmentSnapshot,
  EnvironmentSummary,
  DiagnosticCatalog,
  DiagnosticCaseResult,
  IncidentInvestigation,
  IncidentSummary,
  OperationalProfileAssessment,
  OperationalProfileSpec,
  RegistrySnapshot,
  ScenarioFamily,
  ScenarioInstance,
  SimulationRun,
  SnapshotDiff,
  SnapshotSummary,
  SystemStatus,
  TopologyGraph
} from "../types";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "/api/v1";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options?.headers ?? {})
    }
  });
  const text = await response.text();
  const payload = text ? JSON.parse(text) : null;
  if (!response.ok) {
    const message = Array.isArray(payload?.errors)
      ? payload.errors.join("\n")
      : payload?.detail ?? `Request failed with ${response.status}`;
    throw new Error(message);
  }
  return payload as T;
}

export const api = {
  status: () => request<SystemStatus>("/system/status"),
  families: () => request<ScenarioFamily[]>("/scenario-families"),
  registry: () => request<RegistrySnapshot>("/registry"),
  compile: (payload: Record<string, unknown>) =>
    request<ScenarioInstance>("/scenarios/compile", { method: "POST", body: JSON.stringify(payload) }),
  run: (payload: Record<string, unknown>) =>
    request<SimulationRun>("/scenarios/run", { method: "POST", body: JSON.stringify(payload) }),
  diagnoseScenario: (payload: Record<string, unknown>) =>
    request<DiagnosticCaseResult>("/scenarios/diagnose", { method: "POST", body: JSON.stringify(payload) }),
  runComposition: (payload: Record<string, unknown>) =>
    request<SimulationRun>("/compositions/run", { method: "POST", body: JSON.stringify(payload) }),
  schema: (name: string) => request<Record<string, unknown>>(`/schemas/${name}`),
  artifact: (artifactId: string) => request<ArtifactDetail>(`/artifacts/${artifactId}`),

  environments: () => request<EnvironmentSummary[]>("/environments"),
  environment: (environmentId: string) => request<EnvironmentDefinition>(`/environments/${encodeURIComponent(environmentId)}`),
  createEnvironment: (payload: EnvironmentDefinition) =>
    request<EnvironmentSummary>("/environments", { method: "POST", body: JSON.stringify(payload) }),
  updateEnvironment: (environmentId: string, payload: EnvironmentDefinition) =>
    request<EnvironmentSummary>(`/environments/${encodeURIComponent(environmentId)}`, { method: "PUT", body: JSON.stringify(payload) }),
  validateEnvironment: (environmentId: string, methodId?: string) =>
    request<AccessValidation>(`/environments/${encodeURIComponent(environmentId)}/validate`, {
      method: "POST",
      body: JSON.stringify({ method_id: methodId })
    }),
  snapshots: (environmentId: string) =>
    request<SnapshotSummary[]>(`/environments/${encodeURIComponent(environmentId)}/snapshots`),
  collectSnapshot: (environmentId: string, payload: Record<string, unknown> = {}) =>
    request<EnvironmentSnapshot>(`/environments/${encodeURIComponent(environmentId)}/snapshots`, {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  snapshot: (snapshotId: string) => request<EnvironmentSnapshot>(`/snapshots/${encodeURIComponent(snapshotId)}`),
  topology: (snapshotId: string) => request<TopologyGraph>(`/snapshots/${encodeURIComponent(snapshotId)}/topology`),
  snapshotDiff: (snapshotId: string, before?: string) =>
    request<SnapshotDiff>(`/snapshots/${encodeURIComponent(snapshotId)}/diff${before ? `?before=${encodeURIComponent(before)}` : ""}`),
  snapshotHealth: (snapshotId: string, profileId?: string) =>
    request<OperationalProfileAssessment[] | OperationalProfileAssessment>(
      `/snapshots/${encodeURIComponent(snapshotId)}/health${profileId ? `?profile_id=${encodeURIComponent(profileId)}` : ""}`
    ),
  operationalProfiles: () => request<OperationalProfileSpec[]>("/operational-profiles"),
  diagnosticCatalog: () => request<DiagnosticCatalog>("/diagnostic-catalog"),
  incidents: (environmentId?: string) =>
    request<IncidentSummary[]>(`/incidents${environmentId ? `?environment_id=${encodeURIComponent(environmentId)}` : ""}`),
  incident: (incidentId: string) => request<IncidentInvestigation>(`/incidents/${encodeURIComponent(incidentId)}`),
  openIncident: (snapshotId: string, payload: Record<string, unknown>) =>
    request<IncidentInvestigation>(`/snapshots/${encodeURIComponent(snapshotId)}/incidents`, {
      method: "POST", body: JSON.stringify(payload)
    }),
  runProbe: (incidentId: string, probeId: string, payload: Record<string, unknown> = {}) =>
    request<IncidentInvestigation>(`/incidents/${encodeURIComponent(incidentId)}/probes/${encodeURIComponent(probeId)}/run`, {
      method: "POST", body: JSON.stringify(payload)
    }),
  diagnosisCoverage: () => request<Record<string, unknown>>("/diagnosis/coverage")
};
