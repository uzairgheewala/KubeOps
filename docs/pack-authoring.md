# KubeOps knowledge-pack authoring guide

## Create a pack

Use the SDK:

```python
from kubeops_pack_sdk import scaffold_pack

path = scaffold_pack(
    "packs",
    pack_id="example-controller",
    title="Example Controller",
    pack_kind="platform",
)
print(path)
```

Or create `packs/<pack-id>/pack.yaml` manually using
`KnowledgePackManifest`.

## Required identity

```yaml
pack_id: example-controller
version: 1.0.0
title: Example Controller
pack_kind: platform
api_version: kubeops.io/pack/v1
compatibility:
  kubeops_constraint: ">=0.5.0,<1.0.0"
```

Use semantic versions and constrain every required dependency to the compatible
major range.

## Contribution guidance

### Classifiers

Prefer precise resource kinds plus labels or annotations. Use name regexes only
when the component has a stable naming convention. Assign a specialized type,
but rely on KubeOps type lineage to retain the generic Kubernetes type.

### Relationship resolvers

Choose one registered handler and provide only the fields it requires. Every
edge must have a meaningful relationship type and should define contract and
propagation semantics where known.

### Health profiles

Target stable component contracts, not implementation-specific error strings.
For workload controllers, prefer `workload_available`; use `pod_ready` only
when the classifier actually selects Pods.

### Evidence and diagnosis

Collectors remain R0 in Release 0.5. Declare the exact normalized fact types
they produce. A causal template should list supported entity types and should
inherit from the nearest generic family.

### Actions

Use only registered typed executors. Declare required capabilities, supported
modes, risk, side effects, timeout, idempotency, and rollback semantics. Do not
encode shell strings.

### Coverage

Coverage is a claim with a level:

```text
representable → detectable → diagnosable → guidance → executable → verified
```

Do not label a family `verified` unless an executable scenario or fixture proves
the declared behavior.

## Validate

```bash
kubeops pack validate example-controller
```

From Python:

```python
from kubeops_pack_sdk import validate_manifest

issues = validate_manifest(
    "packs/example-controller/pack.yaml",
    packs_root="packs",
)
```

## Test obligations

A production-quality pack should test:

- manifest validation;
- compatibility boundaries;
- dependency closure;
- classifier positive and negative cases;
- generic type-lineage preservation;
- topology-edge provenance;
- profile healthy, unhealthy, and unknown outcomes;
- collector fact contracts;
- causal-template discrimination;
- action parameter validation;
- policy behavior;
- simulation and interruption;
- live disposable-environment verification where permitted;
- redaction;
- scenario coverage.
