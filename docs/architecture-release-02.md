# Release 0.2 detailed architecture

## 1. Authority boundary

Release 0.2 introduces read-only live-cluster authority. It may invoke bounded
`kubectl` discovery and authorization checks, but no collector or API path is
permitted to create, patch, delete, restart, scale, drain, or otherwise mutate
the target.

This boundary is structural:

- Access methods declare `read_only: true`.
- Discovery sources expose validation and collection only.
- No executor registry is connected to the environment-intelligence service.
- Future action schemas remain inert Release 0.1 IR objects.

## 2. Environment registry

`EnvironmentDefinition` is the user-facing target contract. It describes the
environment class, providers, criticality, operational profiles, knowledge
packs, labels, and one or more access methods.

Access methods are references to a way of reading state, not embedded secrets.
A future secret-provider integration can resolve `credential_ref` without
changing the environment schema.

The environment content hash is stored as a fingerprint of the declaration.
Access validation separately records the observed target fingerprint so a
caller can detect that a context now points somewhere unexpected.

## 3. Discovery-source abstraction

The source interface produces a `RawCollection`:

```text
validate(environment, method)
collect(environment, method, resource_types)
```

Implemented adapters:

- `FixtureDiscoverySource`: deterministic file replay.
- `KubectlDiscoverySource`: bounded read-only commands against a selected
  context or kubeconfig.

Source-specific details end at this boundary. The remainder of the pipeline
consumes the same dictionaries and metadata.

## 4. Sanitization boundary

Sanitization occurs before `ResourceDocument` creation. Secret values and
sensitive token/certificate material are removed before canonical entity,
observation, snapshot, artifact, API, or UI models can receive them.

Key names remain visible because they are required for future reference-integrity
and missing-key reasoning. Redaction is therefore semantic, not merely a UI
mask.

## 5. Normalization

The normalizer converts sanitized objects into provider-neutral entities while
retaining the source object as a replayable document.

Every entity has:

- Stable identity derived from API kind, namespace, and name.
- Operational plane.
- Provider.
- Labels and annotations.
- Desired state.
- Observed state.
- Source references.
- Content hash.

Kubernetes conditions are normalized into queryable state without discarding
the original sanitized payload.

## 6. Topology compilation

The topology compiler runs a set of independent relationship resolvers over the
snapshot. Resolvers share stable relationship types but may attach different
provenance and confidence.

The generic compiler currently covers:

- Ownership and reconciliation.
- Namespace containment.
- Pod scheduling.
- ServiceAccount usage.
- Configuration and Secret references.
- Storage references and binding.
- Service selection and EndpointSlice membership.
- Ingress routing.
- RBAC subject/role binding.

Unresolved references become warnings rather than invented edges. Kubernetes
label keys are always addressed through label maps rather than dotted paths.

## 7. Immutable snapshots

A collection produces two related objects:

- `DiscoveryBundle`: raw sanitized resources and collection evidence.
- `EnvironmentSnapshot`: canonical world projection used for topology and
  health.

The snapshot content hash excludes neither unknowns nor collection gaps.
Two snapshots with the same resources but different permissions or source
fingerprints remain operationally distinguishable.

Artifacts are append-only and content addressed. A snapshot manifest records
all derived artifacts.

## 8. Snapshot differencing

Diffs compare canonical entities and relationships by stable identity and
content hash, then expose field-level entity changes. They do not compare raw
JSON text, so irrelevant serialization order does not produce drift.

Relationship changes are first-class because a healthy resource may become
operationally disconnected without its own state changing.

## 9. Operational profiles

An `OperationalProfileSpec` defines an objective-oriented set of invariant
templates. Templates select entities and instantiate invariant definitions from
the matched objects.

Examples:

- Every selected Node must report ready.
- Deployment available replicas must meet desired replicas.
- Controller observed generation must equal desired generation.
- A Service must have at least one related ready Pod.

The profile engine supports required and optional templates. No selector match
can become `not_applicable` or `unknown` according to template policy rather
than silently passing.

## 10. Graph-aware invariants

Release 0.1 predicates evaluated an entity state. Release 0.2 extends the same
invariant engine with graph predicates such as `RelatedCountGte`.

This is important because operational health often resides in relationships:

```text
Service exists
+ Pods exist
+ Service selects no ready Pods
= serviceability invariant violated
```

The graph is supplied as evaluation context; there is no second health engine
for live Kubernetes.

## 11. Temporal health

Profile assessment accepts snapshot history. Immediate checks use the current
snapshot; stability and bounded-eventual checks evaluate compatible historical
states and evidence timestamps.

Release 0.2 records history and supports the temporal contract, although the
initial profiles intentionally use conservative windows suitable for sparse
manual snapshots.

## 12. Persistence projections

Django stores canonical payloads and indexed relational projections.

The payload remains authoritative for schema evolution. Projections enable:

- Environment filtering.
- Snapshot history queries.
- Entity and relationship lookup.
- Profile status filtering.
- Artifact lineage.

This avoids forcing the core package to depend on Django while still supporting
a useful multi-user control plane.

## 13. UI architecture

The environment workbench synchronizes:

- Environment registry.
- Inventory.
- Topology.
- Health.
- Snapshot history and diff.
- Artifacts.

It uses the same API contracts as the CLI and does not derive independent health
semantics in the browser.

## 14. Fixture round trip

A critical Release 0.2 workflow is:

```text
live read-only collection
→ sanitize
→ persist immutable snapshot
→ export public fixture
→ replay without cluster
→ compare future implementation behavior
```

The export endpoint reconstructs a fixture resources mapping from the sanitized
`ResourceDocument` set. Internal bundle metadata is not required by replay.

## 15. Failure semantics

Collection may be complete, partial, or failed. Permission gaps and individual
resource failures are represented independently.

The system must not equate partial collection with a healthy cluster. Profiles
that require unavailable evidence evaluate unknown or unhealthy according to
their contract.

## 16. Release 0.2 limitations

- Kubernetes collection currently uses `kubectl`; native Python-client and
  in-cluster agents are deferred.
- Collection is synchronous at the API boundary.
- Generic CRDs receive baseline metadata/condition modeling but no
  controller-specific semantics.
- Host and container-runtime collectors are not yet implemented.
- UI topology uses a deterministic layered SVG layout rather than a fleet-scale
  graph renderer.
- No causal diagnosis or active probe selection is performed.
- No mutation or recovery authority exists.
