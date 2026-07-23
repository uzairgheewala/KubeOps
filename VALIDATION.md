# Release 0.4 validation record

## Validation environment

The release was validated in the available Python 3.13 sandbox against the
complete Release 0.3 source overlaid with the Release 0.4 implementation.

The sandbox did not provide installable Django, Django REST Framework,
Hypothesis, Ruff, MyPy, React, or Vite packages. Consequently:

- the pure core and CLI were executed directly;
- Django files, migration structure, URL/view resolution, schemas, and
  integration-test source were statically validated;
- the Django integration suite was not executed here;
- the TypeScript project-reference graph was checked with temporary external
  declaration stubs that were removed before packaging;
- the real Vite production bundle was not executed here;
- Ruff and MyPy were not executed here.

The repository CI and dependency manifests retain the real dependency-backed
commands for a networked environment.

## Python unit suite

Command:

```bash
PYTHONPATH=packages/kubeops_core:packages/kubeops_cli pytest -q tests/unit
```

Result:

```text
55 passed
```

This includes all retained Release 0.1–0.3 unit tests plus Release 0.4 tests for:

- lifecycle plan compilation;
- lifecycle stage and action-template DAG rejection;
- action parameter validation;
- execution-mode compatibility;
- action registry categories and source provenance;
- target fingerprint and capability denial;
- approval requirements;
- distinct approver counting;
- approval expiry and explicit rejection;
- checkpoint creation;
- dry-run journaling;
- simulation effects and idempotency;
- action and operation state transitions;
- stage `pause` behavior;
- durable cancellation;
- failure and rollback receipts;
- terminal Kubernetes Job cleanup safety;
- verification and trust-aware certificates;
- deterministic operation-artifact lineage.

A `pytest-django` configuration warning appears because that package is not
installed in the sandbox; it does not affect the pure unit-suite result.

## Canonical schema validation

All exported `SchemaModel` subclasses successfully generated JSON Schema:

```text
84 exported schemas
```

The canonical registry includes the Release 0.4 categories:

- `action_type`
- `lifecycle_profile`
- `execution_policy`

## Catalog and lifecycle matrix

Validated:

- 10 built-in typed action definitions;
- 2 lifecycle profiles;
- 2 execution policies;
- startup and shutdown plan compilation against both healthy and degraded
  fixture snapshots;
- 20 action-policy evaluation combinations.

All generated plan actions resolved to registered action types and passed their
required-parameter contracts.

## CLI vertical slice

The following path was executed end to end:

```text
degraded fixture
→ canonical snapshot
→ startup lifecycle plan
→ durable guarded operation
→ approval
→ simulation execution
→ R2 checkpoint
→ semantic verification
→ partial recovery certificate
→ immutable operation artifacts
```

Observed result:

```text
receipts:    2
checkpoints: 1
artifacts:   9
certificate: partially_recovered
```

The certificate remained partial because the adapter was simulation, which is
the required trust behavior.

## TypeScript validation

The actual project-reference graph was checked using:

```bash
tsc -b --pretty false
```

Result: passed.

Temporary React/Vite declaration files existed only outside the delivered
source contract and were deleted before packaging. This check caught and fixed:

- a missing `VerificationResult` UI type;
- untyped Release 0.4 select change events;
- operation API/type mismatches.

## Static control-plane validation

Validated without importing unavailable Django dependencies:

- Python compilation and AST parsing across the control plane;
- all 46 URL-imported view classes resolve in `views.py`;
- migration `0004_release_04_guarded_lifecycle` parses successfully;
- all 7 explicit migration constraint/index identifiers are unique;
- duplicate migration constraints were removed before release;
- lifecycle and policy registries preserve source-file provenance;
- the Release 0.4 seeder references valid registry methods and model fields.

The included Django integration suite covers:

- Release 0.4 system-status capabilities;
- lifecycle planning;
- operation creation;
- approval gating;
- dry-run execution;
- cancellation;
- checkpoints;
- verification and certificates;
- artifact persistence;
- server-wide live-execution denial;
- lifecycle/policy catalog seeding.

These tests require the dependencies in `requirements-dev.txt`.

## Configuration and source validation

Passed:

- Python bytecode compilation;
- AST parsing;
- all repository YAML parsing;
- all repository JSON parsing;
- Linux shell-script syntax;
- package versions aligned at `0.4.0`;
- Docker/Compose paths for lifecycle, policy, operation, and artifact data;
- CI environment paths and default live-execution denial.

## Safety properties explicitly tested

- Unregistered or malformed concrete actions cannot create an operation.
- Unsupported execution modes are denied by policy and checked again at the
  executor boundary.
- Missing capabilities deny execution.
- Target-fingerprint mismatch denies execution.
- Duplicate approval records from one identity do not satisfy multi-person
  approval.
- Expired approvals do not count.
- Active rejection denies execution.
- R2 actions create a durable checkpoint under the supplied local policy.
- Repeated idempotency keys are not reexecuted.
- An already-absent terminal Job is successful cleanup.
- An active Job is not deleted by the terminal-Job action.
- Dry-run and simulation cannot issue `recovered`.
- Operation manifests are reproducible from an unchanged persisted operation.

## Packaging validation

The final packaging process additionally performs:

1. full-source manifest hashing across 207 source files;
2. Release 0.3 versus Release 0.4 delta calculation;
3. delta overlay onto a clean Release 0.3 tree;
4. byte-for-byte comparison with the completed Release 0.4 tree;
5. the 55-test unit suite rerun from the overlaid checkout;
6. per-file delta hash verification;
7. ZIP integrity and archive-hygiene checks.

The Release 0.4 delta contains 26 added and 37 modified payload files, no
deleted paths, and one package-level `DELTA_MANIFEST.json`. The final archive
hash is recorded in the companion checksum file.
