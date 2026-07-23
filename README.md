# KubeOps Release 0.2

KubeOps is a typed operational reasoning platform for Kubernetes environments.
Release 0.2 turns the Release 0.1 scenario laboratory into a useful **read-only
cluster-intelligence system** while retaining the same canonical operational IR.

It can now register environments, validate observer access, collect live or
recorded Kubernetes state, sanitize sensitive objects, compile an operational
dependency graph, evaluate reusable health profiles, compare immutable
snapshots, export replayable fixtures, and visualize the result in the web
workbench. It still has **zero mutation authority**.

## Release 0.2 capabilities

- Versioned environment and access-method definitions.
- Read-only access validation for fixture and `kubectl` sources.
- Sanitized Kubernetes discovery with partial-success and permission-gap
  reporting.
- Immutable snapshots, content hashes, snapshot manifests, and structural diffs.
- Provider-neutral normalization into the Release 0.1 `OperationalEntity`,
  `Relationship`, `Observation`, and invariant contracts.
- Topology compilation for ownership, reconciliation, selection, routing,
  scheduling, identity, configuration, secrets, storage, EndpointSlices,
  ingress, and RBAC.
- Operational-profile compilation and graph-aware temporal health evaluation.
- Live → sanitized snapshot → replayable fixture workflow.
- Environment, inventory, topology, health, history, diff, and artifact UI.
- Django persistence and REST APIs for environments and snapshot projections.
- Typer/Rich CLI commands for validation, collection, diffing, and profile
  evaluation.
- All Release 0.1 simulation and scenario-family functionality remains intact.

## Authority boundary

Release 0.2 may read from a live cluster through `kubectl`, but it never creates,
patches, deletes, restarts, or otherwise mutates Kubernetes or host state.
Observer access and future executor access remain separate architectural
capabilities.

```text
Environment definition
        ↓
Access-source resolution (fixture or kubectl)
        ↓
Read-only access validation
        ↓
Raw collection + mandatory sanitization
        ↓
Canonical entities, relationships, observations
        ↓
Topology compiler
        ↓
Immutable environment snapshot
        ↓
Operational-profile health assessment
        ↓
Artifacts / REST API / CLI / Web workbench
```

See [the Release 0.2 architecture](docs/architecture-release-02.md) and
[ADR 0002](docs/adr/0002-read-only-intelligence-boundary.md).

## Applying the delta package

The distributed Release 0.2 archive is a delta. Extract it over the root of an
existing Release 0.1 checkout, preserving paths and replacing changed files.
No Release 0.1 source files are intentionally deleted.

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

The bootstrap migrates both releases and seeds the Release 0.1 scenario catalog,
Release 0.2 operational profiles, and the fixture-backed demonstration
environment.

## Fixture-backed demonstration

A reusable environment definition is included at:

```text
environments/demo-kind-fixture.v1.yaml
```

It exposes both degraded and healthy views of the same synthetic Kind topology.
No cluster is required.

```bash
./scripts/kubeops.sh environment validate \
  environments/demo-kind-fixture.v1.yaml \
  --method-id recorded-degraded

./scripts/kubeops.sh snapshot collect \
  environments/demo-kind-fixture.v1.yaml \
  --method-id recorded-degraded \
  --output /tmp/degraded.json

./scripts/kubeops.sh snapshot collect \
  environments/demo-kind-fixture.v1.yaml \
  --method-id recorded-healthy \
  --output /tmp/healthy.json

./scripts/kubeops.sh snapshot diff \
  /tmp/degraded.json /tmp/healthy.json

./scripts/kubeops.sh profile evaluate \
  local-development-usable.v1 /tmp/degraded.json
```

Expected distinction:

- `cluster-observable.v1` remains healthy in both fixtures.
- `local-development-usable.v1` is unhealthy in the degraded fixture and
  healthy in the healthy fixture.
- The structural diff identifies three changed entities and one changed
  relationship.

## Live read-only collection

Register an environment using a `kubectl` or `kubeconfig` access method. KubeOps
executes bounded read-only commands and records the selected context, server,
cluster version, permissions, and source fingerprint before collection.

Example definition:

```yaml
schema_version: kubeops.io/v1
environment_id: local-kind
name: Local Kind
environment_class: development
provider: local
cluster_provider: kind
access_methods:
  - schema_version: kubeops.io/v1
    method_id: observer
    method_type: kubectl
    context_name: kind-local
    read_only: true
default_access_method_id: observer
operational_profile_ids:
  - cluster-observable.v1
  - local-development-usable.v1
```

Then run:

