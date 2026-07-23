export type ParameterSpec = {
  name: string;
  title: string;
  parameter_type: "string" | "integer" | "boolean" | "enum";
  description: string;
  required: boolean;
  default: unknown;
  options: unknown[];
};

export type ScenarioFamily = {
  family_id: string;
  version: string;
  title: string;
  description: string;
  parent_family_id: string | null;
  abstract: boolean;
  parameters: ParameterSpec[];
  signature: {
    invariant_families: string[];
    disturbance_mechanisms: string[];
    temporal_forms: string[];
    topology_patterns: string[];
    observation_profiles: string[];
    recovery_strategy_classes: string[];
    coverage_labels: string[];
  };
  blueprint: {
    observation_profiles: Array<{ profile_id: string; title: string }>;
  };
  disturbances: Array<{ disturbance_id: string; title: string }>;
  default_disturbance_id: string;
  default_observation_profile_id: string;
  tags: string[];
  lineage: string[];
  content_hash: string;
};

export type OperationalEntity = {
  entity_id: string;
  entity_type: string;
  name: string;
  plane: string;
  namespace?: string | null;
  provider?: string | null;
  labels?: Record<string, string>;
  capabilities?: string[];
  extensions?: Record<string, unknown>;
  desired_state: Record<string, unknown>;
  observed_state: Record<string, unknown>;
};

export type Relationship = {
  relationship_id: string;
  source_id: string;
  target_id: string;
  relationship_type: string;
  confidence?: number;
  provenance?: string;
  contract?: Record<string, unknown>;
  propagation?: Record<string, unknown>;
};

export type InvariantDefinition = {
  invariant_id: string;
  title: string;
  family: string;
  subject_id: string;
  severity: string;
};

export type ScenarioInstance = {
  scenario_id: string;
  family_id: string;
  family_version: string;
  title: string;
  description: string;
  bindings: Record<string, unknown>;
  entities: OperationalEntity[];
  relationships: Relationship[];
  invariants: InvariantDefinition[];
  disturbance: { disturbance_id: string; title: string; mechanism: string; temporal_form: string };
  observation_profile: { profile_id: string; title: string; profile_kind: string };
  metadata: Record<string, unknown>;
};

export type InvariantEvaluation = {
  invariant_id: string;
  status: "healthy" | "unhealthy" | "unknown" | "pending" | string;
  evaluated_at: number;
  actual_value: unknown;
  expected: unknown;
  explanation: string;
  evidence_entity_ids: string[];
};

export type Snapshot = {
  sequence: number;
  at_seconds: number;
  trigger_event_sequence: number | null;
  truth_state: Record<string, Record<string, unknown>>;
  observed_state: Record<string, Record<string, unknown>>;
  invariant_evaluations: InvariantEvaluation[];
};

export type TimelineEvent = {
  sequence: number;
  at_seconds: number;
  event_type: string;
  title: string;
  entity_id: string | null;
  rule_id: string | null;
  mutation_id: string | null;
  details: Record<string, unknown>;
};

export type SimulationRun = {
  run_id: string;
  scenario_id: string;
  family_id: string;
  status: string;
  timeline: TimelineEvent[];
  snapshots: Snapshot[];
  final_summary: {
    simulation_time_seconds: number;
    event_count: number;
    snapshot_count: number;
    unhealthy_invariants: string[];
    unknown_invariants: string[];
    healthy_invariant_count: number;
  };
  scenario: ScenarioInstance;
  artifacts: ArtifactSummary[];
};

export type SystemStatus = {
  service: string;
  release: string;
  mode: string;
  status: string;
  family_count: number;
  profile_count?: number;
  environment_count?: number;
  capabilities: string[];
};

export type RegistryEntry = {
  registry_key: string;
  category: string;
  version: string;
  title: string;
  description: string;
  schema_ref?: string | null;
  capabilities: string[];
  metadata: Record<string, unknown>;
};

export type RegistrySnapshot = {
  entries: RegistryEntry[];
  counts: Record<string, number>;
  schemas: string[];
};

export type ArtifactSummary = {
  artifact_id: string;
  artifact_type: string;
  content_hash: string;
};

export type ArtifactDetail = ArtifactSummary & {
  run_id: string;
  media_type: string;
  payload: unknown;
  derived_from: string[];
};

export type AccessMethodDefinition = {
  method_id: string;
  method_type: "kubectl" | "kubeconfig" | "fixture";
  title: string;
  context_name?: string | null;
  kubeconfig_path?: string | null;
  fixture_path?: string | null;
  command: string;
  read_only: boolean;
  timeout_seconds: number;
  metadata: Record<string, unknown>;
};

