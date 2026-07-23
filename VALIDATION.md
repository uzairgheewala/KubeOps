# Release 0.5 validation record

## Validation environment

Release 0.5 was validated in the available Python 3.13 and Node.js 22 sandbox
against the complete Release 0.4 source overlaid with the Release 0.5 pack
implementation.

The sandbox did not provide installable Django, Django REST Framework,
Hypothesis, Ruff, MyPy, React, or Vite packages. Consequently:

- the pure core, pack SDK, simulator, and CLI were executed directly;
- Django source, migrations, URL/view contracts, seeders, and integration-test
  source were statically validated;
- the dependency-backed Django integration suite was not executed here;
- the TypeScript project-reference graph was checked with temporary external
  React/Vite declarations that were removed before packaging;
- the real Vite production bundle was not executed here;
- Ruff, MyPy, and the Hypothesis suite were not executed here.

The repository CI and pinned dependency manifests retain the real
networked-environment commands.

## Python unit suite

Command:

```bash
PYTHONPATH=packages/kubeops_core:packages/kubeops_sdk:packages/kubeops_cli:\
packages/kubeops_simulator:packages/kubeops_collectors:packages/kubeops_executors:\
packages/kubeops_pack_sdk:control_plane python -m pytest tests/unit -q
```

Result:

```text
72 passed
```

This includes every retained Release 0.1–0.4 unit test plus Release 0.5 tests
for:

- all 11 built-in pack manifests;
- dependency closure and deterministic topological order;
- compatibility rejection;
- required and optional dependency handling;
- dependency-cycle rejection;
- in-pack duplicate contribution rejection;
- cross-pack contribution collision rejection;
- prevention of pack replacement of kernel action and diagnostic IDs;
- specialized entity classification with generic type lineage;
- declarative pack topology resolution;
- pack redaction before evidence persistence;
- pack contribution merging into health, diagnosis, action, lifecycle, and
  verification catalogs;
- component-specific causal-template filtering;
- generic and specialized health evaluation on one entity graph;
- provider lifecycle planning;
- deterministic pack artifact reconstruction;
- pack SDK scaffolding, loading, validation, and rejection of unknown
  executable-style fields.

A `pytest-django` configuration warning appears because `pytest-django` is not
installed in the sandbox; it does not affect the pure unit result.

## Pack resolution universe

All 11 built-in packs loaded and validated:

```text
generic-kubernetes
docker-host
kind
k3s
coredns
ingress-nginx
argocd
postgres
redis
django
celery
```

Every one of the **2,047 non-empty requested pack selections** was resolved.
For each selection:

- required and installed optional dependencies were closed transitively;
- the requested packs appeared in the active resolution;
- no cycle, conflict, compatibility, or contribution-collision issue was
  emitted;
- ordering remained dependency-safe and deterministic.

The fully resolved catalog contributes:

| Contribution family | Count |
|---|---:|
| Entity classifiers | 11 |
| Relationship resolvers | 3 |
| Operational profiles | 7 |
| Evidence intents | 9 |
| Collectors | 9 |
| Causal templates | 9 |
| Typed actions | 12 |
| Lifecycle profiles | 2 |
| Verification templates | 3 |
| Redaction rules | 1 |
| Scenario-coverage declarations | 11 |

After merging with the retained kernel catalogs, the runtime contains 22 typed
action definitions and 22 causal templates without identifier replacement.

## Specialization and fixture matrix

Two broader structural checks were executed:

1. **250 randomized classification cases** generated matching resource labels,
   annotations, kinds, and namespaces from randomly selected classifier rules.
   Whenever a pack specialized an entity, both the previous generic type and
   the new specialized type remained in `entity_type_lineage`.
2. The complete pack-aware fixture was collected and evaluated **100 times**.
   Every run produced the same structural outcome:
   - 36 canonical entities;
   - 32 typed relationships;
   - generic cluster health remained healthy;
   - CoreDNS, Ingress-NGINX, Argo CD, PostgreSQL, and Redis contracts passed;
   - the deliberately degraded Django and Celery contracts failed;
   - Kind specialization preserved `kubernetes.node` lineage;
   - Django and Celery dependency edges retained pack provenance.

Snapshot and topology content hashes intentionally vary between independent
collections because collection IDs and timestamps are new observations. The
validated invariant, entity-count, relationship-count, and profile-status
projection remained stable.

