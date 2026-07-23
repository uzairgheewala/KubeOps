# KubeOps 1.0

KubeOps is a typed, evidence-driven Kubernetes operations platform for environment discovery, health evaluation, incident diagnosis, lifecycle planning, guarded recovery, scenario simulation, fleet coordination, and operational learning.

It is not a wrapper that lets an AI run arbitrary `kubectl` commands. KubeOps models environments as temporal dependency graphs, evaluates explicit invariants, preserves evidence and causal provenance, compiles recovery into registered typed actions, applies independent safety policy and approvals, executes through bounded adapters, and seals recovery only after semantic verification.

## Release 1.0 capabilities

Release 1.0 consolidates the complete roadmap:

- Canonical versioned operational IR and deterministic simulator.
- Generic scenario families and composition operators.
- Read-only Kubernetes discovery, sanitized snapshots, topology, and health profiles.
- Evidence-intent collection, hypotheses, probes, causal graphs, and diagnosis certificates.
- Dependency-aware startup/shutdown planning.
- Typed actions, risk policy, approvals, checkpoints, rollback, and recovery certificates.
- Declarative provider/component knowledge packs.
- Organizations, workspaces, hierarchical RBAC, and object-aware tenant isolation.
- Multi-cluster fleets, common-cause analysis, and dependency-ordered operation waves.
- Capability- and capacity-scoped distributed executors with durable leases and receipts.
- Workspace rate/concurrency limits, tamper-evident audit, legal holds, and retention.
- Maintenance windows and durable operation scheduling.
- HMAC and Ed25519 pack signing with workspace trust policy.
- File and S3-compatible immutable artifact stores.
- Verifiable platform backup/restore and upgrade-readiness checks.
- Production API/UI containers and Helm deployment.
- Interactive Scenario, Environment, Incident, Operations, Pack, Fleet, and Governance workbenches.

## Safety boundary

Every environment mutation follows one authority path:

```text
scope → authorization → governance → typed plan → policy → approval
      → durable operation → bounded executor → receipt → fresh verification
```

Schedules may materialize work but cannot approve or execute it. Fleet plans cannot bypass environment policy. Knowledge-pack signatures establish semantic trust but grant no executor capability. Live execution, destructive retention, and restore are disabled by default.

## Repository layout

```text
packages/kubeops_core/       framework-independent models and runtime
packages/kubeops_cli/        Typer/Rich command-line interface
packages/kubeops_pack_sdk/   declarative pack authoring and validation
control_plane/               Django/DRF persistence and production API
ui/                          React/TypeScript operational workbench
packs/                       built-in provider and component packs
scenarios/                    generic families, basis, and compositions
profiles/                     operational health profiles
lifecycle/                    startup and shutdown profiles
policies/                     guarded execution policies
governance/                   limits, retention, and maintenance windows
fleets/                       fleet definitions
deploy/helm/kubeops/          production Helm chart
lab/                          fixtures and scenario laboratory assets
tests/                        unit, property, integration, and scenario tests
```

## Development quick start

### PowerShell with Docker Compose

```powershell
Copy-Item .env.example .env

docker compose up --build postgres api ui
```

Open:

- UI: `http://localhost:5173`
- API status: `http://localhost:8000/api/v1/system/status`

Optional services:

```powershell
docker compose --profile scheduler --profile executor up --build
```

The development executor is restricted to dry-run, simulation, and wait adapters.

### Python environment

```powershell
conda create -n kubeops python=3.13 -y
conda activate kubeops
python -m pip install --upgrade pip
pip install -r requirements-dev.txt

$env:PYTHONPATH = "packages/kubeops_core;packages/kubeops_pack_sdk;packages/kubeops_cli;control_plane"
python control_plane/manage.py migrate
python control_plane/manage.py seed_release_01
python control_plane/manage.py seed_release_02
python control_plane/manage.py seed_release_04
python control_plane/manage.py seed_release_05
python control_plane/manage.py seed_release_10
python control_plane/manage.py runserver
```

In a second PowerShell window:

```powershell
cd ui
npm install
npm run dev
```

## CLI examples

```powershell
python -m kubeops_cli.main pack validate
python -m kubeops_cli.main environment validate environments/demo-pack-stack-fixture.v1.yaml
python -m kubeops_cli.main snapshot collect environments/demo-pack-stack-fixture.v1.yaml --output-dir artifacts
python -m kubeops_cli.main fleet assess fleets/demo-fleet.v1.yaml
python -m kubeops_cli.main schedule windows governance/default-maintenance-windows.v1.yaml
python -m kubeops_cli.main platform --help
```

Use `python -m kubeops_cli.main --help` to inspect the complete command tree.

## Validation

The repository includes:

- Unit and property-based tests for the operational kernel.
- Django/PostgreSQL integration tests.
- Scenario and pack-resolution matrices.
- TypeScript project build.
- Static Release 1.0 architecture validator.
- Helm lint and render checks in CI.
- Overlay and per-file hash verification for release deltas.

Run locally:

```powershell
pytest
python scripts/validate_release_10.py
cd ui
npm run build
```

## Production deployment

See:

- [`docs/production-operations.md`](docs/production-operations.md)
- [`docs/architecture-release-10.md`](docs/architecture-release-10.md)
- [`deploy/production/README.md`](deploy/production/README.md)

The chart defaults to one API replica with local artifact storage. Configure S3-compatible object storage before horizontally scaling API replicas.

## Architecture history

Each release architecture remains documented under `docs/architecture-release-*.md`, with corresponding decisions under `docs/adr/`.
