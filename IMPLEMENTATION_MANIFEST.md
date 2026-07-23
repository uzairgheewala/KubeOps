# Release 0.2 implementation manifest

Release 0.2 completes the planned read-only environment-intelligence checkpoint
while preserving every Release 0.1 simulation capability.

## Phase 5 — Environment registry and access model

Implemented:

- Environment and access-method canonical IR.
- Fixture, kubectl-context, and explicit-kubeconfig resolution.
- Read-only validation with target fingerprint, version, capability, and
  permission-gap results.
- Django environment and validation persistence.
- Environment registration UI and CLI.

## Phase 6 — Discovery and snapshot engine

Implemented:

- Common `DiscoverySource` and `RawCollection` contracts.
- Fixture and live `kubectl` collectors.
- Mandatory Secret and sensitive-field sanitization.
- Resource normalization into `ResourceDocument`, entity, observation, and base
  relationship representations.
- Partial-success issues and permission gaps.
- Immutable snapshots and content-addressed artifacts.
- Structural entity/relationship snapshot diffing.
- Replayable fixture export.

## Phase 7 — Topology compiler and explorer

Implemented resolvers for:

- Namespace containment.
- Owner references and controller chains.
- Workload and Pod relationships.
- Pod scheduling and ServiceAccount identity.
- ConfigMap, Secret, and PVC references.
- Service selector matches.
- EndpointSlice membership.
- Ingress routing.
- PV/PVC/StorageClass binding.
- RoleBinding subject and role references.

UI implementation:

- Inventory explorer.
- Layered topology graph.
- Namespace, plane, text, and health filtering.
- Entity and edge inspectors with provenance.

## Phase 8 — Invariant engine and operational profiles

Implemented:

- Entity-selector profile templates.
- Profile registry and deterministic compilation.
- Graph-aware predicates.
- Temporal assessment over snapshot history.
- Explicit unknown/pending/not-applicable outcomes.
- Required versus optional aggregation.
- Cluster-observable and local-development-usable seed profiles.
- Health matrix and profile assessment API/CLI/UI.

## Persistence and artifacts

Added relational projections for:

- Environments.
- Access validations.
- Environment snapshots.
- Per-snapshot entities and relationships.
- Operational profiles.
- Profile assessments.
- Generalized operational artifacts.

Every collection persists:

- Raw sanitized discovery bundle.
- Environment snapshot.
- Topology graph.
- Profile assessments.
- Optional diff.
- Snapshot manifest.

## Compatibility retained

- Canonical scenario IR and schemas.
- Scenario-family compiler.
- Composition compiler.
- Deterministic simulator.
- Release 0.1 run artifacts.
- Scenario/Composition Labs.
- Existing scenario API and CLI commands.

## Explicit exclusions

- Diagnosis engine.
- Active probe planning.
- Mutating collectors.
- Typed action execution.
- Startup/shutdown orchestration.
- Recovery planning or verification.
