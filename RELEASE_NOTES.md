# KubeOps Release 0.3 — Read-Only Diagnosis Workbench

## Summary

Release 0.3 adds active, evidence-driven investigation on top of the immutable
snapshots, topology, and operational profiles delivered in Release 0.2. It
introduces no mutation authority.

The release can now transform violated invariants into normalized symptoms,
select bounded R0 collectors, derive reusable causal hypotheses, preserve
contradictions and uncertainty, recommend discriminating probes, refine an
incident after probe execution, and issue a structured diagnosis certificate.
The same pipeline is available against live/fixture snapshots and deterministic
simulations.

## Added

### Canonical diagnosis IR

- `EvidenceIntent`
- `CollectorDefinition`
- `EvidenceFact`
- `EvidenceCollectionPlan`
- `CollectorRunResult`
- `Symptom`
- `CausalTemplate`
- `CausalEdge`
- `Hypothesis`
- `ProbeIntent`
- `ProbePlan`
- `ProbeRun`
- `IncidentTimelineEntry`
- `IncidentInvestigation`
- `DiagnosisCertificate`
- `DiagnosticExpectation`
- `DiagnosticCaseResult`
- `DiagnosticEvaluationReport`

All are schema-versioned Pydantic models and participate in the canonical
registry and JSON Schema API.

### Evidence and collection

- Semantic evidence intents describe questions rather than commands.
- Collector definitions declare produced fact types, supported modes, cost,
  authority, risk, prerequisites, and redaction behavior.
- All built-in collectors are `R0` and read-only.
- Collector planning respects evidence budgets and avoids collectors that cannot
  resolve current hypothesis uncertainty.
- Evidence facts retain subject, collector, authority, freshness, value,
  statement, and provenance.

### Diagnosis

- Deterministic symptom derivation from operational-profile assessments.
- Reusable causal-template catalog.
- Support and contradiction scoring.
- Parent-family and generic-invariant fallback.
- Multiple simultaneous hypotheses.
- Explicit `insufficient_evidence`, `unknown_semantics`, and
  `multiple_plausible_causes` outcomes.
- Causal-edge generation and diagnosis certificates.

### Probe planning

- Missing predicted fact types are computed per unresolved hypothesis.
- Candidate collectors are filtered by actual fact-production capability.
- Probe ranking considers information gain, cost, authority, and redundancy.
- Probe execution appends evidence and receipts, then reruns the deterministic
  diagnosis pipeline.

### Scenario evaluation

- Deterministic simulation-to-diagnosis adapter.
- Observation-aware `DiagnosticExpectation` assertions.
- Case metrics for precision, recall, confidence, and probe count.
- Aggregate evaluation report support.
- Declared Release 0.3 basis cases covering full, partial, unknown, and
  consumer-only observation profiles.
- Scenario Lab v2 and `/api/v1/scenarios/diagnose`.

### Persistence and artifacts

Django projections were added for:

- incidents;
- evidence facts;
- hypotheses;
- probe runs;
- incident timeline entries;
- diagnosis certificates.

Every incident persists a content-addressed artifact chain containing the
canonical investigation, evidence, hypotheses, causal graph, timeline, probes,
certificate, and manifest.

### API, CLI, and UI

Added API routes for:

- diagnostic catalog;
- diagnosis coverage;
- incident creation/list/detail;
- probe execution;
- certificate retrieval;
- simulated diagnostic evaluation.

Added CLI commands:

- `diagnostic catalog`
- `diagnostic evaluate`
- `incident open`
- `incident show`
- `incident probe`

Added UI capabilities:

- incident rail and snapshot-based incident creation;
- hypothesis comparison;
- evidence and contradiction inspection;
- probe planning and execution;
- causal/timeline/certificate/artifact views;
- Scenario Lab diagnostic evaluation.

## Correctness fixes made during implementation

- Evidence and hypothesis persistence uniqueness is scoped to an incident,
  preventing IDs from conflicting across separate investigations.
- Probe selection now requires a collector to produce a currently missing fact
  type; a broadly related but non-discriminating collector is not scheduled.
- Incident artifacts include scope in their content-addressed identity, avoiding
  collisions between structurally similar investigations.
- Simulation diagnostics preserve partial-observation semantics instead of
  inferring hidden truth.
- Scenario evaluation expectations were made observation-aware so a correct
  parent-family diagnosis under consumer-only evidence is not treated as a
  failed leaf diagnosis.
- Scenario Lab TypeScript uses the canonical `DiagnosticCaseResult` rather than
  a UI-only evaluation shape.

## Compatibility

- All Release 0.1 and Release 0.2 unit behavior remains supported.
- The API continues to expose previous scenario, environment, snapshot,
  topology, health, diff, profile, and artifact routes.
- No existing repository path is intentionally deleted.
- The distributed archive is a Release 0.2 → 0.3 delta containing only new and
  modified paths.

## Deliberate boundary

Release 0.3 can recommend evidence-gathering probes only. It cannot execute
mutating probes, create recovery plans, approve actions, or change cluster or
host state.
