# KubeOps Release 0.3

KubeOps is a typed operational reasoning platform for Kubernetes environments.
Release 0.3 turns the Release 0.2 read-only environment model into an
**evidence-driven diagnosis workbench** while retaining zero mutation authority.

The release can open an incident from an immutable environment snapshot,
derive normalized symptoms from violated operational contracts, plan bounded
read-only evidence collection, rank reusable causal hypotheses, retain
supporting and contradictory facts, recommend discriminating probes, refine an
investigation after each probe, and seal the current conclusion as a diagnosis
certificate.

Release 0.3 also connects this same diagnostic engine to the Scenario Lab. A
scenario family can be compiled, simulated, diagnosed, and evaluated against an
observation-aware expectation without introducing a separate test-only
reasoning path.

## Release 0.3 capabilities

- Versioned canonical models for:
  - evidence intents;
  - collector definitions and collection plans;
  - normalized evidence facts and collector receipts;
  - symptoms;
  - reusable causal templates and causal edges;
  - ranked hypotheses with support, contradiction, predictions, and unknowns;
  - probe intents, plans, and executions;
  - incident timelines and investigations;
  - diagnosis certificates;
  - diagnostic expectations, case results, and evaluation reports.
- A read-only diagnostic catalog containing evidence intents, collectors, and
  causal templates.
- Capability-aware collector planning based on unresolved semantic questions,
  available sources, evidence budgets, authority, cost, and redundancy.
- Deterministic hypothesis generation with:
  - parent-family fallback;
  - generic invariant-violation fallback;
  - contradiction preservation;
  - multiple simultaneous hypotheses;
  - explicit unsupported or insufficient-evidence results.
- Active probe planning that selects only collectors capable of supplying
  currently missing predicted fact types.
- Durable incident, evidence, hypothesis, probe, timeline, certificate, and
  artifact projections in the Django control plane.
- CLI flows for diagnostic catalog inspection, scenario diagnostic evaluation,
  incident opening, incident inspection, and probe execution.
- An interactive incident workbench for evidence, hypotheses, causal structure,
  probes, timeline, certificate, and artifact lineage.
- Scenario Lab v2 diagnostic evaluation with predicted-family and
  precision/recall feedback.
- A declared observation-aware diagnostic basis at
  `diagnostics/evaluation/basis-expectations.v1.yaml`.
- Complete preservation of Release 0.1 simulation and Release 0.2 read-only
  environment-intelligence functionality.

## Authority boundary

Release 0.3 remains read-only.

Every built-in collector is classified `R0`. The system can inspect snapshots,
topology, resources, relationships, historical state, and already-collected
facts. It cannot create, patch, delete, restart, drain, scale, or otherwise
mutate Kubernetes or host state.

```text
Immutable environment snapshot
        ↓
Operational-profile assessment
        ↓
Violated invariants
        ↓
Normalized symptoms
        ↓
Evidence intents
        ↓
Capability-aware R0 collection plan
        ↓
Evidence facts + contradictions
        ↓
Causal templates and ranked hypotheses
        ↓
Discriminating probe plan
        ↓
Refined investigation
        ↓
Diagnosis certificate + immutable incident artifacts
```

Diagnosis confidence never grants mutation authority. Typed actions, policy,
approval, and durable execution remain Release 0.4 concerns.

See:

- [Release 0.3 architecture](docs/architecture-release-03.md)
- [ADR 0003: read-only diagnosis boundary](docs/adr/0003-read-only-diagnosis-boundary.md)
- [Release 0.3 implementation manifest](IMPLEMENTATION_MANIFEST.md)
- [Release 0.3 validation record](VALIDATION.md)

## Applying the delta package

The distributed Release 0.3 archive contains only files added or modified since
Release 0.2. Extract it over the root of a complete Release 0.2 checkout while
preserving paths and replacing changed files.

No Release 0.2 paths are intentionally deleted.

## Quick start

### Docker

```bash
cp .env.example .env
docker compose up --build
```

Open:

- UI: `http://localhost:5173`
- API: `http://localhost:8000/api/v1/system/status`

### Local bootstrap

Linux/macOS:

```bash
./scripts/bootstrap.sh
./scripts/dev.sh
```

Windows PowerShell:

```powershell
.\scripts\bootstrap.ps1
.\scripts\dev.ps1
```

The bootstrap applies migrations through Release 0.3 and retains the existing
scenario catalog, operational profiles, and fixture-backed demonstration
environment.

## Fixture-backed diagnosis walkthrough

Collect the degraded fixture:

```bash
./scripts/kubeops.sh snapshot collect \
  environments/demo-kind-fixture.v1.yaml \
  --method-id recorded-degraded \
  --output /tmp/kubeops-degraded.json
```

Open a read-only investigation:

```bash
./scripts/kubeops.sh incident open \
  /tmp/kubeops-degraded.json \
  local-development-usable.v1 \
  --output /tmp/kubeops-incident.json \
  --artifacts /tmp/kubeops-artifacts
```

Inspect ranked hypotheses and recommended probes:

```bash
./scripts/kubeops.sh incident show /tmp/kubeops-incident.json
```

Run one recommended probe using its ID from the incident:

