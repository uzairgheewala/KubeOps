# KubeOps Release 0.4 — Guarded Lifecycle and Recovery

## Summary

Release 0.4 converts the Release 0.3 diagnosis and health foundations into a
policy-governed lifecycle and recovery runtime. It introduces typed actions,
dependency-aware lifecycle plans, independent authorization, durable approvals
and checkpoints, resumable execution, rollback, semantic verification, and
mode-aware recovery certificates.

The release is intentionally conservative. The control plane denies live
execution unless `KUBEOPS_LIVE_EXECUTION_ENABLED=1`, and successful dry-run or
simulation operations remain `partially_recovered` because they do not prove a
live environmental transition.

## Added

### Canonical IR

- `LifecycleActionTemplate`
- `LifecycleStageDefinition`
- `LifecycleProfile`
- expanded `ActionTypeDefinition`
- expanded `ActionInstance`
- expanded `ExecutionPolicy`
- expanded `PolicyDecision`
- expanded `RecoveryPlan`
- `ApprovalRecord`
- `ActionReceipt`
- `ExecutionCheckpoint`
- `OperationEvent`
- `OperationRun`
- operation-aware `RecoveryCertificate`

### Lifecycle planning

- Declarative startup and shutdown profiles.
- Stage and action-template DAG validation.
- Entity selection and parameter rendering from snapshots.
- Partial-state-aware action omission.
- Dependency propagation between stages.
- Compiled verification conditions and protected invariants.

### Typed actions and executors

- Ten bounded built-in action definitions.
- Dry-run executor.
- Simulation executor.
- Wait executor.
- Local-process executor with executable allowlisting and no shell expansion.
- Docker and host-service command adapters.
- Kubernetes-safe executor.
- Port-forward executor.
- Executor registry and capability lookup.

### Policy and approvals

- Environment and target-scope policies.
- Risk-class gates R0–R5.
- Required capability evaluation.
- Mutation budgets.
- Target-fingerprint verification.
- Action and operation approvals.
- Distinct-approver counting.
- Approval expiry handling.
- Explicit rejection handling.
- Checkpoint requirements.

### Durable execution

- Atomic file-backed operation journal.
- Append-oriented operation events.
- Action receipts with attempts, effects, stdout/stderr, and idempotency keys.
- Pause, resume, and durable cancellation.
- Pre-action checkpoints.
- Idempotency suppression.
- Bounded retries.
- Stage-level `stop`, `pause`, `rollback`, and `continue` failure behavior.
- Rollback action compilation and receipts.

### Verification and artifacts

- Verification over canonical world state and relationships.
- Protected-invariant failure detection.
- Mode-aware recovery certificates.
- Immutable operation artifact chain:
  - recovery plan;
  - policy decisions;
  - approvals;
  - action receipts;
  - operation timeline;
  - checkpoints;
  - verification results;
  - recovery certificate;
  - operation manifest.
- Deterministic operation-manifest hashing from the persisted operation revision.

### Django control plane

- Relational projections for lifecycle profiles, policies, operations, policy
  decisions, approvals, receipts, timeline events, checkpoints, verification
  results, and certificates.
- Migration `0004_release_04_guarded_lifecycle`.
- Lifecycle-plan and operation REST APIs.
- Server-wide live-execution gate, disabled by default.

### CLI

- `kubeops lifecycle list`
- `kubeops lifecycle plan`
- `kubeops policy list`
- `kubeops policy actions`
- `kubeops operation create`
- `kubeops operation approve`
- `kubeops operation run`
- `kubeops operation show`
- `kubeops operation cancel`

### UI

- Operations navigation surface.
- Lifecycle-plan preview.
- Stage/action DAG.
- Policy-decision review.
- Approval controls.
- Dry-run and guarded-simulation execution.
- Pause, resume, cancel, and rollback controls.
- Receipt, checkpoint, verification, certificate, timeline, and artifact views.

## Correctness fixes found during implementation

- Rejected cyclic lifecycle-stage and action-template graphs during schema
  validation.
- Required distinct approvers rather than counting duplicate approval records.
- Ignored expired approvals and denied active rejections.
- Preserved simulation/dry-run trust boundaries in recovery certificates.
- Made operation manifests deterministically reproducible.
- Treats deletion of an already-absent terminal Job as an idempotent success.
- Refuses terminal-Job deletion when the Job remains active.
- Removed duplicate migration constraints before packaging.

## Compatibility

Release 0.4 is additive over Release 0.3. It preserves the existing simulator,
fixture replay, read-only collection, topology, health, incident, diagnosis,
probe, and certificate APIs.

## Deliberate limitations

- Live command execution is disabled by default.
- The initial executor set is intended for local/disposable environments.
- No unrestricted shell executor exists.
- No autonomous production remediation exists.
- Dry-run and simulation cannot issue a `recovered` certificate.
- Provider-specific recovery depth remains limited until Release 0.5 packs.
