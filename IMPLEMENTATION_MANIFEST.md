# Release 0.5 implementation manifest

Release 0.5 implements the phased-plan checkpoint **Extensible operational
platform**. Provider and component semantics are now independently versioned
pack contributions consumed by the common Release 0.1–0.4 kernel.

## New packages and modules

```text
packages/kubeops_core/kubeops_core/models/pack.py
packages/kubeops_core/kubeops_core/packs/
packages/kubeops_pack_sdk/
```

## Built-in knowledge packs

```text
packs/generic-kubernetes/
packs/docker-host/
packs/kind/
packs/k3s/
packs/coredns/
packs/ingress-nginx/
packs/argocd/
packs/postgres/
packs/redis/
packs/django/
packs/celery/
```

Each pack contributes only canonical objects and registered handler/executor
references. No pack-owned arbitrary runtime code is imported.

## Canonical model changes

- Pack identity, compatibility, dependency, status, resolution, coverage, and
  contribution contracts.
- Entity classifiers and relationship resolvers.
- Redaction and scenario-coverage contracts.
- `OperationalEntity.entity_type_lineage` for specialization without generic
  semantic loss.
- Registry categories for packs, classifiers, resolvers, verification
  templates, redaction rules, and pack coverage.

## Runtime integration

### Discovery

1. Collect read-only source material.
2. Apply built-in sanitization.
3. Apply resolved pack redaction.
4. Normalize canonical resources and entities.
5. Apply ordered entity classifiers.
6. Preserve generic type lineage and pack provenance.

### Topology

Generic Kubernetes resolvers run first. Pack relationship resolvers then add
content-addressed, provenance-bearing relationships through registered handler
IDs.

### Health and diagnosis

Pack operational profiles join the common profile registry. Pack evidence
intents, collectors, and causal templates join the common diagnostic catalog.
Component-specific templates are considered only when their supported entity
types intersect the subject entity’s type lineage.

### Planning and execution

Pack typed actions and lifecycle profiles join the existing guarded catalogs.
The Release 0.4 policy and execution runtime remains authoritative.

## Pack resolution safeguards

- semantic-version compatibility;
- dependency closure;
- cycle rejection;
- required dependency blocking;
- installed conflict detection;
- duplicate contribution detection;
- cross-pack contribution collision rejection;
- deterministic ordering by dependency, priority, and pack ID;
- immutable manifest hashes;
- enabled-subset projection.

## Artifact chain

`build_pack_artifacts` emits:

```text
knowledge_pack_manifest × N
pack_resolution
pack_coverage
pack_contribution_catalog
pack_resolution_manifest
```

All artifacts are content-addressed and can be persisted by the existing
`FileArtifactStore`.

## Control-plane projection

Migration `0005_release_05_knowledge_packs.py` creates
`KnowledgePackRecord`. The canonical manifest remains authoritative; the
relational record supports filtering, status display, and administration.

`seed_release_05` reconciles installed pack manifests and configured active
status into that projection.

## UI

```text
ui/src/features/packs/PackWorkbench.tsx
```

The workbench provides resolution, contribution, coverage, and raw-manifest
views.

## Example fixture

The pack-stack fixture contains a Kind node, CoreDNS, Ingress-NGINX, Argo CD,
PostgreSQL, Redis, Django, and Celery resources. It verifies that generic
cluster contracts and component-specific contracts operate together.

## Tests

Release 0.5 tests cover:

- all 11 pack manifests;
- contribution counts and dependency closure;
- compatibility rejection;
- dependency-cycle rejection;
- cross-pack collision rejection;
- specialized classification and type lineage;
- declarative topology resolution;
- pack redaction;
- contribution merging into prior registries;
- component-specific causal-template filtering;
- generic and specialized health evaluation;
- provider lifecycle planning;
- immutable pack artifacts;
- SDK scaffolding and validation;
- pack API and seeder contracts;
- every retained Release 0.1–0.4 unit test.
