# KubeOps Release 0.3 architecture

## 1. Purpose

Release 0.3 adds a deterministic diagnosis layer between Release 0.2 health
assessment and future recovery planning.

The architecture answers five questions:

1. Which operational contracts are violated or unknown?
2. What normalized evidence currently exists?
3. Which causal families explain that evidence without contradiction?
4. Which bounded read-only probe would most reduce uncertainty?
5. What conclusion is sufficiently supported to certify now?

It intentionally does not answer “which mutation should be executed?”

## 2. Architectural pipeline

```text
EnvironmentSnapshot
  + TopologyGraph
  + OperationalProfileSpec
  + Snapshot history
        ↓
HealthAssessmentEngine
        ↓
OperationalProfileAssessment
        ↓
SymptomDeriver
        ↓
EvidencePlanner
        ↓
EvidenceExecutor (R0 collectors only)
        ↓
EvidenceFact set
        ↓
HypothesisEngine
        ↓
Hypothesis set + CausalEdge set
        ↓
ProbePlanner
        ↓
ProbePlan
        ↓
DiagnosisCertificateBuilder
        ↓
IncidentInvestigation
        ↓
Django projections + immutable artifacts + API/CLI/UI
```

All arrows exchange canonical, schema-versioned objects.

## 3. Evidence intents

An evidence intent describes a semantic question.

Example:

```text
Determine whether an API failure occurs at name resolution, route, transport,
TLS, authentication, or authorization.
```

It is not a command such as `kubectl describe`.

An intent declares:

- required fact types;
- optional fact types;
- applicable subjects;
- risk class;
- evidence-authority preference;
- stopping conditions.

This allows different providers and packs to answer the same question with
different collectors.

## 4. Collector definitions

A collector declares:

- identifier and version;
- supported source modes;
- produced fact types;
- prerequisites;
- estimated duration/load/cost;
- evidence authority;
- risk class;
- redaction behavior;
- failure semantics.

Release 0.3 enforces `R0` for all built-in collectors. A collector definition
cannot be registered as a read-only probe while carrying mutation semantics.

The collector plan is capability-aware. If Kubernetes API access is missing but
a recorded fixture or topology snapshot is available, the planner may use that
source. If no collector can produce a missing fact type, the hypothesis retains
that uncertainty rather than inventing a result.

## 5. Evidence facts

Evidence is normalized into stable semantic facts.

```yaml
evidence_id: evidence-...
fact_type: dependency.authenticated.false
statement: The worker's Kubernetes request was rejected as unauthenticated.
value: false
subject_ids: [deployment/builder, cluster/api-server]
collector_id: snapshot.authentication.v1
authority: authoritative
observed_at_iso: 2026-07-23T12:00:00Z
contradicts_evidence_ids: []
metadata:
  source_snapshot_id: snapshot-...
```

Raw Kubernetes objects remain available as artifacts, but hypotheses depend on
fact semantics rather than command-output strings.

## 6. Symptom derivation

The symptom layer translates health evaluation into causal input.

A symptom records:

- normalized family;
- statement;
- subject IDs;
- invariant source;
- severity;
- evidence references;
- whether it is direct, propagated, or an observability gap.

Unknown invariants can produce observability symptoms. They are not silently
ignored and are not treated as unhealthy facts.

## 7. Causal templates

A causal template is reusable diagnostic knowledge.

It declares:

- diagnostic family;
- optional parent family;
- applicable invariant and symptom families;
- required supporting fact patterns;
- contradictory fact patterns;
- predicted but potentially missing facts;
- claim template;
- specificity;
- generic-fallback status.

Templates are independent from concrete namespaces and resource names.
Specialized knowledge packs can register child templates later without changing
the hypothesis engine.

## 8. Hypothesis generation

For each symptom/template pairing, the engine computes:

- supporting evidence;
- contradicting evidence;
- unexplained symptoms;
- missing predicted fact types;
- confidence;
- status;
- parent hypothesis;
- applicability metadata.

Possible statuses include:

- proposed;
- supported;
- proven;
- contradicted;
- insufficient evidence;
- unsupported semantics.

Multiple hypotheses can remain active. The engine does not force a single root
cause when evidence supports several causal loci.

## 9. Parent-family fallback

A leaf failure may be hidden by the observation profile.

Example:

