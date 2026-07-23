# Release 0.4 implementation manifest

Release 0.4 implements the phased-plan checkpoint **Guarded local recovery**.
It adds lifecycle planning, typed action authority, policy decisions, approvals,
durable execution, rollback, semantic verification, and the operation workbench
without weakening the Release 0.3 read-only diagnosis boundary.

## New core packages

```text
packages/kubeops_core/kubeops_core/actions/
packages/kubeops_core/kubeops_core/lifecycle/
packages/kubeops_core/kubeops_core/policy/
packages/kubeops_core/kubeops_core/execution/
packages/kubeops_core/kubeops_core/verification/
```

## New declarative catalogs

```text
actions/
lifecycle/local-development-startup.v1.yaml
lifecycle/local-development-shutdown.v1.yaml
policies/local-development-guarded.v1.yaml
policies/production-guidance-only.v1.yaml
```

## New or expanded canonical contracts

- Lifecycle profiles, stages, and action templates.
- Typed action definitions and instances.
- Execution policies and decisions.
- Recovery plans with embedded verification conditions.
- Approval records.
- Action receipts.
- Execution checkpoints.
- Operation timeline events.
- Durable operation runs.
- Operation-aware recovery certificates.

## Control-plane projection

Migration `0004_release_04_guarded_lifecycle.py` creates:

- `LifecycleProfileRecord`
- `ExecutionPolicyRecord`
- `OperationRecord`
- `OperationPolicyDecisionRecord`
- `OperationApprovalRecord`
- `ActionReceiptRecord`
- `OperationTimelineRecord`
- `ExecutionCheckpointRecord`
- `OperationVerificationRecord`
- `RecoveryCertificateRecord`

The canonical `OperationRun` payload remains authoritative; relational rows are
query projections for the UI and API.

## Safety boundary

- `KUBEOPS_LIVE_EXECUTION_ENABLED` defaults to false.
- The API selects dry-run or simulation unless live execution is explicitly
  enabled and requested.
- Every action is resolved through the catalog and executor registry.
- Arbitrary shell strings are not an action type.
- Policy decisions are persisted independently from plans and diagnoses.
- R2+ actions can require checkpoints and approvals.
- Fingerprint and capability mismatches deny execution.
- Active rejections deny execution.
- Expired and duplicate-person approvals do not satisfy quorum.

## Operation state path

```text
created
  → awaiting_approval | authorized | blocked
  → running
  → verifying
  → completed | failed
  → rolling_back
```

Pause, resume, and cancellation operate on the durable journal. Each action attempt emits an
immutable receipt, and each significant transition emits a sequenced event.

## UI additions

```text
ui/src/features/operations/OperationWorkbench.tsx
```

The workbench supports plan preview, creation, approval, execution, pause,
resume, cancellation, rollback, verification, certificate inspection, timeline replay, and
artifact lineage.

## Test additions

`tests/unit/test_release_04_lifecycle.py` covers:

- dependency-aware plan compilation;
- fingerprint, capability, approval, and checkpoint policy behavior;
- distinct, unexpired approvals and active rejections;
- lifecycle DAG rejection;
- dry-run journaling;
- simulation idempotency;
- semantic verification;
- failure and rollback receipts;
- terminal-Job cleanup safety;
- deterministic operation artifacts.

The Django integration suite adds API-level lifecycle planning, operation,
approval, run, certificate, and live-disable tests.
