# KubeOps Release 0.5 — Extensible Provider and Component Semantics

## Summary

Release 0.5 extracts Kubernetes-provider, platform-controller, and application
behavior from the kernel into independently versioned declarative knowledge
packs. Resolved packs contribute typed semantics to the existing discovery,
topology, health, diagnosis, planning, policy, execution, verification, API,
CLI, registry, and UI surfaces.

The release does not introduce unrestricted plugin execution. Pack manifests
can reference only known handler IDs and registered bounded executors. Live
mutation remains subject to every Release 0.4 policy and approval gate.

## Added

### Canonical pack IR

- `PackDependency`
- `PackCompatibility`
- `EntityClassifierRule`
- `RelationshipResolverRule`
- `RedactionRule`
- `PackScenarioCoverage`
- `PackContributions`
- `KnowledgePackManifest`
- `PackValidationIssue`
- `PackStatus`
- `PackResolution`
- `PackCoverageReport`

`OperationalEntity` now includes `entity_type_lineage` so generic and
specialized semantics remain simultaneously applicable.

### Pack manager and runtime

- Directory-based manifest discovery.
- Deterministic dependency closure and topological ordering.
- KubeOps and Kubernetes compatibility validation.
- Required and optional dependency validation.
- Conflict detection.
- Dependency-cycle rejection.
- Duplicate contribution validation.
- Cross-pack contribution collision rejection.
- Enabled-subset resolution.
- Contribution aggregation with pack provenance.
- Entity classification and type-lineage preservation.
- Declarative relationship-resolution handlers.
- Pack redaction before evidence persistence.
- Scenario-family and invariant coverage aggregation.

### Pack SDK

- Manifest loading.
- Installed-root-aware validation.
- Declarative pack scaffolding.
- Standalone `kubeops-pack-sdk` package.

### Built-in packs

- Generic Kubernetes.
- Docker Host.
- Kind.
- k3s.
- CoreDNS.
- Ingress-NGINX.
- Argo CD.
- PostgreSQL.
- Redis.
- Django.
- Celery.

### Runtime integration

Resolved contributions now augment:

- read-only discovery;
- entity normalization and classification;
- topology compilation;
- operational-profile registries;
- evidence-intent and collector catalogs;
- causal-template ranking;
- typed-action catalogs;
- lifecycle-profile registries;
- verification-template catalogs;
- canonical registry introspection.

### Artifacts and CLI

New commands:

```text
kubeops pack list
kubeops pack show
kubeops pack validate
kubeops pack resolve
kubeops pack coverage
kubeops pack export
```

`pack export` produces an immutable resolution artifact chain.

### Control plane

Migration `0005_release_05_knowledge_packs.py` adds the relational
`KnowledgePackRecord` projection.

New APIs:

```text
GET  /api/v1/packs
GET  /api/v1/packs/{pack_id}
POST /api/v1/packs/resolve
GET  /api/v1/packs/coverage
```

Management command:

```text
seed_release_05
```

The system registry and status endpoint now report pack contributions and pack
coverage.

### UI

The Packs workbench visualizes:

- resolution status;
- dependency closure;
- compatibility constraints;
- capabilities;
- contribution catalogs;
- scenario coverage;
- validation issues;
- manifest provenance and hashes.

### Fixtures and examples

- `lab/fixtures/pack-stack-degraded.v1.yaml`
- `environments/demo-pack-stack-fixture.v1.yaml`

The fixture demonstrates generic cluster health together with specialized
CoreDNS, ingress, GitOps, PostgreSQL, Redis, Django, and Celery semantics.

## Changed

- Package and UI versions advanced to `0.5.0`.
- Docker, Compose, bootstrap, CI, Make, and shell paths include the pack SDK and
  pack catalog.
- Built-in provider/component contributions use version-constrained pack
  dependencies.
- Component profiles evaluate workload-controller availability rather than
  applying Pod-only predicates to controller objects.
- Lifecycle selectors and diagnostic template matching understand entity-type
  lineage.
- System status advertises the pack capability boundary.

## Preserved safety properties

- No arbitrary Python plugin loading.
- No unrestricted shell action contribution.
- Pack installation does not grant execution capabilities.
- Pack actions remain subject to execution-mode validation.
- Pack actions remain subject to target fingerprints, policy, approval,
  checkpoint, mutation-budget, and executor checks.
- Evidence redaction occurs before persistence.
- Cross-pack contribution ambiguity blocks resolution.
- Generic semantics are preserved through specialization.
- Live execution remains disabled by default.

## Known limitations

- Packs are locally installed and unsigned in Release 0.5.
- Handler IDs are limited to the built-in declarative resolver and collector
  vocabulary.
- Continuous pack hot-reload is not included; service caches must be cleared or
  the process restarted after manifest changes.
- Real disposable-cluster chaos validation is deferred to the next release.
- The initial component recovery actions are deliberately bounded and do not
  constitute universal application repair.
