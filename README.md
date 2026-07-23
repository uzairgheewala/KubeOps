# KubeOps Release 0.1

KubeOps is a typed operational reasoning platform for Kubernetes environments.
Release 0.1 implements the simulation-first foundation before any live-cluster
authority is introduced.

It is not a collection of shell scripts and it is not an AI wrapper around
`kubectl`. The release provides one canonical operational metamodel shared by a
scenario compiler, deterministic simulator, append-oriented artifact system,
Django API, CLI, and interactive web workbench.

## What is included

- Versioned, immutable canonical operational IR.
- Deterministic serialization and SHA-256 content identity.
- Typed extension registry and JSON Schema introspection.
- Scenario-family inheritance with semantic-identity merging.
- Typed parameter binding and semantic constraint validation.
- Concurrent, sequential, conditional, masking, and
  recovery-interference composition.
- Deterministic event-driven simulation.
- Immediate, bounded-eventual, and stable-window invariants.
- Separate world truth and observer projections.
- Hidden, partial, delayed, and contradictory observation profiles.
- Immutable run artifacts with explicit derivation links.
- Django REST control plane with SQLite or PostgreSQL.
- Typer/Rich CLI.
- React/TypeScript Scenario Lab, Composition Lab, topology explorer, timeline,
  invariant inspector, canonical schema browser, and artifact explorer.
- Linux/macOS, PowerShell, Docker Compose, and CI workflows.

## Release boundary

Release 0.1 does **not** connect to or mutate a live Kubernetes cluster. That is
intentional. It defines the contracts that fixture and live modes will use in
later releases.

The IR already includes forward-compatible schemas for:

- Operational objectives and profiles.
- Evidence intents, symptoms, hypotheses, and probes.
- Typed action definitions and instances.
- Execution policies and decisions.
- Recovery plans.
- Verification conditions and results.
- Diagnosis and recovery certificates.

Those schemas are inspectable and validated in Release 0.1, but no diagnosis or
execution engine is granted authority yet.

## Architecture

```text
Scenario-family YAML
        ↓
ScenarioFamilyRegistry
        ↓
Inheritance + bindings + semantic constraints
        ↓
ScenarioInstance or composed ScenarioInstance
        ↓
Deterministic SimulationEngine
        ↓
Truth snapshots + observation projections + invariant evaluations
        ↓
Immutable artifacts + Django metadata
        ↓
CLI / REST API / Scenario Lab / Composition Lab
```

See [the detailed architecture](docs/architecture-release-01.md),
[release notes](RELEASE_NOTES.md), and [validation record](VALIDATION.md).

## Scenario-family basis

| Family | Architectural capability |
|---|---|
| `entity.required_absent.v1` | Existence and downstream propagation |
| `dependency.failure.v1` | Reusable abstract dependency topology |
| `dependency.endpoint_unreachable.v1` | Layered name-resolution, route, transport, and TLS failure |
| `dependency.authentication_failure.v1` | Authentication distinct from authorization |
| `controller.convergence_failure.v1` | Bounded progress and delayed propagation |

The endpoint and authentication families inherit the same dependency blueprint.
Concrete component identities, failure layers, disturbance choices, and
observation profiles vary without introducing new simulator code paths.

## UI workbench

The React application contains three principal surfaces.

### Scenario Lab

- Select an effective scenario family.
- Bind generic parameters to concrete entities.
- Select a disturbance and observation profile.
- Compile or execute the scenario.
- Step through snapshots.
- Toggle observed state versus world truth.
- Inspect topology, invariant state, timeline events, raw entities, and
  immutable artifacts.

### Composition Lab

- Combine two families under concurrent, sequential, masking, or
  recovery-interference semantics.
- Execute one namespaced world.
- Inspect interleaved events and combined invariant propagation.

### Canonical IR

- Browse extension-registry categories.
- Inspect all canonical JSON Schemas.
- Examine scenario-family lineage and capabilities.

## Quick start with Docker

```bash
cp .env.example .env
docker compose up --build
```

Open:

- UI: `http://localhost:5173`
- API status: `http://localhost:8000/api/v1/system/status`

## Local bootstrap

Linux/macOS:

```bash
./scripts/bootstrap.sh
./scripts/dev.sh
```

Windows PowerShell:

```powershell
.\scripts\bootstrap.ps1
.\scripts\dev.ps1
```