## Canonical schema validation

All 97 exported Pydantic model classes in `kubeops_core.models` successfully
generated JSON Schema, including the Release 0.5 pack, compatibility,
resolution, classifier, relationship-resolver, redaction, status, and coverage
models.

The canonical registry includes Release 0.5 categories for:

- knowledge packs;
- entity classifiers;
- relationship resolvers;
- verification templates;
- redaction rules;
- pack scenario coverage.

## Pack artifact chain and CLI

The following CLI paths were executed successfully:

```text
kubeops pack list
kubeops pack validate
kubeops pack resolve kind
kubeops pack coverage
kubeops pack export --pack kind --output-dir <path>
```

Observed results:

- all 11 manifests validated with no errors;
- requesting Kind resolved the dependency-closed order
  `generic-kubernetes → docker-host → kind`;
- the Kind resolution exported seven immutable artifacts;
- the full 11-pack resolution generated 15 immutable artifacts:
  11 pack manifests plus resolution, coverage, contribution-catalog, and
  aggregate-manifest artifacts;
- rebuilding artifacts from the same resolution and coverage observation
  produced identical content hashes;
- every persisted artifact path existed and matched its canonical content.

## TypeScript validation

The complete project-reference graph was checked with:

```bash
tsc -b --pretty false
```

Result: passed.

Temporary React, ReactDOM, Vite, and plugin declaration files were created only
inside a disposable `ui/node_modules` validation directory and removed before
packaging. No validation declarations or generated `.tsbuildinfo` files are in
the delivered source.

The actual Vite bundle could not run because the package dependencies were not
available in the sandbox.

## Static control-plane validation

Validated without importing unavailable Django dependencies:

- AST parsing across 137 Python source files;
- Python bytecode compilation across packages, control plane, and tests;
- all 50 URL-imported view classes/functions resolve in `views.py`;
- migration `0005_release_05_knowledge_packs.py` parses successfully;
- the `KnowledgePackRecord` model, seeder, APIs, and registry integration are
  referenced consistently;
- package versions align at `0.5.0` for core, CLI, pack SDK, control plane, and
  UI;
- bootstrap, Compose, Make, and CI paths include the pack SDK, built-in pack
  directory, and Release 0.5 seeder.

The included dependency-backed Django integration tests cover:

- Release 0.5 status capabilities;
- pack listing and detail;
- enabled-subset resolution;
- coverage projection;
- pack catalog seeding and stale-record cleanup;
- persistence of active and inactive installed packs.

## Configuration and source validation

Passed:

- `compileall` across Python packages, control plane, and tests;
- AST parsing across all Python files;
- six repository JSON files parsed;
- 35 repository YAML files parsed;
- Linux shell-script syntax;
- Git whitespace checks;
- package-version alignment;
- manifest dependency constraints;
- Docker and Compose path checks;
- default preservation of the Release 0.4 live-execution gate.

## Extension-safety properties explicitly tested

- Packs cannot import arbitrary runtime code through the manifest.
- Unknown executable-style manifest fields are rejected by strict schemas.
- Packs cannot silently replace kernel action or diagnostic identifiers.
- Duplicate contribution IDs inside one pack are rejected.
- Contribution collisions across selected packs block all owners.
- Dependency cycles block the complete cycle.
- Pack installation alone grants no mutation capability.
- Pack-contributed actions still pass Release 0.4 parameter, execution-mode,
  capability, fingerprint, policy, approval, checkpoint, and executor gates.
- Component-specific causal templates apply only when entity-type lineage
  matches.
- Specialization does not erase generic health or topology semantics.
- Pack redaction runs before collected evidence is persisted.
- Pack relationships and classifications preserve pack provenance.

## Packaging validation

The final packaging process performs:

1. complete source-manifest hashing;
2. Release 0.4 versus Release 0.5 delta calculation;
3. delta overlay onto a clean Release 0.4 tree;
4. byte-for-byte comparison with the completed Release 0.5 tree;
5. the 72-test unit suite rerun from the overlaid checkout;
6. per-file delta hash verification;
7. ZIP integrity and archive-hygiene checks.

The final source manifest covers **237 source files** excluding the two generated
manifest files. The Release 0.5 delta contains **30 added** and **51 modified**
payload files, no deleted paths, and one package-level `DELTA_MANIFEST.json`.