export type AccessCheck = {
  check_id: string;
  title: string;
  status: string;
  explanation: string;
  authority: string;
  details: Record<string, unknown>;
};

export type AccessValidation = {
  validation_id: string;
  environment_id: string;
  access_method_id: string;
  checked_at_iso: string;
  status: string;
  target_fingerprint: string;
  current_context?: string | null;
  cluster_server?: string | null;
  cluster_version?: string | null;
  capabilities: string[];
  checks: AccessCheck[];
  permission_gaps: Array<Record<string, unknown>>;
  metadata: Record<string, unknown>;
};

export type SnapshotSummary = {
  snapshot_id: string;
  environment_id: string;
  status: string;
  source_type: string;
  source_fingerprint: string;
  captured_at_iso: string;
  content_hash: string;
  summary: Record<string, unknown>;
  entity_count: number;
  relationship_count: number;
  assessment_count: number;
};

export type EnvironmentSummary = {
  environment_id: string;
  name: string;
  environment_class: string;
  provider: string;
  cluster_provider: string;
  host_provider?: string | null;
  criticality: string;
  fingerprint: string;
  active: boolean;
  updated_at: string;
  latest_validation?: AccessValidation | null;
  latest_snapshot?: SnapshotSummary | null;
  latest_health: OperationalProfileAssessment[];
};

export type EnvironmentDefinition = {
  environment_id: string;
  name: string;
  environment_class: "simulation" | "development" | "staging" | "production";
  provider: string;
  cluster_provider: string;
  host_provider?: string | null;
  criticality: string;
  access_methods: AccessMethodDefinition[];
  default_access_method_id?: string | null;
  operational_profile_ids: string[];
  installed_pack_ids: string[];
  labels: Record<string, string>;
  annotations: Record<string, string>;
  metadata: Record<string, unknown>;
  fingerprint?: string;
  latest_validation?: AccessValidation | null;
  snapshots?: SnapshotSummary[];
};

export type DiscoveryIssue = {
  issue_id: string;
  severity: string;
  collector_id: string;
  resource_type?: string | null;
  message: string;
  details: Record<string, unknown>;
};

export type OperationalProfileAssessment = {
  assessment_id: string;
  profile_id: string;
  profile_version: string;
  environment_id: string;
  snapshot_id: string;
  evaluated_at_iso: string;
  status: string;
  evaluations: InvariantEvaluation[];
  required_invariant_ids: string[];
  optional_invariant_ids: string[];
  violated_invariant_ids: string[];
  unknown_invariant_ids: string[];
  pending_invariant_ids: string[];
  counts: Record<string, number>;
  objective_impact: Record<string, string[]>;
  metadata: Record<string, unknown>;
};

export type OperationalProfileSpec = {
  profile_id: string;
  version: string;
  title: string;
  description: string;
  environment_classes: string[];
  objective_ids: string[];
  invariant_templates: Array<Record<string, unknown>>;
  metadata: Record<string, unknown>;
  content_hash: string;
};

export type EnvironmentSnapshot = {
  snapshot_id: string;
  environment_id: string;
  captured_at_iso: string;
  started_at_iso: string;
  completed_at_iso: string;
  status: string;
  source_type: string;
  source_fingerprint: string;
  entities: OperationalEntity[];
  relationships: Relationship[];
  observations: Array<Record<string, unknown>>;
  issues: DiscoveryIssue[];
  permission_gaps: Array<Record<string, unknown>>;
  raw_resource_count: number;
  collection_summary: Record<string, unknown>;
  raw_artifact_ids: string[];
  metadata: Record<string, unknown>;
  assessments: OperationalProfileAssessment[];
  artifacts: ArtifactSummary[];
  topology?: TopologyGraph;
  diff_from_previous?: SnapshotDiff | null;
};

export type TopologyGraph = {
  graph_id: string;
  environment_id: string;
  snapshot_id: string;
  generated_at_iso: string;
  entities: OperationalEntity[];
  relationships: Array<Relationship & {
    confidence?: number;
    provenance?: string;
    contract?: Record<string, unknown>;
  }>;
  layers: Record<string, string[]>;
  statistics: Record<string, unknown>;
  warnings: string[];
};

export type SnapshotDiff = {
  diff_id: string;
  environment_id: string;
  before_snapshot_id: string;
  after_snapshot_id: string;
  created_at_iso: string;
  entity_changes: Array<{
    entity_id: string;
    change_type: "added" | "removed" | "changed";
    before_hash?: string | null;
    after_hash?: string | null;
    field_changes: Array<{ path: string; before: unknown; after: unknown }>;
  }>;
  relationship_changes: Array<{
    relationship_id: string;
    change_type: "added" | "removed" | "changed";
  }>;
  summary: Record<string, number>;
};
