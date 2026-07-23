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
  incident_count?: number;
  diagnostic_intent_count?: number;
  diagnostic_collector_count?: number;
  causal_template_count?: number;
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

export type EvidenceFact = {
  evidence_id: string;
  fact_type: string;
  statement: string;
  value: unknown;
  subject_ids: string[];
  intent_id?: string | null;
  collector_id: string;
  observed_at_iso: string;
  authority: string;
  freshness_seconds: number;
  source_artifact_ids: string[];
  attributes: Record<string, unknown>;
};

export type Symptom = {
  symptom_id: string;
  symptom_type: string;
  statement: string;
  subject_ids: string[];
  invariant_id?: string | null;
  invariant_family?: string | null;
  health_status?: string | null;
  causal_role: string;
  confidence: number;
  evidence_ids: string[];
  metadata: Record<string, unknown>;
};

export type Hypothesis = {
  hypothesis_id: string;
  family_id: string;
  claim: string;
  template_id?: string | null;
  parent_hypothesis_id?: string | null;
  subject_ids: string[];
  status: string;
  confidence: number;
  explains_symptom_ids: string[];
  unexplained_symptom_ids: string[];
  supporting_evidence_ids: string[];
  contradicting_evidence_ids: string[];
  required_probe_ids: string[];
  predictions: string[];
  score_components: Record<string, number>;
  metadata: Record<string, unknown>;
};

export type CausalEdge = {
  edge_id: string;
  source_id: string;
  target_id: string;
  relation: string;
  statement: string;
  confidence: number;
  evidence_ids: string[];
};

export type ProbeIntent = {
  probe_id: string;
  title: string;
  evidence_intent_id: string;
  applicable_hypothesis_ids: string[];
  discriminates_hypothesis_ids: string[];
  candidate_collector_ids: string[];
  expected_outcomes: Record<string, string[]>;
  preconditions: string[];
  rationale: string;
  information_gain_score: number;
  cost_score: number;
  risk_class: string;
  status: string;
  metadata: Record<string, unknown>;
};

export type ProbePlan = {
  plan_id: string;
  incident_id: string;
  created_at_iso: string;
  probes: ProbeIntent[];
  stopping_reason?: string | null;
  evidence_budget?: number | null;
  metadata: Record<string, unknown>;
};

export type ProbeRun = {
  probe_run_id: string;
  incident_id: string;
  probe: ProbeIntent;
  status: string;
  started_at_iso: string;
  completed_at_iso: string;
  evidence_ids: string[];
  hypothesis_changes: Record<string, unknown>;
};

export type DiagnosisCertificate = {
  certificate_id: string;
  incident_id: string;
  issued_at_iso?: string | null;
  violated_invariant_ids: string[];
  causal_chain: string[];
  causal_edges: CausalEdge[];
  root_cause_hypothesis_ids: string[];
  ruled_out_hypothesis_ids: string[];
  unresolved_hypothesis_ids: string[];
  unresolved_questions: string[];
  evidence_ids: string[];
  status: string;
  confidence: number;
  nearest_supported_family_ids: string[];
  metadata: Record<string, unknown>;
};

export type IncidentTimelineEntry = {
  sequence: number;
  occurred_at_iso: string;
  event_type: string;
  title: string;
  subject_ids: string[];
  artifact_ids: string[];
  details: Record<string, unknown>;
};

export type IncidentSummary = {
  incident_id: string;
  environment_id: string;
  snapshot_id: string;
  profile_id: string;
  title: string;
  initial_symptom: string;
  status: string;
  certificate_status?: string | null;
  confidence: number;
  symptom_count: number;
  evidence_count: number;
  hypothesis_count: number;
  recommended_probe_count: number;
  updated_at: string;
};

export type IncidentInvestigation = {
  incident_id: string;
  environment_id: string;
  snapshot_id: string;
  profile_id: string;
  title: string;
  initial_symptom: string;
  status: string;
  created_at_iso: string;
  updated_at_iso: string;
  assessment_id?: string | null;
  violated_invariant_ids: string[];
  symptoms: Symptom[];
  evidence: EvidenceFact[];
  hypotheses: Hypothesis[];
  probe_plan?: ProbePlan | null;
  probe_runs: ProbeRun[];
  causal_edges: CausalEdge[];
  timeline: IncidentTimelineEntry[];
  certificate?: DiagnosisCertificate | null;
  metadata: Record<string, unknown>;
  artifacts?: ArtifactSummary[];
};

