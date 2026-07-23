# ADR 0006: Production control-plane boundary

- **Status:** Accepted
- **Release:** 1.0

## Context

Releases 0.1–0.5 established a generic operational metamodel, read-only environment intelligence, diagnosis, guarded lifecycle execution, and declarative knowledge packs. Production use adds users, tenants, multiple clusters, distributed executors, automated schedules, retention, audit, supply-chain trust, high availability, and recovery of KubeOps itself.

A naive implementation could let each new subsystem mutate environments directly. That would create multiple authority paths and invalidate the safety guarantees established in Release 0.4.

## Decision

KubeOps 1.0 uses one canonical mutation boundary:

1. Tenant and object scope are resolved.
2. Authorization and durable governance are evaluated.
3. A typed action plan is created.
4. Independent policy decisions and approvals are persisted.
5. An `OperationRun` becomes the authoritative aggregate.
6. Execution occurs locally or through a capability-scoped distributed task.
7. Receipts reconcile into the operation.
8. Fresh evidence and semantic verification determine recovery.

Fleet orchestration, scheduling, and distributed execution are planning, transport, and coordination systems—not alternative mutation authorities.

Knowledge packs remain declarative. Release 1.0 trust policy decides whether a pack may contribute data to the runtime; a pack signature never grants execution capability.

## Consequences

### Positive

- Every mutation retains the same policy, approval, checkpoint, receipt, and verification semantics.
- Multi-cluster and scheduled operations remain explainable and auditable.
- Distributed executors can be horizontally scaled without trusting their local queue state.
- Tenant isolation is enforceable in both authorization and data access.
- Production pack verification can use public keys without distributing private signing material.
- KubeOps can recover itself through verifiable, separately gated backups.

### Costs

- Fleet and schedule workflows require materialization into ordinary operations.
- Distributed execution requires relational leases and reconciliation.
- API endpoints must resolve tenant scope explicitly rather than relying on user defaults.
- High availability requires shared PostgreSQL and artifact storage.
- Production deployment has more configuration and operational checks than development mode.

## Rejected alternatives

### Direct fleet mutation

Rejected because it would bypass environment policy and make partial fleet failures difficult to reconcile.

### Scheduler-owned execution

Rejected because a timer is not an approval or safety authority.

### Arbitrary executor commands

Rejected because a remote worker must not transform a typed task into unrestricted shell access.

### In-process-only rate limits

Rejected because multiple API replicas would each admit work independently.

### Shared-secret-only pack trust

Rejected as the sole production mechanism because verifiers should not need access to the release signing key.

### Local filesystem artifacts with API autoscaling

Rejected because independent pods cannot reconstruct one immutable artifact namespace without shared-write storage.