Local settings default to SQLite unless `DATABASE_URL` is set. Docker Compose
uses PostgreSQL 16.

## CLI

```bash
./scripts/kubeops.sh family list
./scripts/kubeops.sh family validate
./scripts/kubeops.sh family show dependency.endpoint_unreachable.v1

./scripts/kubeops.sh registry list --category scenario_family

./scripts/kubeops.sh scenario compile dependency.endpoint_unreachable.v1 \
  --binding consumer_name="Builder" \
  --binding provider_name="Kubernetes API" \
  --binding failure_layer=tls

./scripts/kubeops.sh scenario run dependency.authentication_failure.v1 \
  --binding consumer_name="Builder" \
  --binding provider_name="Kubernetes API" \
  --observation-profile consumer_only

./scripts/kubeops.sh composition run \
  scenarios/basis/concurrent-network-controller.yaml
```

PowerShell users can replace `kubeops.sh` with `kubeops.ps1`.

## API examples

Compile a scenario:

```bash
curl -X POST http://localhost:8000/api/v1/scenarios/compile \
  -H 'Content-Type: application/json' \
  -d '{
    "family_id": "dependency.endpoint_unreachable.v1",
    "bindings": {
      "consumer_name": "Builder",
      "provider_name": "Kubernetes API",
      "failure_layer": "tls"
    },
    "observation_profile_id": "delayed_provider"
  }'
```

Run and persist artifacts:

```bash
curl -X POST http://localhost:8000/api/v1/scenarios/run \
  -H 'Content-Type: application/json' \
  -d '{"family_id":"controller.convergence_failure.v1"}'
```

Inspect the canonical registry and schemas:

```bash
curl http://localhost:8000/api/v1/registry
curl http://localhost:8000/api/v1/schemas/RecoveryPlan
```

## Scenario-family authoring

A family contains:

- Typed parameters.
- Semantic constraints.
- A structural signature.
- Entity and relationship templates.
- Invariant templates.
- Transition rules.
- Observation profiles.
- One or more disturbances.

Templates use `${binding_name}`. A placeholder occupying an entire scalar keeps
the original typed value; embedded placeholders are interpolated as text.

Child families set `parent_family_id`. The compiler merges named objects by
stable semantic identity:

- `entity_id`
- `relationship_id`
- `invariant_id`
- `rule_id`
- `profile_id`
- `disturbance_id`

## Observation semantics

Every snapshot contains two states:

- **World truth** — actual simulated state.
- **Observed state** — state visible under the selected observation profile.

Profiles support hidden entities, hidden paths, observation lag, and
contradictory overrides. Invariants evaluate observed state, so missing evidence
produces `unknown` rather than fabricated confidence.

## Artifacts

Every run emits:

- Compiled scenario instance.
- Event timeline.
- Snapshot sequence.
- Observation set.
- Run manifest.

Artifacts are immutable JSON documents with SHA-256 payload hashes. The
run-manifest records derivation links to all source artifacts. The Django
control plane stores searchable metadata while payloads pass through the
artifact-store abstraction.

## Validation

After bootstrap:

```bash
./scripts/test.sh
```

The suite includes:

- Canonical-hash stability.
- Extended IR round-tripping.
- Family inheritance and constraint rejection.
- Cross-domain family reuse.
- Temporal invariants.
- Failure propagation.
- Partial-observation unknowns.
- Delayed controller effects.
- Composition semantics and one-shot rule behavior.
- Renaming invariance through Hypothesis.
- Django compile, run, persistence, and artifact APIs.
- TypeScript production build.

The exact checks executed for this delivered archive and sandbox dependency
limitations are recorded in [VALIDATION.md](VALIDATION.md).

## Repository map

```text
packages/kubeops_core   Canonical IR, registries, compiler, simulator, artifacts
packages/kubeops_cli    CLI
control_plane           Django API and persistence
ui                      React operational scenario workbench
scenarios/families      Executable scenario-family definitions
scenarios/basis         Representative basis and compositions
docs                    Architecture and ADRs
tests                   Unit, property, integration, and security-ready layout
```

## Next release boundary

Release 0.2 can now add read-only environment registration, Kubernetes snapshot
collection, fixture replay, topology compilation from real objects, and
operational-profile health evaluation without replacing the Release 0.1 core.