export type DiagnosticCatalog = {
  intents: Array<Record<string, unknown>>;
  collectors: Array<Record<string, unknown>>;
  causal_templates: Array<Record<string, unknown>>;
  counts: { intents: number; collectors: number; causal_templates: number };
  read_only: boolean;
};

export type DiagnosticCaseResult = {
  case_id: string;
  scenario_id: string;
  passed: boolean;
  certificate_status: string;
  predicted_family_ids: string[];
  expected_family_ids: string[];
  probe_count: number;
  metrics: Record<string, number>;
  failures: string[];
  incident?: IncidentInvestigation | null;
  run?: SimulationRun;
  scenario?: ScenarioInstance;
  artifacts?: ArtifactSummary[];
};

export type RiskAssessment = {
  risk_class: "R0" | "R1" | "R2" | "R3" | "R4" | "R5";
  blast_radius: string;
  availability_risk: string;
  data_risk: string;
  security_risk: string;
  reversible: boolean;
  idempotent: boolean;
  rationale: string[];
};

export type ActionTypeDefinition = {
  action_type_id: string;
  title: string;
  description: string;
  required_capabilities: string[];
  supported_modes: string[];
  executor_id: string;
  default_risk: RiskAssessment;
  expected_effects: string[];
  possible_side_effects: string[];
  rollback_action_type_id?: string | null;
};

export type PlannedAction = {
  action_id: string;
  action_type_id: string;
  title: string;
  target_ids: string[];
  parameters: Record<string, unknown>;
  depends_on_action_ids: string[];
  risk: RiskAssessment;
  status: string;
  idempotency_key?: string | null;
  stage_id?: string | null;
  checkpoint_before: boolean;
  optional: boolean;
  metadata: Record<string, unknown>;
};

export type RecoveryPlan = {
  plan_id: string;
  incident_id?: string | null;
  environment_id?: string | null;
  operation_type: string;
  objective_id: string;
  target_invariant_ids: string[];
  protected_invariant_ids: string[];
  actions: PlannedAction[];
  verification_condition_ids: string[];
  mode: string;
  policy_id?: string | null;
  assumptions: string[];
  unsupported_assumptions: string[];
  created_at_iso?: string | null;
  metadata: Record<string, unknown>;
};

export type LifecycleProfile = {
  profile_id: string;
  version: string;
  title: string;
  description: string;
  operation_type: "startup" | "shutdown" | "maintenance";
  environment_classes: string[];
  target_operational_profile_id: string;
  protected_invariant_ids: string[];
  default_policy_id?: string | null;
  stages: Array<{
    stage_id: string;
    title: string;
    description: string;
    depends_on_stage_ids: string[];
    action_templates: Array<Record<string, unknown>>;
    timeout_seconds: number;
    on_failure: string;
  }>;
  metadata: Record<string, unknown>;
};

export type ExecutionPolicy = {
  policy_id: string;
  title: string;
  environment_classes: string[];
  allowed_risk_classes: string[];
  allowed_action_type_ids: string[];
  denied_action_type_ids: string[];
  required_approvals_by_risk: Record<string, number>;
  maximum_concurrent_actions: number;
  require_checkpoint_for_risk: string[];
  require_target_fingerprint: boolean;
  mutation_budget?: number | null;
  capability_grants: string[];
  break_glass_allowed: boolean;
};

export type PolicyDecision = {
  decision_id: string;
  policy_id: string;
  action_id: string;
  outcome: "allow" | "deny" | "approval_required";
  reasons: string[];
  required_approval_count: number;
  capability_gaps: string[];
  requires_checkpoint: boolean;
};

export type OperationApproval = {
  approval_id: string;
  operation_id: string;
  action_id?: string | null;
  approver_id: string;
  decision: string;
  reason: string;
  granted_at_iso: string;
};

export type ActionReceipt = {
  receipt_id: string;
  operation_id: string;
  action_id: string;
  action_type_id: string;
  executor_id: string;
  status: string;
  attempt: number;
  started_at_iso: string;
  completed_at_iso: string;
  exit_code?: number | null;
  stdout: string;
  stderr: string;
  observed_effects: string[];
  idempotency_key?: string | null;
  metadata: Record<string, unknown>;
};

