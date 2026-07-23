# KubeOps Release 1.0 architecture

## Purpose

Release 1.0 turns the single-environment guarded-recovery platform from Releases 0.1–0.5 into a production-capable, multi-tenant and multi-cluster control plane. It preserves the architectural rule established in Release 0.4: every mutation must pass through a registered typed action, independent policy evaluation, required approvals, target-fingerprint validation, durable execution, and semantic verification.

Release 1.0 does not create a second privileged orchestration path for fleets, schedules, distributed agents, or recovery. Those systems may plan, queue, or materialize existing operations, but they cannot bypass the canonical operation state machine.

## Control-plane decomposition

Release 1.0 adds six coordinated production control planes:

1. **Tenancy and authorization** — organizations, workspaces, hierarchical grants, capabilities, and object-aware scope enforcement.
2. **Fleet intelligence** — multi-environment topology, common-cause findings, failure-domain analysis, dependency-ordered operation waves, and fleet artifacts.
3. **Distributed execution** — agent registration, immutable agent identity, capability/capacity matching, durable tasks, expiring leases, nonce verification, receipts, and operation reconciliation.
4. **Governance** — durable rate and concurrency limits, tamper-evident audit chains, legal-hold-aware retention, maintenance windows, and operation scheduling.
5. **Supply-chain trust and secret references** — HMAC/Ed25519 pack signatures, workspace trust policy, public-key verification, and references to externally managed secrets rather than persisted secret material.
6. **Platform recovery** — content-addressed artifacts, S3-compatible storage, verifiable database/configuration/artifact backups, guarded restore plans, and upgrade-readiness reports.

## Canonical authority flow

```text
User, schedule, or fleet plan
        ↓
Workspace scope and authorization
        ↓
Rate/concurrency governance
        ↓
Lifecycle or recovery plan
        ↓
Typed action validation
        ↓
Independent policy decisions and approvals
        ↓
Durable OperationRun
        ↓
Local executor or distributed ExecutionTask
        ↓
Lease, nonce, fingerprint, capability checks
        ↓
ActionReceipt reconciliation
        ↓
Fresh snapshot and semantic verification
        ↓
RecoveryCertificate and audit chain
```

A schedule can materialize an operation but cannot approve or execute it. A fleet plan can create dependency-ordered waves but cannot skip environment-level policy. A distributed executor can run only the action definition and payload whose hashes were authorized by the control plane.

## Tenancy model

The hierarchy is:

```text
Organization
  └── Workspace
       ├── Environments
       ├── Fleets
       ├── Snapshots and incidents
       ├── Operations and schedules
       ├── Executor agents and tasks
       ├── Pack signatures and trust policy
       ├── Governance rules
       ├── Audit events
       ├── Artifacts
       └── Platform backups
```

Role grants bind a principal to a system, organization, workspace, environment, fleet, or operation scope. Authorization walks the scope hierarchy and returns an explicit decision with matched grants and reasons. API list queries are workspace-filtered, object endpoints perform object-aware scope checks, and payload organization/workspace identifiers must match the request headers.

The UI sends `X-KubeOps-Organization` and `X-KubeOps-Workspace` on every authenticated API request. Credentials are held in browser memory rather than local storage.

## Fleet model

A fleet is a named workspace-owned set of environments with:

- Failure-domain labels.
- Criticality and ordering metadata.
- Dependencies between environments.
- Maximum concurrency.
- Per-wave availability limits.

The fleet service produces:

- Environment health distribution.
- Common-cause candidates.
- Shared provider and failure-domain findings.
- Dependency-ordered operation waves.
- Blocked wave explanations.

Fleet plans remain plans. Environment operations are still created, approved, dispatched, and verified individually.

## Distributed execution

### Agent identity

An `agent_id` is permanently bound to its organization, workspace, and public identity. Re-registration may refresh capabilities and status but cannot move an identity across tenants or keys.

### Task identity

An `ExecutionTask` contains:

- Operation, action, environment, and tenant identity.
- Action-type and executor identity.
- Required capabilities.
- Target fingerprint.
- Canonical payload hash.
- Idempotency key.
- Attempts, deadline, priority, and dependency metadata.

Posting the same task ID and content is idempotent and never resets terminal state. Reusing a task ID with different content is rejected.

### Leasing

