# KubeOps Release 0.2 — Read-Only Environment Intelligence

## Summary

Release 0.2 connects the Release 0.1 operational metamodel to real and recorded
Kubernetes state without introducing mutation authority. Environments can be
registered, access can be validated, cluster objects can be sanitized and
normalized, dependency topology can be compiled, health profiles can be
evaluated, snapshots can be diffed, and the complete evidence chain can be
explored through the CLI, API, and UI.

## Added

### Environment and access model

- Versioned `EnvironmentDefinition` and `AccessMethodDefinition` schemas.
- Fixture, `kubectl`, and explicit-kubeconfig access routes.
- Target fingerprinting, context/server/version checks, capability reporting,
  and permission-gap representation.
- Fixture-backed demo environment with healthy and degraded access methods.

### Discovery and snapshots

- Common discovery-source contract.
- Bounded read-only `kubectl` source.
- Deterministic fixture source.
- Mandatory resource sanitization before canonicalization and persistence.
- `ResourceDocument`, `DiscoveryBundle`, `EnvironmentSnapshot`, and structural
  `SnapshotDiff` contracts.
- Immutable content-addressed snapshot artifact chains.
- Replayable sanitized fixture export.

### Topology

- Generic topology compiler for ownership, control, scheduling, identity,
  configuration, secrets, storage, Service selectors, EndpointSlices, ingress,
  and RBAC.
- Relationship confidence and provenance.
- Graph warnings for unresolved or inconsistent references.
- Upstream/downstream traversal-ready `TopologyGraph` representation.

### Operational health

- Operational-profile registry and compiler.
- Entity selectors and invariant templates.
- Graph-aware predicates such as related-entity cardinality.
- Immediate and temporal evaluation over snapshot history.
- Required/optional check aggregation with explicit healthy, unhealthy, pending,
  unknown, and not-applicable states.
- Seed profiles for cluster observability and local-development usability.

### Control plane and UI

- Relational persistence for environments, validations, snapshots, entities,
  relationships, profiles, assessments, and generalized artifacts.
- Read-only environment, snapshot, topology, diff, health, profile, and export
  APIs.
- Environment registry and onboarding UI.
- Inventory, topology, health, snapshot history, diff, and artifact workspaces.
- Release 0.1 scenario and composition workbenches retained.

### CLI

- `environment validate` and `environment show`.
- `snapshot collect`, `snapshot show`, and `snapshot diff`.
- `profile list`, `profile show`, and `profile evaluate`.

## Correctness fixes made during implementation

- EndpointSlice Service ownership now reads Kubernetes label maps directly;
  label keys containing dots and slashes are never treated as dotted state paths.
- Fixture export now reconstructs the public replay format instead of exposing
  an internal discovery-bundle payload.
- The previously referenced but absent Release 0.1 artifact-store module is now
  materialized and used by both simulation and environment snapshots.
- UI TypeScript project references now validate both application and Vite
  configuration graphs in dependency-constrained environments.

## Compatibility

- Release 0.1 scenario-family, composition, simulation, artifact, API, and UI
  contracts remain supported.
- No existing files are intentionally deleted.
- The distributed archive is a Release 0.1 → 0.2 delta containing only new and
  modified paths.

## Deliberate boundary

Release 0.2 is read-only. It does not execute probes requiring mutation, restart
workloads, patch resources, perform lifecycle transitions, or produce recovery
plans. Those authority-bearing behaviors remain deferred.