export type ExecutionCheckpoint = {
  checkpoint_id: string;
  operation_id: string;
  created_at_iso: string;
  completed_action_ids: string[];
  pending_action_ids: string[];
  failed_action_ids: string[];
  state_hash: string;
  resumable: boolean;
};

export type VerificationResult = {
  result_id: string;
  condition_id: string;
  status: string;
  evaluated_at_seconds: number;
  explanation: string;
  evidence_ids: string[];
  actual_value: unknown;
};

export type RecoveryCertificate = {
  certificate_id: string;
  incident_id?: string | null;
  operation_id?: string | null;
  plan_id: string;
  status: string;
  restored_invariant_ids: string[];
  unresolved_invariant_ids: string[];
  action_receipt_ids: string[];
  verification_result_ids: string[];
  residual_risks: string[];
  metadata: Record<string, unknown>;
};

export type OperationTimelineEvent = {
  sequence: number;
  operation_id: string;
  event_type: string;
  occurred_at_iso: string;
  title: string;
  action_id?: string | null;
  artifact_ids: string[];
  details: Record<string, unknown>;
};

export type OperationRun = {
  operation_id: string;
  environment_id: string;
  operation_type: string;
  objective_id: string;
  status: string;
  mode: string;
  plan: RecoveryPlan;
  policy_decisions: PolicyDecision[];
  approvals: OperationApproval[];
  action_receipts: ActionReceipt[];
  verification_results: VerificationResult[];
  recovery_certificate?: RecoveryCertificate | null;
  events: OperationTimelineEvent[];
  checkpoints: ExecutionCheckpoint[];
  current_action_ids: string[];
  created_at_iso: string;
  updated_at_iso: string;
  started_at_iso?: string | null;
  completed_at_iso?: string | null;
  pause_reason?: string | null;
  failure_reason?: string | null;
  metadata: Record<string, unknown>;
  artifacts?: ArtifactSummary[];
};

export type OperationSummary = {
  operation_id: string;
  environment_id: string;
  snapshot_id?: string | null;
  incident_id?: string | null;
  operation_type: string;
  objective_id: string;
  status: string;
  mode: string;
  plan_id: string;
  policy_id?: string | null;
  certificate_status?: string | null;
  action_count: number;
  receipt_count: number;
  approval_count: number;
  updated_at: string;
};

export type PackValidationIssue = {
  code: string;
  severity: "info" | "warning" | "error";
  message: string;
  pack_id?: string | null;
  contribution_id?: string | null;
  details: Record<string, unknown>;
};

export type PackScenarioCoverage = {
  family_ids: string[];
  invariant_families: string[];
  disturbance_mechanisms: string[];
  topology_patterns: string[];
  support_level: string;
};

export type KnowledgePackManifest = {
  pack_id: string;
  version: string;
  title: string;
  pack_kind: string;
  description: string;
  priority: number;
  dependencies: Array<{ pack_id: string; version_constraint: string; optional: boolean; reason: string }>;
  conflicts_with: string[];
  compatibility: Record<string, unknown>;
  capabilities: string[];
  supported_entity_types: string[];
  contributions: Record<string, unknown[]>;
  metadata: Record<string, unknown>;
};

export type PackStatus = {
  pack_id: string;
  version: string;
  state: string;
  source: string;
  enabled: boolean;
  resolved_dependencies: string[];
  contribution_counts: Record<string, number>;
  issues: PackValidationIssue[];
  manifest_hash: string;
};

export type PackResolution = {
  resolution_id: string;
  created_at_iso: string;
  requested_pack_ids: string[];
  ordered_pack_ids: string[];
  active_pack_ids: string[];
  blocked_pack_ids: string[];
  statuses: PackStatus[];
  issues: PackValidationIssue[];
  contribution_counts: Record<string, number>;
};

export type PackCoverageReport = {
  generated_at_iso: string;
  active_pack_ids: string[];
  by_pack: Record<string, PackScenarioCoverage[]>;
  family_support: Record<string, Array<{ pack_id: string; support_level: string }>>;
  invariant_support: Record<string, Array<{ pack_id: string; support_level: string }>>;
  gaps: string[];
};

export type PackCatalogResponse = {
  packs: Array<{ manifest: KnowledgePackManifest; source: string; status: PackStatus | null }>;
  resolution: PackResolution;
  coverage: PackCoverageReport;
};
