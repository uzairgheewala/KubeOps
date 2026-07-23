# KubeOps Release 1.0 implementation manifest

## Release boundary

Release 1.0 is delivered as a delta over the complete Release 0.5 repository. The delta contains only added or modified files and preserves all repository-relative paths.

## Canonical models added

### Tenancy

- `OrganizationDefinition`
- `WorkspaceDefinition`
- `RoleGrant`
- `AuthorizationRequest`
- `AuthorizationDecision`
- `ScopeBinding`

### Fleet

- `FleetMember`
- `FleetDependency`
- `FleetDefinition`
- `FleetEnvironmentStatus`
- `CommonCauseFinding`
- `FleetAssessment`
- `FleetOperationWave`
- `FleetOperationPlan`

### Distributed execution

- `ExecutorAgentDefinition`
- `ExecutorHeartbeat`
- `ExecutionTask`
- `TaskLease`
- `DispatchDecision`

### Governance

- `RateLimitRule`
- `ConcurrencyRule`
- `GovernanceDecision`
- `RetentionPolicy`
- `RetentionCandidate`
- `RetentionPlan`
- `AuditEvent`
- `AuditChainVerification`
- `AuditExport`

### Security and trust

- `SecretReference`
- `SecretResolutionReceipt`
- `PackSignature`
- `PackTrustPolicy`
- `PackVerificationResult`

### Platform recovery

- `BackupComponent`
- `ControlPlaneBackupManifest`
- `RestoreStep`
- `ControlPlaneRestorePlan`
- `UpgradeReadinessCheck`
- `UpgradeReadinessReport`

### Scheduling

- `MaintenanceWindow`
- `ScheduledOperation`
- `ScheduleDecision`

## Core services added

- Hierarchical authorization engine.
- Fleet assessment and operation-wave planner.
- Distributed task dispatcher.
- Audit-chain implementation.
- Rate/concurrency governor.
- Retention planner.
- Schedule and maintenance-window service.
- Secret-provider abstraction.
- HMAC and Ed25519 pack signer/verifier.
- Platform backup/restore/readiness service.
- S3-compatible artifact store.

## Control-plane additions

- Release 1.0 relational migration covering 50 canonical projections across the complete control plane.
- Organization/workspace scoping middleware and permission classes.
- Object-aware authorization and workspace-filtered querysets.
- Fleet, executor, governance, audit, retention, scheduling, trust, backup, and recovery APIs.
- Release 1.0 catalog and default-tenant seeder.
- Durable executor-agent command.
- Operation-scheduler command.
- Platform backup and guarded restore commands.

## Deployment additions

- Gunicorn production API container.
- Multi-stage Vite/Nginx UI container.
- Complete Helm chart.
- Migration/seed hook.
- Distributed executor deployment.
- Schedule and backup CronJobs.
- Services, ingress, RBAC, NetworkPolicy, PDBs, PVCs, and HPA.
- S3 artifact configuration.
- HTTPS/HSTS configuration.

## UI additions

- Token login and tenant-scope state.
- Fleet Control workbench.
- Governance & Recovery workbench.
- Executor, audit, retention, scheduling, backup, and upgrade-readiness views.

## Default data

- Demo fleet.
- Workspace rate/concurrency rules.
- Retention policy.
- Maintenance windows.
- Default pack trust policy.

## Safety properties

- No unrestricted executor or shell-action type.
- No schedule-owned approval or execution.
- No fleet bypass of environment policy.
- No cross-workspace object access by guessed identifiers.
- No agent identity rebinding.
- No task-content rebinding.
- No completion under an expired lease.
- No trusted-pack implication of executor authority.
- No destructive retention or restore without explicit global enablement.
- No full recovery certificate without live semantic verification.
