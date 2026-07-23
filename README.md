# KubeOps Release 0.4

KubeOps is a typed, evidence-driven Kubernetes operations runtime. Release 0.4
adds the first guarded mutation boundary on top of the read-only topology,
health, incident, and diagnosis foundations from Releases 0.1–0.3.

The release can compile an environment objective into a dependency-aware
lifecycle plan, evaluate each typed action under an independent execution
policy, persist approvals and checkpoints, execute through an explicitly
selected adapter, resume interrupted work, attempt bounded rollback, and seal
the result only after semantic verification.

Release 0.4 does **not** enable unrestricted production remediation. Live
execution is disabled by default at the control-plane boundary. Dry-run and
simulation operations are deliberately certified as `partially_recovered`,
not as authoritative live recoveries.

## Release 0.4 capabilities

### Lifecycle profiles

Lifecycle profiles describe goal-directed transitions rather than shell-script
sequences. The initial profiles are:

- `local-development-startup.v1`
- `local-development-shutdown.v1`

A profile declares stages, stage dependencies, typed action templates,
selection rules, verification conditions, protected invariants, and a default
execution policy. Stage and action-template graphs are validated as acyclic.

### Typed action catalog

The built-in action catalog includes bounded definitions for:

- waiting for an explicit condition;
- starting or stopping an allowlisted local process;
- starting or stopping a Docker container;
- restarting an allowlisted host service;
- restarting a selected Kubernetes workload;
- deleting a terminal Kubernetes Job;
- refreshing an Argo CD application;
- ensuring a local port-forward.

Every action definition declares its executor, supported modes, required
capabilities, default risk, timeout, retry limit, expected effects, possible
side effects, and rollback action where available.

### Independent safety policy

Policy evaluation is separate from diagnosis and planning. A confident
diagnosis never grants authority by itself.

Policies can constrain:

- environment class;
- allowed and denied action types;
- allowed risk classes;
- target patterns;
- required capabilities;
- mutation budgets;
- target fingerprints;
- checkpoint requirements;
- approval counts by risk class;
- break-glass behavior.

Approvals are action- or operation-scoped. Expired approvals do not count,
multiple approvals from one identity count once, and an active explicit
rejection blocks execution.

### Durable operation runtime

An `OperationRun` persists:

- the immutable recovery plan;
- policy decisions;
- approvals;
- action receipts;
- checkpoints;
- verification results;
- recovery or rollback certificate;
- append-oriented timeline events.

The file-backed journal uses atomic replacement and supports pause, resume,
idempotency suppression, bounded retries, rollback attempts, and reconstruction
after process restart.

### Verification and certification

Command success is not recovery. Verification operates over the canonical
world and relationship graph and can evaluate:

- target invariant restoration;
- protected-invariant preservation;
- semantic application health;
- side-effect guards.

Certificate trust is mode-aware:

- dry run: `partially_recovered`;
- simulation: `partially_recovered`;
- live execution with passing semantic verification: `recovered`;
- failed verification: `recovery_failed`;
- completed rollback: `rollback_completed`.

### Operation workbench

The React workbench adds an **Operations** surface with:

- environment, lifecycle-profile, policy, and mode selection;
- dependency-aware plan preview;
- stage/action DAG inspection;
- independent policy-decision review;
- operation- and action-level approval controls;
- dry-run and guarded-simulation execution;
- pause, resume, and rollback controls;
- action receipts and checkpoints;
- verification results and certificates;
- timeline replay;
- immutable artifact lineage.

## Repository layering

```text
packages/kubeops_core/
  models/           canonical lifecycle, policy, operation, and certificate IR
  actions/          typed action catalog
  lifecycle/        profile registry and plan compiler
  policy/           independent authorization engine
  execution/        adapters, durable journal, operation state machine
  verification/     semantic and protected-invariant verification

control_plane/
  Django persistence, APIs, settings, and live-authority gate

ui/
  lifecycle and guarded-operation workbench

lifecycle/           declarative lifecycle profiles
policies/            declarative execution policies
operations/          runtime journal; ignored by Git
```

