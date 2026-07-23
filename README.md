# KubeOps Release 0.5

KubeOps is a typed, evidence-driven Kubernetes operations runtime. Release 0.5
moves provider and component knowledge out of the operational kernel and into
independently versioned, declarative **knowledge packs**.

The same Release 0.1–0.4 kernel now discovers, classifies, relates, evaluates,
diagnoses, plans, authorizes, executes, and verifies provider-specific and
component-specific behavior through resolved pack contributions. A pack cannot
run arbitrary Python or shell code: it contributes only canonical typed objects
and references to pre-registered handlers and bounded executors.

Release 0.5 keeps all Release 0.4 mutation protections. Live execution remains
disabled by default, and installing a pack does not grant its required
capabilities or authorize its actions.

## Release 0.5 capabilities

### Declarative pack contract

Each `pack.yaml` declares:

- identity, semantic version, priority, and pack kind;
- KubeOps, Kubernetes, Python, provider, OS, and architecture compatibility;
- required and optional pack dependencies;
- explicit conflicts;
- entity classifiers;
- topology relationship resolvers;
- operational health profiles;
- evidence intents and collectors;
- causal templates;
- typed actions;
- lifecycle profiles;
- verification templates;
- redaction rules;
- scenario-family coverage claims.

The manifest uses the canonical immutable IR, rejects unknown fields, and has a
deterministic content hash.

### Pack resolution and linting

The pack manager performs:

- dependency closure;
- deterministic topological ordering;
- compatibility checks;
- missing-dependency detection;
- dependency-cycle rejection;
- conflict detection;
- duplicate contribution detection within a pack;
- cross-pack contribution-ID collision rejection;
- active, blocked, incompatible, and disabled status projection;
- contribution and semantic-coverage aggregation.

A pack set must resolve successfully before any contribution enters a runtime
registry.

### Type specialization without semantic loss

An entity now carries `entity_type_lineage`. A Kind control-plane node can be
specialized as:

```text
provider.kind.control_plane
```

while retaining:

```text
kubernetes.node
```

Generic health profiles and topology rules continue to apply, while Kind-aware
profiles, probes, actions, and causal templates gain additional precision.
Specialization refines the common model instead of replacing it.

### Runtime integration

Resolved pack contributions are consumed by existing Release 0.1–0.4 surfaces:

```text
read-only resource collection
  → pack redaction
  → generic normalization
  → entity classification
  → generic + pack topology resolution
  → generic + pack health profiles
  → generic + pack diagnostic catalog
  → generic + pack lifecycle/action catalogs
  → policy-governed execution
  → pack verification templates
```

No parallel provider-specific orchestration runtime was introduced.

### Initial pack set

Release 0.5 includes 11 packs:

| Pack | Kind | Primary contribution |
|---|---|---|
| `generic-kubernetes` | core | Generic resource semantics and credential redaction |
| `docker-host` | provider | Docker runtime/container lifecycle |
| `kind` | provider | Kind control-plane diagnosis and lifecycle |
| `k3s` | provider | k3s service diagnosis and maintenance |
| `coredns` | platform | DNS health and bounded rollout recovery |
| `ingress-nginx` | platform | Ingress-controller health and recovery |
| `argocd` | platform | GitOps ownership, health, evidence, and refresh |
| `postgres` | application | PostgreSQL readiness, diagnosis, and guarded recovery |
| `redis` | application | Redis readiness, diagnosis, and guarded recovery |
| `django` | application | Django service dependencies, health, and recovery |
| `celery` | application | Worker dependencies, health, and recovery |

The resolved catalog contributes 11 classifiers, 3 relationship resolvers,
7 operational profiles, 9 evidence intents, 9 collectors, 9 causal templates,
12 action types, 2 lifecycle profiles, 3 verification templates, 1 redaction
rule, and 11 scenario-coverage declarations.

### Pack SDK

`kubeops-pack-sdk` provides:

- manifest loading;
- manifest validation against an installed pack root;
- new-pack scaffolding;
- canonical model exports for pack authors.

The SDK deliberately does not expose an arbitrary plugin execution hook.

### Pack workbench

The React UI adds a **Packs** workspace with:

