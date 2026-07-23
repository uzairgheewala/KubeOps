# Release 0.3 validation record

## Executed in this delivery environment

### Python and retained behavior

- 39 unit tests passed.
- Every retained Release 0.1 and Release 0.2 unit test passed.
- Python bytecode compilation passed for:
  - `packages/kubeops_core`;
  - `packages/kubeops_cli`;
  - `control_plane`;
  - `tests`.
- All repository JSON, YAML, and YML source/configuration files parsed.
- All Linux shell scripts passed `bash -n`.

The sandbox does not contain `pytest-django`, so pytest reports the existing
`DJANGO_SETTINGS_MODULE` option as unknown when only the dependency-free unit
suite is run. This does not affect the unit results.

### Canonical model and registry

- 37 canonical IR schemas generated valid JSON Schema documents.
- The built-in canonical registry contained 137 entries before loading external
  scenario families, operational profiles, and diagnostic catalog entries.
- New diagnostic models completed deterministic validation and serialization.
- Evidence and hypothesis cross-references were validated.
- Incident aggregates rejected unknown evidence and parent-hypothesis links.

### Diagnostic catalog

Validated:

- 10 evidence intents.
- 13 built-in collectors.
- 13 causal templates, including the generic fallback.
- Every built-in collector is risk class `R0`.
- Collector plans selected only collectors that could produce a currently
  missing required fact type.
- Evidence budgets and collector redundancy checks were enforced.

### Unit diagnosis behavior

Validated:

- symptom derivation from unhealthy and unknown invariants;
- required-entity diagnosis;
- invalid binding/reference diagnosis;
- endpoint reachability diagnosis;
- authentication versus authorization separation;
- controller convergence diagnosis;
- serviceability fallback;
- parent-family fallback under partial observation;
- contradiction retention;
- unknown-semantics and insufficient-evidence outcomes;
- probe planning and refinement;
- diagnosis-certificate construction;
- incident artifact generation and derivation links;
- simulation diagnostic evaluation and aggregate reports.

### Declared diagnostic basis

All 10 cases in
`diagnostics/evaluation/basis-expectations.v1.yaml` passed.

The basis includes:

- full-observation leaf diagnosis;
- consumer-only parent-family diagnosis;
- controller-only/resource-only evidence;
- generic inherited disturbances;
- insufficient evidence;
- unknown semantics;
- probe-budget limits.

This explicitly validates that the evaluator respects observation boundaries
instead of reading hidden simulation truth.

### Generative scenario matrix

All 25 valid combinations across the current nonabstract scenario families,
disturbances, and observation profiles:

- compiled;
- simulated;
- produced final invariant state;
- entered the Release 0.3 diagnosis pipeline;
- produced a diagnosis certificate;
- completed without exceptions.

Certificate outcomes across the matrix:

- 11 `root_cause_identified`;
- 4 `failure_class_identified`;
- 2 `multiple_plausible_causes`;
- 2 `insufficient_evidence`;
- 6 `unknown_semantics`.

These differences are intentional consequences of disturbance and observation
profiles, not forced leaf classifications.

### Randomized fixture-backed investigations

100 randomized development/staging environment identities were bound to the
sanitized degraded Kind fixture.

Every iteration:

- retained the fixture topology;
- evaluated `local-development-usable.v1`;
- opened an incident;
- produced normalized evidence;
- generated hypotheses;
- generated a diagnosis certificate;
- preserved the read-only collector boundary.

All 100 produced a valid `multiple_plausible_causes` certificate for the fixture,
which contains separate unhealthy Deployment and Pod causal loci.

### CLI workflow

Executed successfully:

```text
snapshot collect
incident open
incident show
incident probe
diagnostic catalog
diagnostic evaluate
```

The end-to-end fixture workflow produced:

- 25 initial evidence facts;
- 33 evidence facts after one probe;
- one persisted probe receipt;
- a refined diagnosis certificate;
- 18 incident artifact JSON files across initial and refined artifact chains;
- a passing simulated diagnostic evaluation.

### Incident artifacts

Validated generation of:

- incident investigation;
- evidence set;
- hypothesis set;
- causal graph;
- timeline;
- probe history;
- probe plan;
- diagnosis certificate;
- incident manifest.

Artifact identities are content-addressed and incident-scoped. Derivation links
connect the manifest and certificate to their source evidence and hypothesis
artifacts.

### TypeScript

- The actual `tsc -b` project-reference graph passed for the complete UI and
  Vite configuration source.
- The check used temporary ambient React/Vite declarations inside a disposable
  `node_modules` directory because the pinned npm packages are unavailable in
  this sandbox.
- The temporary declarations, TypeScript build-info files, and `node_modules`
  were removed before packaging.

Validated Release 0.3 UI types and flows include:

- diagnostic catalog;
- incident summaries and investigations;
- evidence, hypotheses, probes, timeline, certificate, and artifacts;
- snapshot-based incident creation;
- probe execution;
- Scenario Lab diagnostic evaluation.

## Dependency-gated checks

This sandbox does not contain Django, Django REST Framework, pytest-django,
Hypothesis, React, or Vite runtime packages, and package installation is not
available through its mirror. Therefore the following were not executed here:

- Django migration application.
- Django/DRF integration tests.
- Actual API server startup.
- Hypothesis property suite.
- Vite production bundle.
- Browser runtime interaction tests.

The migration, expanded integration suite, pinned dependencies, Docker setup,
and CI paths are included.

## Expected full validation matrix after normal bootstrap

```bash
ruff check packages control_plane tests
mypy packages/kubeops_core/kubeops_core
pytest --cov --cov-report=term-missing
cd ui && npm run build
```

The expanded Django integration tests cover:

- Release 0.3 system status and diagnostic catalog;
- snapshot-based incident creation;
- incident detail and artifact retrieval;
- probe execution;
- diagnosis certificate retrieval;
- simulated scenario diagnosis.