## Applying this delta

The Release 0.4 package contains only files added or modified since Release
0.3. Extract it over a repository containing Release 0.1 plus the Release 0.2
and 0.3 deltas, preserving repository-relative paths.

```bash
unzip kubeops-release-0.4-delta.zip -d /path/to/kubeops
cd /path/to/kubeops
```

Then install or refresh dependencies and apply the new migration.

## Local bootstrap

### Linux/macOS

```bash
./scripts/bootstrap.sh
./scripts/dev.sh
```

### Windows PowerShell

```powershell
.\scripts\bootstrap.ps1
.\scripts\dev.ps1
```

### Docker Compose

```bash
docker compose up --build
```

The UI is served at `http://localhost:5173` and the API at
`http://localhost:8000/api/v1`.

## Safety configuration

The default environment file contains:

```text
KUBEOPS_LIVE_EXECUTION_ENABLED=0
```

Keep this disabled while using the Release 0.4 workbench. The API defaults to
dry-run or simulation adapters. Enabling live execution only removes the
server-wide denial; individual actions must still pass target-fingerprint,
capability, policy, approval, checkpoint, and executor checks.

The live boundary is intentionally suitable for controlled local development
and disposable test environments, not unattended production repair.

## CLI examples

Collect or load a Release 0.2 snapshot:

```bash
kubeops snapshot collect environments/demo-kind-fixture.v1.yaml \
  --method-id recorded-degraded \
  --profile local-development-usable.v1 \
  --output /tmp/kubeops-snapshot.json
```

Compile a startup plan:

```bash
kubeops lifecycle plan local-development-startup.v1 \
  /tmp/kubeops-snapshot.json \
  --mode guarded_execution \
  --policy-id local-development-guarded.v1 \
  --output /tmp/kubeops-plan.json
```

Create and approve an operation:

```bash
kubeops operation create /tmp/kubeops-plan.json demo-kind-fixture \
  --mode guarded_execution

kubeops operation approve <operation-id> operator-1
# Optional before execution:
# kubeops operation cancel <operation-id> --reason "No longer required"
```

Run using the non-live simulation adapter:

```bash
kubeops operation run <operation-id> /tmp/kubeops-snapshot.json \
  local-development-guarded.v1 \
  --adapter-mode simulation \
  --capability argocd.application.refresh \
  --capability kubernetes.workload.restart \
  --artifacts artifacts
```

## API additions

```text
GET  /api/v1/action-catalog
GET  /api/v1/lifecycle-profiles
GET  /api/v1/lifecycle-profiles/{profile_id}
GET  /api/v1/execution-policies
POST /api/v1/snapshots/{snapshot_id}/lifecycle-plan

GET  /api/v1/operations
POST /api/v1/operations
GET  /api/v1/operations/{operation_id}
POST /api/v1/operations/{operation_id}/approve
POST /api/v1/operations/{operation_id}/run
POST /api/v1/operations/{operation_id}/pause
POST /api/v1/operations/{operation_id}/cancel
POST /api/v1/operations/{operation_id}/resume
POST /api/v1/operations/{operation_id}/rollback
GET  /api/v1/operations/{operation_id}/certificate
```

## Testing

```bash
make test-python
make test-ui
```

The Python suite covers all retained Release 0.1–0.3 behavior and the Release
0.4 planner, policy, execution, idempotency, rollback, artifact, and
verification contracts.

## Documentation

- [Release 0.4 architecture](docs/architecture-release-04.md)
- [Guarded mutation authority ADR](docs/adr/0004-guarded-mutation-authority.md)
- [Release notes](RELEASE_NOTES.md)
- [Implementation manifest](IMPLEMENTATION_MANIFEST.md)
- [Validation record](VALIDATION.md)

## Next boundary

Release 0.5 should extract provider and component behavior into independently
versioned knowledge packs, add live disposable-cluster scenario validation,
expand action and verification adapters, measure semantic support coverage, and
promote resolved incidents into regression-tested operational knowledge.
