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
  desired_state: Record<string, unknown>;
  observed_state: Record<string, unknown>;
};

export type Relationship = {
  relationship_id: string;
  source_id: string;
  target_id: string;
  relationship_type: string;
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
