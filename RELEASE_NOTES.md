# KubeOps Release 1.0

## Production-capable control plane

Release 1.0 completes the planned KubeOps roadmap. It extends the single-environment operational intelligence and guarded-recovery platform into a multi-user, multi-workspace, multi-cluster system while preserving the typed-action safety boundary introduced in Release 0.4.

## Added

### Tenancy and access control

- Organizations and workspaces.
- Hierarchical role grants across system, organization, workspace, environment, fleet, and operation scopes.
- Capability-aware and object-aware API authorization.
- Workspace-filtered data access for environments, snapshots, incidents, operations, tasks, agents, artifacts, packs, policies, schedules, fleets, audit, retention, and backups.
- Token-authenticated UI bootstrap with explicit tenant-scope headers.

### Fleet intelligence

- Fleet definitions, members, dependencies, failure domains, and criticality.
- Multi-environment health assessments.
- Common-cause and shared-factor findings.
- Dependency-ordered operation waves with concurrency bounds.
- Fleet artifacts, REST APIs, CLI commands, and Fleet Control UI.

### Distributed execution

- Durable executor-agent registration and heartbeats.
- Immutable agent-to-tenant/public-identity binding.
- Capability, environment, executor, and capacity matching.
- Content-idempotent execution tasks.
- Row-locked task claims.
- Expiring nonce-protected leases.
- Retry/terminal handling after lease expiry.
- Authoritative action-definition and payload-hash validation.
- Receipt reconciliation into canonical `OperationRun` state.
- Deployable executor management command, Compose profile, and Helm deployment.

### Governance

- Durable workspace rate and concurrency limits.
- Tamper-evident append-only audit chains and exports.
- Legal-hold-aware retention plans.
- Explicit destructive-retention gate.
- Timezone-aware maintenance windows.
- Durable scheduled operations with delay, readiness, denial, expiry, cancellation, and materialization.
- Scheduler that can materialize but cannot approve or execute work.

### Pack supply-chain trust

- HMAC-SHA256 pack signatures.
- Ed25519 signatures and public-key verification.
- Workspace-scoped pack trust policies.
- Trust-aware discovery, diagnosis, lifecycle, registry, and execution catalogs.
- Strict resolution that blocks untrusted contributions.

### Artifact and platform recovery

- S3-compatible immutable artifact-store backend.
- Helm validation preventing autoscaled API use of local artifact storage.
- Concrete database, configuration, and artifact backup components.
- Component and manifest hash verification.
- Safe archive restore that rejects traversal, links, and device entries.
- Explicit restore enablement and backup-ID confirmation.
- Upgrade-readiness reports.
- Scheduled platform-backup job.

### Production deployment

- Nonroot Gunicorn API image.
- Multi-stage React/Nginx UI image.
- Production Helm chart with migration hook, API, UI, executor, scheduler, backup, ingress, services, RBAC, NetworkPolicy, PDBs, persistence, and optional HPA.
- Secure-cookie/proxy settings and configurable HTTPS redirect/HSTS.
- Production operations guide and architecture documentation.
- CI migration, test, UI build, static architecture, and Helm lint/render jobs.

### UI

- Fleet Control workbench.
- Governance & Recovery workbench.
- In-memory token login and tenant selection.
- Executor status and task visibility.
- Audit verification and retention planning.
- Scheduled-operation visibility and controls.
- Backup and upgrade-readiness visibility.

## Hardened

- Re-registering an agent cannot move its identity across tenants or public keys.
- Reposting an identical task never resets terminal state.
- Reusing a task ID with different content is rejected.
- Lease renewal and completion reject expired leases.
- Dispatcher decisions and governance outputs use caller-supplied time deterministically.
- Executor heartbeats persist capacity, active tasks, and diagnostics.
- Recovery archives reject symbolic links, hard links, and device members.
- Restore compatibility tracks the backup's major KubeOps version.
- `DJANGO_ALLOWED_HOSTS` strips empty and whitespace-only entries.
- Lifecycle schedules remain unable to bypass normal approvals and execution policy.

## Compatibility

Release 1.0 is an additive delta over Release 0.5. It preserves:

- Release 0.1 scenario and simulator contracts.
- Release 0.2 discovery, snapshot, topology, and health contracts.
- Release 0.3 incident diagnosis and probe contracts.
- Release 0.4 guarded execution and verification contracts.
- Release 0.5 declarative pack boundaries and built-in packs.

No repository-relative paths are deleted by the Release 1.0 delta.

## Upgrade notes

1. Apply the Release 1.0 delta over a complete Release 0.5 checkout.
2. Install updated Python and UI dependencies.
3. Run all Django migrations.
4. Run `seed_release_10` after the prior seed commands.
5. Keep live execution, destructive retention, and restore disabled.
6. Create users/tokens and narrow role grants.
7. Configure pack trust before enabling strict workspace trust.
8. Configure S3-compatible artifacts before scaling API replicas.
9. Create and verify a platform backup before enabling production mutations.

See `docs/production-operations.md` for the complete operating procedure.