```text
World truth: credential omitted
Observed: consumer not serviceable
Hidden: provider authentication state
```

The correct result is often:

```text
component.not_serviceable
+ credential/authentication probes recommended
```

not an unsupported assertion that authentication definitely failed.

Release 0.3 therefore supports resolution at the nearest justified parent
family and explicitly reports the missing specialization.

## 10. Contradiction handling

Contradictory evidence is retained as first-class input.

A hypothesis can be:

- supported by one source;
- contradicted by another;
- downgraded because the contradiction is more authoritative or fresher;
- left unresolved when source authority is comparable.

The evidence model can link facts that contradict one another. The certificate
includes supporting, contradicting, and unresolved evidence references.

## 11. Probe planning

The probe planner starts with unresolved hypotheses and computes the fact types
that would discriminate them.

A probe is scheduled only when:

- it answers a declared evidence intent;
- at least one candidate collector can produce a missing fact type;
- required capabilities are available;
- risk is R0;
- it is not redundant with existing authoritative evidence;
- it fits the evidence budget.

Probe ranking considers:

- number of hypotheses discriminated;
- specificity of the produced fact;
- evidence authority;
- collection cost;
- redundancy;
- expected information gain.

Running a probe appends a `ProbeRun`, adds evidence facts, reruns hypothesis
scoring, creates a new probe plan, and reseals the current certificate.

## 12. Diagnosis certificate

A certificate is a bounded statement of what is known now.

It records:

- violated invariants;
- root or highest-supported hypotheses;
- causal chain;
- supporting evidence;
- contradictory evidence;
- ruled-out families;
- unresolved uncertainty;
- confidence;
- terminal status;
- recommended next evidence actions.

Terminal statuses include:

- `root_cause_identified`;
- `failure_class_identified`;
- `multiple_plausible_causes`;
- `insufficient_evidence`;
- `unknown_semantics`.

A certificate does not authorize a recovery action.

## 13. Incident state

`IncidentInvestigation` is the canonical aggregate.

It contains:

- environment/snapshot/profile identity;
- initial symptom and status;
- violated invariants;
- symptoms;
- evidence;
- hypotheses;
- probe plan and history;
- causal edges;
- timeline;
- diagnosis certificate;
- metadata.

The Django database stores relational projections for common queries, but the
canonical aggregate and immutable artifacts remain the fidelity boundary.

## 14. Simulation diagnostic adapter

`ScenarioDiagnosisEvaluator` adapts a simulation final snapshot into the same
health/evidence/diagnosis objects used for environment incidents.

The adapter:

1. Builds a synthetic compiled operational profile from scenario invariants.
2. Converts final invariant evaluations into a profile assessment.
3. Converts observed simulation state into normalized evidence facts.
4. Runs symptom derivation, hypothesis generation, probe planning, and
   certificate construction.
5. Compares the result with a `DiagnosticExpectation`.

It never reads simulation world truth when the observation profile hides it.

## 15. Observation-aware evaluation

Evaluation must distinguish architectural failure from legitimate uncertainty.

The basis therefore tests:

- full evidence identifies a leaf family;
- partial evidence identifies a supported parent family;
- contradictory evidence remains represented;
- hidden evidence produces probes rather than invented certainty;
- generic inherited disturbances may end as unknown semantics;
- probe budgets are respected.

## 16. Persistence model

Release 0.3 migration adds:

- `IncidentRecord`;
- `EvidenceFactRecord`;
- `HypothesisRecord`;
- `ProbeRunRecord`;
- `IncidentTimelineRecord`;
- `DiagnosisCertificateRecord`.

Evidence and hypothesis uniqueness is scoped per incident.

## 17. UI architecture

The incident workbench coordinates:

- persisted incident rail;
- summary metrics;
- evidence table;
- hypothesis cards/tree;
- probe controls;
- timeline;
- causal graph;
- certificate;
- artifact lineage.

The Scenario Lab uses `DiagnosticCaseResult` directly, avoiding a UI-specific
diagnosis representation.

## 18. Extension points

Knowledge packs can later add:

- evidence intents;
- collectors;
- fact normalizers;
- causal templates;
- probe semantics;
- certificate explanation metadata.

No extension can add mutation through the Release 0.3 collector interface.
Mutation requires the separate typed-action and policy kernel planned for
Release 0.4.