```bash
./scripts/kubeops.sh incident probe \
  /tmp/kubeops-incident.json \
  /tmp/kubeops-degraded.json \
  local-development-usable.v1 \
  <probe-id> \
  --output /tmp/kubeops-incident-refined.json \
  --artifacts /tmp/kubeops-artifacts
```

The probe does not mutate the fixture or cluster. It gathers additional facts,
re-ranks the hypotheses, updates the causal graph, regenerates the next probe
plan, and produces a new immutable artifact lineage.

## Diagnostic catalog

Inspect all built-in evidence intents, collectors, and causal templates:

```bash
./scripts/kubeops.sh diagnostic catalog
./scripts/kubeops.sh diagnostic catalog --category intent
./scripts/kubeops.sh diagnostic catalog --category collector
./scripts/kubeops.sh diagnostic catalog --category template
```

The initial catalog contains generic support for:

- required entity absent;
- invalid references or bindings;
- dependency endpoint unreachable;
- authentication failure;
- authorization failure;
- controller convergence failure;
- no feasible workload placement;
- component not serviceable;
- resource exhaustion;
- declared/observed state divergence;
- idempotency violation;
- observability gaps;
- generic operational-invariant violations.

These are reusable causal families, not error-string handlers.

## Scenario diagnostic evaluation

The Release 0.1 simulator and Release 0.3 diagnosis engine are connected through
one canonical evaluation path:

```bash
./scripts/kubeops.sh diagnostic evaluate \
  dependency.authentication_failure.v1 \
  --expected-family dependency.authentication_failure \
  --maximum-probe-count 8 \
  --output /tmp/auth-diagnostic-case.json
```

The result contains:

- predicted diagnostic families;
- certificate status;
- recommended probe count;
- expectation failures;
- precision and recall for the declared expectation;
- a complete generated `IncidentInvestigation`.

The web Scenario Lab exposes the same operation through **Run diagnostic
evaluation**.

## Observation-aware expectations

A concrete cause is not always observable from a given evidence profile.
Release 0.3 therefore does not require a hidden root cause to be guessed.

For example:

- Full authentication evidence should identify
  `dependency.authentication_failure`.
- Consumer-only evidence may correctly stop at `component.not_serviceable` and
  recommend credential probes.
- A generic inherited disturbance that produces no concrete violation may
  correctly terminate as `unknown_semantics`.

The included diagnostic basis encodes those distinctions explicitly rather than
marking every non-leaf result as a failure.

## Web workbench

### Incidents

The incident workspace supports:

- opening an investigation from an environment snapshot and operational profile;
- selecting persisted incidents;
- viewing initial symptom, impact, violated contracts, and certificate status;
- comparing root, supported, contradicted, and unresolved hypotheses;
- examining supporting and contradicting evidence;
- inspecting the causal edge graph;
- running recommended R0 probes;
- reviewing probe history and evidence deltas;
- following the investigation timeline;
- inspecting the diagnosis certificate;
- browsing the immutable incident artifact chain.

### Scenario Lab v2

The Scenario Lab retains topology, truth/observation switching, invariant
playback, event history, and run artifacts. Release 0.3 adds diagnostic
evaluation against a scenario-family expectation and exposes:

- predicted causal families;
- certificate status;
- recommended probe count;
- precision and recall;
- the generated incident and diagnosis certificate.

### Existing Release 0.2 surfaces

The environment registry, inventory, topology explorer, health matrix, snapshot
history, structural diff, and fixture export remain available.

## REST API additions

```text
GET  /api/v1/diagnostic-catalog
GET  /api/v1/diagnosis/coverage

GET  /api/v1/incidents
POST /api/v1/snapshots/{snapshot_id}/incidents
GET  /api/v1/incidents/{incident_id}
GET  /api/v1/incidents/{incident_id}/certificate
POST /api/v1/incidents/{incident_id}/probes/{probe_id}/run

POST /api/v1/scenarios/diagnose
```

`POST /api/v1/scenarios/diagnose` compiles and simulates a scenario, evaluates
the diagnostic pipeline against an optional `DiagnosticExpectation`, persists
the normal simulation artifacts, and returns a `DiagnosticCaseResult` with the
generated investigation.

## Incident artifact bundle

Every persisted investigation emits a content-addressed bundle containing:

```text
incident_investigation
evidence_set
hypothesis_set
causal_graph
incident_timeline
probe_history
probe_plan
diagnosis_certificate
incident_manifest
```

The manifest records derivation links so the certificate can be traced back to
the evidence, hypotheses, and probes that produced it.

## Compatibility

- Release 0.1 scenario, composition, simulator, schema, and artifact contracts
  remain supported.
- Release 0.2 environment, discovery, topology, health, snapshot, diff, fixture,
  API, CLI, and UI contracts remain supported.
- No live mutation endpoint or executor is introduced.
- New diagnostic models are versioned canonical IR objects rather than
  Django-only payloads.

## Next release boundary

Release 0.4 will add lifecycle planning and guarded execution foundations:

- startup and shutdown operational-profile planning;
- typed actions;
- risk classes and policy decisions;
- approval gates;
- durable, idempotent operation execution;
- low-risk local adapters;
- recovery verification and certificates.

Those capabilities will consume the Release 0.3 diagnosis certificates rather
than bypassing them.
