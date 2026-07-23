import type {
  AccessValidation,
  ArtifactDetail,
  ArtifactSummary,
  EnvironmentDefinition,
  EnvironmentSnapshot,
  EnvironmentSummary,
  DiagnosticCatalog,
  DiagnosticCaseResult,
  IncidentInvestigation,
  IncidentSummary,
  OperationalProfileAssessment,
  OperationalProfileSpec,
  ActionTypeDefinition,
  ExecutionPolicy,
  LifecycleProfile,
  OperationRun,
  OperationSummary,
  RecoveryPlan,
  RegistrySnapshot,
  ScenarioFamily,
  ScenarioInstance,
  SimulationRun,
  SnapshotDiff,
  SnapshotSummary,
  SystemStatus,
  TopologyGraph,
  PackCatalogResponse,
  PackResolution,
  PackCoverageReport,
  OrganizationDefinition,
  WorkspaceDefinition,
  RoleGrant,
  FleetDefinition,
  FleetAssessment,
  FleetOperationPlan,
  ExecutorAgentDefinition,
  ExecutionTask,
  AuditEvent,
  AuditChainVerification,
  RetentionPolicy,
  RetentionPlan,
  ControlPlaneBackupManifest,
  ControlPlaneRestorePlan,
  UpgradeReadinessReport,
  CurrentIdentity,
  RateLimitRule,
  ConcurrencyRule,
  MaintenanceWindow,
  ScheduledOperation,
  ScheduleDecision
} from "../types";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "/api/v1";
let apiToken: string | null = null;
let apiOrganizationId = "default";
let apiWorkspaceId = "default";