Leasing is capacity- and capability-aware. A lease contains a one-time nonce, stores only its hash in the relational projection, and expires at a bounded time. Renewal and completion fail after expiry. The agent validates the task payload hash, authoritative action-definition hash, execution mode, target fingerprint, and live-execution gate before invoking an executor.

Every terminal path releases or expires the lease and persists a receipt. Receipts are reconciled into the canonical `OperationRun`; queued dependents are cancelled when prerequisite actions fail.

## Governance

### Rate and concurrency limits

Workspace-owned rules are persisted and evaluated under database row locks. Usage receipts prevent horizontally scaled API replicas from independently exceeding a limit. Governance applies at operation creation and distributed dispatch.

### Audit chain

Audit events include the previous event hash, canonical event hash, sequence, tenant, actor, request, action, resource, outcome, and metadata. Verification identifies gaps or tampering. Audit export produces immutable artifacts.

### Retention

Retention plans classify candidates by artifact type, age, legal hold, incident or operation references, and policy. Destructive application is separately gated by `KUBEOPS_RETENTION_APPLY_ENABLED`; dry-run planning remains available without that authority.

### Scheduling

Maintenance windows are timezone-aware and support days of week, local start time, duration, target restrictions, and operation allowlists. Scheduled requests have `not_before`, deadline, window, environment/fleet target, and durable decision state.

The scheduler may transition requests through pending, delayed, ready, blocked, expired, cancelled, and materialized states. Materialization creates a normal governed operation or fleet plan; it does not approve, dispatch, or execute it.

## Knowledge-pack trust

The declarative pack boundary from Release 0.5 remains intact. Release 1.0 adds:

- HMAC-SHA256 signing for local/shared-secret workflows.
- Ed25519 signing and public-key verification for production distribution.
- Workspace-scoped trust policies.
- Required signer and allowed-algorithm constraints.
- Signature-expiration handling.
- Trust-aware pack discovery, registry inspection, diagnosis, lifecycle catalogs, and execution.

Strict trust resolution blocks an untrusted pack before its contribution graph can affect runtime behavior.

## Artifact storage

The artifact-store interface supports:

- Local content-addressed filesystem storage.
- S3-compatible immutable object storage.

Horizontal API scaling requires shared object storage. The Helm chart rejects an autoscaled API configuration that still uses the local file backend. Artifact records remain workspace-scoped and store content hashes, size, media type, provenance, and derivation links.

## Platform backup and restore

A platform backup is a manifest over concrete components:

- PostgreSQL logical backup.
- KubeOps configuration archive.
- Local artifact archive or externally verified object-store backup.
- Manifest metadata and compatibility range.

Each component stores its relative source, size, and SHA-256 hash. Verification recomputes every component and the manifest. Restore re-verifies before any write, rejects path traversal, links, and device entries, and requires both `KUBEOPS_RESTORE_ENABLED=1` and explicit backup-ID confirmation.

Restore compatibility follows the backup's KubeOps major version rather than a hard-coded future range. Upgrade readiness reports check migrations, pack compatibility, artifact storage, backups, audit integrity, executor status, and operational configuration.

## Deployment topology

The production Helm chart can deploy:

- Stateless Gunicorn API replicas.
- Static Nginx UI replicas.
- Migration and catalog-seed hook.
- Distributed executor deployment.
- Operation-scheduler CronJob.
- Platform-backup CronJob.
- Services and ingress.
- Service account and read-oriented RBAC.
- NetworkPolicy.
- Pod disruption budgets.
- Optional HPA.
- Artifact, operation, and backup persistent volumes for single-replica file mode.

Live execution, retention application, and restore are disabled by default. The default executor advertises only dry-run, simulation, and wait capabilities.

## Production invariants

Release 1.0 enforces the following system-level invariants:

- No request may read or mutate another workspace through a guessed object ID.
- Agent and task identities cannot be rebound to different content or tenants.
- A lease cannot be renewed or completed after expiry.
- No distributed task may execute a non-authoritative action definition.
- No schedule can approve or execute an operation.
- No fleet wave can bypass environment policy.
- No untrusted pack can contribute semantics under strict trust policy.
- No destructive retention or restore can occur through read-only configuration.
- No recovery certificate can be sealed from command completion alone.
- No horizontally scaled API configuration may rely on non-shared local artifacts.