```bash
./scripts/kubeops.sh environment validate local-kind.yaml
./scripts/kubeops.sh snapshot collect local-kind.yaml --output local-kind.json
```

Secret values are removed before `ResourceDocument` creation or artifact
persistence. Secret and ConfigMap key names remain available so missing-key and
reference diagnosis can be added later without retaining values.

## Web workbench

Release 0.2 makes **Environments** the default UI surface.

### Environment registry

- Register fixture, `kubectl`, or explicit kubeconfig access.
- Validate observer connectivity and capabilities.
- Review source fingerprints and permission gaps.

### Inventory

- Search normalized resources.
- Filter by namespace.
- Inspect provider-neutral desired and observed state.
- Confirm sanitization before artifact export.

### Topology

- Filter by operational plane and namespace.
- Trace typed edges and their provenance.
- Inspect inferred versus authoritative relationships.
- Hide healthy entities while retaining the full graph.

### Health

- Select an operational profile.
- Group evaluations by invariant family.
- Inspect evidence, predicate result, temporal state, and explanation.
- Preserve `unknown`, `pending`, and `not_applicable` separately from healthy.

### Snapshots and artifacts

- Browse immutable history.
- Compare two snapshots structurally.
- Inspect artifact lineage and hashes.
- Export a snapshot as a directly replayable sanitized fixture.

The Scenario Lab, Composition Lab, canonical schema browser, and Release 0.1
artifact explorer remain available unchanged.

## Operational profiles

Profiles live in `profiles/` and compile invariant templates over matching
entities.

Included profiles:

### `cluster-observable.v1`

Checks that the cluster can be meaningfully inspected, including node readiness,
CoreDNS availability, and the presence of expected cluster-level structures.

### `local-development-usable.v1`

Checks that a development environment is actually usable, including:

- Node readiness.
- Desired versus available workload replicas.
- Controller generation convergence.
- Pod readiness.
- Service-to-ready-Pod relationships.
- PVC binding.

A profile can produce many concrete invariant instances without hard-coding
resource names.

## Snapshot and topology semantics

Each snapshot retains:

- Sanitized raw resource documents.
- Canonical entities.
- Typed relationships.
- Observations.
- Discovery issues.
- Permission gaps.
- Source fingerprint.
- Collection summary.
- Artifact references.

The topology compiler currently derives:

- Namespace containment.
- Owner-reference ownership and controller chains.
- Pod-to-node scheduling.
- ServiceAccount identity usage.
- ConfigMap, Secret, and PVC references.
- Service selector matches.
- EndpointSlice membership.
- Ingress routing.
- PV/PVC/StorageClass bindings.
- RoleBinding subject and role relationships.

Every derived edge carries a confidence and provenance record.

## REST API additions

```text
GET/POST /api/v1/environments
GET/PUT/DELETE /api/v1/environments/{environment_id}
POST /api/v1/environments/{environment_id}/validate
GET/POST /api/v1/environments/{environment_id}/snapshots
GET /api/v1/snapshots/{snapshot_id}
GET /api/v1/snapshots/{snapshot_id}/topology
GET /api/v1/snapshots/{snapshot_id}/health
GET /api/v1/snapshots/{snapshot_id}/diff
GET /api/v1/snapshots/{snapshot_id}/export
GET /api/v1/operational-profiles
GET /api/v1/operational-profiles/{profile_id}
```

All Release 0.1 scenario, composition, run, artifact, registry, and schema routes
remain available.

## Repository additions

```text
environments/                  Reusable environment definitions
profiles/                      Operational-profile specifications
lab/fixtures/                  Sanitized discovery fixtures
packages/kubeops_core/
  artifacts/                   General operational artifact store
  discovery/                   Fixture/kubectl sources and normalization
  environments/                Read-only intelligence orchestration
  health/                      Profile assessment engine
  profiles/                    Profile registry
  topology/                    Dependency graph compiler
control_plane/api/             Environment and snapshot persistence/API
ui/src/features/environments/  Read-only workbench
```

## Validation

```bash
./scripts/test.sh
```

The delivered validation performed in this environment is documented in
[VALIDATION.md](VALIDATION.md). Django/DRF and the actual Vite runtime dependencies
were not available in this sandbox, so those dependency-gated boundaries are
included and statically validated but must be executed after normal bootstrap or
in CI.

## Next release boundary

Release 0.3 adds active investigation while remaining read-only:
question-oriented evidence intents, collector selection, deterministic causal
hypotheses, contradiction handling, parent-family fallback, diagnosis
certificates, and an interactive probe workflow.