export function setApiToken(token: string | null): void { apiToken = token; }
export function setApiScope(organizationId: string, workspaceId: string): void {
  apiOrganizationId = organizationId.trim() || "default";
  apiWorkspaceId = workspaceId.trim() || "default";
}
export function getApiScope(): { organizationId: string; workspaceId: string } {
  return { organizationId: apiOrganizationId, workspaceId: apiWorkspaceId };
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "X-KubeOps-Organization": apiOrganizationId,
      "X-KubeOps-Workspace": apiWorkspaceId,
      ...(apiToken ? { Authorization: `Token ${apiToken}` } : {}),
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
  login: (username: string, password: string) => request<{ token: string }>("/auth/token", { method: "POST", body: JSON.stringify({ username, password }) }),
  me: () => request<CurrentIdentity>("/auth/me"),
  packs: () => request<PackCatalogResponse>("/packs"),
  resolvePacks: (packIds?: string[]) => request<PackResolution>("/packs/resolve", { method: "POST", body: JSON.stringify({ pack_ids: packIds ?? [] }) }),
  packCoverage: () => request<PackCoverageReport>("/packs/coverage"),
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
  diagnosisCoverage: () => request<Record<string, unknown>>("/diagnosis/coverage"),
  actionCatalog: () => request<ActionTypeDefinition[]>("/action-catalog"),
  lifecycleProfiles: () => request<LifecycleProfile[]>("/lifecycle-profiles"),
  executionPolicies: () => request<ExecutionPolicy[]>("/execution-policies"),
  planLifecycle: (snapshotId: string, payload: Record<string, unknown>) =>
    request<RecoveryPlan>(`/snapshots/${encodeURIComponent(snapshotId)}/lifecycle/plan`, { method: "POST", body: JSON.stringify(payload) }),
  operations: (environmentId?: string) =>
    request<OperationSummary[]>(`/operations${environmentId ? `?environment_id=${encodeURIComponent(environmentId)}` : ""}`),
  operation: (operationId: string) => request<OperationRun>(`/operations/${encodeURIComponent(operationId)}`),
  createOperation: (payload: Record<string, unknown>) =>
    request<OperationRun>("/operations", { method: "POST", body: JSON.stringify(payload) }),
  approveOperation: (operationId: string, payload: Record<string, unknown>) =>
    request<OperationRun>(`/operations/${encodeURIComponent(operationId)}/approvals`, { method: "POST", body: JSON.stringify(payload) }),
  runOperation: (operationId: string, payload: Record<string, unknown> = {}) =>
    request<OperationRun>(`/operations/${encodeURIComponent(operationId)}/run`, { method: "POST", body: JSON.stringify(payload) }),
  pauseOperation: (operationId: string, reason: string) =>
    request<OperationRun>(`/operations/${encodeURIComponent(operationId)}/pause`, { method: "POST", body: JSON.stringify({ reason }) }),
  cancelOperation: (operationId: string, reason: string) =>
    request<OperationRun>(`/operations/${encodeURIComponent(operationId)}/cancel`, { method: "POST", body: JSON.stringify({ reason }) }),
  resumeOperation: (operationId: string, payload: Record<string, unknown> = {}) =>
    request<OperationRun>(`/operations/${encodeURIComponent(operationId)}/resume`, { method: "POST", body: JSON.stringify(payload) }),
  rollbackOperation: (operationId: string, payload: Record<string, unknown> = {}) =>
    request<OperationRun>(`/operations/${encodeURIComponent(operationId)}/rollback`, { method: "POST", body: JSON.stringify(payload) }),

  organizations: () => request<OrganizationDefinition[]>("/organizations"),
  workspaces: () => request<WorkspaceDefinition[]>("/workspaces"),
  roleGrants: () => request<RoleGrant[]>("/role-grants"),
  createRoleGrant: (payload: RoleGrant) => request<RoleGrant>("/role-grants", { method: "POST", body: JSON.stringify(payload) }),
  evaluateAuthorization: (payload: Record<string, unknown>) => request<Record<string, unknown>>("/authorization/evaluate", { method: "POST", body: JSON.stringify(payload) }),

  fleets: () => request<FleetDefinition[]>("/fleets"),
  fleet: (fleetId: string) => request<FleetDefinition>(`/fleets/${encodeURIComponent(fleetId)}`),
  assessFleet: (fleetId: string) => request<{ assessment: FleetAssessment; artifacts: ArtifactSummary[] }>(`/fleets/${encodeURIComponent(fleetId)}/assess`, { method: "POST", body: "{}" }),
  planFleetOperation: (fleetId: string, operationType: string) => request<FleetOperationPlan>(`/fleets/${encodeURIComponent(fleetId)}/operations/plan`, { method: "POST", body: JSON.stringify({ operation_type: operationType }) }),

  executorAgents: () => request<ExecutorAgentDefinition[]>("/executors"),
  executionTasks: () => request<ExecutionTask[]>("/execution-tasks"),
  auditEvents: (workspaceId?: string) => request<AuditEvent[]>(`/audit/events${workspaceId ? `?workspace_id=${encodeURIComponent(workspaceId)}` : ""}`),
  verifyAudit: (workspaceId?: string) => request<AuditChainVerification>(`/audit/verify${workspaceId ? `?workspace_id=${encodeURIComponent(workspaceId)}` : ""}`),
  rateLimits: () => request<RateLimitRule[]>("/governance/rate-limits"),
  concurrencyLimits: () => request<ConcurrencyRule[]>("/governance/concurrency-limits"),
  maintenanceWindows: () => request<MaintenanceWindow[]>("/maintenance-windows"),
  scheduledOperations: () => request<ScheduledOperation[]>("/scheduled-operations"),
  createScheduledOperation: (payload: Partial<ScheduledOperation>) => request<ScheduledOperation & { decision: ScheduleDecision }>("/scheduled-operations", { method: "POST", body: JSON.stringify(payload) }),
  evaluateScheduledOperation: (scheduleId: string) => request<{ schedule: ScheduledOperation; decision: ScheduleDecision }>(`/scheduled-operations/${encodeURIComponent(scheduleId)}/evaluate`, { method: "POST", body: "{}" }),
  materializeScheduledOperation: (scheduleId: string) => request<{ schedule: ScheduledOperation; decision: ScheduleDecision; result?: Record<string, unknown> }>(`/scheduled-operations/${encodeURIComponent(scheduleId)}/materialize`, { method: "POST", body: "{}" }),
  cancelScheduledOperation: (scheduleId: string, reason = "cancelled by operator") => request<ScheduledOperation>(`/scheduled-operations/${encodeURIComponent(scheduleId)}/cancel`, { method: "POST", body: JSON.stringify({ reason }) }),
  retentionPolicies: () => request<RetentionPolicy[]>("/retention/policies"),
  planRetention: (policyId: string) => request<RetentionPlan>("/retention/plan", { method: "POST", body: JSON.stringify({ policy_id: policyId }) }),
  platformBackups: () => request<ControlPlaneBackupManifest[]>("/platform/backups"),
  createPlatformBackup: (payload: Record<string, unknown> = {}) => request<{ backup: ControlPlaneBackupManifest; artifacts: ArtifactSummary[] }>("/platform/backups", { method: "POST", body: JSON.stringify(payload) }),
  platformRestorePlan: (backupId: string, targetVersion = "1.0.0") => request<ControlPlaneRestorePlan>("/platform/restore-plan", { method: "POST", body: JSON.stringify({ backup_id: backupId, target_version: targetVersion }) }),
  platformReadiness: (workspaceId?: string, targetVersion = "1.0.0") => request<UpgradeReadinessReport>(`/platform/readiness?target_version=${encodeURIComponent(targetVersion)}${workspaceId ? `&workspace_id=${encodeURIComponent(workspaceId)}` : ""}`)
};
