# Release 0.3 implementation manifest

Release 0.3 completes Epoch III of the phased plan: evidence-driven diagnosis,
active read-only investigation, and scenario-based diagnostic evaluation.

## Phase 9 — Evidence-intent and collector SDK

Implemented:

- Evidence-intent canonical schema.
- Collector-definition canonical schema.
- Normalized evidence facts and collection receipts.
- Collector catalog and registry integration.
- Collector planning by required fact type, mode, risk, authority, cost, and
  evidence budget.
- Fixture/snapshot/topology-backed R0 collector handlers.
- Explicit unsupported, missing-capability, and failed-collection semantics.
- Diagnostic catalog API, CLI, and schema exposure.

Initial intent coverage includes:

- endpoint path layering;
- authentication versus authorization;
- missing dependency or reference;
- workload placement;
- controller convergence;
- Service endpoint/serviceability;
- container initialization;
- resource pressure;
- declared/observed divergence;
- idempotent cleanup state.

## Phase 10 — Diagnosis engine v1

Implemented:

- Symptom derivation from violated and unknown profile invariants.
- Generic invariant-family normalization.
- Reusable causal templates.
- Deterministic hypothesis generation.
- Supporting and contradicting evidence sets.
- Evidence-prediction and missing-fact tracking.
- Parent-family fallback.
- Generic operational-invariant fallback.
- Multi-hypothesis ranking.
- Causal edges.
- Diagnosis certificates.
- Explicit unknown and insufficient-evidence results.

Initial causal-family coverage:

- required entity absent;
- invalid binding/reference;
- endpoint unreachable;
- authentication failure;
- authorization failure;
- controller convergence failure;
- no feasible placement;
- component not serviceable;
- resource exhaustion;
- state divergence;
- idempotency violation;
- observability gap;
- generic operational-invariant violation.

## Phase 11 — Probe planner

Implemented:

- Probe intent construction from unresolved hypotheses.
- Missing predicted-fact calculation.
- Candidate collector capability matching.
- Information-gain scoring.
- Cost, authority, and redundancy weighting.
- Evidence-budget enforcement.
- Probe receipts.
- Investigation refinement and next-probe replanning.
- Read-only probe API, CLI, and UI execution.

## Phase 12 — Scenario Lab v2 and diagnostic evaluation

Implemented:

- Simulation-final-state evidence adapter.
- Scenario-to-operational-profile assessment adapter.
- Diagnostic expectation schema.
- Case result and aggregate report schemas.
- Precision, recall, confidence, status, and probe-count checks.
- Observation-aware basis expectations.
- Scenario diagnostic API and CLI.
- Scenario Lab evaluation panel.
- Diagnosis coverage endpoint for persisted incidents.

## Persistence

Added relational projections for:

- incidents;
- evidence facts;
- hypotheses;
- probe runs;
- incident timeline entries;
- diagnosis certificates.

The canonical incident payload remains authoritative while relational
projections support querying and UI workflows.

## Artifact contract

Added immutable artifact types:

- `incident_investigation`
- `evidence_set`
- `hypothesis_set`
- `causal_graph`
- `incident_timeline`
- `probe_history`
- `probe_plan`
- `diagnosis_certificate`
- `incident_manifest`

## UI implementation

Added:

- Incidents primary navigation.
- Snapshot/profile incident-opening flow.
- Incident summary metrics.
- Evidence table with authority and contradiction context.
- Hypothesis tree/cards with support and missing predictions.
- Probe recommendations and execution.
- Timeline and causal views.
- Diagnosis certificate and artifact exploration.
- Scenario Lab v2 diagnostic evaluation.

## Compatibility retained

- Canonical scenario IR and family compiler.
- Composition compiler.
- Deterministic simulator.
- Environment registry and access validation.
- Discovery, sanitization, snapshots, fixture replay, and structural diff.
- Topology compiler and health profiles.
- Existing REST, CLI, and web workbenches.

## Explicit exclusions

- Mutating probes.
- Recovery planning.
- Typed action execution.
- Approval workflows.
- Startup/shutdown orchestration.
- Rollback.
- Recovery verification.
- Autonomous repair.
