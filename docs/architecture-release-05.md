# Release 0.5 architecture: declarative operational knowledge packs

## 1. Purpose

Release 0.5 makes KubeOps extensible without fragmenting the operational model
or creating an unsafe general-purpose plugin runtime. Provider and component
knowledge is packaged as versioned canonical data, resolved before use, and
interpreted by the same deterministic kernel.

## 2. Architectural boundary

```text
pack.yaml
  → canonical validation
  → dependency/compatibility resolution
  → collision and conflict linting
  → immutable PackResolution
  → PackRuntime
  → existing kernel registries and engines
```

Packs may select registered behavior through identifiers; they may not execute
arbitrary code merely by being installed.

## 3. Pack manifest

A `KnowledgePackManifest` contains:

```text
identity
compatibility
required/optional dependencies
conflicts
capabilities
supported entity types
contributions
metadata
```

The manifest is immutable, rejects unknown fields, serializes canonically, and
exposes a SHA-256 content hash.

## 4. Resolution algorithm

Given requested pack IDs:

1. Compute required and installed optional dependency closure.
2. Build the required-dependency graph.
3. Reject dependency cycles.
4. Topologically order dependencies before dependents.
5. Use priority and pack ID for deterministic peer ordering.
6. Validate KubeOps and Kubernetes compatibility.
7. Validate dependency versions.
8. Validate conflicts.
9. Detect duplicate contribution IDs within each pack.
10. Detect contribution-ID collisions across the active closure.
11. Block dependents of blocked required dependencies.
12. Produce statuses, active/blocked sets, issues, and contribution counts.

The runtime includes only active manifests.

## 5. Contribution model

### Entity classifiers

Classifiers match canonical resource documents using resource kind, namespace,
name regex, labels, and annotations. They can refine entity type, plane,
provider, capabilities, and namespaced extensions.

Classifiers are evaluated by descending priority. Every match is recorded in
`extensions.kubeops_pack.classifiers`.

### Type lineage

A specialized entity keeps all semantically valid ancestor types:

```text
entity_type: provider.kind.control_plane
entity_type_lineage:
  - kubernetes.node
  - provider.kind.control_plane
```

Selectors, relationship resolvers, lifecycle planning, and causal-template
matching use lineage-aware semantics. This prevents specialization from
breaking generic contracts.

### Relationship resolvers

Release 0.5 supports a bounded handler vocabulary:

- annotation reference;
- label group;
- named Kubernetes resource;
- declared component dependency.

Resolvers emit canonical relationships with pack provenance, confidence,
contract, and propagation metadata.

### Health and diagnosis contributions

Operational profiles, evidence intents, collectors, and causal templates are
canonical Release 0.2/0.3 objects. They enter the existing registries rather
than a provider-specific engine.

### Mutation contributions

Action types and lifecycle profiles are canonical Release 0.4 objects. Packs
select an already registered bounded executor. Policy and approval evaluation
remain independent.

### Redaction

Pack redaction executes after source sanitization and before normalized evidence
is persisted. Key and path regexes can replace credential-like fields, but
cannot reveal material removed by earlier sanitization.

## 6. Runtime flow

```text
PackManager
  ├── manifests
  ├── sources
  └── resolution
        ↓
PackRuntime
  ├── classifiers
  ├── relationship resolvers
  ├── profiles
  ├── diagnostics
  ├── actions
  ├── lifecycle profiles
  ├── verification templates
  ├── redaction
  └── coverage
```

Runtime consumers accept an optional `PackRuntime`; without one, retained
Release 0.1–0.4 generic behavior remains available.

## 7. Persistence and APIs

The source manifest and immutable resolution remain authoritative.
`KnowledgePackRecord` is a relational projection containing identity, state,
source, hash, counts, capabilities, payload, and validation issues.

The API exposes installed manifests, configured resolution, ad hoc subset
resolution, and semantic coverage.

## 8. UI

The Pack Workbench is intentionally an interpretability surface, not an app
marketplace. It shows exactly which knowledge entered the kernel and why a pack
was active or blocked.

## 9. Safety invariants

- Unresolved packs contribute nothing.
- Dependency ambiguity blocks activation.
- Pack code is not dynamically imported.
- Unknown handler and executor IDs fail during downstream catalog validation.
- Pack installation does not grant capabilities.
- Live execution remains globally disabled by default.
- Generic entity semantics remain available after specialization.
- Redaction precedes evidence persistence.
- Artifact export preserves manifest and resolution provenance.

## 10. Future extension

The contract permits future signed distribution, isolated code adapters,
versioned handler capability negotiation, and a marketplace, but none should be
added before signing, sandboxing, and supply-chain policies exist.