- active and blocked pack status;
- dependency and compatibility inspection;
- contribution counts and canonical payloads;
- capability and supported-entity summaries;
- validation issues;
- scenario-family and invariant coverage;
- manifest hash and raw canonical manifest.

### Immutable pack artifacts

The CLI can export a resolved pack set as a content-addressed artifact chain:

- one artifact per manifest;
- pack resolution;
- contribution catalog;
- coverage report;
- aggregate resolution manifest.

## Repository additions

```text
packages/kubeops_core/kubeops_core/packs/
  manager.py       dependency and compatibility resolution
  runtime.py       contribution aggregation and runtime interpretation
  versioning.py    constrained semantic-version checks

packages/kubeops_pack_sdk/
  authoring and validation SDK

packs/
  generic-kubernetes/
  docker-host/
  kind/
  k3s/
  coredns/
  ingress-nginx/
  argocd/
  postgres/
  redis/
  django/
  celery/

ui/src/features/packs/
  Pack Workbench
```

## Applying this delta

The Release 0.5 archive contains only files added or modified since Release
0.4. Extract it over a complete Release 0.4 repository while preserving paths.

```bash
unzip kubeops-release-0.5-delta.zip -d /path/to/kubeops
cd /path/to/kubeops
```

Run migrations and seed the pack projection:

```bash
python control_plane/manage.py migrate
python control_plane/manage.py seed_release_05
```

The bootstrap and Docker Compose paths perform both steps automatically.

## Local bootstrap

### Linux/macOS

```bash
./scripts/bootstrap.sh
./scripts/dev.sh
```

### Windows PowerShell

```powershell
.\scripts\bootstrap.ps1
.\scripts\dev.ps1
```

### Docker Compose

```bash
docker compose up --build
```

The UI is served at `http://localhost:5173`; the API is served at
`http://localhost:8000/api/v1`.

## Pack configuration

```text
KUBEOPS_PACK_DIR=./packs
KUBEOPS_ENABLED_PACKS=
```

An empty `KUBEOPS_ENABLED_PACKS` value activates every successfully resolved
installed pack. A comma-separated value selects a subset and its required
dependency closure.

Pack enablement does not change the Release 0.4 live authority gate:

```text
KUBEOPS_LIVE_EXECUTION_ENABLED=0
```

## CLI examples

Inspect and validate the pack set:

```bash
kubeops pack list
kubeops pack validate
kubeops pack show kind
```

Resolve only Kind and its dependencies:

```bash
kubeops pack resolve kind
```

Inspect scenario coverage:

```bash
kubeops pack coverage
```

Export immutable resolution artifacts:

```bash
kubeops pack export --pack kind --output-dir artifacts
```

Exercise the pack-aware fixture:

```bash
kubeops snapshot collect environments/demo-pack-stack-fixture.v1.yaml \
  --output /tmp/pack-stack-snapshot.json
```

## API additions

```text
GET  /api/v1/packs
GET  /api/v1/packs/{pack_id}
POST /api/v1/packs/resolve
GET  /api/v1/packs/coverage
```

The existing registry, profile, diagnostic, action, lifecycle, environment,
incident, and operation APIs now include resolved pack contributions.

## Testing

```bash
make test-python
make test-ui
```

The Release 0.5 suite covers resolution, dependency closure, compatibility,
cycles, contribution collisions, classification, type lineage, relationship
resolution, redaction, catalog merging, pack-aware diagnosis, health,
lifecycle planning, artifact export, SDK authoring, API projections, and all
retained Release 0.1–0.4 behavior.

## Documentation

- [Release 0.5 architecture](docs/architecture-release-05.md)
- [Declarative pack boundary ADR](docs/adr/0005-declarative-knowledge-pack-boundary.md)
- [Pack authoring guide](docs/pack-authoring.md)
- [Built-in pack catalog](packs/README.md)
- [Release notes](RELEASE_NOTES.md)
- [Implementation manifest](IMPLEMENTATION_MANIFEST.md)
- [Validation record](VALIDATION.md)

## Next boundary

The next release can use these pack contracts to add disposable-cluster fault
injection, systematic live scenario validation, semantic support coverage, and
incident-to-pack knowledge promotion without modifying the operational kernel.
